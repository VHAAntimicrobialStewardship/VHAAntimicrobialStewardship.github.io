"""
scripts/compile-cms.py

Compiles CMS page files from cms-data/001-TestStation/pages/ back into
TestStationOMJSON.json. Run after editing pages in the CMS or local files.

What it does:
  - Reads all {page-id}.json files under cms-data/001-TestStation/pages/
  - Replaces matching combined pages in OMJSON (matched by Inpt source)
  - Adds any new pages not yet in OMJSON
  - Updates Combined cross-ref on inpatient source pages
  - Preserves all non-combined pages unchanged
  - Preserves inpt-main (combined main menu) — not managed by CMS page files
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
JSON_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"
CMS_ROOT = ROOT / "cms-data" / "001-TestStation" / "pages"


# ── Load OMJSON ───────────────────────────────────────────────────────────────
with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

menus: list[dict] = data["menus"]

# Build lookup tables
by_name: dict[str, dict] = {m["Name"]: m for m in menus}
inpt_to_combined: dict[str, str] = {}  # inpatient_page_name -> current combined PageID
for m in menus:
    if isinstance(m.get("Combined"), str) and m["Combined"].strip():
        inpt_to_combined[m["Name"]] = m["Combined"]

# ── Read CMS page files ────────────────────────────────────────────────────────
if not CMS_ROOT.exists():
    print(f"ERROR: CMS pages directory not found: {CMS_ROOT}")
    print("Run scripts/export-cms.py first.")
    raise SystemExit(1)

cms_pages: dict[str, dict] = {}  # page_id -> page record
for page_file in sorted(CMS_ROOT.rglob("*.json")):
    try:
        page_rec = json.loads(page_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  SKIP (JSON error): {page_file.name}: {e}")
        continue
    page_id = page_rec.get("PageID")
    if not page_id:
        # Derive from filename
        page_id = page_file.stem
        page_rec["PageID"] = page_id
    cms_pages[page_id] = page_rec

print(f"CMS page files loaded: {len(cms_pages)}")

# ── Build new combined page records for OMJSON ────────────────────────────────
def build_omjson_record(page_rec: dict) -> dict:
    """Convert a CMS page file record to an OMJSON menu record."""
    page_id = page_rec["PageID"]
    record: dict = {
        "Name": page_id,
        "Term1": page_rec.get("Term1", page_id),
        "Term2": page_rec.get("Term2", ""),
        "Text": page_rec.get("Text", ""),
    }
    inpt = page_rec.get("Inpt", "")
    if inpt:
        record["Inpt"] = inpt
    for field in ("Outpt", "ERUC"):
        if page_rec.get(field):
            record[field] = page_rec[field]
    return record


# ── Update or insert combined pages in OMJSON ─────────────────────────────────
existing_combined_ids: set[str] = {m["Name"] for m in menus if m.get("Inpt")}

# Pages present in both CMS and OMJSON: update in-place
updated = 0
for menu in menus:
    pid = menu["Name"]
    if pid in cms_pages and menu.get("Inpt"):
        new_rec = build_omjson_record(cms_pages[pid])
        menu.update(new_rec)
        menu.pop("LinkTargets", None)
        updated += 1
    elif pid == "main-menu":
        menu.pop("LinkTargets", None)

# Pages in CMS but not yet in OMJSON: add new
added = 0
for page_id, page_rec in cms_pages.items():
    if page_id not in by_name:
        new_rec = build_omjson_record(page_rec)
        menus.append(new_rec)
        added += 1
        print(f"  Added new page: {page_id}")

print(f"Combined pages updated: {updated}")
print(f"New combined pages added: {added}")

# ── Refresh Combined cross-refs on inpatient pages ────────────────────────────
# For each CMS page that has an Inpt pointer, ensure the inpatient page's
# Combined field points back to this PageID
cross_updated = 0
for page_id, page_rec in cms_pages.items():
    inpt_source = page_rec.get("Inpt", "")
    if not inpt_source:
        continue
    inpt_menu = by_name.get(inpt_source)
    if inpt_menu and inpt_menu.get("Combined") != page_id:
        inpt_menu["Combined"] = page_id
        cross_updated += 1

print(f"Inpatient Combined cross-refs refreshed: {cross_updated}")

# ── Save ──────────────────────────────────────────────────────────────────────
with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"Total menus: {len(menus)}")
print("Compile complete.")
