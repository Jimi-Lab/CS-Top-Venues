#!/usr/bin/env python3
"""Fetch and audit abstracts from official proceedings platforms.

Only adapters that have been verified against an official platform are enabled.
The audit is external: paper records retain the established 13-field schema and
only their existing ``abstract`` value is updated after an exact title match.

Initial supported adapter: USENIX technical-session pages (USENIX Security,
FAST, NSDI, OSDI).  Other venue families are intentionally not guessed.
"""

from __future__ import annotations

import argparse
import gzip
import datetime as dt
import html
import json
import re
import shutil
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent / "Source" / "2026"
USER_AGENT = "PaperDB-OfficialAbstractAudit/1.0"
USENIX_VENUES = {
    "USENIXSec": (
        "Security/USENIX_Security/USENIXSec-2026.json",
        "https://www.usenix.org/conference/usenixsecurity26/technical-sessions",
    ),
    "FAST": (
        "Sys/FAST/FAST-2026.json",
        "https://www.usenix.org/conference/fast26/technical-sessions",
    ),
    "NSDI": (
        "Sys/NSDI/NSDI-2026.json",
        "https://www.usenix.org/conference/nsdi26/technical-sessions",
    ),
    "OSDI": (
        "Sys/OSDI/OSDI-2026.json",
        "https://www.usenix.org/conference/osdi26/technical-sessions",
    ),
}

AAAI_VENUE = {
    "AAAI": "AI/AAAI/AAAI-2026.json",
}

JMLR_VENUE = {
    "JMLR": ("AI/JMLR/JMLR-2026.json", "https://www.jmlr.org/papers/v27/"),
}

VIRTUAL_VENUES = {
    "ICLR": ("AI/ICLR/ICLR-2026.json", "https://iclr.cc/static/virtual/data/iclr-2026-orals-posters.json", "https://iclr.cc"),
    "ICML": ("AI/ICML/ICML-2026.json", "https://icml.cc/static/virtual/data/icml-2026-orals-posters.json", "https://icml.cc"),
}

RESEARCHR_VENUES = {
    "FSE": ("SE/FSE/FSE-2026.json", "https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/{number}/x"),
    "ICSE": ("SE/ICSE/ICSE-2026.json", "https://conf.researchr.org/details/icse-2026/icse-2026-research-track/{number}/x"),
    "ISSTA": ("SE/ISSTA/ISSTA-2026.json", "https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/{number}/x"),
    "PLDI": ("PL/PLDI/PLDI-2026.json", "https://pldi26.sigplan.org/details/pldi-2026-papers/{number}/x"),
    "POPL": ("PL/POPL/POPL-2026.json", "https://popl26.sigplan.org/details/POPL-2026-popl-research-papers/{number}/x"),
}


