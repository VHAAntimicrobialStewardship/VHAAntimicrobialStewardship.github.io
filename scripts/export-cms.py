"""
scripts/export-cms.py

Exports all combined guidance pages from TestStationOMJSON.json into the CMS
file structure and regenerates admin/config.yml.

Output:
  cms-data/001-TestStation/pages/{group}/{page-id}.json  — one file per page
  admin/config.yml updated with one primary station collection plus the
  Abx-links and site-settings collections

How it works (high level):
  1. Load the OMJSON and pick out the "combined" pages (those with an Inpt field).
  2. Walk the click paths (markdown links) outward from each main-menu section
     to score which clinical group every page is closest to.
  3. Pick one group per page (see group_rank / pick_best_group for the rules),
     with explicit overrides from MAIN_MENU_SECTION_GROUPS.
  4. Number the "navigation" pages inside each group ("3. Foo (Navigation)").
  5. Write one JSON file per page, then rewrite the collections block of
     admin/config.yml (header section of the file is preserved).

SCOPE NOTE (multi-station): This script is intentionally NOT generalized to
loop over multiple stations. It regenerates admin/config.yml's collections
wholesale from scratch (see build_config_text below), so blindly looping it
over every station would require it to merge multiple stations' collection
blocks correctly in one pass — a much larger, riskier rewrite of that section.
New stations added by copying 001-TestStation's cms-data directly (rather than
deriving cms-data from OMJSON via this script) do not need this script at all;
scripts/compile-cms.py (cms-data -> OMJSON) is already multi-station-aware and
is the one that matters for day-to-day CMS edits. If export-cms.py ever needs
to target a different station, change STATION_ID/JSON_PATH/CMS_ROOT below
manually and re-review the admin/config.yml generation logic before running —
never run this script without asking the user first, per repo memory.
"""

import hashlib
import json
import re
from collections import deque
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATION_ID = "001-TestStation"
JSON_PATH = ROOT / "stations" / STATION_ID / "TestStationOMJSON.json"
CMS_ROOT = ROOT / "cms-data" / STATION_ID / "pages"
ADMIN_CONFIG = ROOT / "admin" / "config.yml"

# Matches markdown links: [label](target)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# The combined main menu's PageID (older data used "inpt-main").
MAIN_MENU_ID = "main-menu"
LEGACY_MAIN_MENU_ID = "inpt-main"
# CMS group folder that holds the main menu page itself.
MAIN_MENU_GROUP = "main-menu"
# Group used for any page that cannot be reached from a main-menu section.
FALLBACK_GROUP = "general"


# ══════════════════════════════════════════════════════════════════════════════
# Group configuration (edit these tables to change how pages are categorized)
# ══════════════════════════════════════════════════════════════════════════════

