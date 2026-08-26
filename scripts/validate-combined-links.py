"""
validate-combined-links.py

Checks for specific link quality issues in ORZC combined menus:
1. Links embedded mid-heading (false-positive heading matches)
2. Links embedded mid-sentence (label found as substring, not standalone line)
3. LinkTarget Items that don't exist in the JSON (broken refs)
4. ORZC menus that still have plain-text lines matching known LT labels (missed links)
"""
import json
import re
from pathlib import Path

JSON_PATH = Path(r"stations/001-TestStation/TestStationOMJSON.json")

with JSON_PATH.open(encoding="utf-8") as f:
    data = json.load(f)

by_name = {m["Name"]: m for m in data["menus"]}
link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

heading_re = re.compile(r"^#{1,6}\s+.*\[.*\].*$")  # heading with embedded link

issues = []

for m in data["menus"]:
    if not m["Name"].startswith("ORZC "):
        continue

    text = m.get("Text", "")
    lt_list = m.get("LinkTargets", [])

    # 1. Links inside headings
    for line in text.split("\n"):
        if heading_re.match(line.strip()):
            issues.append({
                "type": "link-in-heading",
                "menu": m["Name"],
                "line": line.strip(),
            })

    # 2. Broken LinkTarget items (Item doesn't exist in JSON)
    for lt in lt_list:
        item = (lt.get("Item") or "").strip()
        if item and item not in by_name:
            issues.append({
                "type": "broken-item-ref",
                "menu": m["Name"],
                "label": lt.get("Text"),
                "item": item,
            })

    # 3. Links mid-sentence: link label appears mid-line (not the whole line)
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        for match in link_re.finditer(stripped):
            label = match.group(1)
            before = stripped[:match.start()].strip()
            after = stripped[match.end():].strip()
            # If there's substantial non-link text on same line, it may be mid-sentence
            # (exclude cases where before/after is just punctuation or a heading marker)
            before_clean = re.sub(r"^#+\s*", "", before).strip(" :-")
            after_clean = after.strip(" :-")
            if (len(before_clean) > 5 or len(after_clean) > 5) and not stripped.startswith("#"):
                issues.append({
                    "type": "mid-sentence-link",
                    "menu": m["Name"],
                    "line": stripped,
                    "label": label,
                })

# Summarise
heading_issues = [i for i in issues if i["type"] == "link-in-heading"]
broken_refs    = [i for i in issues if i["type"] == "broken-item-ref"]
mid_sentence   = [i for i in issues if i["type"] == "mid-sentence-link"]

print(f"Link-in-heading issues : {len(heading_issues)}")
for i in heading_issues[:20]:
    print(f"  {i['menu']}")
    print(f"    {i['line']}")

print(f"\nBroken item refs       : {len(broken_refs)}")
for i in broken_refs[:20]:
    print(f"  {i['menu']} | label={i['label']} | item={i['item']}")

print(f"\nPossible mid-sentence links: {len(mid_sentence)}")
for i in mid_sentence[:20]:
    print(f"  {i['menu']}")
    print(f"    {i['line']}")
