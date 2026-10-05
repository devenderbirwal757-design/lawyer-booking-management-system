#!/usr/bin/env python3
"""Validate the planning-document set stays mutually consistent.

Checks, in order of severity:

  1. Every relative markdown link (./file.md) resolves to a real file.
  2. Every PRD section 1..N is covered by at least one traceability-matrix row
     (a parent counts as covered when a child subsection is covered).
  3. Every traceability-matrix row points at a PRD section that actually exists.
  4. Every shorthand section reference (B/F/S §x) resolves to a real heading in
     the target document.
  5. No duplicate section numbers within a document.
  6. Each companion document links back to the other three.

Exit code 0 when clean, 1 when any check fails. No third-party dependencies so
it can run in CI, in a pre-commit hook, or by hand.

    python3 scripts/check_docs.py
    python3 scripts/check_docs.py --quiet
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PRD = "prd.md"
PLANS = {"backend-plan.md": "B", "frontend-plan.md": "F", "security.md": "S"}
ALL_DOCS = [PRD, *PLANS]

# Section numbers that are structural rather than requirements.
MATRIX_SECTION = "33"

# "## 3. Data model"  ->  "3"
NUM_HEADING = re.compile(r"^#{1,3}\s+(\d+(?:\.\d+)*)[.\s]")
# "## A4. Authorization"  ->  "A4"
LET_HEADING = re.compile(r"^#{1,3}\s+([A-I])(\d*)[.\s]")
# "# Part B — Performance"  ->  "B" and "Part B"
PART_HEADING = re.compile(r"^#{1,3}\s+Part\s+([A-I])\b")
# "### Phase 4 — Customers & OTP auth"  ->  "Phase 4"
PHASE_HEADING = re.compile(r"^#{1,3}\s+Phase\s+(\d+)\b")
# PRD section headings: "1. Product Overview" and "5.1 Landing Page". The two
# forms are matched separately so bare numbers like "15 October" or
# "30 minutes" in prose are not mistaken for section headings.
PRD_SECTION = re.compile(r"^(?:(\d+)\.\s+\S|(\d+\.\d+)\s+\S)")
# "| 7 | **Prevent double booking** | B §5 | ..."
MATRIX_ROW = re.compile(r"^\|\s*(\d+(?:\.\d+)*)\s*\|")
# "./backend-plan.md#anchor" or "./backend-plan.md"
MD_LINK = re.compile(r"\]\(\./([^)#\s]+)")
# "B §5", "F §11 Phase 7", "S §A4", "S §C"
SHORTHAND = re.compile(r"\b([BFS])\s+(§\s*)(\d+(?:\.\d+)*|[A-I]\d*)")
# A bare "§5" / "§A4" not preceded by a B/F/S prefix.
BARE_REF = re.compile(r"(?<![BFS]\s)(§\s*)(\d+(?:\.\d+)*|[A-I]\d*)")

# Rows that are legitimately not about a numbered PRD section.
NO_MATRIX_ROW = {
    "33",  # the matrix itself
}


def read(name: str) -> list[str]:
    return (ROOT / name).read_text(encoding="utf-8").splitlines()


def prd_section_of(line: str) -> str | None:
    """The PRD section number a line opens, if any. Handles both '1. X' and '5.1 X'."""
    if m := PRD_SECTION.match(line):
        return m.group(1) or m.group(2)
    return None


def section_keys(lines: list[str]) -> set[str]:
    """Every addressable section token in a document."""
    keys: set[str] = set()
    for line in lines:
        if (sec := prd_section_of(line)) is not None:
            keys.add(sec)
            continue
        if m := NUM_HEADING.match(line):
            keys.add(m.group(1))
            continue
        if m := LET_HEADING.match(line):
            keys.add(m.group(1) + m.group(2))
            continue
        if m := PART_HEADING.match(line):
            # Referenced both as "§B" and "§Part B".
            keys.add(m.group(1))
            keys.add(f"Part {m.group(1)}")
            continue
        if m := PHASE_HEADING.match(line):
            keys.add(f"Phase {m.group(1)}")
    return keys


def numbered_headings(lines: list[str]) -> list[str]:
    """Top-level section numbers, for duplicate detection."""
    out: list[str] = []
    for line in lines:
        if m := NUM_HEADING.match(line):
            out.append(m.group(1))
    return out


def prd_requirements(lines: list[str]) -> set[str]:
    """PRD sections that must be traceable, i.e. everything except the matrix."""
    out: set[str] = set()
    for line in lines:
        if (sec := prd_section_of(line)) is not None and sec not in NO_MATRIX_ROW:
            out.add(sec)
    return out


def matrix_rows(lines: list[str]) -> list[tuple[int, str]]:
    """(line number, prd section) for each traceability-matrix row."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        if m := MATRIX_ROW.match(line):
            out.append((i, m.group(1)))
    return out


