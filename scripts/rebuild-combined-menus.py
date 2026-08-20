"""
rebuild-combined-menus.py

Rebuilds all ORZC combined menus in TestStationOMJSON.json from scratch,
merging guidance from BOTH spreadsheet tabs:
  Tab 1 (Minneapolis_SideBySideGuida) = Mimi's entries
  Tab 2 (Mehul) = Dr. Mehul's entries  -- takes precedence where both exist

Steps:
  1. Extract merged guidance from both tabs
  2. Remove all existing ORZC menus
  3. Remove Combined field from all inpatient menus
  4. Add fresh ORZC menus and Combined cross-refs
  5. Rebuild ORZC main menu from inpatient main menu structure
"""
import json, re, copy, os, openpyxl
from pathlib import Path

ROOT     = Path(__file__).parent.parent
XLSX     = ROOT / 'AntimicrobialStewardshipGuidanceCombined.xlsx'
TEST_PATH = ROOT / 'stations' / '001-TestStation' / 'TestStationOMJSON.json'

PLACEHOLDERS = {'', 'mehul', 'mahul', 'mimi'}

# ── 1. Extract guidance from both tabs ────────────────────────────────────────
def extract_tab(ws):
    headers = {str(ws.cell(1,c).value).strip(): c
               for c in range(1, ws.max_column+1) if ws.cell(1,c).value}
    if 'Combined Guidance' not in headers:
        return {}
    comb_col = headers['Combined Guidance']
    menu_col = headers['Source Menu Name (Inpatient)']
    result = {}
    for r in range(2, ws.max_row+1):
        menu = ws.cell(r, menu_col).value
        comb = ws.cell(r, comb_col).value
        if not menu or not comb:
            continue
        menu = str(menu).strip()
        comb = str(comb).strip()
        if comb.lower() in PLACEHOLDERS:
            continue
        result[menu] = comb
    return result

wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
mimi_data  = extract_tab(wb.worksheets[0])   # Tab 1 = Mimi
mehul_data = extract_tab(wb.worksheets[1])   # Tab 2 = Mehul (precedence)
guidance   = {**mimi_data, **mehul_data}

print(f'Mimi tab:  {len(mimi_data)} entries')
print(f'Mehul tab: {len(mehul_data)} entries')
print(f'Merged:    {len(guidance)} unique entries')

# ── 2. Load TestStation JSON ──────────────────────────────────────────────────
with open(TEST_PATH, encoding='utf-8') as f:
    data = json.load(f)

# Strip all existing ORZC menus and Combined fields
data['menus'] = [m for m in data['menus'] if not m['Name'].startswith('ORZC ')]
for m in data['menus']:
    m.pop('Combined', None)

print(f'Menus after stripping ORZC: {len(data["menus"])}')
inpt_by_name = {m['Name']: m for m in data['menus']}

# ── Helper: name conversion ───────────────────────────────────────────────────
def to_orzc(inpt_name):
    return re.sub(r'^ORZID2\s+', 'ORZC ', inpt_name)

# ── Helper: format combined text ──────────────────────────────────────────────
def format_combined(raw):
    text = raw.replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n{2,}', text)
    return '\n\n'.join(b.strip() for b in blocks if b.strip())

# ── 3. Build new ORZC menus and add Combined cross-refs ───────────────────────
new_menus = []
cross_refs = 0

for inpt_name, combined_text in guidance.items():
    orzc_name = to_orzc(inpt_name)
    combined_menu = {
        'Name': orzc_name,
        'Term1': '',
        'Term2': '',
        'Text': format_combined(combined_text),
        'LinkTargets': []
    }
    new_menus.append(combined_menu)
    if inpt_name in inpt_by_name:
        inpt_by_name[inpt_name]['Combined'] = orzc_name
        cross_refs += 1

print(f'ORZC menus created: {len(new_menus)}')
print(f'Combined cross-refs added: {cross_refs}')

data['menus'].extend(new_menus)

# ── 4. Rebuild ORZC main menu from inpatient main menu ───────────────────────
by_name = {m['Name']: m for m in data['menus']}

inpt_main = by_name.get('ORZID2 GMENU ABX INPT MAIN')
orzc_main = by_name.get('ORZC GMENU ABX INPT MAIN')

if inpt_main and orzc_main:
    orzc_main['Term1']       = inpt_main.get('Term1', '')
    orzc_main['Term2']       = inpt_main.get('Term2', '')
    orzc_main['Text']        = inpt_main.get('Text', '')
    orzc_main['LinkTargets'] = copy.deepcopy(inpt_main.get('LinkTargets', []))
    remapped = 0
    for lt in orzc_main['LinkTargets']:
        target = by_name.get(lt.get('Item', ''))
        if target and target.get('Combined') and target['Combined'] in by_name:
            lt['Item'] = target['Combined']
            remapped += 1
    print(f'ORZC main menu: {len(orzc_main["LinkTargets"])} links, {remapped} remapped to Combined')
elif not orzc_main:
    print('WARNING: ORZC GMENU ABX INPT MAIN not found — will be created as a new ORZC menu if inpt_main was in guidance')

# ── 5. Save ───────────────────────────────────────────────────────────────────
with open(TEST_PATH, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f'Total menus: {len(data["menus"])}')
print('Saved.')
