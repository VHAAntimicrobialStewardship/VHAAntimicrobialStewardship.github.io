"""Remove hard-wrap blank lines from Text and Therapy in the four CMS stations.

Legacy VistA text was fixed-width; conversion put a blank line after every
wrapped line. A blank line is removed only when the next line clearly continues
the previous one (starts lowercase and the previous line has no terminal
punctuation). Heading continuations ("# ...F" / "# and G ...") are merged into
one heading. Pages with column delimiters are skipped.

Usage:
    python scripts/fix-extra-linebreaks.py            # dry run, per-page counts
    python scripts/fix-extra-linebreaks.py --show <PageID>
    python scripts/fix-extra-linebreaks.py --apply
Then run compile-cms.py and audit-teststation.py.
"""
import glob
import json
import os
import re
import sys

STATIONS = ['001-TestStation', '506-AnnArbor', '539-Cincinnati', '541-Cleveland']
FIELDS = ('Text', 'Therapy')
HEADING = re.compile(r'^(#{1,6})\s+(.*)$')
TERMINAL = ('.', '!', '?', ':', ';', '"', ')', '\u201d', ']')
STRUCTURAL = re.compile(r'^(#{1,6}\s|---+|\*\*\*+|___+|!\[|```|>)')


def fix(text):
    lines = text.split('\n')
    out = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('```'):
            in_fence = not in_fence
        if (not in_fence and line.strip() == '' and out and out[-1].strip()
                and i + 1 < len(lines) and lines[i + 1].strip()):
            prev, nxt = out[-1], lines[i + 1]
            ph, nh = HEADING.match(prev), HEADING.match(nxt)
            if ph and nh and (nh.group(2)[:1].islower() or nh.group(2)[:1] == '(') \
                    and not prev.rstrip().endswith(TERMINAL) and not set(prev) <= set('#_ '):
                out[-1] = prev.rstrip() + ' ' + nh.group(2)
                i += 2
                continue
            if not ph and not STRUCTURAL.match(prev.strip()) and not STRUCTURAL.match(nxt.strip()):
                lower = nxt.strip()[:1].islower()
                open_end = not prev.rstrip().endswith(TERMINAL)
                # A full-width line with no sentence end followed by a short sentence-ending line is a wrap.
                short_tail = (len(nxt.strip()) <= 40 and nxt.rstrip().endswith('.')
                              and (i + 2 >= len(lines) or not lines[i + 2].strip()))
                if (lower and (open_end or prev.rstrip().endswith(')'))) or \
                        (open_end and len(prev.strip()) >= 60 and short_tail):
                    i += 1
                    continue
        out.append(line)
        i += 1
    return '\n'.join(out)


def main():
    apply = '--apply' in sys.argv
    show = sys.argv[sys.argv.index('--show') + 1] if '--show' in sys.argv else None
    total_pages = total_blank = 0
    for st in STATIONS:
        for p in sorted(glob.glob(f'cms-data/{st}/pages/**/*.json', recursive=True)):
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
            changed = False
            for fld in FIELDS:
                t = data.get(fld)
                if not isinstance(t, str) or '<!-- COLUMN' in t or '<!-- RIGHT COLUMN' in t:
                    continue
                new = fix(t)
                if new != t:
                    removed = t.count('\n') - new.count('\n')
                    total_blank += removed
                    changed = True
                    data[fld] = new
                    if show and os.path.splitext(os.path.basename(p))[0] == show:
                        print(f'--- {fld} ---\n{new}')
                    elif not show:
                        print(f'{removed:3d} {fld:7s} {p}')
            if changed:
                total_pages += 1
                if apply:
                    with open(p, 'w', encoding='utf-8', newline='\n') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                        f.write('\n')
    print(f'{total_pages} pages, {total_blank} line breaks removed' + ('' if apply else ' (dry run)'))


if __name__ == '__main__':
    main()
