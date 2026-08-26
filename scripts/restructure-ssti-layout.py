#!/usr/bin/env python3
"""
Restructure SSTI main menu to have three-column layout like Minneapolis.
Maps Minneapolis structure to test station combined page PageIDs.
"""

import json
import sys

def build_ssti_three_column():
    """Build the three-column SSTI main menu structure."""
    return [
        # Row 1: Headers
        {"Row": 3, "Column": 1, "Text": "Mild, Non-purulent", "Header": 1},
        {"Row": 3, "Column": 2, "Text": "Purulent SSTI", "Header": 1},
        {"Row": 3, "Column": 3, "Text": "Complex SSTI", "Header": 1},
        
        # Row 1 content
        {"Row": 4, "Column": 1, "Item": "cellulitis", "Text": "Cellulitis & erysipelas"},
        {"Row": 4, "Column": 2, "Text": "INCLUDING:"},
        {"Row": 4, "Column": 3, "Item": "surg-surgical-site-infect", "Text": "Surgical site infections (SSI)"},
        
        # Row 2 content (Purulent items)
        {"Row": 5, "Column": 2, "Text": "Cutaneous Abscess"},
        {"Row": 6, "Column": 2, "Text": "Furuncles"},
        {"Row": 7, "Column": 2, "Text": "Carbuncles"},
        {"Row": 8, "Column": 2, "Text": "Other SSTI with pus present"},
        
        # Purulent link
        {"Row": 9, "Column": 2, "Item": "ssti-purulent-infections", "Text": "[Click here for above]"},
        
        # Perianal link
        {"Row": 10, "Column": 2, "Item": "perianal-anorectal-abscess", "Text": "Perianal/anorectal abscess"},
        
        # Row 3: Subheaders
        {"Row": 12, "Column": 1, "Text": "Diabetic Foot Infections", "Header": 1},
        {"Row": 12, "Column": 2, "Text": "Necrotizing SSTI", "Header": 1},
        {"Row": 12, "Column": 3, "Text": "Decubitus Ulcers", "Header": 1},
        
        # Row 3 content
        {"Row": 13, "Column": 1, "Item": "foot-ulcer-w-infect", "Text": "Foot ulcer in patient with diabetes mellitus"},
        {"Row": 13, "Column": 2, "Item": "necrotizing-infections", "Text": "[Click here]"},
        {"Row": 13, "Column": 3, "Item": "decubitus-ulcers", "Text": "[Click here]"},
        
        # Row 4: Viral/Fungal/Misc subheaders
        {"Row": 15, "Column": 1, "Text": "Viral Skin Infections", "Header": 1},
        {"Row": 15, "Column": 2, "Text": "Fungal Skin Infections", "Header": 1},
        {"Row": 15, "Column": 3, "Text": "Miscellaneous", "Header": 1},
        
        # Row 4 content
        {"Row": 16, "Column": 1, "Item": "viral-ssti", "Text": "[Click here]"},
        {"Row": 16, "Column": 2, "Item": "ssti-fungal", "Text": "[Click here]"},
        {"Row": 16, "Column": 3, "Item": "acne", "Text": "Acne"},
        
        # Row 5 content (Column 3 items)
        {"Row": 17, "Column": 3, "Item": "erythrasma", "Text": "Erythrasma"},
        {"Row": 18, "Column": 3, "Item": "folliculitis", "Text": "Folliculitis"},
        
        # Row 6: Dermatology/Bite Wounds
        {"Row": 18, "Column": 1, "Text": "Bite Wounds", "Header": 1},
        {"Row": 18, "Column": 2, "Text": "Dermatology Post-Op Infection", "Header": 1},
        
        # Row 6 content
        {"Row": 19, "Column": 1, "Text": "Animal Bite"},
        {"Row": 19, "Column": 2, "Item": "dermatologic-surgery-guidelines", "Text": "[Click here]"},
        {"Row": 19, "Column": 3, "Item": "impetigo", "Text": "Impetigo"},
        
        # Row 7 content
        {"Row": 20, "Column": 1, "Text": "Human Bite"},
        {"Row": 20, "Column": 3, "Item": "lyme-disease", "Text": "Lyme Disease"},
        
        # Row 8 content
        {"Row": 21, "Column": 1, "Item": "bite-wounds", "Text": "[Click here for above]"},
        {"Row": 21, "Column": 3, "Item": "hidradenitis-suppurativa", "Text": "Hidradenitis Suppurativa"},
        
        # Row 9 content
        {"Row": 22, "Column": 3, "Item": "rosacea", "Text": "Rosacea"},
        
        # Row 10: Bed Bugs section
        {"Row": 23, "Column": 1, "Text": "Bed Bugs, Lice, Scabies", "Header": 1},
        {"Row": 23, "Column": 3, "Item": "paronychia", "Text": "Paronychia"},
        
        # Row 11 content
        {"Row": 24, "Column": 1, "Item": "ssti-bed-bugs-lice-scabies", "Text": "[Click here]"},
        
        # Help link at top
        {"Row": 1, "Column": 1, "Item": "general-information-inpatient", "Text": "Help Information"},
    ]

