"""
restore-combined-links.py

For each combined menu that has plain text (no markdown links), reconstructs
clickable links by matching LinkTarget labels from source inpatient/outpatient
menus against combined text.

Strategy:
  1. For each combined menu, collect candidate LinkTargets from source menus.
  2. Prefer the mapped combined sub-page target when available.
  3. Match labels to text lines (exact line match, then long-label substring).
  4. Wrap matched labels as [label](key).
  5. Populate LinkTargets on combined pages.
"""

import json
import re
from pathlib import Path

JSON_PATH = Path(r"stations/001-TestStation/TestStationOMJSON.json")
COMBINED_MAIN = "INPT MAIN"

# Menus already manually tuned; skip automatic rewrite.
SKIP_NAMES = {
    "COM-ACQ PNEUMONIA",
    COMBINED_MAIN,
}

NAV_LINK_PREFIXES = (
    "help, legend",
    "help, legend, allergy",
)
MIN_LABEL_LEN = 15

with JSON_PATH.open(encoding="utf-8") as f:
    data = json.load(f)

menus = data["menus"]
by_name = {m["Name"]: m for m in menus}
combined_name_set = {
    m.get("Combined")
    for m in menus
    if isinstance(m.get("Combined"), str) and m.get("Combined").strip()
}

link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def make_key_from_item(item_name: str) -> str:
    """Legacy helper kept for VistA-order key derivation only."""
    return (
        item_name.lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace(".", "")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
    )


def build_candidate_link_targets(combined_menu: dict) -> list:
    """Collect potential link targets for one combined menu."""
    candidates = []
    seen_texts = set()

    source_names = []
    if combined_menu.get("Inpt"):
        source_names.append(combined_menu["Inpt"])
    if combined_menu.get("Outpt"):
        source_names.append(combined_menu["Outpt"])

    for src_name in source_names:
        src = by_name.get(src_name)
        if not src:
            continue

        for lt in src.get("LinkTargets", []):
            text = (lt.get("Text") or "").strip()
            item = (lt.get("Item") or "").strip()
            key = (lt.get("Key") or "").strip()
            if not text or not item:
                continue
            if text.lower().startswith(NAV_LINK_PREFIXES):
                continue

            # Prefer mapped combined page when available.
            target_menu = by_name.get(item)
            if target_menu and target_menu.get("Combined") and target_menu["Combined"] in by_name:
                item = target_menu["Combined"]
                # PageID slug IS the item; no Key needed
            
            # Deduplicate by text label; no Key emitted for combined->combined links
            norm_text = text.lower().strip()
            if norm_text not in seen_texts:
                seen_texts.add(norm_text)
                candidates.append({"Text": text, "Item": item})

    return candidates


def restore_links(combined_menu: dict, candidates: list) -> tuple[str, list]:
    text = combined_menu.get("Text", "")
    lines = text.split("\n")
    new_lines = []
    matched_candidates = []
    matched_texts = set()

    for line in lines:
        stripped = line.strip()
        matched = False

        # Exact full-line match first.
        for lt in candidates:
            label = lt["Text"].strip()
            if len(label) < MIN_LABEL_LEN:
                continue
            if label.lower() in matched_texts:
                continue
            if stripped.lower() == label.lower():
                new_lines.append(f"[{stripped}]({lt['Key']})")
                matched_texts.add(label.lower())
                if lt not in matched_candidates:
                    matched_candidates.append(lt)
                matched = True
                break

        if not matched:
            for lt in candidates:
                label = lt["Text"].strip()
                if len(label) < MIN_LABEL_LEN:
                    continue
                if label.lower() in matched_texts:
                    continue
                if link_re.search(line):
                    continue
                idx = stripped.lower().find(label.lower())
                if idx != -1:
                    before = stripped[:idx]
                    found = stripped[idx : idx + len(label)]
                    after = stripped[idx + len(label) :]
                    new_lines.append(f"{before}[{found}]({lt['Key']}){after}")
                    matched_texts.add(label.lower())
                    if lt not in matched_candidates:
                        matched_candidates.append(lt)
                    matched = True
                    break

        if not matched:
            new_lines.append(line)

    return "\n".join(new_lines), matched_candidates


total_menus_fixed = 0
total_links_added = 0
zero_matches = []

for m in menus:
    name = m["Name"]
    # Combined pages are the ones carrying an Inpt pointer.
    if not isinstance(m.get("Inpt"), str) or not m.get("Inpt").strip():
        continue
    if name not in combined_name_set:
        continue
    if name in SKIP_NAMES:
        continue
    if m.get("LinkTargets"):
        continue

    candidates = build_candidate_link_targets(m)
    if not candidates:
        zero_matches.append(name)
        continue

    new_text, matched = restore_links(m, candidates)
    if matched:
        m["Text"] = new_text
        m["LinkTargets"] = matched
        total_menus_fixed += 1
        total_links_added += len(matched)
    else:
        zero_matches.append(name)

with JSON_PATH.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Menus with links restored : {total_menus_fixed}")
print(f"Total link targets added  : {total_links_added}")
print(f"Menus with no matches     : {len(zero_matches)}")
if zero_matches:
    print("\nNo matches (likely pure narrative text):")
    for n in zero_matches[:30]:
        print(" -", n)
