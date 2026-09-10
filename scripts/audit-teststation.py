import json
import re
from pathlib import Path

json_path = Path(r"stations/001-TestStation/TestStationOMJSON.json")
od_path = Path(r"stations/001-TestStation/TestStationODJSON.json")
html_path = Path(r"stations/001-TestStation/TestStationCDSS.html")

with json_path.open(encoding="utf-8") as f:
    data = json.load(f)["menus"]

with od_path.open(encoding="utf-8") as f:
    od_data = json.load(f)

by = {m["Name"]: m for m in data}


def normalize_comparable_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").strip().lower())


normalized_om_names = {normalize_comparable_id(m["Name"]) for m in data}
normalized_od_names = {normalize_comparable_id(m["Name"]) for m in od_data}

issues = []
warns = []

required_menus = [
    "ORZID2 GMENU ABX INPT MAIN",
    "ORZID3 GMENU ABX OUTPT MAIN",
    "ORZID GMENU ER/UC EMERGENCY DEPARTMENT MAIN MENU",
    "main-menu",
]
for required in required_menus:
    if required not in by:
        issues.append(f"Missing required menu: {required}")

for m in data:
    n = m["Name"]
    for field in ["Outpt", "ERUC", "Combined", "Inpt"]:
        t = m.get(field)
        if t and t not in by:
            issues.append(f"{n} has broken {field} reference -> {t}")

combined_names = {
    m.get("Combined")
    for m in data
    if isinstance(m.get("Combined"), str) and m.get("Combined").strip()
}
combined_menus = [
    m for m in data
    if m["Name"] in combined_names and isinstance(m.get("Inpt"), str) and m.get("Inpt").strip()
]

for m in combined_menus:
    n = m["Name"]
    txt = m.get("Text", "")
    if txt.strip().lower() in ("mimi", "mehul", "mahul", ""):
        issues.append(f"{n} has placeholder/empty text: {txt!r}")
    if not m.get("Inpt"):
        warns.append(f"{n} missing Inpt pointer")

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


def is_non_menu_link(target_lower: str) -> bool:
    if target_lower.startswith(NON_MENU_LINK_PREFIXES):
        return True
    return bool(NON_MENU_GMENU_RE.match(target_lower))


# Negative lookbehind for "!" so markdown images (![alt](src)) aren't matched
# as broken internal links -- images point to uploaded assets, not menus.
link_re = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
for m in data:
    txt = m.get("Text", "")
    if not txt:
        continue

    links = link_re.findall(txt)
    if not links:
        continue

    for label, target in links:
        t = target.strip()
        tl = t.lower()
        normalized_t = normalize_comparable_id(t)
        if tl.startswith("http://") or tl.startswith("https://"):
            continue
        if tl.startswith("cdss:"):
            continue
        if tl.startswith("/"):
            continue
        if normalized_t in normalized_om_names:
            continue
        if normalized_t in normalized_od_names:
            continue
        if is_non_menu_link(tl):
            continue
        warns.append(f"{m['Name']} unresolved link target ({t}) label={label}")

escaped_count = sum(1 for m in data if r"\[" in m.get("Text", "") or r"\]" in m.get("Text", ""))
if escaped_count:
    warns.append(f"{escaped_count} menus still contain escaped square brackets")

for m in combined_menus:
    txt = m.get("Text", "")
    if re.search(r"^##[^\s#]", txt, flags=re.MULTILINE):
        warns.append(f"{m['Name']} has heading missing space after ##")

html = html_path.read_text(encoding="utf-8")
html_checks = [
    "<button id=\"combinedButton\">Combined</button>",
    "document.getElementById('combinedButton').addEventListener('click', handleCombined);",
    "const combinedMenu =",
    "function handleCombined()",
]
for check in html_checks:
    if check not in html:
        issues.append(f"HTML missing: {check}")

print("ISSUES:", len(issues))
for item in issues[:80]:
    print(" -", item)
print()
print("WARNINGS:", len(warns))
for item in warns[:120]:
    print(" -", item)
