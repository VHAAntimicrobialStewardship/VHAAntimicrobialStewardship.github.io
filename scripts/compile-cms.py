"""
scripts/compile-cms.py

Compiles CMS page files from cms-data/{station}/pages/ back into each
station's OMJSON file. Run after editing pages in the CMS or local files.

What it does, per station:
  - Reads all {page-id}.json files under cms-data/{station}/pages/
  - Replaces matching combined pages in OMJSON (matched by PageID == Name)
  - Adds any new pages not yet in OMJSON
  - Updates Combined cross-ref on inpatient source pages
  - Preserves all non-combined pages unchanged
  - Preserves inpt-main / main-menu (combined main menu) — not managed by CMS page files
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

# One entry per station: (station folder under stations/, OMJSON filename).
# cms-data/{station_dir}/pages/ is assumed for every station.
STATIONS: list[tuple[str, str]] = [
    ("001-TestStation", "TestStationOMJSON.json"),
    ("541-Cleveland", "ClevelandOMJSON.json"),
    ("539-Cincinnati", "CincinnatiOMJSON.json"),
    ("506-AnnArbor", "AnnArborOMJSON.json"),
]


def compile_station(station_dir: str, omjson_filename: str) -> None:
    json_path = ROOT / "stations" / station_dir / omjson_filename
    cms_root = ROOT / "cms-data" / station_dir / "pages"

    print(f"\n=== {station_dir} ===")

    # ── Load OMJSON ─────────────────────────────────────────────────────────
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    menus: list[dict] = data["menus"]

    # Build lookup tables
    by_name: dict[str, dict] = {m["Name"]: m for m in menus}

    # ── Read CMS page files ─────────────────────────────────────────────────
    if not cms_root.exists():
        print(f"ERROR: CMS pages directory not found: {cms_root}")
        print("Run scripts/export-cms.py first, or create the folder manually.")
        return

    cms_pages: dict[str, dict] = {}  # page_id -> page record
    for page_file in sorted(cms_root.rglob("*.json")):
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

    # ── Build new combined page records for OMJSON ───────────────────────────
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

    # ── Update or insert combined pages in OMJSON ────────────────────────────
    # Pages present in both CMS and OMJSON: update in-place
    updated = 0
    for menu in menus:
        pid = menu["Name"]
        if pid in cms_pages:
            new_rec = build_omjson_record(cms_pages[pid])
            menu.update(new_rec)
            if not new_rec.get("Inpt"):
                menu.pop("Inpt", None)
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

    # ── Refresh Combined cross-refs on inpatient pages ───────────────────────
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

    # ── Save ──────────────────────────────────────────────────────────────
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Total menus: {len(menus)}")


if __name__ == "__main__":
    for station_dir, omjson_filename in STATIONS:
        compile_station(station_dir, omjson_filename)
    print("\nCompile complete.")
