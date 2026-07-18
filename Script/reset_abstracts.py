"""Reset empty-string abstracts so they get retried on next run."""
import json, os, sys

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Source', '2026')
total_reset = 0

for root, dirs, files in os.walk(BASE):
    for f in files:
        if not f.endswith('-2026.json'): continue
        path = os.path.join(root, f)
        with open(path, 'r', encoding='utf-8') as fp:
            papers = json.load(fp)
        reset = 0
        for p in papers:
            a = p.get('abstract')
            # Keep real abstracts (longer than 100 chars, or journal ones)
            if isinstance(a, str) and len(a) > 100:
                continue
            if a == '' or a is None:
                # Remove so it retries
                if 'abstract' in p:
                    del p['abstract']
                    reset += 1
        if reset:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fp:
                json.dump(papers, fp, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        rel = os.path.relpath(path, BASE)
        print(f'{rel}: reset {reset} papers')
        total_reset += reset

print(f'\nTotal: {total_reset} papers reset')

if total_reset == 0:
    print('Nothing to reset — already clean.')