def normalized_text(value: str) -> str:
    value = html.unescape(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def plain_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


def fetch_bytes(url: str, timeout: int = 90) -> bytes:
    """Download a page and transparently decode HTTP gzip content."""
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read()
        encoding = (response.headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip" or payload[:2] == b"\x1f\x8b":
        return gzip.decompress(payload)
    return payload


def fetch_usenix_page(url: str) -> dict[str, str]:
    """Return {normalized official title: official abstract} from one page."""
    soup = BeautifulSoup(fetch_bytes(url), "html.parser")
    result: dict[str, str] = {}
    for article in soup.select("article.node-paper"):
        heading = article.select_one("h2 a")
        abstract = article.select_one(".field-name-field-paper-description-long")
        if not heading or not abstract:
            continue
        title = plain_text(heading.get_text(" ", strip=True))
        text = plain_text(abstract.get_text(" ", strip=True))
        if title and len(text) >= 100:
            result.setdefault(normalized_text(title), text)
    return result


def fetch_aaai_record(index: int, record: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Fetch one OJS article and return a verified result without mutation."""
    url = str(record.get("paper_url") or "")
    result: dict[str, Any] = {"index": index, "url": url}
    if not url.startswith("https://ojs.aaai.org/"):
        result["status"] = "unsupported_or_missing_official_url"
        return index, result
    try:
        soup = BeautifulSoup(fetch_bytes(url, timeout=60), "html.parser")
        heading = soup.select_one("h1")
        abstract_node = soup.select_one("section.item.abstract")
        page_title = plain_text(heading.get_text(" ", strip=True)) if heading else ""
        abstract = plain_text(abstract_node.get_text(" ", strip=True)) if abstract_node else ""
        if abstract.lower().startswith("abstract "):
            abstract = abstract[9:].strip()
        result.update({"page_title": page_title, "official_abstract": abstract})
        if not page_title or normalized_text(page_title) != normalized_text(str(record.get("title") or "")):
            result["status"] = "official_title_mismatch"
        elif len(abstract) < 100:
            result["status"] = "official_abstract_missing"
        else:
            result["status"] = "verified"
    except Exception as exc:  # Kept in audit; never write an unverified result.
        result.update({"status": "network_or_parse_error", "error": f"{type(exc).__name__}: {exc}"})
    return index, result


def fetch_jmlr_article(url: str) -> tuple[str, str, str | None]:
    """Return official title and abstract from one JMLR abstract page."""
    try:
        soup = BeautifulSoup(fetch_bytes(url, timeout=60), "html.parser")
        heading = soup.select_one("h2")
        abstract_node = soup.select_one("p.abstract")
        title = plain_text(heading.get_text(" ", strip=True)) if heading else ""
        abstract = plain_text(abstract_node.get_text(" ", strip=True)) if abstract_node else ""
        return title, abstract, None
    except Exception as exc:
        return "", "", f"{type(exc).__name__}: {exc}"


def fetch_jmlr_volume(url: str, workers: int) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Build a title-keyed official abstract map for a JMLR volume."""
    index = BeautifulSoup(fetch_bytes(url), "html.parser")
    links = []
    for anchor in index.select("a[href]"):
        if plain_text(anchor.get_text(" ", strip=True)).lower() == "abs":
            href = anchor["href"]
            if href.endswith(".html"):
                links.append("https://www.jmlr.org" + href if href.startswith("/") else href)
    official: dict[str, str] = {}
    issues: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_jmlr_article, url): url for url in links}
        for future in as_completed(futures):
            article_url = futures[future]
            title, abstract, error = future.result()
            if error or not title or len(abstract) < 100:
                issues.append({"official_url": article_url, "status": "network_or_parse_error" if error else "official_abstract_missing", "error": error})
            else:
                official.setdefault(normalized_text(title), abstract)
    return official, issues


def fetch_virtual_record(index: int, record: dict[str, Any], official_url: str) -> tuple[int, dict[str, Any]]:
    """Fetch an official ICLR/ICML virtual-proceedings page with title verification."""
    try:
        soup = BeautifulSoup(fetch_bytes(official_url, timeout=60), "html.parser")
        heading = soup.select_one("h1.event-title")
        abstract_node = soup.select_one(".abstract-section .abstract-text-inner")
        page_title = plain_text(heading.get_text(" ", strip=True)) if heading else ""
        abstract = plain_text(abstract_node.get_text(" ", strip=True)) if abstract_node else ""
        result: dict[str, Any] = {"index": index, "url": official_url,
                                  "page_title": page_title, "official_abstract": abstract}
        if not page_title or normalized_text(page_title) != normalized_text(str(record.get("title") or "")):
            result["status"] = "official_title_mismatch"
        elif len(abstract) < 100:
            result["status"] = "official_abstract_missing"
        else:
            result["status"] = "verified"
        return index, result
    except Exception as exc:
        return index, {"index": index, "url": official_url, "status": "network_or_parse_error",
                       "error": f"{type(exc).__name__}: {exc}"}


def virtual_urls(index_url: str, base_url: str) -> dict[str, str]:
    """Return title-keyed official event URLs from the conference's static virtual data."""
    payload = json.loads(fetch_bytes(index_url, timeout=120))
    events = payload.get("results", [])
    urls: dict[str, str] = {}
    for event in events:
        title = str(event.get("name") or "")
        relative = str(event.get("virtualsite_url") or "")
        if title and relative.startswith("/"):
            urls.setdefault(normalized_text(title), base_url + relative)
    return urls


def fetch_researchr_page(url: str) -> tuple[str, str, str | None]:
    """Extract title/abstract from a Researchr or SIGPLAN conference detail page."""
    try:
        soup = BeautifulSoup(fetch_bytes(url, timeout=60), "html.parser")
        heading = soup.select_one("h2")
        label = next((node for node in soup.select("label")
                      if plain_text(node.get_text(" ", strip=True)) == "Abstract"), None)
        abstract_node = label.find_next_sibling("div") if label else None
        title = plain_text(heading.get_text(" ", strip=True)) if heading else ""
        abstract = plain_text(abstract_node.get_text(" ", strip=True)) if abstract_node else ""
        return title, abstract, None
    except Exception as exc:
        return "", "", f"{type(exc).__name__}: {exc}"


def write_json_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".official-abstract-tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    supported = sorted({*USENIX_VENUES, *AAAI_VENUE, *JMLR_VENUE, *VIRTUAL_VENUES, *RESEARCHR_VENUES})
    parser.add_argument("--venues", nargs="+", choices=supported,
                        default=supported, help="official-source venues to audit")
    parser.add_argument("--apply", action="store_true", help="replace differing abstracts with official text")
    parser.add_argument("--workers", type=int, default=8,
                        help="parallel requests for direct official-paper pages (default: 8)")
    parser.add_argument("--progress-every", type=int, default=100,
                        help="print direct-page progress every N completed requests (default: 100)")
    args = parser.parse_args()

    timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_root = ROOT / "_official_abstract_backup" / timestamp
    audit_root = ROOT / "_official_abstract_audit"
    audit_path = audit_root / f"usenix_audit_{timestamp}.jsonl"
    audit_rows: list[dict[str, Any]] = []
    changed_files = 0
    counts: dict[str, int] = {}

    for venue in [v for v in args.venues if v in USENIX_VENUES]:
        relative, official_url = USENIX_VENUES[venue]
        official = fetch_usenix_page(official_url)
        path = ROOT / relative
        records = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        venue_counts = {"same": 0, "replaced": 0, "title_not_found": 0, "official_abstract_missing": 0}
        for index, record in enumerate(records):
            title = str(record.get("title") or "")
            official_abstract = official.get(normalized_text(title))
            row = {
                "venue": venue, "file": relative, "index": index, "id": record.get("id"),
                "title": title, "official_url": official_url,
            }
            if not official_abstract:
                row["status"] = "title_not_found_or_official_abstract_missing"
                venue_counts["title_not_found"] += 1
            else:
                current = plain_text(str(record.get("abstract") or ""))
                similarity = SequenceMatcher(None, normalized_text(current), normalized_text(official_abstract)).ratio()
                row["official_abstract_chars"] = len(official_abstract)
                row["current_abstract_chars"] = len(current)
                row["normalized_similarity"] = round(similarity, 6)
                if normalized_text(current) == normalized_text(official_abstract):
                    row["status"] = "same_as_official"
                    venue_counts["same"] += 1
                else:
                    row["status"] = "replaced_with_official" if args.apply else "differs_from_official"
                    venue_counts["replaced"] += 1
                    if args.apply:
                        record["abstract"] = official_abstract
                        changed = True
            audit_rows.append(row)
        if args.apply and changed:
            target = backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            write_json_atomic(path, records)
            changed_files += 1
        counts[venue] = venue_counts
        print(f"{venue}: official_abstracts={len(official)} | {venue_counts}", flush=True)

    for venue in [v for v in args.venues if v in AAAI_VENUE]:
        relative = AAAI_VENUE[venue]
        path = ROOT / relative
        records = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        venue_counts = {"same": 0, "replaced": 0, "official_title_mismatch": 0,
                        "official_abstract_missing": 0, "network_or_parse_error": 0,
                        "unsupported_or_missing_official_url": 0}
        workers = max(1, min(args.workers, 16))
        print(f"{venue}: fetching {len(records)} direct official pages with {workers} workers...", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(fetch_aaai_record, index, record)
                       for index, record in enumerate(records)]
            for completed, future in enumerate(as_completed(futures), start=1):
                index, result = future.result()
                record = records[index]
                status = result["status"]
                row = {"venue": venue, "file": relative, "index": index,
                       "id": record.get("id"), "title": record.get("title"),
                       "official_url": result.get("url"), "status": status}
                if status == "verified":
                    official_abstract = result["official_abstract"]
                    current = plain_text(str(record.get("abstract") or ""))
                    similarity = SequenceMatcher(None, normalized_text(current), normalized_text(official_abstract)).ratio()
                    row.update({"official_abstract_chars": len(official_abstract),
                                "current_abstract_chars": len(current),
                                "normalized_similarity": round(similarity, 6)})
                    if normalized_text(current) == normalized_text(official_abstract):
                        row["status"] = "same_as_official"
                        venue_counts["same"] += 1
                    else:
                        row["status"] = "replaced_with_official" if args.apply else "differs_from_official"
                        venue_counts["replaced"] += 1
                        if args.apply:
                            record["abstract"] = official_abstract
                            changed = True
                else:
                    venue_counts[status] += 1
                    if "page_title" in result:
                        row["official_title"] = result["page_title"]
                    if "error" in result:
                        row["error"] = result["error"]
                audit_rows.append(row)
                if args.progress_every > 0 and (completed % args.progress_every == 0 or completed == len(records)):
                    print(f"{venue}: progress {completed}/{len(records)} | {venue_counts}", flush=True)
        if args.apply and changed:
            target = backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            write_json_atomic(path, records)
            changed_files += 1
        counts[venue] = venue_counts
        print(f"{venue}: {venue_counts}", flush=True)

    for venue in [v for v in args.venues if v in JMLR_VENUE]:
        relative, official_url = JMLR_VENUE[venue]
        workers = max(1, min(args.workers, 16))
        print(f"{venue}: indexing the official volume and fetching its abstract pages with {workers} workers...", flush=True)
        official, issues = fetch_jmlr_volume(official_url, workers)
        path = ROOT / relative
        records = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        venue_counts = {"same": 0, "replaced": 0, "title_not_found": 0,
                        "volume_page_issue": len(issues)}
        for index, record in enumerate(records):
            title = str(record.get("title") or "")
            official_abstract = official.get(normalized_text(title))
            row = {"venue": venue, "file": relative, "index": index, "id": record.get("id"),
                   "title": title, "official_url": official_url}
            if not official_abstract:
                row["status"] = "title_not_found_or_official_abstract_missing"
                venue_counts["title_not_found"] += 1
            else:
                current = plain_text(str(record.get("abstract") or ""))
                similarity = SequenceMatcher(None, normalized_text(current), normalized_text(official_abstract)).ratio()
                row.update({"official_abstract_chars": len(official_abstract),
                            "current_abstract_chars": len(current),
                            "normalized_similarity": round(similarity, 6)})
                if normalized_text(current) == normalized_text(official_abstract):
                    row["status"] = "same_as_official"
                    venue_counts["same"] += 1
                else:
                    row["status"] = "replaced_with_official" if args.apply else "differs_from_official"
                    venue_counts["replaced"] += 1
                    if args.apply:
                        record["abstract"] = official_abstract
                        changed = True
            audit_rows.append(row)
        for issue in issues:
            audit_rows.append({"venue": venue, "file": relative, "index": None, "id": None,
                               "title": None, **issue})
        if args.apply and changed:
            target = backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            write_json_atomic(path, records)
            changed_files += 1
        counts[venue] = venue_counts
        print(f"{venue}: official_abstracts={len(official)} | {venue_counts}", flush=True)

    for venue in [v for v in args.venues if v in VIRTUAL_VENUES]:
        relative, index_url, base_url = VIRTUAL_VENUES[venue]
        path = ROOT / relative
        records = json.loads(path.read_text(encoding="utf-8"))
        workers = max(1, min(args.workers, 16))
        print(f"{venue}: loading official virtual-proceedings index, then fetching {len(records)} verified pages with {workers} workers...", flush=True)
        index_urls = virtual_urls(index_url, base_url)
        jobs: list[tuple[int, dict[str, Any], str]] = []
        changed = False
        venue_counts = {"same": 0, "replaced": 0, "title_missing_from_official_index": 0,
                        "official_title_mismatch": 0, "official_abstract_missing": 0,
                        "network_or_parse_error": 0}
        for index, record in enumerate(records):
            official_url = index_urls.get(normalized_text(str(record.get("title") or "")))
            if official_url:
                jobs.append((index, record, official_url))
            else:
                audit_rows.append({"venue": venue, "file": relative, "index": index, "id": record.get("id"),
                                   "title": record.get("title"), "official_url": index_url,
                                   "status": "title_missing_from_official_index"})
                venue_counts["title_missing_from_official_index"] += 1
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(fetch_virtual_record, index, record, official_url)
                       for index, record, official_url in jobs]
            for completed, future in enumerate(as_completed(futures), start=1):
                index, result = future.result()
                record = records[index]
                status = result["status"]
                row = {"venue": venue, "file": relative, "index": index, "id": record.get("id"),
                       "title": record.get("title"), "official_url": result.get("url"), "status": status}
                if status == "verified":
                    official_abstract = result["official_abstract"]
                    current = plain_text(str(record.get("abstract") or ""))
                    similarity = SequenceMatcher(None, normalized_text(current), normalized_text(official_abstract)).ratio()
                    row.update({"official_abstract_chars": len(official_abstract),
                                "current_abstract_chars": len(current),
                                "normalized_similarity": round(similarity, 6)})
                    if normalized_text(current) == normalized_text(official_abstract):
                        row["status"] = "same_as_official"
                        venue_counts["same"] += 1
                    else:
                        row["status"] = "replaced_with_official" if args.apply else "differs_from_official"
                        venue_counts["replaced"] += 1
                        if args.apply:
                            record["abstract"] = official_abstract
                            changed = True
                else:
                    venue_counts[status] += 1
                    if "page_title" in result:
                        row["official_title"] = result["page_title"]
                    if "error" in result:
                        row["error"] = result["error"]
                audit_rows.append(row)
                if args.progress_every > 0 and (completed % args.progress_every == 0 or completed == len(jobs)):
                    print(f"{venue}: progress {completed}/{len(jobs)} | {venue_counts}", flush=True)
        if args.apply and changed:
            target = backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            write_json_atomic(path, records)
            changed_files += 1
        counts[venue] = venue_counts
        print(f"{venue}: official_index_titles={len(index_urls)} | {venue_counts}", flush=True)

    for venue in [v for v in args.venues if v in RESEARCHR_VENUES]:
        relative, url_template = RESEARCHR_VENUES[venue]
        path = ROOT / relative
        records = json.loads(path.read_text(encoding="utf-8"))
        workers = max(1, min(args.workers, 16))
        official: dict[str, str] = {}
        issues: list[dict[str, Any]] = []
        print(f"{venue}: fetching {len(records)} official detail pages with {workers} workers...", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_researchr_page, url_template.format(number=number)): number
                       for number in range(1, len(records) + 1)}
            for completed, future in enumerate(as_completed(futures), start=1):
                number = futures[future]
                title, abstract, error = future.result()
                url = url_template.format(number=number)
                if error or not title or len(abstract) < 100:
                    issues.append({"official_url": url,
                                   "status": "network_or_parse_error" if error else "official_abstract_missing",
                                   "error": error})
                else:
                    official.setdefault(normalized_text(title), abstract)
                if args.progress_every > 0 and (completed % args.progress_every == 0 or completed == len(records)):
                    print(f"{venue}: source-page progress {completed}/{len(records)} | official_abstracts={len(official)} | issues={len(issues)}", flush=True)
        changed = False
        venue_counts = {"same": 0, "replaced": 0, "title_not_found": 0,
                        "source_page_issue": len(issues)}
        for index, record in enumerate(records):
            title = str(record.get("title") or "")
            official_abstract = official.get(normalized_text(title))
            row = {"venue": venue, "file": relative, "index": index, "id": record.get("id"),
                   "title": title, "official_url": url_template}
            if not official_abstract:
                row["status"] = "title_not_found_or_official_abstract_missing"
                venue_counts["title_not_found"] += 1
            else:
                current = plain_text(str(record.get("abstract") or ""))
                similarity = SequenceMatcher(None, normalized_text(current), normalized_text(official_abstract)).ratio()
                row.update({"official_abstract_chars": len(official_abstract),
                            "current_abstract_chars": len(current), "normalized_similarity": round(similarity, 6)})
                if normalized_text(current) == normalized_text(official_abstract):
                    row["status"] = "same_as_official"
                    venue_counts["same"] += 1
                else:
                    row["status"] = "replaced_with_official" if args.apply else "differs_from_official"
                    venue_counts["replaced"] += 1
                    if args.apply:
                        record["abstract"] = official_abstract
                        changed = True
            audit_rows.append(row)
        for issue in issues:
            audit_rows.append({"venue": venue, "file": relative, "index": None, "id": None,
                               "title": None, **issue})
        if args.apply and changed:
            target = backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            write_json_atomic(path, records)
            changed_files += 1
        counts[venue] = venue_counts
        print(f"{venue}: official_abstracts={len(official)} | {venue_counts}", flush=True)

    audit_root.mkdir(parents=True, exist_ok=True)
    with audit_path.open("w", encoding="utf-8") as handle:
        for row in audit_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Changed files: {changed_files}", flush=True)
    print(f"Audit: {audit_path}", flush=True)
    if args.apply:
        print(f"Backups: {backup_root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
