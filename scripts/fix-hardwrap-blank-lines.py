"""Fix spurious mid-paragraph blank lines in cms-data page Text fields.

Root cause: some legacy-converted pages have a blank line (\n\n) inserted after
EVERY hard-wrapped line of the original fixed-width VistA text, instead of only
at real paragraph/section breaks. Since the live-site renderer
(createRichTextTable in TestStationCDSS.html) puts one physical line per table
row and renders a blank line as an empty spacer row, this makes affected pages
look "double-spaced" throughout (see cms-notes.md for full analysis).

This script removes only the spurious blank lines (mid-sentence/mid-item wraps)
while preserving the underlying line-wrap structure and genuine paragraph/list/
heading boundaries, so the result matches the site's normal formatting
convention (e.g. bells-palsy.json).

Usage:
    python scripts/fix-hardwrap-blank-lines.py preview <page.json>
    python scripts/fix-hardwrap-blank-lines.py apply <page.json> [<page2.json> ...]
    python scripts/fix-hardwrap-blank-lines.py scan   (report affected pages, no changes)
"""
import json
import re
import sys
import glob

HEADING_RE = re.compile(r'^#{1,6}\s+')
LIST_RE = re.compile(r'^[-*+]\s+')
OLIST_RE = re.compile(r'^\d+\.\s+')
QUOTE_RE = re.compile(r'^>\s+')
HR_RE = re.compile(r'^(---+|\*\*\*+|___+)\s*$')
FENCE_RE = re.compile(r'^```')
IMAGE_RE = re.compile(r'^!\[')
COMPARISON_START_RE = re.compile(r'^[<>]\s*/?=?\d')
PSEUDO_LIST_RE = re.compile(r'^\*(?!\*)\S')

TERMINAL_ENDINGS = ('.', '!', '?', ':', ';', '"', ')', '\u201d', ']')


def classify(line):
    if line is None:
        return 'blank'
    s = line.strip()
    if s == '':
        return 'blank'
    if FENCE_RE.match(s):
        return 'fence'
    if HEADING_RE.match(s):
        return 'heading'
    if HR_RE.match(s):
        return 'hr'
    if IMAGE_RE.match(s):
        return 'image'
    if COMPARISON_START_RE.match(s):
        return 'prose'
    if QUOTE_RE.match(s):
        return 'quote'
    if LIST_RE.match(s):
        return 'list'
    if OLIST_RE.match(s):
        return 'list'
    if PSEUDO_LIST_RE.match(s):
        return 'list'
    return 'prose'


def reflow(text):
    lines = text.split('\n')
    result = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == '':
            prev = result[-1] if result else None
            nxt = lines[i + 1] if i + 1 < n else None
            prev_type = classify(prev)
            next_type = classify(nxt)
            prev_stripped = (prev or '').rstrip()

            handled = False
            if prev is not None and nxt is not None:
                if (
                    prev_type in ('prose', 'list', 'quote')
                    and next_type == 'prose'
                    and not prev_stripped.endswith(TERMINAL_ENDINGS)
                ):
                    # Blank line is a hard-wrap artifact mid-paragraph/mid-item;
                    # drop the blank line but keep both lines distinct (matches
                    # the site's normal single-newline paragraph convention).
                    i += 1
                    handled = True

            if not handled:
                result.append('')
                i += 1
            continue
        else:
            result.append(line)
            i += 1
    return '\n'.join(result)


def scan():
    pages = glob.glob('cms-data/001-TestStation/pages/**/*.json', recursive=True)
    affected = []
    for p in pages:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        text = data.get('Text', '')
        if not isinstance(text, str):
            continue
        lines = text.split('\n')
        bad = 0
        for i in range(len(lines) - 2):
            if lines[i].strip() == '':
                continue
            if lines[i + 1].strip() == '':
                nxt = lines[i + 2] if i + 2 < len(lines) else ''
                prev = lines[i]
                if nxt.strip() and nxt.strip()[0].islower() and not prev.rstrip().endswith((':', ')', ']')):
                    bad += 1
        if bad > 3:
            affected.append((p, bad))
    affected.sort(key=lambda x: -x[1])
    print(len(affected), "affected pages")
    for p, bad in affected:
        print(bad, p)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'preview'
    if mode == 'scan':
        scan()
        sys.exit(0)

    paths = sys.argv[2:]
    for path in paths:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        old_text = data['Text']
        new_text = reflow(old_text)
        if mode == 'preview':
            print('=====', path, '=====')
            print(new_text)
            print()
        elif mode == 'apply':
            data['Text'] = new_text
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write('\n')
            print('applied to', path)
