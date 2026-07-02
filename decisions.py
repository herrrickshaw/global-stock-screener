#!/usr/bin/env python3
# decisions.py
# ============
# Parse the Architecture Decision Record register (DECISIONS.md) into structured
# records so decisions are queryable, validatable, and surfaceable on the
# dashboard — traceability for the repo's key design choices.
#
#   python3 decisions.py            # list ADRs (id · status · title)
#   python3 decisions.py --check    # validate structure (exit 1 on problems)
#
# ⚠️ Research/education only. Not advice.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).parent
REGISTER = HERE / "DECISIONS.md"

_HEAD = re.compile(r"^-\s+\*\*(ADR-\d+)\s+—\s+(.+?)\*\*\s+`([^`]+)`\s+\((\d{4}-\d{2}-\d{2})\)")
_FIELD = re.compile(r"^\s*-\s+\*\*(Context|Decision|Impact|Alternatives)\*\*\s+—\s+(.+)$")

VALID_STATUS = {"accepted", "superseded", "proposed", "rejected"}


@dataclass
class Decision:
    id: str
    title: str
    status: str
    date: str
    fields: Dict[str, str] = field(default_factory=dict)

    @property
    def impact(self) -> str:
        return self.fields.get("Impact", "")


def load(path: Optional[Path] = None) -> List[Decision]:
    """Parse DECISIONS.md into Decision records (in file order)."""
    p = path or REGISTER
    if not p.exists():
        return []
    out: List[Decision] = []
    cur: Optional[Decision] = None
    for line in p.read_text().splitlines():
        m = _HEAD.match(line)
        if m:
            cur = Decision(
                id=m.group(1), title=m.group(2).strip(), status=m.group(3).strip(), date=m.group(4)
            )
            out.append(cur)
            continue
        if cur is not None:
            fm = _FIELD.match(line)
            if fm:
                cur.fields[fm.group(1)] = fm.group(2).strip()
    return out


def validate(path: Optional[Path] = None) -> List[str]:
    """Return a list of structural problems (empty == valid)."""
    recs = load(path)
    problems: List[str] = []
    if not recs:
        return ["no ADRs found in DECISIONS.md"]
    seen = set()
    for r in recs:
        if r.id in seen:
            problems.append(f"{r.id}: duplicate id")
        seen.add(r.id)
        if r.status not in VALID_STATUS:
            problems.append(f"{r.id}: invalid status '{r.status}'")
        for f in ("Context", "Decision", "Impact"):
            if not r.fields.get(f):
                problems.append(f"{r.id}: missing {f}")
    return problems


def by_status(status: str, path: Optional[Path] = None) -> List[Decision]:
    return [d for d in load(path) if d.status == status]


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Architecture Decision Record register")
    ap.add_argument("--check", action="store_true", help="validate structure; exit 1 on problems")
    a = ap.parse_args(argv)
    if a.check:
        probs = validate()
        if probs:
            print("DECISIONS.md problems:")
            for p in probs:
                print(f"  - {p}")
            return 1
        print(f"DECISIONS.md OK — {len(load())} ADRs")
        return 0
    for d in load():
        print(f"{d.id}  {d.status:11}  {d.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
