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
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent.parent
XLSX = ROOT / "AntimicrobialStewardshipGuidanceCombined.xlsx"
TEST_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"

PLACEHOLDERS = {"", "mehul", "mahul", "mimi"}
INPT_MAIN_NAME = "ORZID2 GMENU ABX INPT MAIN"
COMBINED_MAIN_ID = "inpt-main"


def to_combined_name(inpt_name: str) -> str:
    """Convert inpatient VistA menu names into PageID slugs for combined pages."""
    name = inpt_name
    name = re.sub(r"^ORZID2\s+GMENU\s+", "", name)
    name = re.sub(r"^ORZID2\s+", "", name)
    name = re.sub(r"^GMENU\s+", "", name)
    name = re.sub(r"^ABX\s+", "", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    # Convert to PageID slug
    slug = name.lower()
    slug = re.sub(r"[\s/]", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "page"


def extract_tab(ws):
    headers = {
        str(ws.cell(1, c).value).strip(): c
        for c in range(1, ws.max_column + 1)
        if ws.cell(1, c).value
    }
    if "Combined Guidance" not in headers:
        return {}

    comb_col = headers["Combined Guidance"]
    menu_col = headers["Source Menu Name (Inpatient)"]
    result = {}

    for r in range(2, ws.max_row + 1):
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

# Keep legacy pages, remove only previously generated combined pages.
data["menus"] = [
    m
    for m in data["menus"]
    if m["Name"] not in existing_combined_names
    and not m["Name"].startswith("ORZC ")
    and not m["Name"].startswith("COMBINED ")
    and not re.match(r'^[a-z0-9][a-z0-9\-]*$', m["Name"])  # existing PageID pages
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
combined_main = by_name.get(COMBINED_MAIN_ID)

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
    print("WARNING: INPT MAIN not found while rebuilding combined main menu")

with open(TEST_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Total menus: {len(data['menus'])}")
print("Saved.")
