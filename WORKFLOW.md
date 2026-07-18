# Annual Workflow — Maintaining the Paper Database

This guide covers the yearly cycle: adding a new year's papers, filling in venues that were previously not yet published, and keeping everything up to date.

## Overview

```
Verify URLs ──► Fetch paper lists ──► Migrate to JSON ──► Fill abstracts (arXiv) ──► Validate
     │                │                     │                    │                    │
  30 min          2-6 hours              5 min               2-12 hours             5 min
  (manual)      (semi-auto)            (script)             (script)            (spot-check)
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

## Step 5: Fill abstracts from arXiv

```powershell
# Bulk mode (all venues)
python Script/fetch_abstracts.py --workers 8

# Or single venue
python Script/fetch_abstracts.py --file SE/ICSE/ICSE-2027.json
```

If some papers need retrying (HTTP 429/503 errors):

```powershell
python Script/reset_abstracts.py
python Script/fetch_abstracts.py --workers 4  # fewer workers to avoid rate limits
```

## Step 6: Validate final output

```powershell
python -c "
import json, os, glob
total = 0
has_abs = 0
for f in sorted(glob.glob('Source/2027/**/*-2027.json', recursive=True)):
    venue = os.path.basename(f).replace('-2027.json','')
    papers = json.load(open(f, encoding='utf-8'))
    abs_count = sum(1 for p in papers if p.get('abstract') and len(p['abstract'])>50)
    print(f'{venue:20s}: {len(papers):5d} papers, {abs_count:5d} abstracts ({abs_count*100//max(1,len(papers))}%)')
    total += len(papers)
    has_abs += abs_count
print(f'\nTOTAL: {total} papers, {has_abs} abstracts ({has_abs*100//max(1,total)}%)')
"
```

## Step 7: Update README & push

1. Update venue table in `README.md` (paper counts, new venues)
2. Update `index.json` if needed
3. Commit and push:

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
| `Script/fetch_abstracts.py` | Bulk-fill abstracts from arXiv |
| `Script/merge_chunks.py` | Merge parallel-fetch chunk files |
| `Script/reset_abstracts.py` | Clear empty abstracts for retry |
| `WORKFLOW.md` | This file |
| `README.md` | Project overview |
