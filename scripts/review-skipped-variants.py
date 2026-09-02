#!/usr/bin/env python3
"""
Second-pass review of skipped multi-version pages.

For each page with Inpt/Outpt/ERUC variants that was skipped in the first pass:
1. Check if outpatient/ER versions are identical to inpatient (or trivial variants).
2. Check if outpatient/ER text contains redirect-to-inpatient patterns.
3. If either condition is met, create a combined page from inpatient.
4. Report remaining truly multi-version pages.
"""

import json
import re
from pathlib import Path

OMJSON_PATH = Path("stations/001-TestStation/TestStationOMJSON.json")
REPORT_IN = Path("cms-data/001-TestStation/documents/missing-combined-pass-report.json")
REPORT_OUT = Path("cms-data/001-TestStation/documents/review-skipped-variants-report.json")

# Load OMJSON and prior report
with OMJSON_PATH.open(encoding="utf-8") as f:
    data = json.load(f)

with REPORT_IN.open(encoding="utf-8") as f:
    prior_report = json.load(f)

menus = data["menus"]
by_name = {m["Name"]: m for m in menus}
used_names = set(by_name.keys())

# Existing combined mapping
inpt_to_combined = {}
for m in menus:
    combined_name = (m.get("Combined") or "").strip()
    if combined_name:
        inpt_to_combined[m["Name"]] = combined_name
for m in menus:
    inpt = (m.get("Inpt") or "").strip()
    if inpt and inpt not in inpt_to_combined:
        inpt_to_combined[inpt] = m["Name"]


