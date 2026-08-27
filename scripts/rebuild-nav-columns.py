"""
rebuild-nav-columns.py

Rebuilds combined navigation page Text from Minneapolis Contents column data.
Generates semantic linear text with explicit delimiters:
  - <!-- RIGHT COLUMN --> for the second section
  - <!-- COLUMN N --> for third and later sections

Run from repo root:
  python scripts/rebuild-nav-columns.py
"""

import json
import os
import re


with open('stations/618-Minneapolis/MinneapolisOMJSON.json', encoding='utf-8') as f:
    mpls_data = json.load(f)

with open('stations/001-TestStation/TestStationOMJSON.json', encoding='utf-8') as f:
    ts_data = json.load(f)

ts_menus = ts_data['menus']


# Complex or intentionally custom pages to keep manual for now.
SKIP_MPLS_NAMES = {
    'ORZID2 GMENU ABX INPT MAIN',
    'ORZID2 GMENU SURG PROPHYLAXIS DOSES AND REDOSING',
    'ORZID3 GMENU ABX HEPB VACCINE INFORMATION OLD PAGE',
    'ORZID2 GMENU ABX INPT MAIN',
    'ORZID3 GMENU ABX OUTPT MAIN',
    'ORZID GMENU ER/UC EMERGENCY DEPARTMENT MAIN MENU',
}


def normalize_ref(value):
    return (value or '').strip().upper()


def vista_to_slug(item_name):
    s = item_name.lower()
    s = re.sub(r"[/\\()',.]", '-', s)
    s = re.sub(r'[^a-z0-9\-]', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def normalize_link_label(text):
    value = (text or '').strip()
    match = re.match(r'^\[(.*)\]$', value)
    if match:
        return match.group(1).strip()
    return value


def delimiter_for_column_start(column_index):
    if column_index == 2:
        return '<!-- RIGHT COLUMN -->'
    return '<!-- COLUMN %d -->' % column_index


def extract_trailing(existing_text):
    # Preserve manually-maintained trailing guidance sections where present.
    match = re.search(r'\n## (Outpatient|ERUC|ER-UC|ER/UC)\b', existing_text or '')
    if match:
        return existing_text[match.start():].strip()
    return ''


def find_cms_path(slug):
    base = 'cms-data/001-TestStation/pages'
    if not os.path.isdir(base):
        return None
    for group in os.listdir(base):
        path = os.path.join(base, group, slug + '.json')
        if os.path.exists(path):
            return path
    return None


# Mapping of any known source ref (Inpt/Outpt/ERUC) to combined page object and slug.
ref_to_combined = {}
ref_to_slug = {}
slug_name_regex = re.compile(r'^[a-z0-9][a-z0-9\-]*$')
for menu in ts_menus:
    if not isinstance(menu, dict):
        continue
    slug = menu.get('Name')
    if not slug:
        continue
    if not slug_name_regex.match(slug):
        continue

    for ref_key in ('Inpt', 'Outpt', 'ERUC'):
        ref_value = normalize_ref(menu.get(ref_key))
        if ref_value:
            ref_to_combined[ref_value] = menu
            ref_to_slug[ref_value] = slug


def render_entry(entry, page_problems):
    text = (entry.get('Text') or '').strip()
    if not text:
        return None

    vista_item = (entry.get('Item') or '').strip()
    is_header = bool(entry.get('Header'))

    if vista_item:
        lookup = normalize_ref(vista_item)
        slug = ref_to_slug.get(lookup)
        if not slug:
            slug = vista_to_slug(vista_item)
            page_problems.append('No combined slug for item: %s (using %s)' % (vista_item, slug))

        label = normalize_link_label(text)
        if not label:
            label = vista_item
        return '[%s](%s)' % (label, slug)

    if is_header:
        return '## ' + text

    return text


updated = []
skipped = []
problems = []

for mpls_menu in mpls_data:
    if not isinstance(mpls_menu, dict) or 'Contents' not in mpls_menu:
        continue

    mpls_name = (mpls_menu.get('Name') or '').strip()
    if not mpls_name:
        continue

    if normalize_ref(mpls_name) in SKIP_MPLS_NAMES:
        skipped.append((mpls_name, 'explicitly excluded (custom/complex)'))
        continue

    contents = [c for c in mpls_menu.get('Contents', []) if isinstance(c, dict)]
    column_numbers = sorted({c.get('Column') for c in contents if isinstance(c.get('Column'), int)})
    if len(column_numbers) <= 1:
        continue

    combined = ref_to_combined.get(normalize_ref(mpls_name))
    if not combined:
        skipped.append((mpls_name, 'no combined equivalent in TestStation'))
        continue

    slug = combined['Name']
    entries_by_column = {}
    for col in column_numbers:
        entries_by_column[col] = sorted(
            [e for e in contents if e.get('Column') == col],
            key=lambda x: x.get('Row', 0)
        )

    # Locate and remove top banner (first header containing ++).
    banner_text = None
    banner_row = None
    for col in column_numbers:
        for entry in entries_by_column[col]:
            text = (entry.get('Text') or '').strip()
            if entry.get('Header') and '++' in text:
                inner = text.strip('+').strip()
                banner_text = '## ++ %s ++' % inner
                banner_row = (col, entry.get('Row'))
                break
        if banner_text:
            break

    page_problems = []
    lines = []

    if banner_text:
        lines.append(banner_text)

    for idx, col in enumerate(column_numbers):
        for entry in entries_by_column[col]:
            if banner_row and col == banner_row[0] and entry.get('Row') == banner_row[1]:
                continue
            rendered = render_entry(entry, page_problems)
            if rendered:
                lines.append(rendered)

        if idx < len(column_numbers) - 1:
            lines.append(delimiter_for_column_start(idx + 2))

    trailing = extract_trailing(combined.get('Text', ''))
    if trailing:
        lines.append(trailing)

    new_text = '\n'.join(lines)
    combined['Text'] = new_text

    cms_path = find_cms_path(slug)
    if cms_path:
        with open(cms_path, encoding='utf-8') as f:
            cms_data = json.load(f)
        cms_data['Text'] = new_text
        with open(cms_path, 'w', encoding='utf-8') as f:
            json.dump(cms_data, f, ensure_ascii=False, indent=2)
        cms_status = 'CMS updated: %s' % cms_path
    else:
        cms_status = 'CMS JSON not found (OMJSON updated only)'

    updated.append((mpls_name, slug, len(column_numbers), cms_status))
    if page_problems:
        problems.append((mpls_name, slug, page_problems))


with open('stations/001-TestStation/TestStationOMJSON.json', 'w', encoding='utf-8') as f:
    json.dump(ts_data, f, ensure_ascii=False, indent=2)


print('=' * 70)
print('UPDATED PAGES (%d)' % len(updated))
print('=' * 70)
for mpls_name, slug, col_count, cms_status in updated:
    print('  Minneapolis: %s' % mpls_name)
    print('  TestStation: %s' % slug)
    print('  Columns: %d' % col_count)
    print('  %s' % cms_status)
    print()

print('=' * 70)
print('SKIPPED PAGES (%d)' % len(skipped))
print('=' * 70)
for mpls_name, reason in skipped:
    print('  %s' % mpls_name)
    print('    Reason: %s' % reason)
    print()

print('=' * 70)
print('SLUG MAPPING PROBLEMS (%d pages)' % len(problems))
print('=' * 70)
for mpls_name, slug, page_probs in problems:
    print('  %s => %s' % (mpls_name, slug))
    for problem in page_probs:
        print('    ! %s' % problem)
    print()
