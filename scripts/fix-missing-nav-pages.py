#!/usr/bin/env python3
"""
Create missing combined pages from inpatient-only sources and relink combined-page
markdown targets to the combined PageID.

Rules:
- Scan all combined pages (menus with Inpt field) for markdown links.
- If a markdown target resolves to an inpatient menu name and has no combined page:
  - Create a combined page only when no Outpt/ERUC variants exist.
  - Rewrite the markdown link target to the new PageID.
- If Outpt or ERUC variants exist, skip creation and report it.
"""

import json
import re
from pathlib import Path

OMJSON_PATH = Path("stations/001-TestStation/TestStationOMJSON.json")
REPORT_PATH = Path("cms-data/001-TestStation/documents/missing-combined-pass-report.json")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def slugify(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"^orzid2\s+gmenu\s+abx\s+", "", s)
    s = re.sub(r"^orzid2\s+gmenu\s+", "", s)
    s = re.sub(r"^orzid2\s+", "", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "page"


def has_alt_versions(menu: dict) -> bool:
    return bool((menu.get("Outpt") or "").strip() or (menu.get("ERUC") or "").strip())


def is_external_target(target: str) -> bool:
    t = (target or "").strip().lower()
    return t.startswith("http://") or t.startswith("https://") or t.startswith("cdss:")


def make_unique_slug(base: str, used_names: set[str]) -> str:
    if base not in used_names:
        return base
    i = 2
    while f"{base}-{i}" in used_names:
        i += 1
    return f"{base}-{i}"


with OMJSON_PATH.open(encoding="utf-8") as f:
    data = json.load(f)

menus: list[dict] = data["menus"]
by_name = {m["Name"]: m for m in menus}
used_names = set(by_name.keys())

# Map normalized link keys to canonical menu Items using LinkTargets metadata.
link_key_to_item: dict[str, str] = {}
for m in menus:
    for lt in m.get("LinkTargets", []) or []:
        key = (lt.get("Key") or "").strip()
        item = (lt.get("Item") or "").strip()
        if key and item:
            link_key_to_item[key.lower()] = item

# Existing inpt->combined map from cross refs (authoritative if present)
inpt_to_combined: dict[str, str] = {}
for m in menus:
    combined_name = (m.get("Combined") or "").strip()
    if combined_name:
        inpt_to_combined[m["Name"]] = combined_name

# Also infer from combined pages already in menu list.
for m in menus:
    inpt = (m.get("Inpt") or "").strip()
    if inpt and inpt not in inpt_to_combined:
        inpt_to_combined[inpt] = m["Name"]

combined_pages = [m for m in menus if (m.get("Inpt") or "").strip()]

created_pages: list[tuple[str, str]] = []  # (page_id, inpt_name)
rewired_links = 0
updated_pages = 0
skipped_multi_version: dict[str, dict] = {}

for page in combined_pages:
    text = page.get("Text", "")
    if not text:
        continue

    links = LINK_RE.findall(text)
    if not links:
        continue

    page_updated = False
    new_text = text

    for label, target in links:
        tgt = target.strip()
        if not tgt or is_external_target(tgt):
            continue

        # If target is already a known combined page ID, nothing to do.
        target_menu = by_name.get(tgt)
        if target_menu and target_menu.get("Inpt"):
            continue

        # Resolve slug-style/legacy key aliases to canonical menu Item names.
        if not target_menu:
            aliased_item = link_key_to_item.get(tgt.lower())
            if aliased_item:
                target_menu = by_name.get(aliased_item)

        # Only migrate links that currently point to an inpatient menu name.
        inpt_menu = target_menu
        if not inpt_menu:
            continue

        # If an existing combined equivalent is known, relink directly.
        inpt_name = inpt_menu["Name"]
        existing_combined = inpt_to_combined.get(inpt_name)
        if existing_combined and existing_combined in by_name:
            repl = f"[{label}]({existing_combined})"
            old = f"[{label}]({target})"
            if old in new_text and old != repl:
                new_text = new_text.replace(old, repl)
                rewired_links += 1
                page_updated = True
            continue

        if has_alt_versions(inpt_menu):
            skipped_multi_version[inpt_name] = {
                "label": label,
                "outpt": inpt_menu.get("Outpt", ""),
                "eruc": inpt_menu.get("ERUC", ""),
                "linked_from": page["Name"],
            }
            continue

        # No alternate versions: create a new combined page by copying inpatient.
        base_slug = slugify(inpt_menu.get("Term1") or inpt_menu["Name"])
        new_page_id = make_unique_slug(base_slug, used_names)

        new_page = {
            "Name": new_page_id,
            "Term1": inpt_menu.get("Term1", ""),
            "Term2": inpt_menu.get("Term2", ""),
            "Text": inpt_menu.get("Text", ""),
            "LinkTargets": inpt_menu.get("LinkTargets", []),
            "Inpt": inpt_menu["Name"],
        }
        if inpt_menu.get("Outpt"):
            new_page["Outpt"] = inpt_menu["Outpt"]
        if inpt_menu.get("ERUC"):
            new_page["ERUC"] = inpt_menu["ERUC"]

        menus.append(new_page)
        by_name[new_page_id] = new_page
        used_names.add(new_page_id)
        inpt_to_combined[inpt_menu["Name"]] = new_page_id
        inpt_menu["Combined"] = new_page_id
        created_pages.append((new_page_id, inpt_menu["Name"]))

        repl = f"[{label}]({new_page_id})"
        old = f"[{label}]({target})"
        if old in new_text:
            new_text = new_text.replace(old, repl)
            rewired_links += 1
            page_updated = True

    if page_updated and new_text != text:
        page["Text"] = new_text
        updated_pages += 1

with OMJSON_PATH.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
report_payload = {
    "combined_pages_scanned": len(combined_pages),
    "combined_pages_created": len(created_pages),
    "pages_updated": updated_pages,
    "links_rewired": rewired_links,
    "created_pages": [
        {"page_id": page_id, "inpt_source": inpt_name}
        for page_id, inpt_name in sorted(created_pages)
    ],
    "skipped_multi_version": [
        {
            "inpt_source": inpt_name,
            "label": info["label"],
            "linked_from": info["linked_from"],
            "outpt": info["outpt"],
            "eruc": info["eruc"],
        }
        for inpt_name, info in sorted(skipped_multi_version.items())
    ],
}
with REPORT_PATH.open("w", encoding="utf-8") as f:
    json.dump(report_payload, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("Full missing-combined pass complete.")
print(f"Combined pages scanned: {len(combined_pages)}")
print(f"Combined pages created: {len(created_pages)}")
print(f"Pages updated (link rewrites): {updated_pages}")
print(f"Links rewired: {rewired_links}")

if created_pages:
    print("\nCreated pages:")
    for page_id, inpt_name in sorted(created_pages):
        print(f"  {page_id} <- {inpt_name}")

if skipped_multi_version:
    print("\nSkipped (multiple versions exist across Inpt/Outpt/ER):")
    for inpt_name in sorted(skipped_multi_version):
        info = skipped_multi_version[inpt_name]
        print(
            "  "
            f"{inpt_name} | label={info['label']} | linked_from={info['linked_from']} "
            f"| Outpt={info['outpt'] or '-'} | ERUC={info['eruc'] or '-'}"
        )
else:
    print("\nSkipped (multiple versions exist across Inpt/Outpt/ER): none")

print(f"\nReport written: {REPORT_PATH}")
