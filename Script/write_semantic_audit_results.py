#!/usr/bin/env python3
"""Persist the title-and-abstract semantic audit of the fixed 120-paper sample."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "Output" / "120篇语义审计样本.json"
OUTPUT = ROOT / "Output" / "120篇语义审计结果.json"

# Labels were assigned by reading each title and available abstract against the
# user's three research taxonomies.  Order is the stable order in the sample.
LABELS = {
    "core_ai_direct": [
        "directly_related", "unrelated", "directly_related", None, "directly_related",
        "directly_related", "boundary_related", "directly_related", "directly_related", "directly_related",
        "directly_related", "directly_related", "directly_related", "boundary_related", "foundation_related",
        "foundation_related", "directly_related", "foundation_related", "directly_related", "directly_related",
        "directly_related", "directly_related", None, "directly_related", "directly_related",
        "directly_related", "directly_related", "boundary_related", "directly_related", "directly_related",
        "directly_related", "foundation_related", "directly_related", "directly_related", "directly_related",
        "directly_related", "directly_related", "foundation_related", "directly_related", "directly_related",
    ],
    "core_security_foundation": [
        "directly_related", None, "directly_related", "directly_related", "directly_related",
        "boundary_related", "directly_related", "directly_related", "directly_related", "directly_related",
        "directly_related", "directly_related", "foundation_related", "foundation_related", "foundation_related",
        "directly_related", "foundation_related", None, "directly_related", "directly_related",
        None, "directly_related", "directly_related", None, "foundation_related",
        "foundation_related", "directly_related", "directly_related", "directly_related", "directly_related",
        "directly_related", "boundary_related", "foundation_related", "directly_related", "directly_related",
        "directly_related", "foundation_related", "directly_related", "directly_related", "directly_related",
    ],
    "observation_ai_direct": [
        "unrelated", "unrelated", "unrelated", "unrelated", "unrelated",
        "unrelated", "unrelated", "boundary_related", "unrelated", "unrelated",
        "unrelated", "boundary_related", "boundary_related", "foundation_related", "unrelated",
        "boundary_related", "unrelated", "unrelated", "unrelated", "directly_related",
    ],
    "observation_frontier_boundary": [
        "boundary_related", "boundary_related", "boundary_related", "unrelated", "unrelated",
        "directly_related", "directly_related", "boundary_related", "unrelated", "boundary_related",
        "boundary_related", "directly_related", "unrelated", "directly_related", "directly_related",
        "boundary_related", "directly_related", "unrelated", "unrelated", None,
    ],
}

# The paper title and abstract conflict for these records; the missing-abstract
# records cannot be classified reliably from title alone.
IDENTITY_CONFLICT = {
    ("core_ai_direct", 4),
    ("core_ai_direct", 23),
    ("core_security_foundation", 2),
}
MISSING_ABSTRACT = {
    ("core_security_foundation", 18),
    ("core_security_foundation", 21),
    ("core_security_foundation", 24),
    ("observation_frontier_boundary", 20),
}


def reason_code(label: str | None, conflict: bool, missing: bool) -> str:
    if conflict:
        return "title_abstract_identity_conflict"
    if missing:
        return "abstract_missing"
    return {
        "directly_related": "primary_problem_or_threat_model_matches_user_taxonomy",
        "foundation_related": "relevant_program_analysis_or_software_security_foundation_without_primary_ai_security_focus",
        "boundary_related": "adjacent_ai_or_security_topic_but_threat_model_or_target_is_not_a_primary_user_direction",
        "unrelated": "security_or_ai_terms_are_not_the_paper_primary_research_problem",
    }[label]


def main() -> None:
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = source["papers"]
    per_stratum: dict[str, int] = Counter()
    output_rows = []
    for row in rows:
        stratum = row["audit_stratum"]
        per_stratum[stratum] += 1
        position = per_stratum[stratum]
        label = LABELS[stratum][position - 1]
        conflict = (stratum, position) in IDENTITY_CONFLICT
        missing = (stratum, position) in MISSING_ABSTRACT
        if conflict or missing:
            label = None
        result = dict(row)
        result["semantic_audit"] = {
            "label": label,
            "status": "needs_metadata_repair" if conflict else ("insufficient_abstract" if missing else "reviewed"),
            "reason_code": reason_code(label, conflict, missing),
            "basis": "manual title-and-abstract review against the user research taxonomy",
        }
        output_rows.append(result)

    expected = {name: len(labels) for name, labels in LABELS.items()}
    if dict(per_stratum) != expected:
        raise ValueError(f"Unexpected sample order or counts: {dict(per_stratum)} != {expected}")
    labels = Counter(row["semantic_audit"]["label"] for row in output_rows)
    statuses = Counter(row["semantic_audit"]["status"] for row in output_rows)
    document = {
        "name": "120篇语义审计结果",
        "schema_version": "2026-candidate-semantic-audit-result-v1",
        "generated_on": date.today().isoformat(),
        "scope": "Title-and-abstract review only; not a full-paper judgment.",
        "taxonomy_labels": ["directly_related", "foundation_related", "boundary_related", "unrelated"],
        "summary": {
            "sample_size": len(output_rows),
            "labels": {str(key): value for key, value in sorted(labels.items(), key=lambda item: str(item[0]))},
            "statuses": dict(sorted(statuses.items())),
        },
        "papers": output_rows,
    }
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
