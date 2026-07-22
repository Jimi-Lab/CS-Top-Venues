# Annual Workflow — Maintaining the Paper Database

This guide covers the yearly cycle: adding a new year's papers, filling in venues that were previously not yet published, and keeping everything up to date.

## Overview

```
Verify URLs ──► Fetch official metadata ──► Normalize JSON ──► Official abstracts ──► arXiv fallback ──► Validate
     │                    │                       │                    │                    │                 │
  30 min              2-6 hours                5 min              venue-specific       rate-limited      audit + summary
```

---

## Step 0: Setup

```powershell
cd C:\Users\Admin\Desktop\paper
git pull
```

## Step 1: Update Excel with new year

1. Open `Top_Venues_Official_Paper_Directory.xlsx`
2. For each venue, add/update the new year's columns:
   - Official paper directory URL
   - Directory status (✅ / 🟡 / ∅ / ❌)
   - Notes (cycle count, round info, paper count estimates)
3. Verify each URL opens correctly in a browser
4. Save

## Step 2: Fetch paper lists

For each venue with status ✅:

| Venue type | Approach | Example command |
|-----------|----------|-----------------|
| NeurIPS/ICML/ICLR type | Download JSON from `*/static/virtual/data/*.json` | `curl -o icml2027.json "https://icml.cc/static/virtual/data/icml-2027-orals-posters.json"` |
| USENIX (OSDI/NSDI/FAST/Sec) | Download HTML, parse paper nodes | `curl -o osdi27.html "https://www.usenix.org/conference/osdi27/technical-sessions"` |
| SIGPLAN via researchr.org | Download HTML, find "Accepted Papers" tab table | `curl -o pldi27.html "https://pldi27.sigplan.org/track/pldi-2027-papers"` |
| ACM DL / IEEE / Elsevier journals | Export BibTeX or CSV from publisher website (manual) | Open in browser → export → save as .txt/.bib |
| IJCAI / ACL / AAAI type | Download HTML, parse title/author blocks | `curl -o ijcai27.html "https://2027.ijcai.org/accepted-papers/"` |
| VLDB | Download Front Matter PDFs, parse with pdfplumber | Download PDFs → run `pdfplumber` extraction script |

Parse the downloaded files into `papers.json` using venue-specific extraction scripts (reuse patterns from 2026 extraction).

## Step 3: Validate paper lists

For each venue:
- Confirm `collected == official count` (check cycle/round totals)
- Spot-check 3 papers: verify title, authors, paper_type
- Check no workshop/demo/industry papers mixed in

```powershell
python -c "
import json
with open('Source/2027/SE/ICSE/ICSE-2027.json') as f:
    papers = json.load(f)
print(f'Total: {len(papers)}')
print(f'Sample: {papers[0][\"title\"]}')
"
```

## Step 4: Migrate to unified JSON

Generate unified JSON from the raw paper lists (update `month` and `cycle` mappings for the new year first). Use the standard JSON schema from `README.md` as the target format.

## Step 5: Fill and verify abstracts

Use a source hierarchy.  Never accept the first arXiv search result or copy an
abstract between papers merely because titles look similar.

1. Prefer a verified official adapter (proceedings, virtual venue, paper page,
   or official PDF) and require title identity before replacement.
2. If no official per-paper abstract is available, use arXiv only after a
   conservative title match.  For modest proceedings/preprint title revisions,
   require author confirmation as well.
3. Persist backups and external JSONL audits.  Do not add provenance fields to
   individual paper records; the canonical 13-field schema stays unchanged.

```powershell
# Inspect currently supported official adapters, then run selected venues.
python Script/fetch_official_abstracts.py --help
python Script/fetch_official_abstracts.py --venues AAAI JMLR --apply

# Conservative arXiv fallback for still-missing abstracts.  Keep the default
# request pacing; this is intentionally not a high-concurrency scraper.
python Script/repair_abstracts.py --repair --scope missing --apply
```

If some papers need retrying, re-run the same conservative command; first read
the generated audit report to distinguish a network error from no verified
identity match.  Do not use a broad reset/clear operation as a retry shortcut.

```powershell
python Script/repair_abstracts.py --repair --scope missing --apply
```

## Step 6: Validate final output

```powershell
python -c "
import json, os, glob
total = 0
has_abs = 0
for f in sorted(glob.glob('Source/2027/**/*-2027.json', recursive=True)):
    if any(part.startswith('_') for part in f.replace('\\', '/').split('/')):
        continue  # backups/audits are never corpus inputs
    venue = os.path.basename(f).replace('-2027.json','')
    papers = json.load(open(f, encoding='utf-8'))
    abs_count = sum(1 for p in papers if p.get('abstract') and len(p['abstract'])>50)
    print(f'{venue:20s}: {len(papers):5d} papers, {abs_count:5d} abstracts ({abs_count*100//max(1,len(papers))}%)')
    total += len(papers)
    has_abs += abs_count
print(f'\nTOTAL: {total} papers, {has_abs} abstracts ({has_abs*100//max(1,total)}%)')
"
```

## Step 7: Refresh summaries, update README, and push

1. Run the year-specific summary refresh script (for 2026, `python Script/update_library_summary.py`).
2. Update the venue table and abstract-coverage statement in `README.md`.
3. Update the annual workflow if a new official venue platform/adapter was needed.
4. Keep underscore-prefixed backup/audit directories out of all corpus statistics, LLM inputs, and Git commits; `.gitignore` retains them locally.
5. Commit and push:

```powershell
git add .
git commit -m "Add 2027 papers: X venues, Y papers total"
git push origin main
```

## Special Cases

### Filling in previously unpublished venues

When CCS (Nov), ASE (Oct), NeurIPS (Dec), or SOSP (TBD) finally publish proceedings, follow Steps 2-5 for just that venue, then place the JSON in the correct category folder under the existing year.

### Journals (ongoing publication)

Journals publish continuously. Recommended: re-export BibTeX/CSV from the publisher website every 6 months (June, December) to capture new articles, then re-run Step 4.

### Handling new venue additions

If you add a venue to the Excel that was not previously tracked:
1. Assign it a `venue_short` code
2. Add it to the category mapping in `migrate_to_json.py`
3. Follow Steps 2-5 as usual

## File Reference

| File | Purpose |
|------|---------|
| `Top_Venues_Official_Paper_Directory.xlsx` | Master venue list with URLs and status |
| `Script/repair_abstracts.py` | Conservatively audit and repair arXiv abstracts with backups and audit sidecars |
| `Script/fetch_official_abstracts.py` | Fetch and verify abstracts from supported official platforms |
| `Script/build_keyword_candidate_pools.py` | Build an auditable high-recall reading candidate pool |
| `Script/build_full_recommendations.py` | Produce the current direct, foundation, boundary, and metadata-repair reading outputs |
| `Output/直接相关推荐.json` | Primary reading queue |
| `Output/基础相关推荐.json` | Relevant technical foundations |
| `Output/边界相关推荐.json` | Adjacent reading queue for deliberate review |
| `Output/元数据待修复.json` | Candidate metadata requiring title/abstract repair before recommendation |
| `WORKFLOW.md` | This file |
| `README.md` | Project overview |
