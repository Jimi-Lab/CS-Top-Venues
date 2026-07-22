#!/usr/bin/env python3
"""Safely audit and repair arXiv abstracts in the paper database.

The old fetch_abstracts.py accepted the first arXiv title-search result.  This
script never does that: it retrieves several candidates and fills an abstract
only after a conservative title match.  Ambiguous or unavailable papers remain
empty and are recorded in a JSONL audit report.

Typical workflow (run from the repository root):

  # 1. Inspect the known-corrupted duplicate abstracts; makes no changes.
  python Script/repair_abstracts.py

  # 2. Immediately remove those unsafe abstracts, with automatic backups.
  python Script/repair_abstracts.py --quarantine-only --apply

  # 3. Re-fetch the quarantined records.  This is resumable and rate limited.
  python Script/repair_abstracts.py --repair --apply --scope missing

  # 4. Optional complete audit: revalidate every record, including records
  #    whose old abstract was unique (and thus not caught by duplicate checks).
  python Script/repair_abstracts.py --repair --apply --scope all

Use --limit N to make a small trial run.  Repair requests batch ten titles by
default, while retaining a three-second delay between requests; do not reduce
the delay for bulk repair.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent / "Source" / "2026"
ARXIV_API = "https://export.arxiv.org/api/query"
USER_AGENT = "PaperDB-AbstractRepair/1.0 (metadata verification)"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
TITLE_CUT_MARKERS = re.compile(
    r"\s+(?:Research Track|Research Papers|Journal-first Papers|"
    r"Demonstrations|Industry Challenge Track|DOI|Pre-print)\b",
    re.IGNORECASE,
)
STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into",
    "of", "on", "or", "the", "to", "toward", "towards", "via", "with",
}


def clean_source_title(title: str) -> str:
    """Remove known proceedings-track suffixes for matching, never for storage."""
    return TITLE_CUT_MARKERS.split(title, maxsplit=1)[0].strip()


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def title_tokens(title: str) -> set[str]:
    return {
        token for token in normalize_title(clean_source_title(title)).split()
        if token not in STOPWORDS and len(token) > 1
    }


def title_match(source_title: str, candidate_title: str) -> dict[str, float | bool]:
    """Return conservative match features for one source/candidate title pair."""
    left = normalize_title(clean_source_title(source_title))
    right = normalize_title(candidate_title)
    exact = bool(left and left == right)
    source_tokens, candidate_tokens = title_tokens(source_title), title_tokens(candidate_title)
    overlap = len(source_tokens & candidate_tokens)
    recall = overlap / max(1, len(source_tokens))
    precision = overlap / max(1, len(candidate_tokens))

    # Exact normalized titles are accepted.  Fuzzy matches must retain almost
    # all source-title content and cannot contain many unrelated title tokens.
    accepted = exact or (
        len(source_tokens) >= 4 and len(candidate_tokens) >= 4
        and recall >= 0.90 and precision >= 0.80
    )
    return {
        "exact": exact,
        "recall": recall,
        "precision": precision,
        "score": (recall + precision) / 2,
        "accepted": accepted,
    }


def abstract_key(abstract: str) -> str | None:
    canonical = " ".join(abstract.split())
    if len(canonical) < 100:
        return None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_files(root: Path) -> list[tuple[Path, list[dict[str, Any]]]]:
    loaded = []
    for path in sorted(root.rglob("*-2026.json")):
        relative = path.relative_to(root)
        # All auxiliary directories deliberately retain original filenames.
        # They are backups/audits, never live corpus inputs.  This includes
        # the official-source, schema, and metadata audit trees added later.
        if any(part.startswith("_") for part in relative.parts):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN cannot read {path}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            print(f"WARN skip non-list JSON {path}", file=sys.stderr)
            continue
        if all(isinstance(item, dict) for item in data):
            loaded.append((path, data))
        else:
            print(f"WARN skip malformed records {path}", file=sys.stderr)
    return loaded


def find_duplicate_abstract_records(
    loaded: list[tuple[Path, list[dict[str, Any]]]],
) -> tuple[set[tuple[Path, int]], dict[str, list[tuple[Path, int]]]]:
    groups: dict[str, list[tuple[Path, int]]] = collections.defaultdict(list)
    titles: dict[tuple[Path, int], str] = {}
    for path, papers in loaded:
        for index, paper in enumerate(papers):
            key = abstract_key(str(paper.get("abstract") or ""))
            if key:
                groups[key].append((path, index))
                titles[(path, index)] = normalize_title(str(paper.get("title") or ""))

    duplicate_groups = {
        key: locations for key, locations in groups.items()
        if len({titles[location] for location in locations}) > 1
    }
    records = {location for locations in duplicate_groups.values() for location in locations}
    return records, duplicate_groups


def arxiv_candidates_for_titles(
    titles: Iterable[str], max_results_per_title: int, timeout: int
) -> list[dict[str, str]]:
    """Fetch candidates for several titles in one arXiv request.

    Results are still matched to each source title independently by
    ``choose_candidate``.  Batching reduces API requests but never allows one
    paper's candidate to bypass another paper's title-identity check.
    """
    clauses = []
    for title in titles:
        # arXiv's full-title phrase query misses harmless title revisions
        # between preprint and proceedings versions.  Search several
        # high-information title terms instead; the candidate is *still*
        # rejected unless title identity (and, where necessary, authors) is
        # independently verified below.
        terms = sorted(title_tokens(title), key=lambda token: (-len(token), token))[:3]
        if terms:
            clauses.append(" AND ".join(f"ti:{term}" for term in terms))
    if not clauses:
        return []
    search_query = clauses[0] if len(clauses) == 1 else "(" + " OR ".join(clauses) + ")"
    params = urllib.parse.urlencode({
        "search_query": search_query,
        "start": "0",
        # arXiv ranks the union globally, so reserve several candidates for
        # each title.  The cap keeps responses and URLs manageable.
        "max_results": str(min(100, max_results_per_title * len(clauses))),
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    request = urllib.request.Request(
        f"{ARXIV_API}?{params}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        root = ET.fromstring(response.read().decode("utf-8"))

    results = []
    for entry in root.findall("atom:entry", ATOM_NS):
        results.append({
            "title": " ".join(entry.findtext("atom:title", "", ATOM_NS).split()),
            "abstract": " ".join(entry.findtext("atom:summary", "", ATOM_NS).split()),
            "url": entry.findtext("atom:id", "", ATOM_NS).strip(),
            "authors": [" ".join(author.findtext("atom:name", "", ATOM_NS).split())
                        for author in entry.findall("atom:author", ATOM_NS)],
        })
    return results


def arxiv_candidates(title: str, max_results: int, timeout: int) -> list[dict[str, str]]:
    """Backward-compatible single-title wrapper used by fetch_abstracts.py."""
    return arxiv_candidates_for_titles([title], max_results, timeout)


def normalized_author(value: str) -> str:
    return normalize_title(value).replace(" ", "")


def author_match(source_authors: Iterable[str], candidate_authors: Iterable[str]) -> bool:
    """Conservatively confirm authors for a modest proceedings-title revision."""
    source_authors = list(source_authors)
    candidate_authors = list(candidate_authors)
    source = {normalized_author(str(author)) for author in source_authors if normalized_author(str(author))}
    candidate = {normalized_author(str(author)) for author in candidate_authors if normalized_author(str(author))}
    if not source or not candidate:
        return False
    full_overlap = source & candidate
    if full_overlap:
        return True
    source_last = {name.split()[-1] for name in map(normalize_title, source_authors) if name.split()}
    candidate_last = {name.split()[-1] for name in map(normalize_title, candidate_authors) if name.split()}
    # A surname alone is not enough when both papers list multiple authors.
    required = 2 if min(len(source), len(candidate)) >= 2 else 1
    return len(source_last & candidate_last) >= required


def choose_candidate(title: str, candidates: Iterable[dict[str, Any]],
                     source_authors: Iterable[str] = ()) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    accepted = []
    for candidate in candidates:
        match = title_match(title, candidate["title"])
        match["author_verified"] = author_match(source_authors, candidate.get("authors", []))
        revised_title_but_authors_match = (
            bool(match["author_verified"])
            and float(match["recall"]) >= 0.70
            and float(match["precision"]) >= 0.70
        )
        if (match["accepted"] or revised_title_but_authors_match) and len(candidate["abstract"]) >= 100:
            accepted.append((match, candidate))
    if not accepted:
        return None, None

    accepted.sort(
        key=lambda item: (bool(item[0]["exact"]), bool(item[0]["author_verified"]), float(item[0]["score"])),
        reverse=True,
    )
    match, candidate = accepted[0]
    return candidate, match


def backup_path(backup_root: Path, root: Path, source_path: Path) -> Path:
    target = backup_root / source_path.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_json_atomic(path: Path, papers: list[dict[str, Any]]) -> None:
    temp = path.with_suffix(path.suffix + ".repair-tmp")
    temp.write_text(json.dumps(papers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def format_duration(seconds: float) -> str:
    """Format long durations without time.strftime's 24-hour wraparound."""
    total = max(0, int(seconds))
    days, remainder = divmod(total, 24 * 60 * 60)
    hours, remainder = divmod(remainder, 60 * 60)
    minutes, seconds = divmod(remainder, 60)
    prefix = f"{days}d " if days else ""
    return f"{prefix}{hours:02d}:{minutes:02d}:{seconds:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="paper JSON root")
    parser.add_argument("--scope", choices=("duplicates", "missing", "all"), default="duplicates",
                        help="records to process; default is known duplicate-abstract records")
    parser.add_argument("--quarantine-only", action="store_true", help="clear selected abstracts without querying arXiv")
    parser.add_argument("--repair", action="store_true", help="query arXiv and fill only verified matches")
    parser.add_argument("--apply", action="store_true", help="write changes; omit for a read-only audit/dry run")
    parser.add_argument("--limit", type=int, default=0, help="process only the first N selected records")
    parser.add_argument("--max-results", type=int, default=8, help="arXiv candidates per title")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="titles per arXiv request during --repair (default: 10; use 1 to disable batching)")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between arXiv requests (default: 3)")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds")
    parser.add_argument("--progress-every", type=int, default=25,
                        help="print progress after this many records; 0 disables progress output")
    parser.add_argument("--checkpoint-every", type=int, default=100,
                        help="persist pending repaired files every N records; 0 writes only at file boundaries")
    parser.add_argument("--report-dir", type=Path, default=None, help="directory for JSONL audit reports")
    args = parser.parse_args()

    if args.quarantine_only and args.repair:
        parser.error("choose either --quarantine-only or --repair")
    if not args.quarantine_only and not args.repair:
        args.quarantine_only = True  # a no-risk audit by default
    if args.delay < 0:
        parser.error("--delay must be non-negative")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if args.checkpoint_every < 0:
        parser.error("--checkpoint-every must be non-negative")

    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"root does not exist: {root}")
    loaded = load_files(root)
    duplicate_records, duplicate_groups = find_duplicate_abstract_records(loaded)
    all_locations = [(path, index) for path, papers in loaded for index in range(len(papers))]
    if args.scope == "duplicates":
        selected = sorted(duplicate_records, key=lambda item: (str(item[0]), item[1]))
    elif args.scope == "missing":
        selected = [(path, index) for path, index in all_locations
                    if not abstract_key(str(dict(loaded)[path][index].get("abstract") or ""))]
    else:
        selected = all_locations
    if args.limit:
        selected = selected[:args.limit]

    report_dir = (args.report_dir or root / "_abstract_audit").resolve()
    timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    report_path = report_dir / f"abstract_repair_{timestamp}.jsonl"
    backup_root = root / "_abstract_backup" / timestamp

    print(f"Loaded {sum(len(papers) for _, papers in loaded)} papers from {len(loaded)} files.")
    print(f"Found {len(duplicate_groups)} duplicate-abstract groups covering {len(duplicate_records)} records.")
    print(f"Selected {len(selected)} records (scope={args.scope}; mode={'repair' if args.repair else 'quarantine'}; apply={args.apply}).")
    if args.repair:
        request_count = (len(selected) + args.batch_size - 1) // args.batch_size
        print(f"arXiv batching: {args.batch_size} titles/request, about {request_count} requests before retries.")
    if not args.apply:
        print("Dry run: no JSON files will be changed. Add --apply to write backups and updates.")

    papers_by_path = {path: papers for path, papers in loaded}
    changes: dict[Path, bool] = collections.defaultdict(bool)
    written_files: set[Path] = set()
    backed_up: set[Path] = set()
    report_rows = []
    counters = collections.Counter()
    started_at = time.monotonic()

    def show_progress(position: int) -> None:
        if not args.progress_every or (position % args.progress_every and position != len(selected)):
            return
        elapsed = time.monotonic() - started_at
        rate = position / max(elapsed, 0.001)
        remaining = (len(selected) - position) / max(rate, 0.001)
        summary = ", ".join(f"{key}={value}" for key, value in sorted(counters.items()))
        print(
            f"Progress {position}/{len(selected)} ({position * 100 / len(selected):.1f}%) | "
            f"elapsed {format_duration(elapsed)} | ETA {format_duration(remaining)} | {summary}",
            flush=True,
        )

    def checkpoint() -> int:
        """Persist dirty files so a restarted --scope missing run skips them."""
        saved = 0
        for dirty_path in sorted(changes, key=str):
            if changes[dirty_path]:
                write_json_atomic(dirty_path, papers_by_path[dirty_path])
                changes[dirty_path] = False
                written_files.add(dirty_path)
                saved += 1
        return saved

    batches = (
        [[location] for location in selected]
        if args.quarantine_only
        else [selected[start:start + args.batch_size] for start in range(0, len(selected), args.batch_size)]
    )
    position = 0
    for batch_number, batch in enumerate(batches, start=1):
        candidates: list[dict[str, str]] = []
        batch_error: tuple[str, str] | None = None
        if args.repair:
            try:
                candidates = arxiv_candidates_for_titles(
                    [str(papers_by_path[path][index].get("title") or "") for path, index in batch],
                    args.max_results,
                    args.timeout,
                )
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError) as exc:
                batch_error = ("network_or_api_error", str(exc))
            except Exception as exc:  # preserve malformed data and continue to the next batch
                batch_error = ("unexpected_error", repr(exc))

        for path, index in batch:
            position += 1
            paper = papers_by_path[path][index]
            old_abstract = str(paper.get("abstract") or "")
            row: dict[str, Any] = {
                "file": str(path.relative_to(root)), "index": index,
                "id": paper.get("id"), "title": paper.get("title"),
                "old_abstract_sha256": abstract_key(old_abstract),
            }

            if args.quarantine_only:
                row["status"] = "quarantined_duplicate" if old_abstract else "already_empty"
                if args.apply and old_abstract:
                    if path not in backed_up:
                        target = backup_path(backup_root, root, path)
                        shutil.copy2(path, target)
                        backed_up.add(path)
                    paper["abstract"] = ""
                    changes[path] = True
                counters[row["status"]] += 1
                report_rows.append(row)
                show_progress(position)
                continue

            if batch_error:
                candidate, match = None, None
                row["status"], row["error"] = batch_error
            else:
                candidate, match = choose_candidate(
                    str(paper.get("title") or ""), candidates,
                    paper.get("authors") or (),
                )

            if candidate and match:
                row.update({
                    "status": "repaired_exact" if match["exact"] else "repaired_fuzzy",
                    "arxiv_url": candidate["url"], "arxiv_title": candidate["title"],
                    "title_recall": round(float(match["recall"]), 4),
                    "title_precision": round(float(match["precision"]), 4),
                    "author_verified": bool(match["author_verified"]),
                })
                if args.apply:
                    if path not in backed_up:
                        target = backup_path(backup_root, root, path)
                        shutil.copy2(path, target)
                        backed_up.add(path)
                    paper["abstract"] = candidate["abstract"]
                    changes[path] = True
            else:
                # No verification means the old selected value is unsafe,
                # including when arXiv is temporarily unavailable.
                if "status" not in row:
                    row["status"] = "no_verified_arxiv_match"
                if args.apply and old_abstract:
                    if path not in backed_up:
                        target = backup_path(backup_root, root, path)
                        shutil.copy2(path, target)
                        backed_up.add(path)
                    paper["abstract"] = ""
                    changes[path] = True
            counters[row["status"]] += 1
            report_rows.append(row)
            # Persist a completed source file before moving to the next one.
            is_last_in_file = position == len(selected) or selected[position][0] != path
            if args.apply and args.repair and is_last_in_file and changes[path]:
                write_json_atomic(path, papers_by_path[path])
                changes[path] = False
                written_files.add(path)
            if (
                args.apply and args.repair and args.checkpoint_every
                and position % args.checkpoint_every == 0
            ):
                checkpoint()
            show_progress(position)

        # One delay per batch follows arXiv's request guidance.  The next
        # request carries several independent title clauses.
        if args.repair and batch_number < len(batches) and args.delay:
            time.sleep(args.delay)

    if args.apply:
        checkpoint()
        report_dir.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as report:
            for row in report_rows:
                report.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {len(written_files)} changed JSON files.")
        print(f"Backups: {backup_root}")
        print(f"Audit report: {report_path}")
    print("Result counts:", ", ".join(f"{key}={value}" for key, value in sorted(counters.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
