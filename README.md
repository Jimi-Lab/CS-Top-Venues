# 2026 Top Venue Paper Database

## description:

* A comprehensive, year-by-year collection of papers from top venues in Security, AI, Software Engineering, Programming Languages, Systems, Databases, and Formal Methods.
* Paper identity metadata (`id`, venue, title, authors, year, cycle, and paper URL) is collected from official conference proceedings, journal websites, or publisher pages.
* Abstracts use an evidence-first policy: official proceedings/pages where available, followed by title-verified arXiv records (including author verification for modest proceedings/preprint title revisions).
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

| Category            | Venue     | Expected |
| ------------------- | --------- | -------- |
| Security            | ACM CCS   | Nov 2026 |
| AI                  | NeurIPS   | Dec 2026 |
| SE                  | ASE<br /> | Oct 2026 |
| Sys / OS / AI Infra | SOSP      | TBD      |

## What I Did

1. **Verified 36 venues' official 2026 paper directories** — checked URLs, cycles/rounds, and status for each conference/journal
2. **Extracted all 2026 papers** from official websites, JSON APIs, ACM/IEEE BibTeX, HTML pages, and PDF front matter
3. **Normalized title pollution and unified every paper to the same 13-field JSON schema**
4. **Audited and repaired abstracts** using official venue pages first and conservative arXiv identity matching as a fallback
5. **Preserved backups and JSONL audit trails** outside the live corpus directories

## Folder Structure

```
Source/2026/
├── index.json              ← Metadata for all 36 venues (counts, URLs, status)
├── AI/                     ← live 2026 AI venue JSONs
│   ├── ICML/ICML-2026.json (6,796 papers)
│   ├── ICLR/ICLR-2026.json (5,691 papers)
│   └── ...
├── Security/               ← live 2026 Security venue JSONs
├── SE/                     ← live 2026 Software Engineering venue JSONs
├── PL/                     ← live 2026 Programming Languages venue JSONs
├── Sys/                    ← live 2026 Systems venue JSONs
├── DB/                     ← 3 venues: SIGMOD, VLDB, ICDE
└── Formal_Methods/         ← 1 venue: CAV
```

Only the seven non-underscore category directories above are live corpus inputs.
All underscore-prefixed directories (for example `_official_abstract_audit` and
`_schema_backup`) are audit/backup artefacts and must be excluded from reading,
statistics, filtering, and LLM summarization.

The four venues not yet published — ACM CCS, NeurIPS, ASE, and SOSP — are tracked
in `Source/2026/index.json`; they do not yet have live paper JSON files.

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

| Field                  | Coverage                | Source                                                     |
| ---------------------- | ----------------------- | ---------------------------------------------------------- |
| `title`              | 100%                    | Official proceedings                                       |
| `authors`            | 100%                    | Official proceedings                                       |
| `abstract`           | 20,870 / 21,787 (95.8%) | Official pages first; title/author-verified arXiv fallback |
| `keywords`           | 10%                     | IEEE/ACM journal metadata                                  |
| `research_direction` | 100%                    | AI-classified from title                                   |
| `cycle`              | S&P, NDSS, SIGMOD only  | Official proceedings                                       |



## Scripts

| Script                                      | Purpose                                                                                                                                                                                    |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Script/fetch_abstracts.py`               | Safely fill missing abstracts from arXiv only after conservative title verification; intentionally rate-limited to one worker.                                                             |
| `Script/repair_abstracts.py`              | Audit duplicate/wrong arXiv abstracts, quarantine unsafe values with automatic backups, and conservatively re-fetch title-verified arXiv matches in batches. Run without`--apply` first. |
| `Script/fetch_official_abstracts.py`      | Fetch and compare abstracts from verified official venue platforms; only replaces an abstract after title identity verification.                                                           |
| `Script/normalize_titles.py`              | Remove deterministic proceedings-parser pollution from titles without changing the paper schema.                                                                                           |
| `Script/normalize_schema.py`              | Enforce the canonical 13-field paper-record schema and field order.                                                                                                                        |
| `Script/update_library_summary.py`        | Refresh`index.json` and the Excel 2026 local-corpus summary from live JSON files.                                                                                                        |
| `Script/build_keyword_candidate_pools.py` | Build an auditable, high-recall candidate pool from titles and abstracts without changing source JSONs.                                                                                    |
| `Script/build_full_recommendations.py`    | Classify the candidate pool into direct, foundation, boundary, unrelated, and metadata-repair reading outputs.                                                                             |
| `Script/write_semantic_audit_results.py`  | Reproduce the fixed 120-paper semantic-audit sidecar used to calibrate reading recommendations.                                                                                            |



## Reading Outputs

`Output/` contains derived reading material; it never changes the live corpus.

1. `直l接相关推荐.json` is the primary reading queue.
2. `基础相关推荐.json` contains relevant technical foundations.
3. `边界相关推荐.json` contains adjacent work such as Agent, MCP/RAG, CUA,
   multimodal, and world-model security.
4. `元数据待修复.json` holds candidate papers whose title/abstract identity must
   be repaired before recommendation.

`候选池.json` and the 120-paper audit sidecars are retained for reproducibility.
Generated backups, raw operation audits, and Python caches are intentionally
ignored by Git; they remain local recovery/provenance artefacts.

## Usage Quickstart

```powershell
# Audit known duplicated/mismatched abstracts (read-only)
python Script/repair_abstracts.py

# After reviewing the audit, quarantine unsafe values and re-fetch only
# title/author-verified arXiv matches (with automatic backups and an audit report)
python Script/repair_abstracts.py --quarantine-only --apply
python Script/repair_abstracts.py --repair --scope missing --apply

# Audit/fetch from currently supported official venue platforms.
python Script/fetch_official_abstracts.py --help

# Refresh the index and Excel summary after corpus changes.
python Script/update_library_summary.py

# Check venue status
python -c "import json; idx=json.load(open('Source/2026/index.json')); print(idx['total_papers'])"
```
