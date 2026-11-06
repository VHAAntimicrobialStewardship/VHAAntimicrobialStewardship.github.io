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
import re
import subprocess
from pathlib import Path

import station_registry

ROOT = Path(__file__).parent.parent

# One entry per station: (station folder under stations/, OMJSON filename).
# cms-data/{station_dir}/pages/ is assumed for every station.
STATIONS: list[tuple[str, str]] = [(s["folder"], s["omjson"]) for s in station_registry.load()]

# Stations whose OMJSON records get LastUpdated metadata from git history.
GIT_META_STATIONS = {folder for folder, _ in STATIONS}
# Pages that never show a "Last updated" line.
GIT_META_SKIP_PAGES = {"main-menu", "inpt-main"}
# Sveltia's default commit subject, e.g. Update 001-TestStation “group/page”.
SVELTIA_COMMIT = re.compile(r"^(?:Update|Create)\s+\S+\s+[“\"]")


def load_git_last_updated(pages_dir: Path) -> dict[str, tuple[str, str, str]]:
    """Map repo-relative page file path -> (editor, edit date, initial date).

    The editor/edit date come from the newest Sveltia commit ("" when the page
    was never edited in Sveltia); the initial date is the oldest commit that
    touched the page (renames are followed). Returns {} (so existing values are
    kept) when git is unavailable or the clone is shallow.
    """
    git = ["git", "-c", "core.quotepath=false", "-C", str(ROOT)]
    try:
        shallow = subprocess.run(
            git + ["rev-parse", "--is-shallow-repository"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if shallow == "true":
            print("  WARNING: shallow clone; skipping LastUpdated metadata (use fetch-depth: 0)")
            return {}
        log = subprocess.run(
            git + ["log", "--name-status", "--format=%x1e%an%x1f%aI%x1f%s",
                   "--", pages_dir.relative_to(ROOT).as_posix()],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"  WARNING: git history unavailable ({e}); skipping LastUpdated metadata")
        return {}

    # Commits are listed newest first. canon maps an older path to the page's
    # current path once a rename has been seen.
    canon: dict[str, str] = {}
    edits: dict[str, tuple[str, str]] = {}
    initial: dict[str, str] = {}
    for chunk in log.split("\x1e"):
        header, _, files = chunk.partition("\n")
        author, _, rest = header.partition("\x1f")
        iso, _, subject = rest.partition("\x1f")
        if not iso:
            continue
        date = iso[:10]
        is_sveltia = bool(SVELTIA_COMMIT.match(subject))
        for line in files.splitlines():
            parts = line.split("\t")
            if len(parts) < 2 or parts[0].startswith("D"):
                continue
            path = canon.get(parts[-1], parts[-1])
            if parts[0][0] in "RC" and len(parts) == 3:
                canon[parts[1]] = path
            if is_sveltia:
                edits.setdefault(path, (author.strip(), date))
            initial[path] = date  # overwritten until the oldest commit is reached
    return {
        path: (*edits.get(path, ("", "")), initial_date)
        for path, initial_date in initial.items()
    }


def build_omjson_record(page_rec: dict) -> dict:
    """Convert a CMS page file record to an OMJSON menu record.

    Only the fields the runtime uses are kept (LinkTargets is deliberately
    never written: markdown links in Text are the only link source).
    """
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
    # CMS folder group; the runtime uses it to build the Sveltia edit URL.
    if page_rec.get("Group"):
        record["CmsGroup"] = page_rec["Group"]
    # Optional right-hand "Therapy" panel text (sidebar layout only).
    if page_rec.get("Therapy", "").strip():
        record["Therapy"] = page_rec["Therapy"]
    for field in ("Outpt", "ERUC"):
        if page_rec.get(field):
            record[field] = page_rec[field]
    return record


def compile_station(station_dir: str, omjson_filename: str) -> None:
    """Merge one station's CMS page files into its OMJSON file (in place)."""
    json_path = ROOT / "stations" / station_dir / omjson_filename
    cms_root = ROOT / "cms-data" / station_dir / "pages"

    print(f"\n=== {station_dir} ===")

    # ── Load OMJSON ─────────────────────────────────────────────────────────
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    menus: list[dict] = data["menus"]

    # Lookup of existing OMJSON records by Name (PageID)
    by_name: dict[str, dict] = {m["Name"]: m for m in menus}

    # ── Read CMS page files ─────────────────────────────────────────────────
    if not cms_root.exists():
        print(f"ERROR: CMS pages directory not found: {cms_root}")
        print("Run scripts/export-cms.py first, or create the folder manually.")
        return

    cms_pages: dict[str, dict] = {}  # page_id -> page record
    cms_files: dict[str, Path] = {}  # page_id -> source file
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
        cms_files[page_id] = page_file

    print(f"CMS page files loaded: {len(cms_pages)}")

    # ── Update or insert combined pages in OMJSON ────────────────────────────
    # Pages present in both CMS and OMJSON: update in-place (fields not in the
    # CMS record, e.g. Combined/Contents, are kept; Inpt is dropped when the CMS
    # record has none). The main menu is not CMS-managed, so it only has any
    # stale LinkTargets removed.
    updated = 0
    for menu in menus:
        pid = menu["Name"]
        if pid in cms_pages:
            new_rec = build_omjson_record(cms_pages[pid])
            menu.update(new_rec)
            if not new_rec.get("Inpt"):
                menu.pop("Inpt", None)
            if not new_rec.get("Therapy"):
                menu.pop("Therapy", None)  # cleared in the CMS
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

    # ── Last-updated metadata from git history (opt-in stations only) ────────
    if station_dir in GIT_META_STATIONS:
        last_updated = load_git_last_updated(cms_root)
        stamped = edited = 0
        for menu in menus:
            pid = menu["Name"]
            if pid not in cms_files or pid in GIT_META_SKIP_PAGES:
                continue
            meta = last_updated.get(cms_files[pid].relative_to(ROOT).as_posix())
            if not meta:
                continue
            editor, edit_date, initial_date = meta
            if edit_date:
                menu["LastUpdatedBy"], menu["LastUpdated"] = editor, edit_date
                menu.pop("InitialLoaded", None)
                edited += 1
            else:
                menu["InitialLoaded"] = initial_date
                menu.pop("LastUpdatedBy", None)
                menu.pop("LastUpdated", None)
            stamped += 1
        print(f"Pages stamped: {stamped} ({edited} edited in Sveltia)")

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
