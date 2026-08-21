"""
scripts/export-cms.py

Exports all combined guidance pages from TestStationOMJSON.json into the CMS
file structure and regenerates admin/config.yml.

Output:
  cms-data/001-TestStation/pages/{group}/{page-id}.json  — one file per page
  admin/config.yml updated with disease-group folder collections
"""

import json
import re
from collections import deque
from pathlib import Path

ROOT = Path(__file__).parent.parent
JSON_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"
CMS_ROOT = ROOT / "cms-data" / "001-TestStation" / "pages"
ADMIN_CONFIG = ROOT / "admin" / "config.yml"
STATION_ID = "001-TestStation"

# Merged group assignments: PageIDs that share a clinical group folder
MERGED_GROUPS: dict[str, str] = {
    "bacteremia": "systemic-infections",
    "immunocom-neut-fever": "systemic-infections",
    "lyme-disease": "systemic-infections",
    "toxic-megacolon": "gi-intraabdominal",
}

# Display labels for each group folder
GROUP_LABELS: dict[str, str] = {
    "adj-exist-abx-therapy": "Adjust Existing Therapy",
    "cns": "Central Nervous System",
    "lung-and-mediastinum": "Lungs & Mediastinum",
    "dermatologic-surgery-guidelines": "Dermatology & Surgery",
    "device-related-infections": "Device-related Infections",
    "prevention-of-infection": "Prevention of Infection",
    "pneumonia": "Pneumonia",
    "hiv-aids": "HIV / AIDS",
    "cardiovascular": "Cardiovascular",
    "immunocompromised-patient": "Immunocompromised",
    "gi-intraabdominal": "GI & Intraabdominal",
    "recommended-immunizations": "Immunizations",
    "genitourinary": "Urogenital",
    "ssti-main-menu": "Skin & Soft Tissue",
    "systemic-infections": "Systemic Infections",
    "general": "General / Uncategorized",
}


# ── Load data ─────────────────────────────────────────────────────────────────
with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

menus = data["menus"]
by_name: dict[str, dict] = {m["Name"]: m for m in menus}

# All combined pages: those with Inpt field
combined_pages: dict[str, dict] = {m["Name"]: m for m in menus if m.get("Inpt")}
combined_pages["inpt-main"] = by_name.get("inpt-main", {})

print(f"Combined pages to export: {len(combined_pages)}")

# ── Assign each combined page to a group via inpatient tree ancestry ──────────
# Strategy: BFS the INPATIENT tree from ORZID2 GMENU ABX INPT MAIN, recording
# which inpatient group root each page descends from. Then map combined pages to
# groups via their Inpt pointer. This correctly captures orphan combined pages
# that aren't linked from other combined pages.

page_group: dict[str, str] = {}  # page_id -> group_folder

inpt_main_omjson = by_name.get("ORZID2 GMENU ABX INPT MAIN")
combined_main = by_name.get("inpt-main")
if not combined_main:
    print("ERROR: inpt-main not found. Run migrate-pageids.py first.")
    raise SystemExit(1)

# Build map: inpatient group root name -> combined group folder name
# These are the inpatient pages directly linked from ORZID2 GMENU ABX INPT MAIN
# that have a Combined counterpart
inpt_group_map: dict[str, str] = {}   # inpatient_name -> group_folder
if inpt_main_omjson:
    for lt in inpt_main_omjson.get("LinkTargets", []):
        inpt_root = lt.get("Item", "")
        inpt_page = by_name.get(inpt_root)
        if not inpt_page:
            continue
        combined_id = inpt_page.get("Combined")
        if combined_id and combined_id in combined_pages:
            group_folder = MERGED_GROUPS.get(combined_id, combined_id)
            inpt_group_map[inpt_root] = group_folder

