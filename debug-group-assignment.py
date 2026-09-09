#!/usr/bin/env python3
"""Debug group assignment for new combined pages."""
import json
import re

with open("stations/001-TestStation/TestStationOMJSON.json", encoding="utf-8") as f:
    data = json.load(f)

menus = data["menus"]
by_name = {m["Name"]: m for m in menus}

# New combined pages created today
new_pages = [
    "abscess-submenu",
    "colonized-wounds",
    "fever-of-unk-origin",
    "foot-ulcer-with-dm",
    "infect-diarrhea-gastro",
    "m.-avium-intracellulare",
    "osteomyelitis",
    "peritonitis-submenu",
]

# For each new page, find its inpatient source
print("=== New Combined Pages and Their Inpatient Sources ===\n")
for slug in new_pages:
    page = by_name.get(slug)
    if page:
        inpt_source = page.get("Inpt", "UNKNOWN")
        print(f"{slug}")
        print(f"  Inpt source: {inpt_source}")
        
        # Find pages that link to the inpatient source
        print(f"  Linked from (inpatient): ", end="")
        found_links = []
        for m in menus:
            if m.get("Name") == slug or m.get("Inpt"):  # Skip combined pages
                continue
            text = m.get("Text", "")
            if inpt_source in text:
                found_links.append(m.get("Name", "???"))
        
        if found_links:
            print(", ".join(found_links[:3]))
            if len(found_links) > 3:
                print(f"         ... and {len(found_links) - 3} more")
        else:
            print("(NONE FOUND)")
        print()