# Pages linked directly from the main menu -> the CMS group they belong to.
# Several main-menu sections can share one group (e.g. all organism pages).
# A page listed here is ALWAYS placed in that group; every other page is
# placed by click-path ancestry (see assign_groups).
MAIN_MENU_SECTION_GROUPS: dict[str, str] = {
    # Syndromes and Diseases, by Body Systems
    "bone-joint-muscle-infections": "bone-joint-muscle-infections",
    "cardiovascular": "cardiovascular",
    "cns": "cns",
    "gi-intraabdominal": "gi-intraabdominal",
    "head-and-neck": "head-and-neck",
    "lung-and-mediastinum": "lung-and-mediastinum",
    "ssti-main-menu": "ssti-main-menu",
    "system-infectious-diseases": "system-infectious-diseases",
    "genitourinary": "genitourinary",
    # Organisms
    "bacteria": "organisms",
    "fungi": "organisms",
    "other-pathogens": "organisms",
    "parasites": "organisms",
    "viruses": "organisms",
    # General and Miscellaneous (collapsed per heading)
    "dermatologic-surgery-guidelines": "dermatologic-surgery-guidelines",
    "device-related-infections": "device-related-infections",
    "hiv-aids": "hiv-aids",
    "immunocompromised-patient": "immunocompromised-patient",
    "tpoxx-monkeypox-treatment": "tpoxx-monkeypox-treatment",
    "prevention-of-infection": "prevention-of-infection",
    "recommended-immunizations": "recommended-immunizations",
    "surgical-pre-op-antibiotics": "surgical-antimicrobial-prophylaxis",
    "surgical-post-op-antimicrobial-prophylaxis": "surgical-antimicrobial-prophylaxis",
    "surg-surgical-site-infect": "surgical-site-infections",
    "bispecific-disease-specific-management": "bispecific-antibody",
    "bispecific-crs-monitoring": "bispecific-antibody",
    "bispecific-lodging-admit-information": "bispecific-antibody",
    "bispecific-icans-monitoring": "bispecific-antibody",
    # Help
    "additional-assistance": "help-page",
    "help-page": "help-page",
    "faq": "help-page",
    "clinical-on-call-schedule": "help-page",
    "up-to-date-online": "help-page",
    # Important Antimicrobial Information
    "susceptibilities-antibiogram": "important-antimicrobial",
    "antimicrobial-formulary": "important-antimicrobial",
    "abx-restriction-policy": "important-antimicrobial",
    "adj-exist-abx-therapy": "important-antimicrobial",
    "how-to-find-alt-abx": "important-antimicrobial",
    "beta-lactam-allergy-assessment": "important-antimicrobial",
    "infection-control": "important-antimicrobial",
    "vanco-mrsa-nares-information": "important-antimicrobial",
    "esbl-kpc-etc": "important-antimicrobial",
    "abx-not-required": "important-antimicrobial",
    # Utility/reference pages that are footer-linked from nearly every
    # clinical page. Without an explicit override, BFS adjacency sweeps
    # them into whichever disease group happens to be enumerated first in
    # the main menu, which is incorrect since they aren't disease-specific.
    "about-the-cdss": "help-page",
    "acknowledgement": "help-page",
    "contact-cdss-project-team": "help-page",
    "diseases-and-syndromes-not-covered": "help-page",
    "elements-of-cdss-advice-page": "help-page",
    "home-iv-therapy": "help-page",
    "how-to-use-the-cdss": "help-page",
    "references": "help-page",
    "adj-exist-therapy": "important-antimicrobial",
    "beta-lactam-allergy-facts": "important-antimicrobial",
    "duration-of-antimicrobial-therapy": "important-antimicrobial",
    "genrl-alternative-drug": "important-antimicrobial",
    "pregnancy-risk-factors-for-antimicrobials": "important-antimicrobial",
    "warfarin-interactions-with-antimicrobials": "important-antimicrobial",
    # Utility/reference pages found miscategorized under
    # bone-joint-muscle-infections (footer-linked from many pages, so BFS
    # adjacency incorrectly swept them into whichever disease group's
    # pages happened to link to them first).
    "antimicrobial-cost-information": "important-antimicrobial",
    "drug-allergies": "important-antimicrobial",
    "general-information-legend": "help-page",
    "how-to-find-alt": "important-antimicrobial",
    "important-drug-properties": "important-antimicrobial",
    "restriction-policy": "important-antimicrobial",
}

# Main-menu links that are global (not category-defining) and must never be
# used as a starting point when scoring click paths.
IGNORED_MAIN_MENU_TARGETS: set[str] = {
    "index-inpatient",
    "drug-info",
}