def slugify(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"^orzid[23]?\s+gmenu\s+abx\s+", "", s)
    s = re.sub(r"^orzid[23]?\s+gmenu\s+", "", s)
    s = re.sub(r"^orzid[23]?\s+", "", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "page"


def make_unique_slug(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    i = 2
    while f"{base}-{i}" in used:
        i += 1
    return f"{base}-{i}"


def normalize_text(text: str) -> str:
    """Normalize whitespace and line endings for comparison."""
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip().lower()


def is_redirect_to_inpatient(text: str, inpt_name: str) -> bool:
    """Check if text is a redirect/stub pointing to inpatient."""
    if not text:
        return True
    text_lower = text.lower().strip()
    # Common redirect patterns
    patterns = [
        r"refer.*inpatient",
        r"see.*inpatient",
        r"same as inpatient",
        r"not available in outpatient",
        r"outpatient.*refer",
        r"follow.*inpatient",
        r"use.*inpatient",
    ]
    for pat in patterns:
        if re.search(pat, text_lower):
            return True
    # Minimal text patterns (likely placeholders)
    if len(text_lower) < 50:
        return True
    return False


def texts_effectively_same(text1: str, text2: str) -> bool:
    """Check if two texts are effectively identical after normalization."""
    if not text1 or not text2:
        return not text1 and not text2
    t1 = normalize_text(text1)
    t2 = normalize_text(text2)
    return t1 == t2


# Process skipped pages
created_from_variants = []
still_truly_multi_version = []

for skipped_entry in prior_report["skipped_multi_version"]:
    inpt_name = skipped_entry["inpt_source"]
    outpt_name = (skipped_entry["outpt"] or "").strip()
    eruc_name = (skipped_entry["eruc"] or "").strip()

    inpt_menu = by_name.get(inpt_name)
    if not inpt_menu:
        still_truly_multi_version.append(inpt_name)
        continue

    inpt_text = inpt_menu.get("Text", "")
    outpt_menu = by_name.get(outpt_name) if outpt_name else None
    eruc_menu = by_name.get(eruc_name) if eruc_name else None

    outpt_text = outpt_menu.get("Text", "") if outpt_menu else ""
    eruc_text = eruc_menu.get("Text", "") if eruc_menu else ""

    # Check conditions for auto-creation
    # Condition 1: Outpatient same as inpatient (or not present)
    outpt_is_same_or_redirect = (
        not outpt_name
        or texts_effectively_same(inpt_text, outpt_text)
        or is_redirect_to_inpatient(outpt_text, inpt_name)
    )

    # Condition 2: ERUC same as inpatient (or not present)
    eruc_is_same_or_redirect = (
        not eruc_name
        or texts_effectively_same(inpt_text, eruc_text)
        or is_redirect_to_inpatient(eruc_text, inpt_name)
    )

    # If both variants are same/redirect, create from inpatient
    if outpt_is_same_or_redirect and eruc_is_same_or_redirect:
        # Skip if already has a combined page
        if inpt_name in inpt_to_combined:
            continue

        # Create combined page
        base_slug = slugify(inpt_menu.get("Term1") or inpt_name)
        new_page_id = make_unique_slug(base_slug, used_names)

        new_page = {
            "Name": new_page_id,
            "Term1": inpt_menu.get("Term1", ""),
            "Term2": inpt_menu.get("Term2", ""),
            "Text": inpt_menu.get("Text", ""),
            "LinkTargets": inpt_menu.get("LinkTargets", []),
            "Inpt": inpt_name,
        }
        if inpt_menu.get("Outpt"):
            new_page["Outpt"] = inpt_menu["Outpt"]
        if inpt_menu.get("ERUC"):
            new_page["ERUC"] = inpt_menu["ERUC"]

        menus.append(new_page)
        by_name[new_page_id] = new_page
        used_names.add(new_page_id)
        inpt_to_combined[inpt_name] = new_page_id
        inpt_menu["Combined"] = new_page_id

        created_from_variants.append(
            {
                "page_id": new_page_id,
                "inpt_source": inpt_name,
                "reason": "outpt_redirect_or_same"
                if outpt_is_same_or_redirect
                else "eruc_redirect_or_same",
            }
        )
    else:
        # Truly multi-version with meaningful differences
        still_truly_multi_version.append(
            {
                "inpt_source": inpt_name,
                "outpt_name": outpt_name,
                "outpt_is_different": not outpt_is_same_or_redirect,
                "eruc_name": eruc_name,
                "eruc_is_different": not eruc_is_same_or_redirect,
            }
        )

# Save OMJSON
with OMJSON_PATH.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

# Write report
REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
report_payload = {
    "review_summary": {
        "pages_reviewed": len(prior_report["skipped_multi_version"]),
        "pages_created_from_variants": len(created_from_variants),
        "pages_still_truly_multi_version": len(still_truly_multi_version),
    },
    "created_from_variants": created_from_variants,
    "still_truly_multi_version": still_truly_multi_version,
}
with REPORT_OUT.open("w", encoding="utf-8") as f:
    json.dump(report_payload, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("Review of skipped multi-version pages complete.")
print(f"Pages reviewed: {len(prior_report['skipped_multi_version'])}")
print(f"Pages created from variants: {len(created_from_variants)}")
print(f"Pages still truly multi-version: {len(still_truly_multi_version)}")

if created_from_variants:
    print("\nCreated from variants (first 15):")
    for item in created_from_variants[:15]:
        print(f"  {item['page_id']} <- {item['inpt_source']} ({item['reason']})")
    if len(created_from_variants) > 15:
        print(f"  ... and {len(created_from_variants) - 15} more")

if still_truly_multi_version:
    print("\nStill truly multi-version (first 10):")
    for item in still_truly_multi_version[:10]:
        inpt = item["inpt_source"]
        outpt_str = (
            f"Outpt differs"
            if item.get("outpt_is_different")
            else f"Outpt: {item.get('outpt_name', 'none')}"
        )
        eruc_str = (
            f"ERUC differs"
            if item.get("eruc_is_different")
            else f"ERUC: {item.get('eruc_name', 'none')}"
        )
        print(f"  {inpt} | {outpt_str} | {eruc_str}")
    if len(still_truly_multi_version) > 10:
        print(f"  ... and {len(still_truly_multi_version) - 10} more")

print(f"\nReport written: {REPORT_OUT}")
