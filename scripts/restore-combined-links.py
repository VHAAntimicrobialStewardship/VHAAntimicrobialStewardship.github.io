"""
restore-combined-links.py

For each ORZC combined menu that has plain text (no markdown links),
reconstructs clickable links by matching LinkTarget text labels from the
corresponding inpatient (and outpatient) source menus against the ORZC text.

Strategy:
  1. For each ORZC menu, collect candidate LinkTargets from:
       - Its inpatient counterpart (Inpt field)
       - Its outpatient counterpart (Outpt field)
  2. For each candidate, prefer the ORZC equivalent if a Combined sub-page exists.
  3. Try to match candidate label text against ORZC plain text:
       a. Exact full-line match
       b. Substring match (only when label is >=20 chars to avoid false positives)
  4. When a match is found, wrap the text with [label](key) markdown.
  5. Populate LinkTargets on the ORZC menu.

Skips:
  - The navigation "Help/legend..." header link (too generic, added separately)
  - Labels under 15 chars (too ambiguous)
  - The CAP menu (already manually corrected)
"""
import json
import re
from pathlib import Path

JSON_PATH = Path(r"stations/001-TestStation/TestStationOMJSON.json")

# Menu names that were already manually corrected - skip them
SKIP_NAMES = {
    "ORZC GMENU ABX COM-ACQ PNEUMONIA",  # already fixed
    "ORZC GMENU ABX INPT MAIN",          # main menu handled separately
}

NAV_LINK_PREFIXES = (
    "help, legend",
    "help, legend, allergy",
)

MIN_LABEL_LEN = 15  # shorter labels are too risky for substring matching

with JSON_PATH.open(encoding="utf-8") as f:
    data = json.load(f)

menus = data["menus"]
by_name = {m["Name"]: m for m in menus}

link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def slugify(name: str) -> str:
    """Convert an ORZC menu Name to a link key (lowercase, spaces→hyphens, remove special chars)."""
    return re.sub(r"[^a-z0-9\-]", "", name.lower().replace(" ", "-"))


def make_key_from_item(item_name: str) -> str:
    return item_name.lower().replace(" ", "-").replace("/", "-").replace(".", "").replace("(", "").replace(")", "").replace(",", "")


def build_candidate_link_targets(orzc_menu: dict) -> list:
    """
    Collect all potential link targets for this ORZC menu,
    preferring ORZC equivalents of sub-pages.
    Returns list of dicts with keys: Key, Text, Item
    """
    candidates = []
    seen_texts = set()

    source_names = []
    if orzc_menu.get("Inpt"):
        source_names.append(orzc_menu["Inpt"])
    if orzc_menu.get("Outpt"):
        source_names.append(orzc_menu["Outpt"])

    for src_name in source_names:
        src = by_name.get(src_name)
        if not src:
            continue
        for lt in src.get("LinkTargets", []):
            text = (lt.get("Text") or "").strip()
            item = (lt.get("Item") or "").strip()
            key  = (lt.get("Key") or "").strip()
            if not text or not item or not key:
                continue
            if text.lower().startswith(NAV_LINK_PREFIXES):
                continue

            # Prefer ORZC equivalent if one exists
            target_menu = by_name.get(item)
            if target_menu and target_menu.get("Combined") and target_menu["Combined"] in by_name:
                combined_item = target_menu["Combined"]
                # Derive key from combined name
                combined_key = make_key_from_item(combined_item)
                item = combined_item
                key  = combined_key

            # Deduplicate by text label
            norm_text = text.lower().strip()
            if norm_text not in seen_texts:
                seen_texts.add(norm_text)
                candidates.append({"Key": key, "Text": text, "Item": item})

    return candidates


def restore_links(orzc_menu: dict, candidates: list) -> tuple[str, list]:
    """
    Walk the ORZC menu text and wrap matching plain-text labels with markdown links.
    Returns (new_text, new_link_targets).
    """
    text = orzc_menu.get("Text", "")
    lines = text.split("\n")
    new_lines = []
    matched_candidates = []
    matched_texts = set()

    for line in lines:
        stripped = line.strip()
        matched = False

        for lt in candidates:
            label = lt["Text"].strip()
            if len(label) < MIN_LABEL_LEN:
                continue
            if label.lower() in matched_texts:
                continue

            # a) Exact full-line match
            if stripped.lower() == label.lower():
                new_lines.append(f"[{stripped}]({lt['Key']})")
                matched_texts.add(label.lower())
                if lt not in matched_candidates:
                    matched_candidates.append(lt)
                matched = True
                break

        if not matched:
            # b) Substring match only for longer labels (to reduce false positives)
            for lt in candidates:
                label = lt["Text"].strip()
                if len(label) < MIN_LABEL_LEN:
                    continue
                if label.lower() in matched_texts:
                    continue
                # Make sure it's not already a link in this line
                if link_re.search(line):
                    continue
                # Case-insensitive search for the label within the line
                idx = stripped.lower().find(label.lower())
                if idx != -1:
                    before = stripped[:idx]
                    found  = stripped[idx:idx+len(label)]
                    after  = stripped[idx+len(label):]
                    new_line = f"{before}[{found}]({lt['Key']}){after}"
                    new_lines.append(new_line)
                    matched_texts.add(label.lower())
                    if lt not in matched_candidates:
                        matched_candidates.append(lt)
                    matched = True
                    break

        if not matched:
            new_lines.append(line)

    return "\n".join(new_lines), matched_candidates


# Process all ORZC menus with empty LinkTargets
total_menus_fixed = 0
total_links_added = 0
zero_matches = []

for m in menus:
    name = m["Name"]
    if not name.startswith("ORZC "):
        continue
    if name in SKIP_NAMES:
        continue
    if m.get("LinkTargets"):  # already has targets
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
    print("\nNo matches (likely pure narrative text - no sub-links needed):")
    for n in zero_matches[:30]:
        print(" -", n)
