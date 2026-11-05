"""Phase 2 of the markdown migration: convert Text/Therapy to Sveltia-style markdown (dry run by default).

    python scripts/convert-markdown.py                         # dry run, test station
    python scripts/convert-markdown.py --show <PageID> [--field Therapy]
    python scripts/convert-markdown.py --apply                 # write cms-data changes
    python scripts/convert-markdown.py --station 541-Cleveland ...

What it does (decisions from the phase 1 review):
  - removes leading > / >> blockquote markers
  - joins wrapped lines into one paragraph (a hyphen-ended line joins without a space)
  - merges headings that were split over several lines
  - "-Item" lines become "- Item" bullets
  - separator lines (## ____, **____**) become ---
  - the lines after "References:" become a bullet list
  - lists are tight; blocks are separated by one blank line; stacked lines keep a single newline
Skipped (left for manual conversion): column pages, nav pages, flattened-table pages, main-menu.
Each field's words and link targets are verified unchanged; a field that fails is not written.
Then run: compile-cms.py, audit-teststation.py, node scripts/render-check.js, node scripts/nav-snapshot.js
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.line_classes import TERMINAL, classify, line_class, page_flags, pair_kind  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ('Text', 'Therapy')
SKIP_PAGES = {'main-menu', 'inpt-main'}
REFERENCES_RE = re.compile(r'^(?:#{1,6}\s*)?\**references?\**:?\s*$', re.I)
LIST_CLASSES = ('list-bullet', 'list-number', 'pseudo-bullet')
TOKEN_RE = re.compile(r'[A-Za-z0-9]+')


def strip_heading_marks(text):
    return re.sub(r'^#{1,6}\s*', '', text).strip()


def build_blocks(text, notes):
    """Parse into blocks: {cls, text, last, blank_before}; joins wraps and heading continuations."""
    lines, _ = classify(text)
    blocks = []
    gap = 0
    in_refs = False
    for ln in lines:
        if ln['quote']:
            notes['blockquote'].append(ln['n'])
        if ln['blank']:
            gap += 1
            continue
        body = ln['text'].rstrip()
        cls = ln['cls']
        if cls == 'code':
            blocks.append({'cls': 'code', 'text': body, 'last': body, 'blank_before': False, 'raw': True})
            gap = 0
            continue
        body = body.strip() if cls != 'code' else body
        if cls == 'pseudo-bullet':
            notes['pseudo_bullet'].append(ln['n'])
            body = '- ' + body.lstrip()[1:].strip()
            cls = 'list-bullet'
        if cls == 'separator':
            body = '---'
        if cls == 'heading' and strip_heading_marks(body).startswith('-'):
            notes['heading_bullet'].append(ln['n'])

        prev = blocks[-1] if blocks else None
        if prev is not None and not prev.get('raw'):
            if in_refs and cls in ('text', 'link-only', 'label'):
                kind = 'wrap' if (body[:1].islower() and not prev['last'].endswith(('.', ':'))) else ('break' if gap else 'stack')
                if kind != 'wrap' and len(prev['last'].replace('- ', '', 1)) >= 74 and not prev['last'].endswith(TERMINAL):
                    notes['refs_suspect'].append(ln['n'])
            else:
                kind = pair_kind(prev['last'], body, prev['cls'], cls, gap)
            if kind in ('wrap', 'wrap-after-paren'):
                glue = '' if prev['last'].endswith('-') and body[:1].islower() else ' '
                prev['text'] = prev['text'] + glue + body
                prev['last'] = body
                gap = 0
                continue
            if kind == 'heading-continuation':
                prev['text'] = prev['text'] + ' ' + strip_heading_marks(body)
                prev['last'] = prev['text']
                notes['heading_merge'] += 1
                gap = 0
                continue
            if kind == 'wrap-into-link':
                notes['wrap_into_link'].append(ln['n'] - 1)

        if cls == 'heading' and REFERENCES_RE.match(body) or (cls in ('label', 'text') and REFERENCES_RE.match(body)):
            in_refs = True
        elif in_refs and cls in ('heading', 'separator'):
            in_refs = False
        elif in_refs and cls in ('text', 'link-only', 'label') and not REFERENCES_RE.match(body):
            cls = 'list-bullet'
            body = '- ' + body
            notes['reference_items'] += 1

        blocks.append({'cls': cls, 'text': body, 'last': body, 'blank_before': gap > 0, 'raw': False})
        gap = 0
    return blocks


def render(blocks):
    out = []
    prev = None
    for b in blocks:
        if prev is not None:
            both_list = b['cls'] in LIST_CLASSES and prev['cls'] in LIST_CLASSES
            structural = {'heading', 'separator'}
            sep = '\n'
            if both_list:
                sep = '\n'
            elif (b['blank_before'] or b['cls'] in structural or prev['cls'] in structural
                  or (b['cls'] in LIST_CLASSES) != (prev['cls'] in LIST_CLASSES)
                  or prev['text'].startswith('- ') and prev['cls'] == 'list-bullet'):
                sep = '\n\n'
            out.append(sep)
        out.append(b['text'])
        prev = b
    return ''.join(out)


def tokens(text):
    return TOKEN_RE.findall(text)


def convert(text):
    notes = {'blockquote': [], 'pseudo_bullet': [], 'heading_bullet': [], 'wrap_into_link': [], 'refs_suspect': [],
             'heading_merge': 0, 'reference_items': 0}
    return render(build_blocks(text, notes)), notes


def skip_reason(page_id, text):
    if page_id in SKIP_PAGES:
        return 'main-menu'
    flags = page_flags(text)
    if 'column-page' in flags:
        return 'column-page'
    if 'nav-page' in flags:
        return 'nav-page'
    types = [line_class(l) for l in text.split('\n') if l.strip()]
    run = max_run = 0
    for t in types:
        run = run + 1 if t == 'heading' else 0
        max_run = max(max_run, run)
    if max_run >= 4:
        return 'flattened-table'
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--station', default='001-TestStation')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--show')
    ap.add_argument('--field', default='Text')
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(ROOT, 'cms-data', args.station, 'pages', '**', '*.json'), recursive=True))
    changed = failed = unchanged = 0
    skipped = {}
    review = {'wrap_into_link': [], 'pseudo_bullet': [], 'heading_bullet': [], 'blockquote': [], 'refs_suspect': [], 'failed': []}
    totals = {'heading_merge': 0, 'reference_items': 0}

    for path in paths:
        page_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        dirty = False
        for field in FIELDS:
            text = data.get(field)
            if not isinstance(text, str) or not text.strip():
                continue
            key = f'{page_id}:{field}'
            reason = skip_reason(page_id, text)
            if reason:
                skipped.setdefault(reason, []).append(key)
                continue
            new, notes = convert(text)
            if args.show == page_id and args.field == field:
                print(new)
                return
            if tokens(new) != tokens(text):
                failed += 1
                review['failed'].append(key)
                continue
            for k in ('wrap_into_link', 'pseudo_bullet', 'heading_bullet', 'blockquote', 'refs_suspect'):
                if notes[k]:
                    review[k].append((key, notes[k]))
            totals['heading_merge'] += notes['heading_merge']
            totals['reference_items'] += notes['reference_items']
            if new == text:
                unchanged += 1
                continue
            changed += 1
            data[field] = new
            dirty = True
        if dirty and args.apply:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write('\n')

    mode = 'APPLIED' if args.apply else 'dry run'
    print(f'{args.station} ({mode}): {changed} fields changed, {unchanged} already clean, {failed} failed verification')
    print(f'  headings merged: {totals["heading_merge"]}, reference items bulleted: {totals["reference_items"]}')
    for reason, keys in skipped.items():
        print(f'  skipped {reason}: {len(keys)} fields')

    with open(os.path.join(ROOT, 'reports', 'markdown-migration-review.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'Markdown migration review list ({args.station}, {mode})\n\n')
        sections = (
            ('wrap_into_link', 'Text line left unjoined from the link line below it (check: wrap or separate items?)'),
            ('pseudo_bullet', '"-Item" lines converted to "- Item" bullets (source line numbers)'),
            ('heading_bullet', 'Headings whose text starts with "-" (flattened bullets; convert by hand)'),
            ('blockquote', '">" markers removed (indentation lost; update by hand later)'),
            ('refs_suspect', 'Reference lines that may be one entry wrapped over two lines (converted to separate bullets; source line numbers)'),
        )
        for key, title in sections:
            f.write(f'== {title}: {len(review[key])} fields\n')
            for page_key, nums in review[key]:
                f.write(f'  {page_key}  lines {", ".join(map(str, nums))}\n')
            f.write('\n')
        f.write(f'== Failed word-for-word verification (not written): {len(review["failed"])}\n')
        for k in review['failed']:
            f.write(f'  {k}\n')
        f.write('\n')
        for reason, keys in skipped.items():
            f.write(f'== Skipped ({reason}): {len(keys)} fields\n')
            for k in keys:
                f.write(f'  {k}\n')
            f.write('\n')
    print('Review list: reports/markdown-migration-review.txt')


if __name__ == '__main__':
    main()