# Display label for each group folder. The ORDER of this dict is also the
# order of the "Group" dropdown options written to admin/config.yml
# (groups with no pages are skipped; unknown groups are appended at the end).
GROUP_LABELS: dict[str, str] = {
    "main-menu": "Main Menu",
    # Syndromes and Diseases
    "bone-joint-muscle-infections": "Bone, Muscle & Joint Infections",
    "cardiovascular": "Cardiovascular",
    "cns": "Central Nervous System",
    "gi-intraabdominal": "GI & Intraabdominal",
    "head-and-neck": "Head and Neck",
    "lung-and-mediastinum": "Lungs & Mediastinum",
    "ssti-main-menu": "Skin & Soft Tissue Infections",
    "system-infectious-diseases": "Systemic Infections",
    "genitourinary": "Urogenital",
    # Organisms
    "organisms": "Organisms",
    # General and Miscellaneous
    "dermatologic-surgery-guidelines": "Dermatological Guidelines",
    "device-related-infections": "Device-Related Infections",
    "hiv-aids": "HIV / AIDS",
    "immunocompromised-patient": "Immunocompromised Patients",
    "tpoxx-monkeypox-treatment": "MPox Treatment",
    "prevention-of-infection": "Prevention of Infection",
    "recommended-immunizations": "Recommended Adult Immunizations",
    "surgical-antimicrobial-prophylaxis": "Surgical Antimicrobial Prophylaxis",
    "surgical-site-infections": "Surgical Site Infections",
    "bispecific-antibody": "Bispecific Antibody",
    # Help
    "help-page": "Help & Resources",
    # Important Antimicrobial Information
    "important-antimicrobial": "Important Antimicrobial Information",
    # General fallback
    FALLBACK_GROUP: "General / Miscellaneous",
}

# Group "families" used by group_rank() to break ties between groups that a
# page can reach. Lower rank wins (disease > organism > general > ... ).
DISEASE_PRIORITY_GROUPS = {
    "bone-joint-muscle-infections",
    "cardiovascular",
    "cns",
    "gi-intraabdominal",
    "head-and-neck",
    "lung-and-mediastinum",
    "ssti-main-menu",
    "system-infectious-diseases",
    "genitourinary",
}
ORGANISM_GROUPS = {"organisms"}
GENERAL_MISC_GROUPS = {
    "dermatologic-surgery-guidelines",
    "device-related-infections",
    "hiv-aids",
    "immunocompromised-patient",
    "tpoxx-monkeypox-treatment",
    "prevention-of-infection",
    "recommended-immunizations",
    "surgical-antimicrobial-prophylaxis",
    "surgical-site-infections",
    "bispecific-antibody",
}


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: group assignment
# ══════════════════════════════════════════════════════════════════════════════

def group_rank(group: str) -> int:
    """Tie-break priority between groups (lower is preferred)."""
    # Prefer disease/syndrome lineage even if it takes more clicks.
    if group in DISEASE_PRIORITY_GROUPS:
        return 0
    if group in ORGANISM_GROUPS:
        return 1
    if group in GENERAL_MISC_GROUPS:
        return 2
    if group == "important-antimicrobial":
        return 3
    if group == "help-page":
        return 4
    if group == FALLBACK_GROUP:
        return 5
    return 6


def pick_best_group(scores: dict[str, tuple[int, int]]) -> str:
    """Choose the winning group from {group: (click_depth, main_menu_order)}.

    Order of preference: group family rank, then fewest clicks from the main
    menu section, then earliest main-menu section, then group name (so the
    result is deterministic).
    """
    return min(scores, key=lambda g: (group_rank(g), scores[g][0], scores[g][1], g))


def find_link_targets(text: str) -> list[str]:
    """Return the target of every markdown link in `text`, in order."""
    return [target for _, target in MARKDOWN_LINK_RE.findall(text)]


