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

# 1) Core required menus
for required in [
    "ORZID2 GMENU ABX INPT MAIN",
    "ORZID3 GMENU ABX OUTPT MAIN",
    "ORZID GMENU ER/UC EMERGENCY DEPARTMENT MAIN MENU",
    "ORZC GMENU ABX INPT MAIN",
]:
    if required not in by:
        issues.append(f"Missing required menu: {required}")

# 2) Cross-ref integrity
for m in data:
    n = m["Name"]
    for field in ["Outpt", "ERUC", "Combined", "Inpt"]:
        t = m.get(field)
        if t and t not in by:
            issues.append(f"{n} has broken {field} reference -> {t}")

# 3) ORZC integrity
orzc = [m for m in data if m["Name"].startswith("ORZC ")]
for m in orzc:
    n = m["Name"]
    txt = m.get("Text", "")
    if txt.strip().lower() in ("mimi", "mehul", "mahul", ""):
        issues.append(f"{n} has placeholder/empty text: {txt!r}")
    if not m.get("Inpt"):
        warns.append(f"{n} missing Inpt pointer")

# 4) Broken markdown links in rich text (non-URL targets without key mapping)
link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
for m in data:
    txt = m.get("Text", "")
    if not txt:
        continue
    links = link_re.findall(txt)
    if not links:
        continue
    keyset = {(lt.get("Key") or "").strip().lower(): lt.get("Item") for lt in m.get("LinkTargets", [])}
    for label, target in links:
        t = target.strip()
        if t.lower().startswith("http://") or t.lower().startswith("https://"):
            continue
        if t.lower().startswith("cdss:"):
            continue
        if t.lower() not in keyset:
            warns.append(f"{m['Name']} unresolved link target key: ({t}) label={label}")

# 5) lingering escaped square brackets
escaped_count = sum(1 for m in data if r"\[" in m.get("Text", "") or r"\]" in m.get("Text", ""))
if escaped_count:
    warns.append(f"{escaped_count} menus still contain escaped square brackets")

# 6) Heading anomalies in ORZC text
for m in orzc:
    txt = m.get("Text", "")
    if re.search(r"^##[^\s#]", txt, flags=re.MULTILINE):
        warns.append(f"{m['Name']} has heading missing space after ##")

# 7) HTML wiring sanity
html = html_path.read_text(encoding="utf-8")
html_checks = [
    '<button id="combinedButton">Combined</button>',
    "document.getElementById('combinedButton').addEventListener('click', handleCombined);",
    "const combinedMenu =",
    "function handleCombined()",
]
for c in html_checks:
    if c not in html:
        issues.append(f"HTML missing: {c}")

print("ISSUES:", len(issues))
for i in issues[:80]:
    print(" -", i)
print()
print("WARNINGS:", len(warns))
for w in warns[:120]:
    print(" -", w)
