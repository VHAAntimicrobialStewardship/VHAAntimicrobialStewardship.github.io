"""Line classification for the markdown migration (phase 1).

classify(text) labels each non-blank line and each adjacent-line relationship so the
conversion script (phase 2) and the dry-run report agree on what a line is.
"""
import re

TERMINAL = ('.', '!', '?', ':', ';', '"', '\u201d', ']', ')')
WRAP_MIN_WIDTH = 55  # VistA text was wrapped near 75-80 columns

HEADING_RE = re.compile(r'^#{1,6}\s+\S')
SEPARATOR_RES = (
    re.compile(r'^#{1,6}\s*[_\-=\s]{5,}$'),
    re.compile(r'^\*{0,2}[_\-=]{5,}\*{0,2}$'),
    re.compile(r'^(\*{3,}|-{3,}|_{3,})$'),
)
COMMENT_RE = re.compile(r'^<!--.*-->$')
TABLE_ROW_RE = re.compile(r'^\|.*\|$')
BULLET_RE = re.compile(r'^\s*[-*+]\s+\S')
PSEUDO_BULLET_RE = re.compile(r'^\s*-[^\s\-]')
NUMBER_RE = re.compile(r'^\s*\d{1,3}[.)]\s+\S')
LINK_LINE_RE = re.compile(r'^\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)\)[.,;:]?$')
CONNECTOR_RE = re.compile(r'^<\s*(?:OR|AND)\s*>$', re.I)
BOLD_ONLY_RE = re.compile(r'^\*\*[^*]+\*\*:?$')
QUOTE_PREFIX_RE = re.compile(r'^(?:\s{0,3}>\s?)+')
COLUMN_GAP_RE = re.compile(r'\S {3,}\S')
LEADING_INDENT_RE = re.compile(r'^( {2,}|\t)\S')


def line_class(line):
    """Class of one stripped-of-quote-markers line."""
    s = line.strip()
    if COMMENT_RE.match(s):
        return 'comment'
    if any(r.match(s) for r in SEPARATOR_RES):
        return 'separator'
    if HEADING_RE.match(s):
        return 'heading'
    if TABLE_ROW_RE.match(s):
        return 'table-row'
    if CONNECTOR_RE.match(s):
        return 'connector'
    if LINK_LINE_RE.match(s):
        return 'link-only'
    if BULLET_RE.match(line):
        return 'list-bullet'
    if PSEUDO_BULLET_RE.match(line):
        return 'pseudo-bullet'
    if NUMBER_RE.match(line):
        return 'list-number'
    if BOLD_ONLY_RE.match(s):
        return 'label'
    if s.endswith(':') and len(s) <= 80:
        return 'label'
    return 'text'


def pair_kind(prev, nxt, prev_cls, next_cls, gap):
    """Relationship between two consecutive non-blank lines (gap = blank lines between)."""
    p, n = prev.rstrip(), nxt.strip()
    if not n:
        return 'none'
    if prev_cls in ('text', 'list-bullet', 'list-number', 'pseudo-bullet') and (
            next_cls == 'text' or (next_cls == 'label' and n[:1].islower())):
        terminal = p.endswith(TERMINAL)
        lower = n[:1].islower()
        if p.endswith('-') and lower:
            return 'wrap'
        if not terminal and (lower or len(p.strip()) >= WRAP_MIN_WIDTH):
            return 'wrap'
        if lower and p.endswith(')'):
            return 'wrap-after-paren'
        if not terminal:
            return 'unterminated-stack'
    if prev_cls == 'text' and next_cls == 'link-only' and not p.endswith(TERMINAL):
        return 'wrap-into-link'
    if prev_cls == 'heading' and next_cls == 'heading' and (n.lstrip('# ')[:1].islower() or n.lstrip('# ')[:1] == '('):
        return 'heading-continuation'
    return 'break' if gap else 'stack'


def classify(text):
    """Returns (lines, pairs, summary).

    lines: [{n, text, cls, quote, indented, in_fence}]
    pairs: [{n, gap, kind}]   n is the line number of the first line of the pair
    """
    lines = []
    in_fence = False
    for i, raw in enumerate(text.split('\n'), 1):
        if raw.strip().startswith('```'):
            in_fence = not in_fence
            lines.append({'n': i, 'text': raw, 'cls': 'code', 'quote': False, 'indented': False, 'blank': False})
            continue
        if in_fence:
            lines.append({'n': i, 'text': raw, 'cls': 'code', 'quote': False, 'indented': False, 'blank': False})
            continue
        quote = bool(QUOTE_PREFIX_RE.match(raw))
        body = QUOTE_PREFIX_RE.sub('', raw) if quote else raw
        blank = body.strip() == ''
        lines.append({
            'n': i, 'text': body, 'cls': 'blank' if blank else line_class(body),
            'quote': quote, 'indented': bool(LEADING_INDENT_RE.match(body)), 'blank': blank,
        })

    pairs = []
    last = None
    gap = 0
    for ln in lines:
        if ln['blank']:
            gap += 1
            continue
        if last is not None and ln['cls'] != 'code' and last['cls'] != 'code':
            pairs.append({
                'n': last['n'], 'gap': gap,
                'kind': pair_kind(last['text'], ln['text'], last['cls'], ln['cls'], gap),
            })
        last = ln
        gap = 0
    return lines, pairs


def page_flags(text):
    """Whole-page flags that decide whether a page needs manual handling."""
    flags = []
    if re.search(r'<!--\s*(?:RIGHT )?COLUMN', text, re.I):
        flags.append('column-page')
    non_blank = [l.strip() for l in text.split('\n') if l.strip()]
    types = [line_class(l) for l in non_blank]
    run = max_run = 0
    for t in types:
        run = run + 1 if t == 'heading' else 0
        max_run = max(max_run, run)
    transitions = sum(1 for a, b in zip(types, types[1:]) if a == 'heading' and b == 'heading')
    if max_run >= 4 or transitions >= 3:
        flags.append('flattened-table')
    gap_lines = sum(1 for l in text.split('\n') if COLUMN_GAP_RE.search(l))
    if gap_lines >= 3:
        flags.append('aligned-columns')
    link_lines = sum(1 for t in types if t == 'link-only')
    others = [t for t in types if t not in ('heading', 'comment', 'separator')]
    if link_lines >= 2 and others and link_lines / len(others) >= 0.5:
        flags.append('nav-page')
    return flags
