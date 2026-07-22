#!/usr/bin/env python3
"""Audit and safely normalize known official-listing title parser artifacts.

The 2026 ICSE and FSE listings were scraped from Researchr cards whose track,
author, DOI, and preprint labels were concatenated into ``title``.  This tool
removes only those venue-specific suffixes.  It preserves the original value in
an external JSONL audit record and creates a file backup on --apply; it never
changes the established per-paper schema beyond replacing the malformed title.

Run first without --apply.  The script intentionally does not guess authors;
author repair requires a per-paper official detail page in a later acquisition
stage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent / "Source" / "2026"

# These rules were derived from the raw HTML parser artifacts in the named
# official Researchr lists.  They are deliberately venue-specific: generic
# terms such as "paper" or "abstract" can legitimately occur in a title.
RULES: dict[str, tuple[str, re.Pattern[str]]] = {
    "SE/FSE/FSE-2026.json": (
        "researchr_fse_card_suffix",
        re.compile(r"\s+Research Papers\s+.+$", re.IGNORECASE),
    ),
    "SE/ICSE/ICSE-2026.json": (
        "researchr_icse_card_suffix",
        re.compile(
            r"(?:\s+(?:Distinguished|Best)\s+Paper(?:\s+Award)?)?\s+Research Track\s+.+$",
            re.IGNORECASE,
        ),
    ),
}
PLACEHOLDER_TITLES = {"paper title under embargo"}


def canonical_whitespace(value: str) -> str:
    return " ".join(value.split()).strip()


def write_json_atomic(path: Path, papers: list[dict[str, Any]]) -> None:
    temp = path.with_suffix(path.suffix + ".title-tmp")
    temp.write_text(json.dumps(papers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--apply", action="store_true", help="write normalized titles and backups")
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"root does not exist: {root}")
    timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_root = root / "_metadata_backup" / timestamp
    audit_root = root / "_metadata_audit"
    audit_path = audit_root / f"title_normalization_{timestamp}.jsonl"
    audit_rows: list[dict[str, Any]] = []
    changed_files = 0
    normalized = 0
    removed_auxiliary_fields = 0
    placeholders = 0

    for relative, (rule_name, suffix) in RULES.items():
        path = root / relative
        papers = json.loads(path.read_text(encoding="utf-8"))
        file_changed = False
        for index, paper in enumerate(papers):
            raw = canonical_whitespace(str(paper.get("title") or ""))
            clean = canonical_whitespace(suffix.sub("", raw))
            # Remove auxiliary fields written by an earlier version of this
            # script.  The raw value remains recoverable from the external
            # audit JSONL and the automatic file backup, while records return
            # to the original schema requested by the user.
            auxiliary = [key for key in ("title_raw", "title_normalization") if key in paper]
            if auxiliary:
                audit_rows.append({
                    "file": relative, "index": index, "id": paper.get("id"),
                    "status": "removed_auxiliary_fields", "fields": auxiliary,
                })
                removed_auxiliary_fields += len(auxiliary)
                if args.apply:
                    for key in auxiliary:
                        paper.pop(key, None)
                    file_changed = True
            if clean and clean != raw:
                audit_rows.append({
                    "file": relative,
                    "index": index,
                    "id": paper.get("id"),
                    "rule": rule_name,
                    "status": "normalized",
                    "title_raw": raw,
                    "title": clean,
                })
                normalized += 1
                if args.apply:
                    paper["title"] = clean
                    file_changed = True
            elif not clean:
                audit_rows.append({
                    "file": relative, "index": index, "id": paper.get("id"),
                    "rule": rule_name, "status": "manual_review_required", "title_raw": raw,
                })

        if args.apply and file_changed:
            target = backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            write_json_atomic(path, papers)
            changed_files += 1

    # Placeholder titles are never silently normalized; record them for later
    # official-page retrieval.
    for path in root.rglob("*-2026.json"):
        relative = path.relative_to(root)
        if "_abstract_backup" in relative.parts or "_metadata_backup" in relative.parts:
            continue
        papers = json.loads(path.read_text(encoding="utf-8"))
        for index, paper in enumerate(papers):
            if canonical_whitespace(str(paper.get("title") or "")).lower() in PLACEHOLDER_TITLES:
                audit_rows.append({
                    "file": str(relative), "index": index, "id": paper.get("id"),
                    "status": "placeholder_title", "title_raw": paper.get("title"),
                })
                placeholders += 1

    print(f"Normalized title candidates: {normalized}")
    print(f"Auxiliary schema fields to remove: {removed_auxiliary_fields}")
    print(f"Placeholder titles requiring official recovery: {placeholders}")
    if args.apply:
        audit_root.mkdir(parents=True, exist_ok=True)
        with audit_path.open("w", encoding="utf-8") as handle:
            for row in audit_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Updated files: {changed_files}")
        print(f"Backups: {backup_root}")
        print(f"Audit: {audit_path}")
    else:
        print("Dry run: no JSON files changed. Add --apply after reviewing the count.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