def restructure_omjson():
    """Load TestStationOMJSON, restructure ssti-main-menu, and save."""
    
    # Load data
    with open("stations/001-TestStation/TestStationOMJSON.json", "r", encoding="utf-8") as f:
        omjson = json.load(f)
    
    # Data is wrapped in {menus: [...]}
    data = omjson.get("menus", [])
    
    # Find ssti-main-menu entry
    ssti_idx = None
    for i, entry in enumerate(data):
        if entry.get("Name") == "ssti-main-menu":
            ssti_idx = i
            break
    
    if ssti_idx is None:
        print("ERROR: ssti-main-menu not found in TestStationOMJSON.json")
        sys.exit(1)
    
    # Get current entry to preserve some fields
    old_entry = data[ssti_idx]
    
    # Build new structure
    new_entry = {
        "Name": "ssti-main-menu",
        "Term1": "Skin and Soft Tissue Infections",
        "Term2": "SSTI",
        "Text": "## Skin and Soft Tissue Infections\n\nInfection management options organized by infection type. Select your clinical scenario from the three-column menu below.\n\n### Column 1: Mild, Non-Purulent Infections\n- Cellulitis & erysipelas\n- Diabetic foot infections\n- Viral skin infections\n- Bite wounds\n- Bed bugs, lice, scabies\n\n### Column 2: Purulent Infections & Complications\n- Purulent SSTI (abscesses, furuncles, carbuncles)\n- Necrotizing SSTI (aggressive infections requiring surgery)\n- Fungal skin infections\n- Dermatology post-op infections\n\n### Column 3: Complex & Specialized\n- Surgical site infections\n- Decubitus ulcers (pressure ulcers)\n- Miscellaneous (acne, rosacea, erythrasma, folliculitis, impetigo, lyme disease, hidradenitis suppurativa, paronychia)",
        "Contents": build_ssti_three_column(),
        "LinkTargets": [
            {"Text": "Help Information", "Item": "general-information-inpatient"},
            {"Text": "Cellulitis & erysipelas", "Item": "cellulitis"},
            {"Text": "Surgical site infections (SSI)", "Item": "surg-surgical-site-infect"},
            {"Text": "[Click here for above]", "Item": "ssti-purulent-infections"},
            {"Text": "Perianal/anorectal abscess", "Item": "perianal-anorectal-abscess"},
            {"Text": "Foot ulcer in patient with diabetes mellitus", "Item": "foot-ulcer-w-infect"},
            {"Text": "Necrotizing infections", "Item": "necrotizing-infections"},
            {"Text": "Decubitus ulcers", "Item": "decubitus-ulcers"},
            {"Text": "Viral SSTI Submenu", "Item": "viral-ssti"},
            {"Text": "Fungal SSTI", "Item": "ssti-fungal"},
            {"Text": "Acne", "Item": "acne"},
            {"Text": "Erythrasma", "Item": "erythrasma"},
            {"Text": "Folliculitis", "Item": "folliculitis"},
            {"Text": "Bite wounds", "Item": "bite-wounds"},
            {"Text": "Dermatology Recommendations", "Item": "dermatologic-surgery-guidelines"},
            {"Text": "Impetigo", "Item": "impetigo"},
            {"Text": "Lyme Disease", "Item": "lyme-disease"},
            {"Text": "Hidradenitis Suppurativa", "Item": "hidradenitis-suppurativa"},
            {"Text": "Rosacea", "Item": "rosacea"},
            {"Text": "Paronychia", "Item": "paronychia"},
            {"Text": "Bed bugs, lice, scabies", "Item": "ssti-bed-bugs-lice-scabies"},
        ],
        "Inpt": "ORZID2 GMENU SSTI MAIN MENU",
        "Outpt": "ORZID3 GMENU SSTI MAIN MENU"
    }
    
    # Replace in data
    data[ssti_idx] = new_entry
    
    # Write back with menus wrapper
    omjson["menus"] = data
    with open("stations/001-TestStation/TestStationOMJSON.json", "w", encoding="utf-8") as f:
        json.dump(omjson, f, indent=2)
    
    print("✓ Restructured ssti-main-menu with three-column layout")
    print(f"  - Added Contents array with {len(new_entry['Contents'])} entries")
    print(f"  - Updated LinkTargets ({len(new_entry['LinkTargets'])} links)")
    print(f"  - Ensured all PageIDs point to combined guidance pages")

if __name__ == "__main__":
    restructure_omjson()