# BFS through INPATIENT pages, tracking group ancestry
inpt_page_to_group: dict[str, str] = {}  # inpatient_page_name -> group_folder
for inpt_root, group_folder in inpt_group_map.items():
    queue: deque[str] = deque([inpt_root])
    visited: set[str] = set()
    while queue:
        inpt_name = queue.popleft()
        if inpt_name in visited:
            continue
        visited.add(inpt_name)
        if inpt_name not in inpt_page_to_group:
            inpt_page_to_group[inpt_name] = group_folder
        inpt_page = by_name.get(inpt_name)
        if inpt_page:
            for lt in inpt_page.get("LinkTargets", []):
                child = lt.get("Item", "")
                if child in by_name and child not in visited:
                    queue.append(child)

# Assign combined pages via their Inpt pointer's group
for pid, page in combined_pages.items():
    if pid == "inpt-main":
        continue
    inpt_source = page.get("Inpt", "")
    group_folder = inpt_page_to_group.get(inpt_source, "general")
    page_group[pid] = group_folder

group_summary: dict[str, int] = {}
for pid, grp in page_group.items():
    group_summary[grp] = group_summary.get(grp, 0) + 1

print("Group assignment summary:")
for grp in sorted(group_summary):
    label = GROUP_LABELS.get(grp, grp)
    print(f"  {grp} ({label}): {group_summary[grp]} pages")

# ── Write CMS page files ──────────────────────────────────────────────────────
CMS_ROOT.mkdir(parents=True, exist_ok=True)
written = 0
skipped = 0

for pid, page in combined_pages.items():
    if pid == "inpt-main":
        continue  # auto-generated; not a user-editable CMS page

    group_folder = page_group.get(pid, "general")
    group_dir = CMS_ROOT / group_folder
    group_dir.mkdir(parents=True, exist_ok=True)

    # Build page record (only CMS-relevant fields)
    page_record: dict = {
        "PageID": pid,
        "Term1": page.get("Term1") or page.get("Name") or pid,
        "Term2": page.get("Term2", ""),
        "Text": page.get("Text", ""),
        "LinkTargets": [
            {k: v for k, v in lt.items() if k != "Key"}
            for lt in page.get("LinkTargets", [])
        ],
        "Inpt": page.get("Inpt", ""),
    }
    # Preserve cross-tab refs if present (transition period)
    for field in ("Outpt", "ERUC"):
        if page.get(field):
            page_record[field] = page[field]

    out_path = group_dir / f"{pid}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(page_record, f, indent=2, ensure_ascii=False)
        f.write("\n")
    written += 1

print(f"Page files written: {written}")


# ── Generate admin/config.yml ─────────────────────────────────────────────────
def make_collection_name(station: str, group: str) -> str:
    """Generate a short collection identifier."""
    short_station = re.sub(r"[^a-z0-9]", "", station.lower())[:6]
    short_group = re.sub(r"[^a-z0-9]", "", group.lower())[:20]
    return f"{short_station}_{short_group}"


# Ordered groups for config.yml (clinical order)
ORDERED_GROUPS = [
    "adj-exist-abx-therapy",
    "cns",
    "cardiovascular",
    "dermatologic-surgery-guidelines",
    "device-related-infections",
    "gi-intraabdominal",
    "hiv-aids",
    "immunizations",  # uses recommended-immunizations folder
    "immunocompromised-patient",
    "lung-and-mediastinum",
    "pneumonia",
    "prevention-of-infection",
    "genitourinary",
    "ssti-main-menu",
    "systemic-infections",
    "general",
]
# Fix: "immunizations" maps to the folder "recommended-immunizations"
ORDERED_GROUPS_FOLDERS = [
    g if g != "immunizations" else "recommended-immunizations"
    for g in ORDERED_GROUPS
]

