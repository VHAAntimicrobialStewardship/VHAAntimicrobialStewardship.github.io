"""
rebuild-combined-menus.py

Rebuilds simplified combined menus in TestStationOMJSON.json from scratch,
merging guidance from BOTH spreadsheet tabs:
  Tab 1 (Minneapolis_SideBySideGuida) = Mimi's entries
  Tab 2 (Mehul) = Dr. Mehul's entries -- takes precedence where both exist

Steps:
  1. Extract merged guidance from both tabs
  2. Remove all previously generated combined menus
  3. Remove Combined field from all menus
  4. Add fresh combined menus and Combined cross-refs
  5. Rebuild combined main menu from inpatient main menu structure
"""

import copy
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent.parent
XLSX = ROOT / "AntimicrobialStewardshipGuidanceCombined.xlsx"
TEST_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"
CMS_ROOT = ROOT / "cms-data" / "001-TestStation" / "pages"

# Copy xlsx to temp dir to avoid OneDrive lock issues
_tmp = Path(tempfile.gettempdir()) / "GuidanceCombined_rebuild.xlsx"
shutil.copy2(XLSX, _tmp)
XLSX = _tmp

PLACEHOLDERS = {"", "mehul", "mahul", "mimi"}
INPT_MAIN_NAME = "ORZID2 GMENU ABX INPT MAIN"
COMBINED_MAIN_NAME = "ORZC GMENU ABX INPT MAIN"


def to_combined_name(inpt_name: str) -> str:
    """Convert inpatient VistA menu name to ORZC equivalent."""
    return re.sub(r"^ORZID2\s+", "ORZC ", inpt_name)


