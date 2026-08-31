"""
scripts/export-cms.py

Exports all combined guidance pages from TestStationOMJSON.json into the CMS
file structure and regenerates admin/config.yml.

Output:
  cms-data/001-TestStation/pages/{group}/{page-id}.json  — one file per page
  admin/config.yml updated with one primary station collection and filtered
  shortcut collections for common groups
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

# Inpatient root menus that do not have a Combined page counterpart but should
# still map descendants into a dedicated CMS group folder.
MANUAL_INPT_ROOT_GROUPS: dict[str, str] = {
  "ORZID2 GMENU ABX HEAD AND NECK": "head-and-neck",
}

# Display labels for each group folder
GROUP_LABELS: dict[str, str] = {
  "main-menu": "Main Menu",
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
    "head-and-neck": "Head and Neck",
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
combined_main_id = "main-menu" if "main-menu" in by_name else "inpt-main"
combined_pages[combined_main_id] = by_name.get(combined_main_id, {})
MAIN_MENU_GROUP = "main-menu"

print(f"Combined pages to export: {len(combined_pages)}")

# ── Assign each combined page to a group via inpatient tree ancestry ──────────
# Strategy: BFS the INPATIENT tree from ORZID2 GMENU ABX INPT MAIN, recording
# which inpatient group root each page descends from. Then map combined pages to
# groups via their Inpt pointer. This correctly captures orphan combined pages
# that aren't linked from other combined pages.

page_group: dict[str, str] = {}  # page_id -> group_folder

inpt_main_omjson = by_name.get("ORZID2 GMENU ABX INPT MAIN")
combined_main = by_name.get(combined_main_id)
if not combined_main:
    print("ERROR: combined main menu not found (expected main-menu or inpt-main).")
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
            continue

        manual_group = MANUAL_INPT_ROOT_GROUPS.get(inpt_root)
        if manual_group:
            inpt_group_map[inpt_root] = manual_group

# BFS through INPATIENT pages, tracking group ancestry
inpt_page_to_group: dict[str, str] = {}  # inpatient_page_name -> group_folder
inpt_page_order: dict[str, int] = {}  # inpatient_page_name -> bfs order within group
for inpt_root, group_folder in inpt_group_map.items():
  queue: deque[str] = deque([inpt_root])
  visited: set[str] = set()
  order = 0
  while queue:
    inpt_name = queue.popleft()
    if inpt_name in visited:
      continue
    visited.add(inpt_name)
    if inpt_name not in inpt_page_to_group:
      inpt_page_to_group[inpt_name] = group_folder
      inpt_page_order[inpt_name] = order
      order += 1
    inpt_page = by_name.get(inpt_name)
    if inpt_page:
      for lt in inpt_page.get("LinkTargets", []):
        child = lt.get("Item", "")
        if child in by_name and child not in visited:
          queue.append(child)

# Assign combined pages via their Inpt pointer's group
for pid, page in combined_pages.items():
  if pid == combined_main_id:
    page_group[pid] = MAIN_MENU_GROUP
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

# Prefer known clinical order, then append discovered groups not listed above.
all_group_folders: list[str] = [
    g for g in [
    "main-menu",
        "adj-exist-abx-therapy",
        "cns",
        "cardiovascular",
        "head-and-neck",
        "dermatologic-surgery-guidelines",
        "device-related-infections",
        "gi-intraabdominal",
        "hiv-aids",
        "recommended-immunizations",
        "immunocompromised-patient",
        "lung-and-mediastinum",
        "pneumonia",
        "prevention-of-infection",
        "genitourinary",
        "ssti-main-menu",
        "systemic-infections",
        "general",
    ]
    if g in group_summary
]
for grp in sorted(group_summary):
    if grp not in all_group_folders:
        all_group_folders.append(grp)

# ── Write CMS page files ──────────────────────────────────────────────────────
CMS_ROOT.mkdir(parents=True, exist_ok=True)
written = 0
skipped = 0

# Remove stale generated page files so recategorized pages do not remain in old
# group folders after re-export.
for old_page_file in CMS_ROOT.glob("*/*.json"):
    old_page_file.unlink()


def strip_nav_prefixes_and_suffixes(title: str) -> str:
  """Remove legacy numeric/nav markers so export owns the numbering format."""
  cleaned = (title or "").strip()
  cleaned = re.sub(r"(?:\s*\(navigation\)\s*)+$", "", cleaned, flags=re.IGNORECASE)
  while True:
    updated = re.sub(r"^\s*\d+(?:\.\d+)*\.\s*", "", cleaned, count=1)
    if updated == cleaned:
      break
    cleaned = updated.strip()
  return cleaned.strip()


page_export_rows: list[dict] = []
for pid, page in combined_pages.items():
  group_folder = page_group.get(pid, "general")
  raw_term1 = page.get("Term1") or page.get("Name") or pid
  cleaned_term1 = strip_nav_prefixes_and_suffixes(raw_term1) or pid
  inpt_source = page.get("Inpt", "")
  source_inpt = by_name.get(inpt_source, {})
  source_link_count = len(source_inpt.get("LinkTargets", [])) if source_inpt else 0
  has_legacy_nav_marker = (
    bool(re.search(r"\(navigation\)", raw_term1, flags=re.IGNORECASE))
    or bool(re.match(r"^\s*\d+(?:\.\d+)*\.\s*", raw_term1))
  )

  is_primary_nav = inpt_source in inpt_group_map
  is_secondary_nav = (
    not is_primary_nav
    and source_link_count >= 8
    and (
      has_legacy_nav_marker
      or inpt_source in inpt_page_order
    )
  )

  page_export_rows.append(
    {
      "pid": pid,
      "page": page,
      "group": group_folder,
      "term1": cleaned_term1,
      "inpt": inpt_source,
      "tree_order": inpt_page_order.get(inpt_source, 10**9),
      "is_primary_nav": is_primary_nav,
      "is_nav": is_primary_nav or is_secondary_nav,
    }
  )


group_nav_numbers: dict[str, dict[str, int]] = {}
for group_folder in sorted({row["group"] for row in page_export_rows}):
    nav_rows = [row for row in page_export_rows if row["group"] == group_folder and row["is_nav"]]
    nav_rows.sort(
        key=lambda row: (
            0 if row["is_primary_nav"] else 1,
            row["tree_order"],
            row["term1"].lower(),
            row["pid"],
        )
    )
    group_nav_numbers[group_folder] = {
        row["pid"]: idx for idx, row in enumerate(nav_rows, start=1)
    }

for row in page_export_rows:
    pid = row["pid"]
    page = row["page"]
    group_folder = row["group"]
    group_dir = CMS_ROOT / group_folder
    group_dir.mkdir(parents=True, exist_ok=True)

    # Build page record (only CMS-relevant fields).
    # Navigation pages are numbered sequentially within each clinical group.
    nav_number = group_nav_numbers.get(group_folder, {}).get(pid)
    display_term1 = (
        f"{nav_number}. {row['term1']} (Navigation)"
        if nav_number is not None
        else row["term1"]
    )
    page_record: dict = {
        "PageID": pid,
        "Group": group_folder,
        "Term1": display_term1,
        "Term2": page.get("Term2", ""),
        "Text": page.get("Text", ""),
        "LinkTargets": [
            {k: v for k, v in lt.items() if k != "Key"}
          for lt in (page.get("LinkTargets") or [])
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


def make_group_options_yaml(order: list[str]) -> str:
    """Build select options YAML for Group field from ordered folders."""
    lines: list[str] = []
    for group_folder in order:
        label = GROUP_LABELS.get(group_folder, group_folder)
        lines.append(f'          - {{ label: "{label}", value: "{group_folder}" }}')
    return "\n".join(lines)


# Ordered groups for config.yml (clinical order)
ORDERED_GROUPS = [
  "main-menu",
    "adj-exist-abx-therapy",
    "cns",
    "cardiovascular",
    "head-and-neck",
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
    summary: "{{fields.Group}} | {{fields.Term1}} [{{fields.PageID}}]"
    sortable_fields: ["PageID", "Term1", "Group"]
    fields:
      - label: "Page ID"
        name: PageID
        widget: string
        hint: "Immutable identifier used in links. Set once when creating — never change."
        pattern: ['^[a-z0-9][a-z0-9\\-]*$', 'Lowercase letters, numbers, hyphens only']
      - label: "Group"
        name: Group
        widget: select
        hint: "Clinical group used for organization and file path under pages/."
        options:
__GROUP_OPTIONS__
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

GROUP_OPTIONS_YAML = make_group_options_yaml(all_group_folders)
FIELD_BLOCK_RESOLVED = FIELD_BLOCK.replace("__GROUP_OPTIONS__", GROUP_OPTIONS_YAML)

collection_yaml_blocks: list[str] = []

# Primary editable station collection
primary_collection_block = f"""\
  - label: "001-TestStation"
    name: "001tes_all_pages"
    folder: "cms-data/{STATION_ID}/pages"
    path: "{{{{fields.Group}}}}/{{{{fields.PageID}}}}"
    create: true
    format: json
    extension: json
    editor:
      preview: false
{FIELD_BLOCK_RESOLVED}"""
collection_yaml_blocks.append(primary_collection_block)

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
print(
    "admin/config.yml updated with 1 station collection (001-TestStation)"
)
print("Export complete.")
