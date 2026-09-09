#!/usr/bin/env python3
"""Update links in hub pages from ORZID names to combined page slugs."""
import json

with open("stations/001-TestStation/TestStationOMJSON.json", encoding="utf-8") as f:
    data = json.load(f)

menus = data["menus"]

# Update gi-intraabdominal hub links
updates = {
    "gi-intraabdominal": [
        ("ORZID2 GMENU ABSCESS SUBMENU", "abscess-submenu"),
        ("ORZID2 GMENU ABX ASSOC COLITIS", "clostridiodes-difficile-infection"),
        ("ORZID2 GMENU INFECT DIARRHEA/GASTRO", "infect-diarrhea-gastro"),
        ("ORZID2 GMENU HEPATITIS SUBMENU", "hepatitis-submenu"),
        ("ORZID2 GMENU PERITONITIS SUBMENU", "peritonitis-submenu"),
    ],
    "index-inpatient": [
        # Could add others if needed
    ],
}

for page_name, link_updates in updates.items():
    for page in menus:
        if page["Name"] == page_name:
            text = page.get("Text", "")
            for old_target, new_target in link_updates:
                text = text.replace(f"]({old_target})", f"]({new_target})")
            page["Text"] = text
            print(f"Updated {page_name}")
            break

# Write back
with open("stations/001-TestStation/TestStationOMJSON.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Done!")
