"""
Rewrite combined-page links to combined targets whenever a combined equivalent exists.

What this script does:
- Scans combined pages (menus with Inpt, plus main-menu) for markdown links and LinkTargets
- Resolves legacy target aliases using LinkTargets Key -> Item map
- If a target resolves to a page/menu that has a Combined equivalent, rewrites target to that combined PageID
- Leaves external URLs and non-resolvable targets unchanged
- Writes report: cms-data/001-TestStation/documents/rewrite-links-to-combined-report.json
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
OMJSON_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"
REPORT_PATH = ROOT / "cms-data" / "001-TestStation" / "documents" / "rewrite-links-to-combined-report.json"

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def is_external_target(target: str) -> bool:
    t = (target or "").strip().lower()
    return t.startswith("http://") or t.startswith("https://") or t.startswith("cdss:")


with OMJSON_PATH.open(encoding="utf-8") as f:
    data = json.load(f)

menus: list[dict] = data["menus"]
by_name = {m.get("Name", ""): m for m in menus}

# Combined pages are authoritative targets.
combined_pages = [m for m in menus if m.get("Inpt")]
combined_ids = {m.get("Name", "") for m in combined_pages}

# Add combined main menu id.
combined_main_id = "main-menu" if "main-menu" in by_name else "inpt-main"
if combined_main_id in by_name:
    combined_ids.add(combined_main_id)

# Build alias map from Key -> Item across all menus.
key_to_item: dict[str, str] = {}
for m in menus:
    for lt in m.get("LinkTargets", []) or []:
        key = (lt.get("Key") or "").strip()
        item = (lt.get("Item") or "").strip()
        if key and item:
            key_to_item[key] = item

# Build lookup from legacy menu name to combined id.
legacy_to_combined: dict[str, str] = {}
for m in menus:
    name = m.get("Name", "")
    combined = (m.get("Combined") or "").strip()
    if name and combined and combined in by_name:
        legacy_to_combined[name] = combined

# Also infer from combined records themselves (Inpt/Outpt/ERUC -> combined Name).
for m in combined_pages:
    cid = m.get("Name", "")
    if not cid:
        continue
    for field in ("Inpt", "Outpt", "ERUC"):
        source = (m.get(field) or "").strip()
        if source:
            legacy_to_combined[source] = cid


def resolve_to_combined(target: str) -> str:
    t = (target or "").strip()
    if not t or is_external_target(t):
        return t

    # Already combined page id.
    if t in combined_ids:
        return t

    # Direct legacy->combined mapping.
    mapped = legacy_to_combined.get(t)
    if mapped:
        return mapped

    # If target matches a menu name that has Combined cross-ref.
    menu = by_name.get(t)
    if menu:
        combined = (menu.get("Combined") or "").strip()
        if combined and combined in by_name:
            return combined

    # Resolve LinkTargets key alias to Item, then map that item.
    item = key_to_item.get(t)
    if item:
        mapped = legacy_to_combined.get(item)
        if mapped:
            return mapped
        menu = by_name.get(item)
        if menu:
            combined = (menu.get("Combined") or "").strip()
            if combined and combined in by_name:
                return combined
            if item in combined_ids:
                return item

    return t


menus_scanned = 0
menus_text_updated = 0
menus_linktargets_updated = 0
text_link_rewrites = 0
linktarget_item_rewrites = 0
unresolved_candidates = []

# Combined content surfaces only.
scan_names = {m.get("Name", "") for m in combined_pages}
if combined_main_id in by_name:
    scan_names.add(combined_main_id)

for name in sorted(scan_names):
    menu = by_name.get(name)
    if not menu:
        continue
    menus_scanned += 1

    # Rewrite markdown links in Text.
    text = menu.get("Text", "")
    text_changed = [False]

    def repl(match: re.Match) -> str:
        global text_link_rewrites
        label = match.group(1)
        target = match.group(2).strip()
        new_target = resolve_to_combined(target)

        if new_target != target:
            text_link_rewrites += 1
            text_changed[0] = True
            return f"[{label}]({new_target})"

        # Track unresolved legacy-like targets for review.
        if (
            target
            and not is_external_target(target)
            and target not in combined_ids
            and (target in legacy_to_combined or target in key_to_item or target in by_name)
        ):
            unresolved_candidates.append(
                {
                    "page": name,
                    "label": label,
                    "target": target,
                }
            )

        return match.group(0)

    new_text = LINK_RE.sub(repl, text)
    if text_changed[0]:
        menu["Text"] = new_text
        menus_text_updated += 1

    # Rewrite LinkTargets Item values.
    lt_changed = False
    for lt in menu.get("LinkTargets", []) or []:
        item = (lt.get("Item") or "").strip()
        if not item:
            continue
        new_item = resolve_to_combined(item)
        if new_item != item:
            lt["Item"] = new_item
            linktarget_item_rewrites += 1
            lt_changed = True

    if lt_changed:
        menus_linktargets_updated += 1

with OMJSON_PATH.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

# De-duplicate unresolved items for report readability.
seen_unresolved = set()
unresolved_unique = []
for row in unresolved_candidates:
    key = (row["page"], row["target"])
    if key in seen_unresolved:
        continue
    seen_unresolved.add(key)
    unresolved_unique.append(row)

report = {
    "summary": {
        "menus_scanned": menus_scanned,
        "menus_text_updated": menus_text_updated,
        "menus_linktargets_updated": menus_linktargets_updated,
        "text_link_rewrites": text_link_rewrites,
        "linktarget_item_rewrites": linktarget_item_rewrites,
        "unresolved_candidate_targets": len(unresolved_unique),
    },
    "unresolved_candidates": unresolved_unique[:1000],
}

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
with REPORT_PATH.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("Combined-link rewrite pass complete.")
print(f"Menus scanned: {menus_scanned}")
print(f"Menus with text updates: {menus_text_updated}")
print(f"Menus with LinkTargets updates: {menus_linktargets_updated}")
print(f"Text links rewritten: {text_link_rewrites}")
print(f"LinkTargets items rewritten: {linktarget_item_rewrites}")
print(f"Unresolved candidate targets: {len(unresolved_unique)}")
print(f"Report: {REPORT_PATH}")