def slugify_combined_name(name: str) -> str:
    """Create a stable slug from legacy ORZC menu names."""
    s = name.lower()
    s = re.sub(r"^orzc\s+gmenu\s+abx\s+", "", s)
    s = re.sub(r"^orzc\s+gmenu\s+", "", s)
    s = re.sub(r"^orzc\s+", "", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "page"


def load_cms_inpt_mapping() -> tuple[dict[str, str], dict[str, str]]:
    """Load stable Inpt->PageID mapping from existing CMS pages."""
    inpt_to_pageid: dict[str, str] = {}
    inpt_to_term1: dict[str, str] = {}
    if not CMS_ROOT.exists():
        return inpt_to_pageid, inpt_to_term1

    for page_file in CMS_ROOT.rglob("*.json"):
        try:
            rec = json.loads(page_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        inpt = (rec.get("Inpt") or "").strip()
        page_id = (rec.get("PageID") or page_file.stem).strip()
        if inpt and page_id:
            inpt_to_pageid[inpt] = page_id
            if rec.get("Term1"):
                inpt_to_term1[inpt] = rec["Term1"]

    return inpt_to_pageid, inpt_to_term1


def extract_tab(ws):
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {}
    headers = {str(v).strip(): i for i, v in enumerate(rows[0]) if v}
    if "Combined Guidance" not in headers:
        return {}

    comb_col = headers["Combined Guidance"]
    menu_col = headers["Source Menu Name (Inpatient)"]
    result = {}

    for row in rows[1:]:
        menu = row[menu_col] if len(row) > menu_col else None
        comb = row[comb_col] if len(row) > comb_col else None
        if not menu or not comb:
            continue

        menu = str(menu).strip()
        comb = str(comb).strip()
        if comb.lower() in PLACEHOLDERS:
            continue
        result[menu] = comb

    return result


def format_combined(raw):
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")

    # Normalize merged heading artifacts from spreadsheet text.
    text = re.sub(
        r"##\s*(Inpatient|Outpatient)\s*##\s*",
        r"## \1\n\n## ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"^(#{2,6})(\S)", r"\1 \2", text, flags=re.MULTILINE)

    lines = []
    for line in text.split("\n"):
        lines.append(re.sub(r" {2,}", " ", line.rstrip()))

    text = "\n".join(lines)
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]

    # If the first line looks like a title, promote it to a heading.
    if blocks and not blocks[0].startswith("#"):
        first_line = blocks[0].split("\n", 1)[0].strip()
        if first_line and first_line == first_line.upper() and len(first_line) <= 120:
            blocks[0] = blocks[0].replace(first_line, f"## {first_line}", 1)

    return "\n\n".join(blocks)


wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
mimi_data = extract_tab(wb.worksheets[0])
mehul_data = extract_tab(wb.worksheets[1])
guidance = {**mimi_data, **mehul_data}

print(f"Mimi tab:  {len(mimi_data)} entries")
print(f"Mehul tab: {len(mehul_data)} entries")
print(f"Merged:    {len(guidance)} unique entries")

with open(TEST_PATH, encoding="utf-8") as f:
    data = json.load(f)

existing_combined_names = {
    m.get("Combined")
    for m in data["menus"]
    if isinstance(m.get("Combined"), str) and m.get("Combined").strip()
}

# Strip all existing combined pages (ORZC prefix and slug-style) and Combined fields.
data["menus"] = [
    m
    for m in data["menus"]
    if not m["Name"].startswith("ORZC ")
    and not m["Name"].startswith("COMBINED ")
    and not re.match(r'^[a-z0-9][a-z0-9\-]*$', m["Name"])  # slug-style pages
]
for m in data["menus"]:
    m.pop("Combined", None)

print(f"Menus after stripping existing combined pages: {len(data['menus'])}")

inpt_by_name = {m["Name"]: m for m in data["menus"]}
new_menus = []
cross_refs = 0

for inpt_name, combined_text in guidance.items():
    combined_name = to_combined_name(inpt_name)
    inpt_menu = inpt_by_name.get(inpt_name)

    combined_menu = {
        "Name": combined_name,
        "Term1": "",
        "Term2": "",
        "Text": format_combined(combined_text),
        "LinkTargets": [],
    }

    if inpt_menu:
        combined_menu["Inpt"] = inpt_name
        if inpt_menu.get("Outpt"):
            combined_menu["Outpt"] = inpt_menu["Outpt"]
        if inpt_menu.get("ERUC"):
            combined_menu["ERUC"] = inpt_menu["ERUC"]

    new_menus.append(combined_menu)
    if inpt_menu:
        inpt_menu["Combined"] = combined_name
        cross_refs += 1

print(f"Combined menus created: {len(new_menus)}")
print(f"Combined cross-refs added: {cross_refs}")

data["menus"].extend(new_menus)
by_name = {m["Name"]: m for m in data["menus"]}

inpt_main = by_name.get(INPT_MAIN_NAME)
combined_main = by_name.get(COMBINED_MAIN_NAME)

if inpt_main and combined_main:
    combined_main["Term1"] = inpt_main.get("Term1", "")
    combined_main["Term2"] = inpt_main.get("Term2", "")
    combined_main["Text"] = inpt_main.get("Text", "")
    combined_main["LinkTargets"] = copy.deepcopy(inpt_main.get("LinkTargets", []))

    remapped = 0
    for lt in combined_main["LinkTargets"]:
        target = by_name.get(lt.get("Item", ""))
        if target and target.get("Combined") and target["Combined"] in by_name:
            lt["Item"] = target["Combined"]
            remapped += 1

    print(
        f"Combined main menu: {len(combined_main['LinkTargets'])} links, "
        f"{remapped} remapped to Combined"
    )
elif not combined_main:
    print("WARNING: Combined main menu not found")

# Convert legacy ORZC names to stable PageIDs while preserving rebuilt content.
inpt_to_pageid, inpt_to_term1 = load_cms_inpt_mapping()
all_menus = data["menus"]
combined_menus = [m for m in all_menus if isinstance(m.get("Inpt"), str) and m.get("Inpt").strip()]
used_names = {m["Name"] for m in all_menus if not m.get("Inpt")}
old_to_new: dict[str, str] = {}

for m in combined_menus:
    old_name = m["Name"]
    inpt = m["Inpt"].strip()
    if old_name == COMBINED_MAIN_NAME or inpt == INPT_MAIN_NAME:
        new_name = "main-menu"
    elif inpt in inpt_to_pageid:
        new_name = inpt_to_pageid[inpt]
    else:
        new_name = slugify_combined_name(old_name)

    base = new_name
    suffix = 2
    while new_name in used_names:
        new_name = f"{base}-{suffix}"
        suffix += 1
    used_names.add(new_name)
    old_to_new[old_name] = new_name

for m in combined_menus:
    old_name = m["Name"]
    inpt = m["Inpt"].strip()
    m["Name"] = old_to_new[old_name]
    if not (m.get("Term1") or "").strip():
        m["Term1"] = inpt_to_term1.get(
            inpt,
            re.sub(r"^ORZID2\s+GMENU\s+ABX\s+", "", inpt).strip(),
        )

for m in all_menus:
    combined_ref = m.get("Combined")
    if isinstance(combined_ref, str) and combined_ref in old_to_new:
        m["Combined"] = old_to_new[combined_ref]

    for lt in m.get("LinkTargets", []):
        item = lt.get("Item")
        if isinstance(item, str) and item in old_to_new:
            lt["Item"] = old_to_new[item]

link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
for m in combined_menus:
    txt = m.get("Text")
    if not isinstance(txt, str) or not txt:
        continue

    def _replace(match: re.Match) -> str:
        label = match.group(1)
        target = match.group(2).strip()
        return f"[{label}]({old_to_new.get(target, target)})"

    m["Text"] = link_re.sub(_replace, txt)

data["menus"].sort(key=lambda menu: menu.get("Name", "").lower())
print(f"Combined PageIDs restored: {len(combined_menus)}")
print(f"Mapped from CMS by Inpt: {sum(1 for m in combined_menus if m['Inpt'].strip() in inpt_to_pageid)}")

with open(TEST_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Total menus: {len(data['menus'])}")
print("Saved.")
