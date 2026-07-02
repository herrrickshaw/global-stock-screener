#!/usr/bin/env python3
"""
Standalone duplicate finder - No database required
Finds identical files across Git branches
"""

import os
import hashlib
import subprocess
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import json

class StandaloneDuplicateFinder:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.checksums = defaultdict(list)  # checksum -> [(branch, file_path, size)]

    def get_branches(self) -> List[str]:
        """Get all local branches"""
        result = subprocess.run(
            ['git', '-C', str(self.repo_path), 'branch', '-a'],
            capture_output=True, text=True
        )
        branches = [b.strip().lstrip('* ').replace('remotes/origin/', '')
                   for b in result.stdout.split('\n')
                   if b.strip() and 'HEAD' not in b]
        return list(set(branches))  # Remove duplicates

    def compute_checksum(self, file_path: Path) -> str:
        """Compute SHA256 checksum"""
        sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except:
            return None

    def scan_branch(self, branch: str) -> Dict[str, Tuple[int, str]]:
        """Scan branch and get file checksums"""
        try:
            # Checkout branch
            subprocess.run(
                ['git', '-C', str(self.repo_path), 'checkout', branch],
                capture_output=True, check=True
            )

            files = {}
            for file_path in self.repo_path.rglob('*'):
                if file_path.is_file() and '.git' not in file_path.parts:
                    try:
                        size = file_path.stat().st_size
                        checksum = self.compute_checksum(file_path)
                        if checksum:
                            relative = file_path.relative_to(self.repo_path)
                            files[str(relative)] = (size, checksum)
                    except:
                        pass

            return files, branch
        except subprocess.CalledProcessError:
            print(f"✗ Failed to checkout {branch}")
            return {}, branch

    def find_duplicates(self, branches: List[str] = None) -> Dict:
        """Find duplicate files across branches"""
        if not branches:
            branches = self.get_branches()

        print(f"Scanning {len(branches)} branches: {', '.join(branches[:5])}{'...' if len(branches) > 5 else ''}\n")

        branch_files = {}
        for branch in branches:
            print(f"  {branch}...", end=' ', flush=True)
            files, _ = self.scan_branch(branch)
            branch_files[branch] = files
            print(f"({len(files)} files)")

        # Group files by checksum
        checksum_map = defaultdict(list)
        for branch, files in branch_files.items():
            for file_path, (size, checksum) in files.items():
                checksum_map[checksum].append({
                    'branch': branch,
                    'file': file_path,
                    'size': size
                })

        # Find duplicates (same checksum, different branches or multiple times)
        duplicates = []
        total_wasted = 0

        for checksum, instances in checksum_map.items():
            if len(instances) > 1:
                # Check if truly duplicate (different files or across branches)
                branches_involved = set(inst['branch'] for inst in instances)
                files_involved = set(inst['file'] for inst in instances)

                if len(branches_involved) > 1 or len(files_involved) > 1:
                    size_per_copy = instances[0]['size']
                    wasted = size_per_copy * (len(instances) - 1)
                    total_wasted += wasted

                    duplicates.append({
                        'checksum': checksum[:8] + '...',
                        'copies': len(instances),
                        'size_per_copy_mb': size_per_copy / (1024**2),
                        'total_wasted_mb': wasted / (1024**2),
                        'branches': list(branches_involved),
                        'files': [inst['file'] for inst in instances[:3]],
                        'instances': instances
                    })

        return {
            'total_duplicates': len(duplicates),
            'total_wasted_mb': total_wasted / (1024**2),
            'duplicates': sorted(duplicates, key=lambda x: x['total_wasted_mb'], reverse=True),
            'branches_scanned': branches,
            'files_scanned': sum(len(f) for f in branch_files.values())
        }

def main():
    repo_path = '/Users/umashankar/Downloads/code/python_files'

    finder = StandaloneDuplicateFinder(repo_path)

    # Scan main branches
    main_branches = ['main', 'global-expansion-screener-v3.1', 'feature/darvas-interpreter', 'feature/scanner-optimise']

    print("=" * 70)
    print("vCRUD Duplicate Finder (Standalone - No Database Required)")
    print("=" * 70)
    print()

    result = finder.find_duplicates(main_branches)

    print("\n" + "=" * 70)
    print("DUPLICATE ANALYSIS RESULTS")
    print("=" * 70)
    print(f"\nBranches scanned: {', '.join(result['branches_scanned'])}")
    print(f"Total files indexed: {result['files_scanned']}")
    print(f"Duplicate groups found: {result['total_duplicates']}")
    print(f"Total wasted space: {result['total_wasted_mb']:.1f} MB")

    if result['duplicates']:
        print("\n" + "=" * 70)
        print("TOP DUPLICATES (by wasted space)")
        print("=" * 70)

        for i, dup in enumerate(result['duplicates'][:15], 1):
            print(f"\n{i}. Checksum {dup['checksum']}")
            print(f"   Copies: {dup['copies']}x")
            print(f"   Size per copy: {dup['size_per_copy_mb']:.1f} MB")
            print(f"   Total wasted: {dup['total_wasted_mb']:.1f} MB")
            print(f"   Branches: {', '.join(dup['branches'])}")
            print(f"   Files:")
            for inst in dup['instances'][:3]:
                print(f"     [{inst['branch']}] {inst['file']}")
            if len(dup['instances']) > 3:
                print(f"     ... and {len(dup['instances']) - 3} more")

        if len(result['duplicates']) > 15:
            remaining_wasted = sum(d['total_wasted_mb'] for d in result['duplicates'][15:])
            print(f"\n... and {len(result['duplicates']) - 15} more duplicates ({remaining_wasted:.1f} MB wasted)")
    else:
        print("\n✓ No significant duplicates found across branches")

    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)

    if result['total_wasted_mb'] > 50:
        print(f"""
1. DEDUPLICATION: You have {result['total_wasted_mb']:.0f} MB of duplicate data
   Consider using Git LFS or moving large files to a shared storage location

2. BRANCH CLEANUP: Some older branches may have redundant copies
   Identify which branches can be safely archived or merged

3. MONITORING: Use this script regularly to catch duplicates early:
   python3 find_duplicates_standalone.py

4. STORAGE: Save approximately {result['total_wasted_mb']:.0f} MB by:
   - Moving duplicate data to LFS
   - Deleting redundant copies from feature branches
   - Using a shared cache directory across branches
""")
    else:
        print(f"""
✓ Duplicate levels are reasonable ({result['total_wasted_mb']:.1f} MB)
   Run this script periodically to monitor for future bloat
""")

    # Save to JSON for further analysis
    output_file = Path(repo_path) / 'duplicates_report.json'
    with open(output_file, 'w') as f:
        # Convert for JSON serialization
        report = {
            'timestamp': str(__import__('datetime').datetime.now()),
            'total_duplicates': result['total_duplicates'],
            'total_wasted_mb': round(result['total_wasted_mb'], 1),
            'branches_scanned': result['branches_scanned'],
            'files_scanned': result['files_scanned'],
            'top_10_duplicates': [
                {
                    'checksum': d['checksum'],
                    'copies': d['copies'],
                    'size_per_copy_mb': round(d['size_per_copy_mb'], 1),
                    'total_wasted_mb': round(d['total_wasted_mb'], 1),
                    'branches': d['branches'],
                    'files': d['files']
                }
                for d in result['duplicates'][:10]
            ]
        }
        json.dump(report, f, indent=2)

    print(f"\n✓ Report saved to {output_file}")

if __name__ == '__main__':
    main()
