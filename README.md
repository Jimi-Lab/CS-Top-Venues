# 2026 Top Venue Paper Database

## description:

* A comprehensive, year-by-year collection of papers from top venues in Security, AI, Software Engineering, Programming Languages, Systems, Databases, and Formal Methods.
* All records are collected directly from official conference proceedings, journal websites, and publisher pages, ensuring that the dataset is based exclusively on authoritative publication sources.
* For a detailed overview of venue selection, CCF rankings, and directory URLs, see the accompanying spreadsheet: `Top_Venues_Official_Paper_Directory.xlsx`.

## Venue Coverage

### ✅ Collected (32 venues, 21,787 papers)

| Category            | Venue                         | Papers |
| ------------------- | ----------------------------- | ------ |
| Security            | IEEE S&P (SP)                 | 254    |
| Security            | USENIX Security (USENIXSec)   | 362    |
| Security            | NDSS                          | 265    |
| Security            | IEEE TDSC                     | 631    |
| Security            | IEEE TIFS                     | 443    |
| AI                  | ICML                          | 6,796  |
| AI                  | ICLR                          | 5,691  |
| AI                  | AAAI                          | 2,274  |
| AI                  | IJCAI                         | 990    |
| AI                  | ACL                           | 515    |
| AI                  | JMLR                          | 137    |
| AI                  | IEEE TPAMI                    | 631    |
| AI                  | Artificial Intelligence (AIJ) | 78     |
| SE                  | ICSE                          | 321    |
| SE                  | FSE                           | 211    |
| SE                  | ISSTA                         | 176    |
| SE                  | IEEE TSE                      | 109    |
| SE                  | ACM TOSEM                     | 212    |
| PL                  | PLDI                          | 118    |
| PL                  | POPL                          | 92     |
| PL                  | OOPSLA                        | 74     |
| PL                  | ACM TOPLAS                    | 12     |
| PL                  | JACM                          | 21     |
| Sys / OS / AI Infra | OSDI                          | 137    |
| Sys / OS / AI Infra | NSDI                          | 151    |
| Sys / OS / AI Infra | EuroSys                       | 138    |
| Sys / OS / AI Infra | ASPLOS                        | 168    |
| Sys / OS / AI Infra | FAST                          | 46     |
| DB                  | SIGMOD                        | 311    |
| DB                  | VLDB                          | 81     |
| DB                  | ICDE                          | 261    |
| Formal Methods      | CAV                           | 81     |

### ❌ Not Yet Collected (4 venues, proceedings not yet released)

| Category            | Venue   | Expected |
| ------------------- | ------- | -------- |
| Security            | ACM CCS | Nov 2026 |
| AI                  | NeurIPS | Dec 2026 |
| SE                  | ASE     | Oct 2026 |
| Sys / OS / AI Infra | SOSP    | TBD      |

## What I Did

1. **Verified 36 venues' official 2026 paper directories** — checked URLs, cycles/rounds, and status for each conference/journal
2. **Extracted all 2026 papers** from official websites, JSON APIs, ACM/IEEE BibTeX, HTML pages, and PDF front matter
3. **Enriched with arXiv abstracts** via `export.arxiv.org/api` title search — 99.9% paper coverage
4. **Unified to a single JSON schema** and organized by research category

## Folder Structure

```
Source/2026/
├── index.json              ← Metadata for all 36 venues (counts, URLs, status)
├── AI/                     ← 9 venues: ICML, ICLR, AAAI, IJCAI, ACL, JMLR,
│   │                                TPAMI, AI Journal, NeurIPS
│   ├── ICML/ICML-2026.json (6,796 papers)
│   ├── ICLR/ICLR-2026.json (5,691 papers)
│   └── ...
├── Security/               ← 6 venues: IEEE S&P, NDSS, USENIX Sec, TDSC, TIFS, CCS
├── SE/                     ← 6 venues: ICSE, FSE, ISSTA, TSE, TOSEM, ASE
├── PL/                     ← 5 venues: PLDI, POPL, OOPSLA, TOPLAS, JACM
├── Sys/                    ← 6 venues: OSDI, NSDI, EuroSys, ASPLOS, FAST, SOSP
├── DB/                     ← 3 venues: SIGMOD, VLDB, ICDE
└── Formal_Methods/         ← 1 venue: CAV
```

4 venues not yet published (empty folders): ACM_CCS, ASE, NeurIPS, SOSP (will be added once proceedings are released).

## JSON Schema

Every paper follows this format:

```json
{
  "id": "sp-2026-0001",
  "venue": "SP",
  "year": 2026,
  "month": 5,
  "cycle": 1,
  "title": "Bridge: High-Order Taint Vulnerabilities Detection...",
  "authors": ["Jiaqian Peng", "Puzhuo Liu", "Yicheng Zeng"],
  "affiliation": [],
  "keywords": [],
  "research_direction": ["Binary Security"],
  "paper_type": "Research Paper",
  "paper_url": "https://sp2026.ieee-security.org/accepted-papers.html",
  "abstract": "We present Bridge, a static analysis framework..."
}
```

| Field                  | Coverage               | Source                    |
| ---------------------- | ---------------------- | ------------------------- |
| `title`              | 100%                   | Official proceedings      |
| `authors`            | 100%                   | Official proceedings      |
| `abstract`           | 99.9%                  | arXiv API                 |
| `keywords`           | 10%                    | IEEE/ACM journal metadata |
| `research_direction` | 100%                   | AI-classified from title  |
| `cycle`              | S&P, NDSS, SIGMOD only | Official proceedings      |

## Scripts

| Script                 | Purpose                                                                                                                          |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `fetch_abstracts.py` | Bulk-fill missing abstracts from arXiv API. Supports multi-process (`--workers 8`) and single-file mode (`--file path.json`) |
| `merge_chunks.py`    | Merge split chunk files back into venue JSONs (one-time use after parallel fetch)                                                |
| `reset_abstracts.py` | Clear empty-string abstracts so papers can be retried                                                                            |

## Usage Quickstart

```powershell
# Fill all missing abstracts (8 parallel workers)
python fetch_abstracts.py --workers 8

# Fill abstracts for a single venue
python fetch_abstracts.py --file SE/FSE/FSE-2026.json

# Check venue status
python -c "import json; idx=json.load(open('Source/2026/index.json')); print(idx['total_papers'])"
```
