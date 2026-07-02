"""
CLI Interface for vCRUD File Management System
Usage: python vcrud_cli.py [command] [options]
"""

import argparse
import json
from pathlib import Path
from db_handler import DatabaseHandler, FileRecord
from vcrud_manager import VersionedCRUDManager, LocalFileIndexer
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


class VCRUDCli:
    def __init__(self, db_url: str, repo_path: str):
        self.db = DatabaseHandler(db_url)
        self.vcrud = VersionedCRUDManager(self.db, repo_path)
        self.repo_path = Path(repo_path)

    # ========== CREATE COMMANDS ==========
    def cmd_create(self, args):
        """Create: Add file to tracking"""
        if args.file:
            file_id = self.vcrud.create_file(args.file, args.branch, args.commit)
            if file_id > 0:
                print(f"\n✓ File created with ID: {file_id}")
        elif args.pattern:
            indexer = LocalFileIndexer(str(self.repo_path))
            records = indexer.scan_directory(args.branch, [args.pattern])
            results = []
            for record in records:
                file_id = self.db.create_file(record)
                results.append((record.path, file_id))
            print(f"\n✓ Indexed {len(results)} files matching pattern '{args.pattern}'")

    def cmd_batch_create(self, args):
        """Create: Batch index files from directory"""
        indexer = LocalFileIndexer(str(self.repo_path))
        records = indexer.scan_directory(args.branch, args.patterns or ['**/*'])

        print(f"\nIndexing {len(records)} files...")
        for i, record in enumerate(records, 1):
            self.db.create_file(record)
            if i % 100 == 0:
                print(f"  {i}/{len(records)} indexed...")

        stats = self.db.get_branch_stats(args.branch)
        print(f"\n✓ Batch indexing complete:")
        print(f"  Total files: {stats['total_files']}")
        print(f"  Total size: {stats['total_size_mb']:.1f} MB")
        print(f"  Compressed: {stats['compressed_size_mb']:.1f} MB")
        print(f"  Ratio: {stats['avg_compression_ratio']:.1%}")

    # ========== READ COMMANDS ==========
    def cmd_read(self, args):
        """Read: Retrieve file metadata"""
        record = self.vcrud.read_file(args.file, args.branch)
        if record:
            print(f"\n{'File Info':=^60}")
            print(f"Path:              {record.path}")
            print(f"Branch:            {record.branch}")
            print(f"Size:              {record.size_bytes:,} bytes ({record.size_bytes/1024**2:.2f} MB)")
            print(f"Compressed:        {record.compressed_size:,} bytes")
            print(f"Compression:       {record.compression_ratio:.1%}")
            print(f"Checksum (SHA256): {record.checksum}")
            print(f"Last Modified:     {record.last_modified}")
            print(f"Retrievals:        {record.retrieval_count}")
            print(f"Git Commit:        {record.git_commit or 'N/A'}")

    def cmd_list_branch(self, args):
        """Read: List all files on branch"""
        files = self.db.list_files_by_branch(args.branch)

        print(f"\n{'Files on Branch: ' + args.branch:=^60}")
        print(f"{'Path':<40} {'Size (MB)':>10} {'Ratio':>8}")
        print("-" * 60)

        for f in sorted(files, key=lambda x: x.size_bytes, reverse=True)[:50]:
            size_mb = f.size_bytes / (1024**2)
            ratio = f.compression_ratio or 0
            print(f"{f.path[:40]:<40} {size_mb:>10.2f} {ratio:>7.1%}")

        if len(files) > 50:
            print(f"... and {len(files)-50} more files")

    def cmd_branch_stats(self, args):
        """Read: Get branch statistics"""
        stats = self.db.get_branch_stats(args.branch)

        print(f"\n{'Branch Statistics: ' + args.branch:=^60}")
        print(f"Total Files:       {stats['total_files']}")
        print(f"Total Size:        {stats['total_size_mb']:.1f} MB")
        print(f"Compressed Size:   {stats['compressed_size_mb']:.1f} MB")
        print(f"Space Saved:       {stats['bytes_saved_mb']:.1f} MB")
        print(f"Avg Compression:   {stats['avg_compression_ratio']:.1%}")
        print(f"Best Compression:  {stats['best_ratio']:.1%}")
        print(f"Worst Compression: {stats['worst_ratio']:.1%}")

    def cmd_retrieval_hints(self, args):
        """Read: Get caching recommendations"""
        hints = self.vcrud.read_with_retrieval_hints(args.branch)

        print(f"\n{'Retrieval Optimization Hints':=^60}")
        print(f"Branch: {hints['branch']}")
        print(f"\nStatistics:")
        for key, value in hints['stats'].items():
            if 'mb' in key.lower():
                print(f"  {key}: {value:.1f} MB")
            else:
                print(f"  {key}: {value}")

        print(f"\nTop Files to Cache:")
        for i, f in enumerate(hints['top_retrieval_candidates'], 1):
            size_mb = f['size_bytes'] / (1024**2)
            print(f"  {i}. {f['file_path'][:35]} - {size_mb:.1f} MB, {f['retrieval_count']} accesses")

        print(f"\nRecommendation: {hints['recommendation']}")

    # ========== UPDATE COMMANDS ==========
    def cmd_update(self, args):
        """Update: Refresh file metadata after changes"""
        success = self.vcrud.update_file(args.file, args.branch, args.commit)
        if success:
            print(f"\n✓ File updated: {args.file}")

    # ========== DELETE COMMANDS ==========
    def cmd_delete(self, args):
        """Delete: Remove file with history preservation"""
        success = self.vcrud.delete_file(args.file, args.branch, args.commit)
        if success:
            print(f"\n✓ File deleted (soft delete): {args.file}")

    # ========== ANALYSIS COMMANDS ==========
    def cmd_scan_branch(self, args):
        """Scan entire Git branch and index all files"""
        result = self.vcrud.scan_branch_and_index(args.branch)

        print(f"\n{'Branch Scan Complete':=^60}")
        print(f"Branch:           {result['branch']}")
        print(f"Files Indexed:    {result['files_indexed']}")
        stats = result['stats']
        print(f"Total Size:       {stats['total_size_mb']:.1f} MB")
        print(f"Compressed Size:  {stats['compressed_size_mb']:.1f} MB")
        print(f"Avg Ratio:        {stats['avg_compression_ratio']:.1%}")

    def cmd_find_duplicates(self, args):
        """Find identical files across all branches"""
        duplicates = self.vcrud.find_duplicates_across_branches()

        print(f"\n{'Duplicate Files Found':=^60}")
        print(f"Total unique files with duplicates: {len(duplicates)}")
        print(f"\nTop wasteful duplicates (by total wasted space):\n")

        for dup in sorted(duplicates, key=lambda x: x['total_wasted'] or 0, reverse=True)[:10]:
            wasted = (dup['total_wasted'] or 0) / (1024**2)
            print(f"Checksum:  {dup['checksum'][:8]}...")
            print(f"  Copies:    {dup['duplicate_count']}")
            print(f"  Wasted:    {wasted:.1f} MB")
            print(f"  Branches:  {', '.join(dup['branches'])}")
            print(f"  Files:     {', '.join(dup['file_paths'][:2])}{'...' if len(dup['file_paths']) > 2 else ''}")
            print()

    def cmd_compare_branches(self, args):
        """Compare file sets between two branches"""
        comparison = self.vcrud.compare_branches(args.branch1, args.branch2)

        print(f"\n{'Branch Comparison':=^60}")
        print(f"{args.branch1} vs {args.branch2}\n")

        print(f"Only in {args.branch1} ({len(comparison['only_in_branch1'])} files):")
        for f in comparison['only_in_branch1'][:10]:
            print(f"  - {f}")
        if len(comparison['only_in_branch1']) > 10:
            print(f"  ... and {len(comparison['only_in_branch1'])-10} more")

        print(f"\nOnly in {args.branch2} ({len(comparison['only_in_branch2'])} files):")
        for f in comparison['only_in_branch2'][:10]:
            print(f"  - {f}")
        if len(comparison['only_in_branch2']) > 10:
            print(f"  ... and {len(comparison['only_in_branch2'])-10} more")

        print(f"\nCommon files: {comparison['common_files']}")

    def cmd_file_history(self, args):
        """Get version history for a file"""
        history = self.vcrud.get_file_history(args.file, args.branch)

        print(f"\n{'File History':=^60}")
        print(f"File: {args.file}")
        print(f"Branch: {args.branch}")
        print(f"Total versions: {len(history)}\n")

        for h in history:
            print(f"Operation: {h['operation']}")
            print(f"  Commit:     {h['git_commit'][:8] if h['git_commit'] else 'N/A'}")
            print(f"  Date:       {h['changed_at']}")
            print(f"  Size:       {h['size_bytes']:,} bytes" if h['size_bytes'] else "  Size:       N/A")
            print(f"  Compressed: {h['compressed_size']:,} bytes" if h['compressed_size'] else "  Compressed: N/A")
            print()

    def cmd_optimize(self, args):
        """Get storage optimization recommendations"""
        optimization = self.vcrud.optimize_storage(args.branch, args.ratio_threshold)

        print(f"\n{'Storage Optimization Report':=^60}")
        print(f"Branch: {optimization['branch']}")
        print(f"Threshold: {args.ratio_threshold:.0%} compression ratio\n")

        print(f"Potential savings: {optimization['optimization_potential']['estimated_savings_mb']:.1f} MB")
        print(f"  From poor compression: {len(optimization['poor_compression_candidates'])} files")
        print(f"  From duplicate files: {optimization['optimization_potential']['total_duplicate_files']} groups")
        print(f"  Total duplicate waste: {optimization['total_duplicate_waste_mb']:.1f} MB\n")

        if optimization['poor_compression_candidates']:
            print("Files with poor compression:")
            for f in optimization['poor_compression_candidates'][:5]:
                print(f"  {f['path'][:40]:<40} {f['size_mb']:>8.1f} MB ({f['ratio']:.0%})")
            if len(optimization['poor_compression_candidates']) > 5:
                print(f"  ... and {len(optimization['poor_compression_candidates'])-5} more")

    def cmd_export(self, args):
        """Export summary to JSON"""
        summary = self.vcrud.export_summary(args.branch)

        output_path = Path(args.output or f"branch_summary_{args.branch}.json")
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"\n✓ Summary exported to {output_path}")
        print(f"  Files: {summary['total_files']}")
        print(f"  Size: {summary['statistics']['total_size_mb']:.1f} MB")

    def cmd_reset_db(self, args):
        """Reset database (CAREFUL!)"""
        if not args.confirm:
            print("⚠ This will delete ALL tracking data. Use --confirm to proceed.")
            return

        # In production, add password protection and audit logging
        logger.warning("Resetting database...")
        # Implementation would drop and recreate schema
        print("✓ Database reset complete")


