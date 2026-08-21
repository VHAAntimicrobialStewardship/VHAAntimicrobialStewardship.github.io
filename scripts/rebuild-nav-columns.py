"""
rebuild-nav-columns.py

Rebuilds the Text field of TestStation combined navigation pages that correspond
to multi-column Minneapolis OMJSON pages. Uses the Minneapolis Column 1 / Column 2
structure to produce semantically correct content with a <!-- RIGHT COLUMN --> delimiter.

Run from the repo root:
    python scripts/rebuild-nav-columns.py
"""

import json
import re
import os

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
with open('stations/618-Minneapolis/MinneapolisOMJSON.json', encoding='utf-8') as f:
    mpls_data = json.load(f)

with open('stations/001-TestStation/TestStationOMJSON.json', encoding='utf-8') as f:
    ts_data = json.load(f)

ts_menus = ts_data['menus']

# ---------------------------------------------------------------------------
# Build mappings
# ---------------------------------------------------------------------------

# VistA inpatient item name (upper) → TestStation combined slug
inpt_to_slug: dict[str, str] = {}
for m in ts_menus:
    if isinstance(m, dict) and m.get('Inpt'):
        inpt_to_slug[m['Inpt'].strip().upper()] = m['Name']

# Minneapolis page name (upper) → TestStation combined page object
mpls_name_to_combined: dict[str, dict] = {}
for m in ts_menus:
    if isinstance(m, dict) and m.get('Inpt'):
        mpls_name_to_combined[m['Inpt'].strip().upper()] = m

# ---------------------------------------------------------------------------
# Pages to SKIP (custom content or complex table — not nav pages)
# ---------------------------------------------------------------------------
SKIP_MPLS_NAMES = {
    # TestStation main-menu is entirely custom; bears no resemblance to Mpls layout
    'ORZID2 GMENU ABX INPT MAIN',
    # Surgical dosing reference table — complex column-as-data format
    'ORZID2 GMENU SURG PROPHYLAXIS DOSES AND REDOSING',
    # Old vaccine info page — 172 lines of custom formatted content
    'ORZID3 GMENU ABX HEPB VACCINE INFORMATION OLD PAGE',
    # CNS already fixed manually
    'ORZID2 GMENU ABX CNS',
}

