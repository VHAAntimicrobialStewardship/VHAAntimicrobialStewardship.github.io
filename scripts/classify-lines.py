"""Phase 1 of the markdown migration: classify every line of every page (dry run, writes a report only).

    python scripts/classify-lines.py                       # test station summary
    python scripts/classify-lines.py --station 541-Cleveland
    python scripts/classify-lines.py --page <PageID> [--field Therapy]   # annotated lines

Writes reports/markdown-line-classes.json. Nothing in cms-data is modified.
"""
import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.line_classes import classify, page_flags  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ('Text', 'Therapy')
SKIP_PAGES = {'main-menu', 'inpt-main'}
SAMPLE_LIMIT = 6


def snippet(text, width=70):
    text = text.strip()
    return text if len(text) <= width else text[:width] + '...'


def analyze(text):
    lines, pairs = classify(text)
    cls = collections.Counter(l['cls'] for l in lines if not l['blank'])
    kinds = collections.Counter(f"{p['kind']} (gap {min(p['gap'], 1)})" for p in pairs)
    return {
        'classes': dict(cls),
        'pairs': dict(kinds),
        'blockquote_lines': sum(1 for l in lines if l['quote']),
        'indented_lines': sum(1 for l in lines if l['indented']),
        'flags': page_flags(text),
    }, lines, pairs


def show_page(station, page_id, field):
    path = glob.glob(os.path.join(ROOT, 'cms-data', station, 'pages', '**', page_id + '.json'), recursive=True)
    if not path:
        sys.exit(f'No page {page_id} in {station}')
    text = json.load(open(path[0], encoding='utf-8')).get(field) or ''
    info, lines, pairs = analyze(text)
    pair_after = {p['n']: p for p in pairs}
    print(f'{station}/{page_id} [{field}] flags={info["flags"]}')
    for ln in lines:
        if ln['blank']:
            print(f'{ln["n"]:4d}  .')
            continue
        mark = ('q ' if ln['quote'] else '  ') + ln['cls']
        p = pair_after.get(ln['n'])
        tail = f'  -> {p["kind"]}(gap {p["gap"]})' if p else ''
        print(f'{ln["n"]:4d}  {mark:<16} {snippet(ln["text"])}{tail}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--station', default='001-TestStation')
    ap.add_argument('--page')
    ap.add_argument('--field', default='Text')
    args = ap.parse_args()

    if args.page:
        show_page(args.station, args.page, args.field)
        return

    pages = sorted(glob.glob(os.path.join(ROOT, 'cms-data', args.station, 'pages', '**', '*.json'), recursive=True))
    totals_cls = collections.Counter()
    totals_pairs = collections.Counter()
    flagged = collections.defaultdict(list)
    samples = collections.defaultdict(list)
    per_page = {}
    fields_checked = 0

    for path in pages:
        page_id = os.path.splitext(os.path.basename(path))[0]
        if page_id in SKIP_PAGES:
            continue
        data = json.load(open(path, encoding='utf-8'))
        for field in FIELDS:
            text = data.get(field)
            if not isinstance(text, str) or not text.strip():
                continue
            fields_checked += 1
            info, lines, pairs = analyze(text)
            key = f'{page_id}:{field}'
            per_page[key] = info
            totals_cls.update(info['classes'])
            totals_pairs.update(info['pairs'])
            for f in info['flags']:
                flagged[f].append(key)
            if info['blockquote_lines']:
                flagged['blockquote-lines'].append(key)
            if info['indented_lines']:
                flagged['indented-lines'].append(key)
            by_n = {l['n']: l for l in lines}
            for p in pairs:
                if p['kind'] in ('wrap-after-paren', 'wrap-into-link', 'heading-continuation'):
                    nxt = next((l for l in lines if l['n'] > p['n'] and not l['blank']), None)
                    if len(samples[p['kind']]) < SAMPLE_LIMIT * 4:
                        samples[p['kind']].append({
                            'page': key, 'line': p['n'], 'gap': p['gap'],
                            'first': snippet(by_n[p['n']]['text']), 'second': snippet(nxt['text']) if nxt else '',
                        })

    print(f'{args.station}: {fields_checked} fields classified (main-menu skipped)\n')
    print('Line classes:')
    for k, v in totals_cls.most_common():
        print(f'  {k:<12} {v}')
    print('\nHow adjacent lines relate (gap = blank lines between):')
    for k, v in totals_pairs.most_common():
        print(f'  {k:<22} {v}')
    print('\nPages needing manual handling or a decision:')
    for k in ('column-page', 'flattened-table', 'aligned-columns', 'nav-page', 'blockquote-lines', 'indented-lines'):
        print(f'  {k:<18} {len(flagged[k])} fields')

    out = {
        'station': args.station,
        'line_classes': dict(totals_cls),
        'pair_kinds': dict(totals_pairs),
        'flagged_fields': {k: v for k, v in flagged.items()},
        'samples': samples,
        'per_field': per_page,
    }
    with open(os.path.join(ROOT, 'reports', 'markdown-line-classes.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write('\n')
    print('\nReport: reports/markdown-line-classes.json')


if __name__ == '__main__':
    main()
