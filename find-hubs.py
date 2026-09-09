#!/usr/bin/env python3
import json

with open("stations/001-TestStation/TestStationOMJSON.json", encoding="utf-8") as f:
    data = json.load(f)

menus = data["menus"]

# Find combined pages that are hub pages
gi_hub = next((m for m in menus if m.get("Inpt") == "ORZID2 GMENU ABX GASTROINTESTINAL"), None)
if gi_hub:
    print("GI Hub Combined Page:")
    print(f"  Name: {gi_hub['Name']}")
else:
    print("GI Hub: NOT FOUND")

index_hub = next((m for m in menus if m.get("Inpt") == "ORZID2 GMENU ABX INDEX INPATIENT"), None)
if index_hub:
    print("\nIndex Hub Combined Page:")
    print(f"  Name: {index_hub['Name']}")
else:
    print("\nIndex Hub: NOT FOUND")