def covered_by_child(section: str, covered: set[str]) -> bool:
    """A parent section counts as covered if any child subsection is covered."""
    prefix = f"{section}."
    return any(c.startswith(prefix) for c in covered)


def check_links(errors: list[str]) -> None:
    for name in ALL_DOCS:
        for i, line in enumerate(read(name), 1):
            for target in MD_LINK.findall(line):
                if not (ROOT / target).is_file():
                    errors.append(
                        f"{name}:{i}: link to '{target}' does not exist "
                        f"(check for a trailing space in the filename)"
                    )


def check_coverage(errors: list[str]) -> None:
    prd_lines = read(PRD)
    required = prd_requirements(prd_lines)
    covered = {sec for _, sec in matrix_rows(prd_lines)}
    known = required | {MATRIX_SECTION}
    for sec in sorted(required, key=lambda s: [int(p) for p in s.split(".")]):
        if sec not in covered and not covered_by_child(sec, covered):
            errors.append(
                f"{PRD}: section {sec} has no row in the section-33 "
                f"traceability matrix"
            )
    for _, sec in matrix_rows(prd_lines):
        if sec not in known:
            errors.append(
                f"{PRD}: traceability matrix references section {sec}, "
                f"which does not exist in the PRD"
            )


def check_shorthand(errors: list[str]) -> None:
    keys = {name: section_keys(read(name)) for name in ALL_DOCS}
    for name in ALL_DOCS:
        for i, line in enumerate(read(name), 1):
            for prefix, _sign, token in SHORTHAND.findall(line):
                target = next(d for d, p in PLANS.items() if p == prefix)
                if token not in keys[target]:
                    errors.append(
                        f"{name}:{i}: '{prefix} §{token}' does not match any "
                        f"section in {target}"
                    )


def check_bare_refs(errors: list[str]) -> None:
    """Validate unprefixed '§5' / '§A4' references inside prose.

    A numeric token is accepted if it exists in the containing document or in
    the PRD, since prose legitimately points at both ("PRD §7", "§5" of this
    file). A lettered token is accepted in the containing document or in
    security.md, the only document that uses lettered sections.

    Known limitation: because the PRD and the plans both have low-numbered
    sections, a misattributed bare numeric reference ('§5' meaning the PRD when
    the writer meant this file) cannot be detected. Use the B/F/S prefix when it
    matters.
    """
    keys = {name: section_keys(read(name)) for name in ALL_DOCS}
    for name in ALL_DOCS:
        for i, line in enumerate(read(name), 1):
            for _sign, token in BARE_REF.findall(line):
                token = token.strip()
                if token in keys[name]:
                    continue
                fallback = PRD if token[0].isdigit() else "security.md"
                if token in keys[fallback]:
                    continue
                errors.append(
                    f"{name}:{i}: '§{token}' does not match any section in "
                    f"{name} or {fallback} (use a B/F/S prefix for clarity)"
                )


def check_duplicates(errors: list[str]) -> None:
    for name in ALL_DOCS:
        seen: set[str] = set()
        for num in numbered_headings(read(name)):
            if num in seen:
                errors.append(
                    f"{name}: duplicate section number '{num}' "
                    f"(section numbers are cross-referenced, keep them unique)"
                )
            seen.add(num)


def check_reciprocal_links(errors: list[str]) -> None:
    for name in ALL_DOCS:
        body = "\n".join(read(name))
        for other in ALL_DOCS:
            if other == name:
                continue
            if f"./{other}" not in body:
                errors.append(f"{name}: does not link to {other}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--quiet", action="store_true", help="print errors only, on failure"
    )
    args = ap.parse_args()

    errors: list[str] = []
    check_links(errors)
    check_coverage(errors)
    check_shorthand(errors)
    check_bare_refs(errors)
    check_duplicates(errors)
    check_reciprocal_links(errors)

    if errors:
        print(f"FAIL: {len(errors)} documentation consistency problem(s)\n")
        for err in errors:
            print(f"  {err}")
        print("\nSee the section-33 traceability matrix in prd.md.")
        return 1

    if not args.quiet:
        prd_lines = read(PRD)
        reqs = prd_requirements(prd_lines)
        rows = matrix_rows(prd_lines)
        print("OK: documentation set is consistent")
        print(f"  {len(ALL_DOCS)} documents, all links resolve")
        print(f"  {len(reqs)} PRD requirements, {len(rows)} traceability rows")
        print(f"  shorthand references verified against {len(ALL_DOCS)} heading sets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
