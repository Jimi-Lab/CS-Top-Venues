"""Merge chunk files back into original venue JSONs, then delete chunk dirs."""
import json, os, shutil

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Source', '2026')

for root, dirs, files in os.walk(BASE):
    if 'chunks_arxiv' not in dirs:
        continue

    chunk_dir = os.path.join(root, 'chunks_arxiv')
    venue_name = os.path.basename(root)
    orig_file = os.path.join(root, f'{venue_name}-2026.json')

    if not os.path.exists(orig_file):
        print(f'SKIP {venue_name}: original file not found')
        continue

    # Read all chunks
    merged = []
    for cf in sorted(os.listdir(chunk_dir)):
        if not cf.endswith('.json'): continue
        with open(os.path.join(chunk_dir, cf), 'r', encoding='utf-8') as f:
            merged.extend(json.load(f))

    # Verify count matches
    with open(orig_file, 'r', encoding='utf-8') as f:
        original = json.load(f)

    if len(merged) != len(original):
        print(f'WARNING {venue_name}: merged {len(merged)} != original {len(original)} — keeping both')
        continue

    # Atomic write
    tmp = orig_file + '.merged'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    os.replace(tmp, orig_file)

    # Delete chunks
    shutil.rmtree(chunk_dir)

    has = sum(1 for p in merged if p.get('abstract') and len(p.get('abstract', '')) > 100)
    print(f'{venue_name}: {len(merged)} papers merged, {has} with abstracts. Chunks deleted.')

print('Done!')
