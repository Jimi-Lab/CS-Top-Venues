#!/usr/bin/env python3
"""
fetch_abstracts.py — Fill missing abstracts from arXiv API

Usage:
  python fetch_abstracts.py                              # all files, serial
  python fetch_abstracts.py --workers 8                  # all files, 8 parallel
  python fetch_abstracts.py --file SE/FSE/FSE-2026.json  # single file only
  python fetch_abstracts.py --file C:/Users/.../FSE-2026.json --workers 4
"""
import os, json, re, sys, time, random, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from multiprocessing import Pool

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Source', '2026')
ARXIV_API = 'http://export.arxiv.org/api/query?search_query=ti:{}&max_results=1'
RETRY_DELAY = 10   # seconds to wait on 429
MAX_RETRIES = 3     # retry count on 429/timeout
MAX_WORKERS = 8     # hard cap to avoid arXiv rate limit


def search_arxiv(title):
    """Returns (abstract_str, error_str). error_str is empty on success."""
    clean = re.sub(r'[:\-–—,"\'\(\)\[\]{}]', ' ', title)
    clean = re.sub(r'\s+', ' ', clean).strip()[:200]
    if not clean or len(clean) < 5:
        return None, 'title too short'

    url = ARXIV_API.format(urllib.parse.quote(clean))

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'PaperDB/1.0'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                xml_text = resp.read().decode('utf-8')

            root = ET.fromstring(xml_text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)
            if not entries:
                return None, 'not on arXiv'

            abstract = entries[0].findtext('atom:summary', '', ns).strip()
            abstract = re.sub(r'\s+', ' ', abstract)
            if len(abstract) < 30:
                return None, 'abstract too short'
            return abstract, None  # SUCCESS

        except urllib.error.HTTPError as e:
            if e.code == 429:
                delay = RETRY_DELAY * (attempt + 1) + random.uniform(0, 5)
                time.sleep(delay)
                continue  # retry
            return None, 'HTTP %d' % e.code
        except Exception as e:
            delay = RETRY_DELAY * (attempt + 1)
            time.sleep(delay)
            continue  # retry on timeout/network error

    return None, 'exhausted retries'


def process_file(json_path):
    """Process a single file. Returns stats dict with error breakdown."""
    rel = os.path.relpath(json_path, BASE)
    with open(json_path, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    need = [(i, p) for i, p in enumerate(papers)
            if not p.get('abstract') or len(p.get('abstract', '')) < 100]

    if not need:
        return {'file': rel, 'found': 0, 'checked': 0, 'not_on_arxiv': 0,
                'errors': 0, 'error_samples': []}

    found = 0
    not_on_arxiv = 0
    err_count = 0
    err_samples = []

    for idx, p in need:
        abstract, error = search_arxiv(p.get('title', ''))

        if abstract:
            p['abstract'] = abstract
            found += 1
        elif error == 'not on arXiv':
            p['abstract'] = ''  # genuinely not on arXiv, don't retry
            not_on_arxiv += 1
        else:
            # Network error, rate limit, etc. — leave abstract as None so it retries
            err_count += 1
            if len(err_samples) < 3:
                err_samples.append('%s: %s' % (p.get('title', '')[:60], error))

    # Atomic save
    tmp_path = json_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, json_path)

    return {
        'file': rel, 'found': found, 'checked': len(need),
        'not_on_arxiv': not_on_arxiv, 'errors': err_count,
        'error_samples': err_samples,
    }


def main():
    # File discovery
    all_files = []
    for root, dirs, files in os.walk(BASE):
        for f in files:
            if not f.endswith('-2026.json'):
                continue
            if os.path.isdir(os.path.join(root, 'chunks_arxiv')):
                continue
            all_files.append(os.path.join(root, f))
        if 'chunks_arxiv' in dirs:
            chunk_dir = os.path.join(root, 'chunks_arxiv')
            for cf in sorted(os.listdir(chunk_dir)):
                if cf.endswith('.json'):
                    all_files.append(os.path.join(chunk_dir, cf))
    all_files = sorted(all_files)

    # Count work
    total_need = 0
    for path in all_files:
        with open(path, 'r', encoding='utf-8') as f:
            papers = json.load(f)
        total_need += sum(1 for p in papers
                          if not p.get('abstract') or len(p.get('abstract', '')) < 100)

    if total_need == 0:
        print('Nothing to do!')
        return

    # Parse args
    workers = 0
    target_file = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--workers' and i + 1 < len(args):
            workers = min(int(args[i + 1]), MAX_WORKERS)
            i += 2
        elif args[i] == '--file' and i + 1 < len(args):
            target_file = args[i + 1]
            i += 2
        else:
            i += 1

    if workers == 0:
        workers = 1

    # If --file specified, filter to only that file
    if target_file:
        # Accept relative path from BASE or absolute path
        if os.path.isabs(target_file):
            target_path = target_file
        else:
            target_path = os.path.join(BASE, target_file)
        if not os.path.exists(target_path):
            print('ERROR: file not found: %s' % target_file)
            sys.exit(1)
        all_files = [target_path]
        # Recount
        total_need = 0
        for path in all_files:
            with open(path, 'r', encoding='utf-8') as f:
                papers = json.load(f)
            total_need += sum(1 for p in papers
                              if not p.get('abstract') or len(p.get('abstract', '')) < 100)
        if workers > 1:
            print('--file mode: single file, using 1 worker')
            workers = 1

    print('%d files, %d papers need abstracts' % (len(all_files), total_need))
    print('Workers: %d  |  arXiv retry: up to %d times on 429/timeout\n' % (workers, MAX_RETRIES))

    start_time = time.time()

    with Pool(processes=workers) as pool:
        results = []
        for result in pool.imap_unordered(process_file, all_files):
            results.append(result)
            elapsed = time.time() - start_time
            total_found = sum(r['found'] for r in results)
            total_checked = sum(r['checked'] for r in results)
            total_errs = sum(r['errors'] for r in results)
            total_not = sum(r['not_on_arxiv'] for r in results)

            rate = total_checked * 100 // max(1, total_need)
            print('  [%3d%%] %s: %d/%d found, %d not on arXiv, %d errors | elapsed %s' % (
                rate, result['file'], result['found'], result['checked'],
                result['not_on_arxiv'], result['errors'],
                time.strftime('%H:%M:%S', time.gmtime(elapsed))))

            if result['error_samples']:
                for s in result['error_samples']:
                    print('         ERR: %s' % s)

    total_dt = time.time() - start_time
    total_found = sum(r['found'] for r in results)
    total_checked = sum(r['checked'] for r in results)
    total_errs = sum(r['errors'] for r in results)
    total_not = sum(r['not_on_arxiv'] for r in results)

    print()
    print('=' * 60)
    print('COMPLETE')
    print('  Found on arXiv:  %d (%d%%)' % (total_found, total_found * 100 // max(1, total_checked)))
    print('  Not on arXiv:    %d' % total_not)
    print('  Errors (retry):  %d' % total_errs)
    print('  Total time:       %s' % time.strftime('%Hh %Mm %Ss', time.gmtime(total_dt)))
    print('=' * 60)

    if total_errs > 0:
        print()
        print('⚠️  %d papers had network errors — re-run to retry them.' % total_errs)


if __name__ == '__main__':
    main()
