"""Debug version of export-cms.py grouping logic"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
JSON_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"

with open(JSON_PATH) as f:
    data = json.load(f)

menus = {m['Name']: m for m in data['menus']}
combined_pages = {m['Name']: m for m in data['menus'] if m.get('Inpt')}

MERGED_GROUPS = {
    "bacteremia": "systemic-infections",
    "immunocom-neut-fever": "systemic-infections",
    "lyme-disease": "systemic-infections",
    "toxic-megacolon": "gi-intraabdominal",
}

# Find root menus with combined equivalents
inpt_group_map = {}
for cid, page in combined_pages.items():
    inpt_root = page.get('Inpt')
    if not inpt_root:
        continue
    if inpt_root not in menus:
        print(f"  Warning: {cid} has missing Inpt: {inpt_root}")
        continue
    
    # Is this inpt page itself a root (no parent)?
    is_root = not any(m.get('Inpt') == inpt_root for m in combined_pages.values() if m.get('Name') != cid)
    if is_root:
        group_folder = MERGED_GROUPS.get(cid, cid)
        inpt_group_map[inpt_root] = group_folder
        print(f"Root: {inpt_root} -> {group_folder}")

# BFS from roots
from collections import deque
inpt_page_to_group = {}
for inpt_root, group_folder in inpt_group_map.items():
    queue = deque([inpt_root])
    visited = set()
    order = 0
    while queue:
        inpt_name = queue.popleft()
        if inpt_name in visited:
            continue
        visited.add(inpt_name)
        if inpt_name not in inpt_page_to_group:
            inpt_page_to_group[inpt_name] = group_folder
            order += 1
        inpt_page = menus.get(inpt_name)
        if inpt_page:
            for lt in inpt_page.get("LinkTargets", []):
                child = lt.get("Item", "")
                if child in menus and child not in visited:
                    queue.append(child)

print(f"\nInpt->Group mappings for cardiovascular:")
for inpt_name, group in sorted(inpt_page_to_group.items()):
    if group == 'cardiovascular':
        print(f"  {inpt_name} -> {group}")

# Now check myocarditis
myo_page = combined_pages.get('myocarditis')
if myo_page:
    inpt_source = myo_page.get('Inpt')
    group = inpt_page_to_group.get(inpt_source, 'general')
    print(f"\nmyocarditis:")
    print(f"  Inpt: {inpt_source}")
    print(f"  Group: {group}")