def score_groups_by_click_path(
    combined_pages: dict[str, dict],
    main_menu_text: str,
    by_name: dict[str, dict],
) -> dict[str, dict[str, tuple[int, int]]]:
    """Breadth-first walk from each main-menu section through markdown links.

    Returns {page_id: {group: (shortest_click_depth, main_menu_order)}} so each
    page knows every group it can be reached from and how directly.
    """
    # Adjacency = markdown links between combined pages (actual click paths).
    adjacency: dict[str, set[str]] = {
        pid: {t for t in find_link_targets(page.get("Text", "")) if t in combined_pages}
        for pid, page in combined_pages.items()
    }

    # Each main-menu link that maps to a group is a BFS starting point.
    roots: list[tuple[str, int, str]] = []  # (group, main_menu_order, root_page_id)
    for order, target in enumerate(find_link_targets(main_menu_text)):
        if target in IGNORED_MAIN_MENU_TARGETS:
            continue
        group = MAIN_MENU_SECTION_GROUPS.get(target)
        if group and target in by_name:
            roots.append((group, order, target))

    scores: dict[str, dict[str, tuple[int, int]]] = {}
    for group, order, root_pid in roots:
        queue: deque[tuple[str, int]] = deque([(root_pid, 0)])
        visited: set[str] = set()
        while queue:
            pid, depth = queue.popleft()
            if pid in visited:
                continue
            visited.add(pid)

            page_scores = scores.setdefault(pid, {})
            best = page_scores.get(group)
            if best is None or (depth, order) < best:
                page_scores[group] = (depth, order)

            for nxt in adjacency.get(pid, ()):
                if nxt not in visited:
                    queue.append((nxt, depth + 1))
    return scores


def assign_groups(
    combined_pages: dict[str, dict],
    main_menu_id: str,
    scores: dict[str, dict[str, tuple[int, int]]],
) -> dict[str, str]:
    """Return {page_id: group_folder} for every combined page.

    Precedence (first match wins):
      1. The main menu itself          -> MAIN_MENU_GROUP
      2. Ignored index pages           -> FALLBACK_GROUP
      3. Explicit MAIN_MENU_SECTION_GROUPS entry
      4. Best click-path group (pick_best_group)
      5. Unreachable pages             -> FALLBACK_GROUP
    """
    page_group: dict[str, str] = {}
    for pid in combined_pages:
        if pid == main_menu_id:
            page_group[pid] = MAIN_MENU_GROUP
        elif pid in IGNORED_MAIN_MENU_TARGETS:
            page_group[pid] = FALLBACK_GROUP
        elif pid in MAIN_MENU_SECTION_GROUPS:
            page_group[pid] = MAIN_MENU_SECTION_GROUPS[pid]
        elif scores.get(pid):
            page_group[pid] = pick_best_group(scores[pid])
        else:
            page_group[pid] = FALLBACK_GROUP
    return page_group


def ordered_group_folders(page_group: dict[str, str]) -> list[str]:
    """Groups that have pages: known groups in GROUP_LABELS order, then any extras."""
    used = set(page_group.values())
    ordered = [g for g in GROUP_LABELS if g in used]
    ordered.extend(sorted(g for g in used if g not in GROUP_LABELS))
    return ordered


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: page titles and navigation numbering
# ══════════════════════════════════════════════════════════════════════════════

LEGACY_NAV_SUFFIX_RE = re.compile(r"(?:\s*\(navigation\)\s*)+$", re.IGNORECASE)
LEGACY_NAV_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.\s*")


def strip_nav_prefixes_and_suffixes(title: str) -> str:
    """Remove legacy numeric/nav markers so export owns the numbering format.

    "3. Foo (Navigation)" -> "Foo"
    """
    cleaned = LEGACY_NAV_SUFFIX_RE.sub("", (title or "").strip())
    while True:
        updated = LEGACY_NAV_NUMBER_RE.sub("", cleaned, count=1)
        if updated == cleaned:
            break
        cleaned = updated.strip()
    return cleaned.strip()