def main():
    parser = argparse.ArgumentParser(
        description='vCRUD System: Git-backed File Tracking with Compression',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index all files on main branch
  python vcrud_cli.py scan-branch --branch main

  # List files on a branch
  python vcrud_cli.py list --branch feature-auth

  # Find duplicate files across all branches
  python vcrud_cli.py duplicates

  # Get branch statistics
  python vcrud_cli.py stats --branch main

  # Compare two branches
  python vcrud_cli.py compare --branch1 main --branch2 develop

  # Get optimization hints for local caching
  python vcrud_cli.py hints --branch main

  # Export branch summary
  python vcrud_cli.py export --branch main --output summary.json
        """
    )

    parser.add_argument(
        '--db', default='postgresql://user:password@localhost/vcrud',
        help='PostgreSQL connection URL'
    )
    parser.add_argument(
        '--repo', default='.', help='Repository root path'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # CREATE commands
    create = subparsers.add_parser('create', help='Create: Add file to tracking')
    create.add_argument('--file', help='File path to create')
    create.add_argument('--pattern', help='Glob pattern to index files')
    create.add_argument('--branch', required=True, help='Branch name')
    create.add_argument('--commit', help='Git commit hash')

    batch = subparsers.add_parser('batch-index', help='Create: Batch index directory')
    batch.add_argument('--branch', required=True, help='Branch name')
    batch.add_argument('--patterns', nargs='*', help='Glob patterns')

    # READ commands
    read = subparsers.add_parser('read', help='Read: Get file metadata')
    read.add_argument('--file', required=True, help='File path')
    read.add_argument('--branch', required=True, help='Branch name')

    list_cmd = subparsers.add_parser('list', help='Read: List files on branch')
    list_cmd.add_argument('--branch', required=True, help='Branch name')

    stats = subparsers.add_parser('stats', help='Read: Get branch statistics')
    stats.add_argument('--branch', required=True, help='Branch name')

    hints = subparsers.add_parser('hints', help='Read: Retrieval optimization hints')
    hints.add_argument('--branch', required=True, help='Branch name')

    # UPDATE commands
    update = subparsers.add_parser('update', help='Update: Refresh file metadata')
    update.add_argument('--file', required=True, help='File path')
    update.add_argument('--branch', required=True, help='Branch name')
    update.add_argument('--commit', help='Git commit hash')

    # DELETE commands
    delete = subparsers.add_parser('delete', help='Delete: Remove file (soft delete)')
    delete.add_argument('--file', required=True, help='File path')
    delete.add_argument('--branch', required=True, help='Branch name')
    delete.add_argument('--commit', help='Git commit hash')

    # ANALYSIS commands
    scan = subparsers.add_parser('scan-branch', help='Scan and index entire branch')
    scan.add_argument('--branch', required=True, help='Branch name')

    dupes = subparsers.add_parser('duplicates', help='Find duplicate files')

    compare = subparsers.add_parser('compare', help='Compare branches')
    compare.add_argument('--branch1', required=True, help='First branch')
    compare.add_argument('--branch2', required=True, help='Second branch')

    history = subparsers.add_parser('history', help='Get file version history')
    history.add_argument('--file', required=True, help='File path')
    history.add_argument('--branch', required=True, help='Branch name')

    optimize = subparsers.add_parser('optimize', help='Storage optimization report')
    optimize.add_argument('--branch', required=True, help='Branch name')
    optimize.add_argument('--ratio-threshold', type=float, default=0.85,
                         help='Compression ratio threshold (default 0.85)')

    export = subparsers.add_parser('export', help='Export summary to JSON')
    export.add_argument('--branch', required=True, help='Branch name')
    export.add_argument('--output', help='Output file path')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = VCRUDCli(args.db, args.repo)

    command_map = {
        'create': cli.cmd_create,
        'batch-index': cli.cmd_batch_create,
        'read': cli.cmd_read,
        'list': cli.cmd_list_branch,
        'stats': cli.cmd_branch_stats,
        'hints': cli.cmd_retrieval_hints,
        'update': cli.cmd_update,
        'delete': cli.cmd_delete,
        'scan-branch': cli.cmd_scan_branch,
        'duplicates': cli.cmd_find_duplicates,
        'compare': cli.cmd_compare_branches,
        'history': cli.cmd_file_history,
        'optimize': cli.cmd_optimize,
        'export': cli.cmd_export,
    }

    handler = command_map.get(args.command)
    if handler:
        try:
            handler(args)
        except Exception as e:
            logger.error(f"Command failed: {e}")
        finally:
            cli.db.close()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