FIELD_BLOCK = """\
      identifier_field: PageID
      summary: "{{fields.Term1}} [{{fields.PageID}}]"
      fields:
        - label: "Page ID"
          name: PageID
          widget: string
          hint: "Immutable identifier used in links. Set once when creating — never change."
          pattern: ['^[a-z0-9][a-z0-9\\-]*$', 'Lowercase letters, numbers, hyphens only']
        - label: "Display Title (search label)"
          name: Term1
          widget: string
          hint: "Human-readable title shown in the search dropdown."
        - label: "Alternate Search Term"
          name: Term2
          widget: string
          required: false
        - label: "Content"
          name: Text
          widget: markdown
          required: false
          hint: "Write content here. Link to other pages using [Label](page-id) where page-id is shown at the bottom of the target page on the live site."
        - label: "Link Targets"
          name: LinkTargets
          widget: list
          required: false
          hint: "Explicit link registry. Required only for links to VistA order dialogs; combined page links resolve automatically by Page ID."
          fields:
            - label: "Link Text"
              name: Text
              widget: string
            - label: "Target Page ID or Order Name"
              name: Item
              widget: string
              hint: "For guidance pages: use the Page ID. For order dialogs: use the full VistA order name."
        - label: "Source Inpatient Menu (read-only)"
          name: Inpt
          widget: string
          required: false
          hint: "Legacy VistA inpatient source menu. Do not edit."
"""

collection_yaml_blocks: list[str] = []
for group_folder in ORDERED_GROUPS_FOLDERS:
    label = GROUP_LABELS.get(group_folder, group_folder)
    col_name = make_collection_name(STATION_ID, group_folder)
    block = f"""\
  - label: "001-TestStation: {label}"
    name: "{col_name}"
    folder: "cms-data/{STATION_ID}/pages/{group_folder}"
    create: true
    format: json
    extension: json
    editor:
      preview: false
{FIELD_BLOCK}"""
    collection_yaml_blocks.append(block)

existing_yml = ADMIN_CONFIG.read_text(encoding="utf-8")

# Extract the header (everything before the first collection entry)
# Keep backend, publish_mode, site_url, media_folder, editor sections
header_end = existing_yml.find("\ncollections:")
if header_end == -1:
    print("ERROR: could not find 'collections:' in config.yml")
    raise SystemExit(1)

header = existing_yml[: header_end]

abx_links_collection = """\
  - label: "Antibiotic Links"
    name: "abx_links"
    files:
      - label: "Antibiotic Links"
        name: "abx_links"
        file: "cms-data/abx-links.cms.json"
        format: "json"
        extension: "json"
        fields:
          - label: "Entries"
            name: "entries"
            widget: list
            fields:
              - { label: "Name", name: "Name", widget: "string", required: false }
              - { label: "URL", name: "URL", widget: "string", required: false }
              - { label: "Route Filter", name: "RouteFilter", widget: "string", required: false }"""

site_settings_collection = """\
  - label: "Site Settings"
    name: "site_settings"
    files:
      - label: "Web Manifest"
        name: "web_manifest"
        file: "manifest.webmanifest"
        format: "json"
        extension: "json"
        identifier_field: name
        summary: "{{name}}"
        fields:
          - {label: "Name", name: "name", widget: "string"}
          - {label: "Short Name", name: "short_name", widget: "string"}
          - {label: "Description", name: "description", widget: "string", required: false}
          - {label: "Scope", name: "scope", widget: "string"}
          - {label: "Start URL", name: "start_url", widget: "string"}
          - {label: "Background Color", name: "background_color", widget: "string"}
          - {label: "Theme Color", name: "theme_color", widget: "string"}
          - {label: "Display", name: "display", widget: "string"}
          - label: "Icons"
            name: "icons"
            widget: list
            fields:
              - {label: "Src", name: "src", widget: "string"}
              - {label: "Sizes", name: "sizes", widget: "string"}
              - {label: "Type", name: "type", widget: "string"}
              - {label: "Purpose", name: "purpose", widget: "string", required: false}"""

new_config = header + "\ncollections:\n"
new_config += abx_links_collection + "\n"
new_config += site_settings_collection + "\n"
for block in collection_yaml_blocks:
    new_config += block + "\n"

ADMIN_CONFIG.write_text(new_config, encoding="utf-8")
print(f"admin/config.yml updated with {len(collection_yaml_blocks)} group collections")
print("Export complete.")