def build_export_rows(
    combined_pages: dict[str, dict],
    page_group: dict[str, str],
    scores: dict[str, dict[str, tuple[int, int]]],
) -> list[dict]:
    """One row per page with the data needed to title/number/write it."""
    rows = []
    for pid, page in combined_pages.items():
        raw_term1 = page.get("Term1") or page.get("Name") or pid
        is_primary_nav = pid in MAIN_MENU_SECTION_GROUPS
        # Pages whose old title carried "(Navigation)" or a "1.2." prefix are
        # navigation pages too, even if not linked from the main menu.
        has_legacy_nav_marker = bool(
            re.search(r"\(navigation\)", raw_term1, flags=re.IGNORECASE)
            or LEGACY_NAV_NUMBER_RE.match(raw_term1)
        )
        rows.append({
            "pid": pid,
            "page": page,
            "group": page_group.get(pid, FALLBACK_GROUP),
            "term1": strip_nav_prefixes_and_suffixes(raw_term1) or pid,
            # Shallowest click depth across all reachable groups (sort key).
            "tree_order": min((v[0] for v in scores.get(pid, {}).values()), default=10**9),
            "is_primary_nav": is_primary_nav,
            "is_nav": is_primary_nav or has_legacy_nav_marker,
        })
    return rows


def number_nav_pages(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Return {group: {page_id: 1-based number}} for navigation pages.

    Within each group, main-menu sections come first, then the rest by click
    depth, then title, then page id.
    """
    numbers: dict[str, dict[str, int]] = {}
    for group in sorted({row["group"] for row in rows}):
        nav_rows = [row for row in rows if row["group"] == group and row["is_nav"]]
        nav_rows.sort(key=lambda row: (
            0 if row["is_primary_nav"] else 1,
            row["tree_order"],
            row["term1"].lower(),
            row["pid"],
        ))
        numbers[group] = {row["pid"]: idx for idx, row in enumerate(nav_rows, start=1)}
    return numbers


# ══════════════════════════════════════════════════════════════════════════════
# Step 3: write page files
# ══════════════════════════════════════════════════════════════════════════════

def ensure_path_safe(group_folder: str, page_id: str) -> str:
    """Shorten page_id (adding a hash suffix) so the file path stays under the
    Windows 260-character limit."""
    base_path = str(CMS_ROOT / group_folder / "")
    json_suffix = ".json"
    # Windows limit is 260 chars; use 240 as a safety margin.
    max_id_len = max(50, 240 - len(base_path) - len(json_suffix))
    if len(page_id) > max_id_len:
        digest = hashlib.md5(page_id.encode()).hexdigest()[:6]
        page_id = page_id[: max_id_len - 7] + "-" + digest
    return page_id


def write_page_files(rows: list[dict], nav_numbers: dict[str, dict[str, int]]) -> int:
    """Write cms-data/<station>/pages/<group>/<page-id>.json; returns the count."""
    CMS_ROOT.mkdir(parents=True, exist_ok=True)

    # Remove stale generated files so recategorized pages do not remain in old
    # group folders after re-export.
    for old_page_file in CMS_ROOT.glob("*/*.json"):
        old_page_file.unlink()

    written = 0
    for row in rows:
        pid, page, group = row["pid"], row["page"], row["group"]
        group_dir = CMS_ROOT / group
        group_dir.mkdir(parents=True, exist_ok=True)

        # Navigation pages are numbered sequentially within each clinical group.
        nav_number = nav_numbers.get(group, {}).get(pid)
        display_term1 = (
            f"{nav_number}. {row['term1']} (Navigation)"
            if nav_number is not None
            else row["term1"]
        )

        # Only CMS-relevant fields are exported (no LinkTargets).
        page_record: dict = {
            "PageID": pid,
            "Group": group,
            "Term1": display_term1,
            "Term2": page.get("Term2", ""),
            "Text": page.get("Text", ""),
            "Inpt": page.get("Inpt", ""),
        }
        # Preserve cross-tab refs if present (transition period).
        for field in ("Outpt", "ERUC"):
            if page.get(field):
                page_record[field] = page[field]

        out_path = group_dir / f"{ensure_path_safe(group, pid)}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(page_record, f, indent=2, ensure_ascii=False)
            f.write("\n")
        written += 1
    return written


# ══════════════════════════════════════════════════════════════════════════════
# Step 4: generate admin/config.yml
# ══════════════════════════════════════════════════════════════════════════════

# Field definitions shared by the station collection. "__GROUP_OPTIONS__" is
# replaced with the generated select options for the Group field.
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
      - label: "Source Inpatient Menu (read-only)"
        name: Inpt
        widget: string
        required: false
        hint: "Legacy VistA inpatient source menu. Do not edit."
"""

ABX_LINKS_COLLECTION = """\
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

SITE_SETTINGS_COLLECTION = """\
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


def make_group_options_yaml(group_folders: list[str]) -> str:
    """Build the YAML `options:` list for the Group select field."""
    return "\n".join(
        f'          - {{ label: "{GROUP_LABELS.get(folder, folder)}", value: "{folder}" }}'
        for folder in group_folders
    )


def build_station_collection(group_folders: list[str]) -> str:
    """YAML for the single editable collection that holds all station pages."""
    fields_yaml = FIELD_BLOCK.replace("__GROUP_OPTIONS__", make_group_options_yaml(group_folders))
    return f"""\
  - label: "{STATION_ID}"
    name: "001tes_all_pages"
    folder: "cms-data/{STATION_ID}/pages"
    path: "{{{{fields.Group}}}}/{{{{fields.PageID}}}}"
    create: true
    format: json
    extension: json
    editor:
      preview: false
{fields_yaml}"""


def write_admin_config(group_folders: list[str]) -> None:
    """Rewrite the `collections:` section of admin/config.yml.

    Everything before `collections:` (backend, publish_mode, site_url,
    media_folder, editor settings) is preserved as-is.
    """
    existing_yml = ADMIN_CONFIG.read_text(encoding="utf-8")
    header_end = existing_yml.find("\ncollections:")
    if header_end == -1:
        print("ERROR: could not find 'collections:' in config.yml")
        raise SystemExit(1)

    new_config = existing_yml[:header_end] + "\ncollections:\n"
    new_config += ABX_LINKS_COLLECTION + "\n"
    new_config += SITE_SETTINGS_COLLECTION + "\n"
    new_config += build_station_collection(group_folders) + "\n"
    ADMIN_CONFIG.write_text(new_config, encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    with open(JSON_PATH, encoding="utf-8") as f:
        menus = json.load(f)["menus"]
    by_name: dict[str, dict] = {m["Name"]: m for m in menus}

    # Combined pages are the ones with an Inpt (inpatient source) pointer.
    # The combined main menu is always included, even if it has no Inpt.
    combined_pages: dict[str, dict] = {m["Name"]: m for m in menus if m.get("Inpt")}
    main_menu_id = MAIN_MENU_ID if MAIN_MENU_ID in by_name else LEGACY_MAIN_MENU_ID
    combined_pages[main_menu_id] = by_name.get(main_menu_id, {})
    print(f"Combined pages to export: {len(combined_pages)}")

    main_menu = by_name.get(main_menu_id)
    if not main_menu:
        print("ERROR: combined main menu not found (expected main-menu or inpt-main).")
        raise SystemExit(1)

    scores = score_groups_by_click_path(combined_pages, main_menu.get("Text", ""), by_name)
    page_group = assign_groups(combined_pages, main_menu_id, scores)

    group_counts: dict[str, int] = {}
    for group in page_group.values():
        group_counts[group] = group_counts.get(group, 0) + 1
    print("Group assignment summary:")
    for group in sorted(group_counts):
        print(f"  {group} ({GROUP_LABELS.get(group, group)}): {group_counts[group]} pages")

    rows = build_export_rows(combined_pages, page_group, scores)
    written = write_page_files(rows, number_nav_pages(rows))
    print(f"Page files written: {written}")

    write_admin_config(ordered_group_folders(page_group))
    print(f"admin/config.yml updated with 1 station collection ({STATION_ID})")
    print("Export complete.")


if __name__ == "__main__":
    main()
