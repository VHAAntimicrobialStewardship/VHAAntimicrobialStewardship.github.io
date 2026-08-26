import json
import re
from pathlib import Path

json_path = Path(r"stations/001-TestStation/TestStationOMJSON.json")
html_path = Path(r"stations/001-TestStation/TestStationCDSS.html")

with json_path.open(encoding="utf-8") as f:
    data = json.load(f)["menus"]
by = {m["Name"]: m for m in data}

issues = []
warns = []

required_menus = [
    "ORZID2 GMENU ABX INPT MAIN",
    "ORZID3 GMENU ABX OUTPT MAIN",
    "ORZID GMENU ER/UC EMERGENCY DEPARTMENT MAIN MENU",
    "ORZC GMENU ABX INPT MAIN",
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

link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
for m in data:
    txt = m.get("Text", "")
    if not txt:
        continue

    links = link_re.findall(txt)
    if not links:
        continue

    keyset = {
        (lt.get("Key") or "").strip().lower(): lt.get("Item")
        for lt in m.get("LinkTargets", [])
        if (lt.get("Key") or "").strip()
    }
    itemset = {
        (lt.get("Item") or "").strip().lower()
        for lt in m.get("LinkTargets", [])
        if (lt.get("Item") or "").strip()
    }

    for label, target in links:
        t = target.strip()
        tl = t.lower()
        if tl.startswith("http://") or tl.startswith("https://"):
            continue
        if tl.startswith("cdss:"):
            continue
        if tl in keyset:
            continue
        if tl in itemset:
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
