"""
scripts/audit-teststation.py

Integrity gate for the station data. Run it after any structural/data rewrite
(rebuild-combined-menus.py, compile-cms.py, link edits, ...).

For each station in STATIONS it checks:
  - the combined main-menu exists
  - no legacy VistA record (Name starting "ORZ", no Inpt) is left in the OMJSON; they were
    removed on 2026-11-05 and archived in docs/legacy-archive/
  - no internal link points at a removed legacy page (orzid/orzid2/orzid3-gmenu-... target)
  - combined pages (records with Inpt) have real text (no placeholders) and "## Heading" spacing
  - every internal markdown link in page Text resolves to a page or order dialog
  - the station HTML still has the markers the runtime/pipeline depend on

Inpt/Outpt/ERUC on combined pages are kept as plain strings naming the removed legacy
records, so they are no longer checked as page references.

ISSUES are real problems (a regression if the count grows); WARNINGS are known,
non-blocking noise (e.g. links to legacy targets that are not in the data).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# (station folder, OMJSON filename, ODJSON filename, HTML filename)
# All four stations are combined-only: no Inpatient/Outpatient/ER-UC tab buttons.
STATIONS: list[tuple[str, str, str, str]] = [
    ("001-TestStation", "TestStationOMJSON.json", "TestStationODJSON.json", "TestStationCDSS.html"),
    ("541-Cleveland", "ClevelandOMJSON.json", "ClevelandODJSON.json", "ClevelandCDSS.html"),
    ("539-Cincinnati", "CincinnatiOMJSON.json", "CincinnatiODJSON.json", "CincinnatiCDSS.html"),
    ("506-AnnArbor", "AnnArborOMJSON.json", "AnnArborODJSON.json", "AnnArborCDSS.html"),
]

REQUIRED_MENUS = ["main-menu"]

# Legacy VistA page records (ORZID = ER/UC, ORZID2 = inpatient, ORZID3 = outpatient).
LEGACY_NAME_RE = re.compile(r"^ORZ")
# A link target naming one of the removed legacy pages.
LEGACY_LINK_RE = re.compile(r"^orzid\d?-gmenu-")

# Page text that means "nobody wrote this page yet".
PLACEHOLDER_TEXTS = ("mimi", "mehul", "mahul", "")

# VistA order-dialog / action-menu / text-object prefixes. These represent
# orderable items (labs, meds, consults, radiology, scheduling), order-set
# groupings, or generic-text (GTX) documents -- none of these are navigable
# CDSS content pages and will never have their own menu record, so unresolved
# links to them are expected/non-actionable noise, not broken navigation.
NON_MENU_LINK_PREFIXES = (
    "lrtz",       # LR package: lab test orders
    "lr-",
    "lr_",
    "gmrctz",     # GMRC package: consult orders
    "psjz",       # PSJ package: inpatient pharmacy orders
    "psoz",       # PSO package: outpatient pharmacy orders
    "pscz",       # PSC package: pharmacy clinic orders (e.g. vaccines)
    "pshizid",    # PSH package: pharmacy IV orders
    "psjizid",
    "psozid",
    "zzpsjizid",  # ZZ = locally created/temporary VistA order mnemonics
    "zzpsozid",
    "zzorzid",
    "raz-",       # RA package: radiology orders
    "sdz-",       # SD package: scheduling actions
    "sd-rtc",
    "orz-set-",   # explicit VistA "order set"
    "orz-nurs-",  # nursing text orders
    "orz-ap-",    # anatomic pathology orders
    "orz-min-",   # informational text reference never given its own menu (e.g. on-call schedule)
    "orz-gtx-",   # OR GTX: generic-text/document objects, not menus
    "or-gtx-",
    "test-",      # explicit dev/test artifacts
    "testing-",
)

# "GMENU" without "-abx-" is a generic VistA order/consult-grouping menu from
# another package (Consults, ED, Sepsis order sets, etc.), not CDSS clinical
# content -- CDSS's own migrated clinical-topic menus are always namespaced
# with "-abx-" (e.g. orzid2-gmenu-abx-cardiovascular).
NON_MENU_GMENU_RE = re.compile(r"^orz(id\d*)?-gmenu-(?!abx-)")

# Markdown link [label](target). Negative lookbehind for "!" so markdown images
# (![alt](src)) aren't matched as broken internal links -- images point to
# uploaded assets, not menus.
LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")

# Markers the station HTML must (or must not) contain.
# The app behaviour lives in shared/cdss-app.js; the page keeps markup + config.
SHARED_JS_PATH = ROOT / "shared" / "cdss-app.js"
SHARED_JS_TAG = '<script src="/shared/cdss-app.js"></script>'
HTML_REQUIRED = [
    "const combinedMenu =",
    SHARED_JS_TAG,
]
HTML_FORBIDDEN = [
    "<button id=\"inptButton\">Inpatient</button>",
    "<button id=\"outptButton\">Outpatient</button>",
    "<button id=\"erucButton\">ER/UC</button>",
]
# Markers the shared script must contain (checked once).
SHARED_JS_REQUIRED = [
    "onClickIfPresent('combinedButton', handleCombined);",
    "function handleCombined()",
]


def normalize_comparable_id(value: str) -> str:
    """Lower-case and strip everything except a-z/0-9 (mirrors the runtime helper)."""
    return re.sub(r"[^a-z0-9]", "", (value or "").strip().lower())


def is_non_menu_link(target_lower: str) -> bool:
    """True for link targets that are VistA orders/documents, never CDSS pages."""
    if target_lower.startswith(NON_MENU_LINK_PREFIXES):
        return True
    return bool(NON_MENU_GMENU_RE.match(target_lower))


def check_required_menus(by_name: dict) -> list[str]:
    return [f"Missing required menu: {required}" for required in REQUIRED_MENUS if required not in by_name]


def check_legacy_records(menus: list[dict]) -> list[str]:
    """Legacy records must stay deleted (compile-cms.py never recreates them, but a merge could)."""
    return [
        f"Legacy record still present: {m['Name']}"
        for m in menus
        if LEGACY_NAME_RE.match(m["Name"]) and not (m.get("Inpt") or "").strip()
    ] + [f"{m['Name']} still has a legacy Combined back-reference -> {m['Combined']}" for m in menus if m.get("Combined")]


def get_combined_menus(menus: list[dict]) -> list[dict]:
    """Combined pages are identified by their Inpt pointer."""
    return [m for m in menus if isinstance(m.get("Inpt"), str) and m.get("Inpt").strip()]


def check_combined_pages(combined_menus: list[dict]) -> tuple[list[str], list[str]]:
    """Returns (issues, warns) for placeholder/empty text and missing Inpt pointers."""
    issues = []
    warns = []
    for m in combined_menus:
        name = m["Name"]
        text = m.get("Text", "")
        if text.strip().lower() in PLACEHOLDER_TEXTS:
            issues.append(f"{name} has placeholder/empty text: {text!r}")
        if not m.get("Inpt"):
            warns.append(f"{name} missing Inpt pointer")
    return issues, warns


def find_unresolved_links(menus: list[dict], om_names: set[str], od_names: set[str]) -> tuple[list[str], list[str]]:
    """(issues, warnings) for internal markdown links whose target is not a known page/order dialog.

    An unresolved link to a removed legacy page is an issue; other unresolved links are warnings.
    """
    issues = []
    warns = []
    for m in menus:
        # Text and the optional right-hand Therapy panel both carry markdown links.
        text = (m.get("Text", "") or "") + "\n" + (m.get("Therapy", "") or "")
        if not text.strip():
            continue

        for label, target in LINK_RE.findall(text):
            t = target.strip()
            tl = t.lower()
            if tl.startswith(("http://", "https://", "cdss:", "/")):
                continue  # external, explicit cdss: target, or site-absolute path
            normalized_t = normalize_comparable_id(t)
            if normalized_t in om_names or normalized_t in od_names:
                continue
            if LEGACY_LINK_RE.match(tl):
                issues.append(f"{m['Name']} links to removed legacy page ({t}) label={label}")
                continue
            if is_non_menu_link(tl):
                continue
            warns.append(f"{m['Name']} unresolved link target ({t}) label={label}")
    return issues, warns


def check_html(html_path: Path) -> list[str]:
    """Checks the station HTML still has the markers the runtime depends on."""
    html = html_path.read_text(encoding="utf-8")
    issues = [
        f"HTML should not contain legacy tab button (combined-only station): {forbidden}"
        for forbidden in HTML_FORBIDDEN if forbidden in html
    ]
    issues += [f"HTML missing: {check}" for check in HTML_REQUIRED if check not in html]
    return issues


def check_shared_js() -> list[str]:
    """Checks shared/cdss-app.js exists and still has the markers the pipeline depends on."""
    if not SHARED_JS_PATH.exists():
        return [f"Shared script missing: {SHARED_JS_PATH.relative_to(ROOT)}"]
    js = SHARED_JS_PATH.read_text(encoding="utf-8")
    return [f"Shared JS missing: {check}" for check in SHARED_JS_REQUIRED if check not in js]


def audit_station(station_dir: str, omjson_filename: str, odjson_filename: str, html_filename: str) -> tuple[list[str], list[str]]:
    """Runs every check for one station. Returns (issues, warns)."""
    station_path = ROOT / "stations" / station_dir

    with (station_path / omjson_filename).open(encoding="utf-8") as f:
        menus = json.load(f)["menus"]
    with (station_path / odjson_filename).open(encoding="utf-8") as f:
        od_data = json.load(f)

    by_name = {m["Name"]: m for m in menus}
    om_names = {normalize_comparable_id(m["Name"]) for m in menus}
    od_names = {normalize_comparable_id(m["Name"]) for m in od_data}
    combined_menus = get_combined_menus(menus)

    issues = []
    warns = []

    issues += check_required_menus(by_name)
    issues += check_legacy_records(menus)
    combined_issues, combined_warns = check_combined_pages(combined_menus)
    issues += combined_issues
    warns += combined_warns

    link_issues, link_warns = find_unresolved_links(menus, om_names, od_names)
    issues += link_issues
    warns += link_warns

    escaped_count = sum(1 for m in menus if r"\[" in m.get("Text", "") or r"\]" in m.get("Text", ""))
    if escaped_count:
        warns.append(f"{escaped_count} menus still contain escaped square brackets")

    for m in combined_menus:
        if re.search(r"^##[^\s#]", m.get("Text", ""), flags=re.MULTILINE):
            warns.append(f"{m['Name']} has heading missing space after ##")

    issues += check_html(station_path / html_filename)

    return issues, warns


if __name__ == "__main__":
    total_issues = 0
    total_warns = 0
    shared_issues = check_shared_js()
    if shared_issues:
        print("\n=== shared/cdss-app.js ===")
        for item in shared_issues:
            print(" -", item)
    total_issues += len(shared_issues)
    for station_dir, omjson_filename, odjson_filename, html_filename in STATIONS:
        print(f"\n=== {station_dir} ===")
        issues, warns = audit_station(station_dir, omjson_filename, odjson_filename, html_filename)
        total_issues += len(issues)
        total_warns += len(warns)

        print("ISSUES:", len(issues))
        for item in issues[:80]:
            print(" -", item)
        print()
        print("WARNINGS:", len(warns))
        for item in warns[:120]:
            print(" -", item)

    print(f"\n=== TOTAL: {total_issues} issues, {total_warns} warnings across {len(STATIONS)} station(s) ===")