# ---------------------------------------------------------------------------
# Helper: convert VistA item name to slug (fallback when no combined page)
# ---------------------------------------------------------------------------
def vista_to_slug(item_name: str) -> str:
    s = item_name.lower()
    s = re.sub(r"[/\\()',.]", '-', s)
    s = re.sub(r'[^a-z0-9\-]', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')

# ---------------------------------------------------------------------------
# Helper: render one Contents entry as a markdown line
# ---------------------------------------------------------------------------
def render_entry(entry: dict, page_problems: list) -> str:
    text = entry.get('Text', '').strip()
    is_header = bool(entry.get('Header'))
    vista_item = entry.get('Item', '').strip()

    if vista_item:
        slug = inpt_to_slug.get(vista_item.upper())
        if not slug:
            slug = vista_to_slug(vista_item)
            page_problems.append('No combined slug for item: %s  (using VistA slug: %s)' % (vista_item, slug))
        return '[%s](%s)' % (text, slug)
    elif is_header:
        # ++ BANNER ++ items are handled separately; non-banner headers get ##
        return '## ' + text
    else:
        return text

# ---------------------------------------------------------------------------
# Helper: extract trailing outpatient/ERUC section from existing combined text
# (preserves sections the SMEs may have added that aren't in Minneapolis)
# ---------------------------------------------------------------------------
def extract_trailing(existing_text: str) -> str:
    # Only match standalone ## Outpatient or ## ERUC/ER-UC, not ## Inpatient/Outpatient
    match = re.search(r'\n## (Outpatient|ERUC|ER-UC|ER/UC)\b', existing_text)
    if match:
        return existing_text[match.start():].strip()
    return ''

# ---------------------------------------------------------------------------
# Helper: find a page's CMS JSON file
# ---------------------------------------------------------------------------
def find_cms_path(slug: str) -> str | None:
    base = 'cms-data/001-TestStation/pages'
    for group in os.listdir(base):
        path = os.path.join(base, group, slug + '.json')
        if os.path.exists(path):
            return path
    return None

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
updated = []
skipped = []
problems = []

for mpls_menu in mpls_data:
    if not isinstance(mpls_menu, dict) or 'Contents' not in mpls_menu:
        continue

    contents = mpls_menu['Contents']
    if not any(c.get('Column') == 2 for c in contents):
        continue  # single-column page, skip

    mpls_name = mpls_menu['Name']

    # Skip pages explicitly excluded
    if mpls_name.upper() in SKIP_MPLS_NAMES:
        skipped.append((mpls_name, 'explicitly excluded (custom content / already fixed)'))
        continue

    # Find corresponding TestStation combined page
    combined = mpls_name_to_combined.get(mpls_name.upper())
    if not combined:
        skipped.append((mpls_name, 'no combined equivalent in TestStation'))
        continue

    slug = combined['Name']

    # Sort contents by column, then row
    col1 = sorted([c for c in contents if c.get('Column') == 1], key=lambda x: x['Row'])
    col2 = sorted([c for c in contents if c.get('Column') == 2], key=lambda x: x['Row'])

    # Identify the banner (++ ... ++ Header in col1)
    banner = None
    col1_body = []
    for entry in col1:
        text = entry.get('Text', '').strip()
        if entry.get('Header') and '++' in text and banner is None:
            # Normalise to ## ++ TEXT ++
            inner = text.strip('+').strip()
            banner = '## ++ %s ++' % inner
        else:
            col1_body.append(entry)

    page_problems: list[str] = []
    lines: list[str] = []

    # Banner
    if banner:
        lines.append(banner)

    # Column 1 body (skip entries with no text)
    for entry in col1_body:
        if not entry.get('Text', '').strip():
            continue
        lines.append(render_entry(entry, page_problems))

    # Column delimiter
    lines.append('<!-- RIGHT COLUMN -->')

    # Column 2 body (skip entries with no text)
    for entry in col2:
        if not entry.get('Text', '').strip():
            continue
        lines.append(render_entry(entry, page_problems))

    # Preserve any existing trailing outpatient/ERUC section
    trailing = extract_trailing(combined.get('Text', ''))
    if trailing:
        lines.append(trailing)

    new_text = '\n'.join(lines)

    # Update OMJSON in-place
    combined['Text'] = new_text

    # Update CMS JSON if it exists
    cms_path = find_cms_path(slug)
    if cms_path:
        with open(cms_path, encoding='utf-8') as f:
            cms = json.load(f)
        cms['Text'] = new_text
        with open(cms_path, 'w', encoding='utf-8') as f:
            json.dump(cms, f, ensure_ascii=False, indent=2)
        cms_status = 'CMS updated: %s' % cms_path
    else:
        cms_status = 'CMS JSON not found (OMJSON updated only)'

    updated.append((mpls_name, slug, cms_status))
    if page_problems:
        problems.append((mpls_name, slug, page_problems))

# Write updated OMJSON
with open('stations/001-TestStation/TestStationOMJSON.json', 'w', encoding='utf-8') as f:
    json.dump(ts_data, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
print('=' * 70)
print('UPDATED PAGES (%d)' % len(updated))
print('=' * 70)
for mpls_name, slug, cms_status in updated:
    print('  Minneapolis: %s' % mpls_name)
    print('  TestStation: %s' % slug)
    print('  %s' % cms_status)
    print()

print('=' * 70)
print('SKIPPED PAGES (%d)' % len(skipped))
print('=' * 70)
for mpls_name, reason in skipped:
    print('  %s\n    Reason: %s' % (mpls_name, reason))
    print()

print('=' * 70)
print('SLUG MAPPING PROBLEMS (%d pages)' % len(problems))
print('=' * 70)
for mpls_name, slug, probs in problems:
    print('  %s => %s' % (mpls_name, slug))
    for p in probs:
        print('    ! %s' % p)
    print()
