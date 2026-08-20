"""
fix-teststation-json.py

Fixes two issues in TestStationOMJSON.json:
1. Copies Outpt and ERUC cross-reference fields from MinneapolisOMJSON.json
2. Removes escaped bracket sequences (\[ \]) from Text fields that break link rendering
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).parent.parent
MPLS_PATH = ROOT / 'stations' / '618-Minneapolis' / 'MinneapolisOMJSON.json'
TEST_PATH = ROOT / 'stations' / '001-TestStation' / 'TestStationOMJSON.json'

# ── Load Minneapolis (list format) ───────────────────────────────────────────
with open(MPLS_PATH, encoding='utf-8') as f:
    mpls_list = json.load(f)
mpls_by_name = {m['Name']: m for m in mpls_list}

# ── Load TestStation (dict format) ───────────────────────────────────────────
with open(TEST_PATH, encoding='utf-8') as f:
    data = json.load(f)

outpt_added = 0
eruc_added = 0
links_fixed = 0

for m in data['menus']:
    name = m['Name']

    # ── Fix 1: Copy Outpt / ERUC from Minneapolis ─────────────────────────
    mpls = mpls_by_name.get(name)
    if mpls:
        if mpls.get('Outpt') and not m.get('Outpt'):
            m['Outpt'] = mpls['Outpt']
            outpt_added += 1
        if mpls.get('ERUC') and not m.get('ERUC'):
            m['ERUC'] = mpls['ERUC']
            eruc_added += 1

    # ── Fix 2: Remove \[ and \] escape sequences from Text fields ─────────
    text = m.get('Text', '')
    if r'\[' in text or r'\]' in text:
        # Remove backslash-escaped square brackets (\[ → [ , \] → ])
        # These break the markdown link regex in appendRichTextLineContent
        cleaned = text.replace(r'\[', '').replace(r'\]', '')
        m['Text'] = cleaned
        links_fixed += 1

print(f'Outpt fields added : {outpt_added}')
print(f'ERUC fields added  : {eruc_added}')
print(f'Text fields fixed  : {links_fixed}')

with open(TEST_PATH, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print('Saved.')
