#!/usr/bin/env python3
"""Enforce the canonical paper-record schema without changing existing values."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent / "Source" / "2026"
FIELDS = (
    "id", "venue", "year", "month", "cycle", "title", "authors",
    "affiliation", "keywords", "research_direction", "paper_type",
    "paper_url", "abstract",
)
DEFAULTS: dict[str, Any] = {"abstract": ""}


def write_json_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".schema-tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_root = ROOT / "_schema_backup" / timestamp
    audit_root = ROOT / "_schema_audit"
    audit_path = audit_root / f"schema_normalization_{timestamp}.jsonl"
    audit: list[dict[str, Any]] = []
    changed_files = 0
    changed_records = 0

    for path in sorted(ROOT.rglob("*-2026.json")):
        relative = path.relative_to(ROOT)
        if any(part.startswith("_") for part in relative.parts):
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        file_changed = False
        normalized_records = []
        for index, record in enumerate(records):
            missing = [field for field in FIELDS if field not in record]
            extras = [field for field in record if field not in FIELDS]
            order_mismatch = tuple(record) != FIELDS
            unsupported = [field for field in missing if field not in DEFAULTS]
            if unsupported:
                raise ValueError(f"{relative} record {index} lacks required fields: {unsupported}")
            if missing or extras or order_mismatch:
                audit.append({
                    "file": str(relative), "index": index, "id": record.get("id"),
                    "missing": missing, "removed_extras": extras,
                    "reordered_keys": order_mismatch,
                })
                changed_records += 1
                file_changed = True
            # Reconstructing the dict guarantees the same key set and key order
            # for every record.  No existing canonical value is changed.
            normalized = {field: record.get(field, DEFAULTS.get(field)) for field in FIELDS}
            normalized_records.append(normalized)

        if file_changed:
            target = backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            write_json_atomic(path, normalized_records)
            changed_files += 1

    audit_root.mkdir(parents=True, exist_ok=True)
    with audit_path.open("w", encoding="utf-8") as handle:
        for row in audit:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Updated files: {changed_files}")
    print(f"Updated records: {changed_records}")
    print(f"Backups: {backup_root}")
    print(f"Audit: {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
