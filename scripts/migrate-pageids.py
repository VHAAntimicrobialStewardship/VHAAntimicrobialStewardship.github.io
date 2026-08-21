"""
scripts/migrate-pageids.py

Migrates all combined guidance pages to use immutable slug-based PageIDs:
  - Combined page Name becomes PageID (kebab-case slug)
  - Term1 set to original display title (search/display label)
  - Text links rewritten: combined->combined targets updated to PageID slug
  - LinkTargets updated: Key removed for combined->combined, kept for VistA orders
  - Combined cross-refs on inpatient pages updated to PageID
  - HTML combinedMenu constant updated

Safe to re-run: exits if inpt-main already exists in data.
"""

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
JSON_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"
HTML_PATH = ROOT / "stations" / "001-TestStation" / "TestStationCDSS.html"
COMBINED_MAIN_DISPLAY = "INPT MAIN"


def to_page_id(display_name: str) -> str:
    """Convert display name to stable immutable PageID slug."""
    slug = display_name.lower()
    slug = re.sub(r"[\s/]", "-", slug)       # spaces and / -> hyphens
    slug = re.sub(r"[^a-z0-9\-]", "", slug)  # strip everything else
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "page"


with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

menus = data["menus"]

# Guard: already migrated if inpt-main exists
if any(m["Name"] == "inpt-main" for m in menus):
    print("Already migrated (inpt-main found). Skipping.")
    raise SystemExit(0)

# ── Identify all combined pages ───────────────────────────────────────────────
combined_display_names: set[str] = set()
for m in menus:
    if isinstance(m.get("Combined"), str) and m["Combined"].strip():
        combined_display_names.add(m["Combined"])
    if isinstance(m.get("Inpt"), str) and m["Inpt"].strip():
        combined_display_names.add(m["Name"])

print(f"Combined pages identified: {len(combined_display_names)}")

# ── Generate PageIDs (collision-safe) ─────────────────────────────────────────
page_id_map: dict[str, str] = {}  # display_name -> page_id
used_ids: set[str] = set()

for display_name in sorted(combined_display_names):
    base = to_page_id(display_name)
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    page_id_map[display_name] = candidate
    used_ids.add(candidate)

print(f"PageIDs generated: {len(page_id_map)}")
print("Sample mappings:")
for dn, pid in list(page_id_map.items())[:6]:
    print(f"  '{dn}' -> '{pid}'")

# ── Build key->item map from current LinkTargets BEFORE any changes ───────────
# Required to rewrite text links that use old ORZC-slug Keys
key_to_item: dict[str, str] = {}
for m in menus:
    for lt in m.get("LinkTargets", []):
        key = (lt.get("Key") or "").strip()
        item = (lt.get("Item") or "").strip()
        if key and item:
            key_to_item[key] = item

print(f"Key->Item entries catalogued: {len(key_to_item)}")


def rewrite_text_links(text: str) -> str:
    """
    Rewrite markdown link targets in combined page text:
    - If target is an old ORZC-slug Key that maps to a combined page -> replace with PageID
    - External URLs, VistA-order keys -> leave unchanged
    """
    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def replace(m: re.Match) -> str:
        label = m.group(1)
        target = m.group(2).strip()

        # Already a PageID (direct page lookup will work) -> keep
        if target in used_ids:
            return f"[{label}]({target})"

        # External URL -> keep
        if target.lower().startswith(("http://", "https://")):
            return m.group(0)

        # Old-format Key that resolves to a combined page -> replace with PageID
        resolved_item = key_to_item.get(target)
        if resolved_item and resolved_item in page_id_map:
            return f"[{label}]({page_id_map[resolved_item]})"

        # VistA order Key or unknown -> leave unchanged (Key kept in LinkTargets)
        return m.group(0)

    return link_re.sub(replace, text)


# ── Step 1: Rename combined pages ─────────────────────────────────────────────
name_to_menu = {m["Name"]: m for m in menus}
renamed = 0

for display_name, page_id in page_id_map.items():
    menu = name_to_menu.get(display_name)
    if not menu:
        print(f"  WARNING: page not found in JSON: '{display_name}'")
        continue
    # Set Term1 to display title if empty (used for search dropdown)
    if not menu.get("Term1"):
        menu["Term1"] = display_name
    # Rewrite text links before renaming
    if menu.get("Text"):
        menu["Text"] = rewrite_text_links(menu["Text"])
    # Rename
    menu["Name"] = page_id
    renamed += 1

print(f"Pages renamed: {renamed}")

# ── Step 2: Update LinkTargets across all pages ───────────────────────────────
links_to_combined = 0
keys_removed = 0
keys_kept = 0

for m in menus:
    new_lt = []
    for lt in m.get("LinkTargets", []):
        lt = dict(lt)
        item = lt.get("Item", "")
        key = lt.get("Key", "")

        if item in page_id_map:
            # combined->combined: update Item to PageID, remove Key
            lt["Item"] = page_id_map[item]
            if "Key" in lt:
                del lt["Key"]
                keys_removed += 1
            links_to_combined += 1
        else:
            # VistA order or non-combined: keep Key (text links still rely on it)
            if key:
                keys_kept += 1

        new_lt.append(lt)
    m["LinkTargets"] = new_lt

print(f"LinkTargets updated to PageID: {links_to_combined}")
print(f"Keys removed (combined->combined): {keys_removed}")
print(f"Keys kept (VistA/order links): {keys_kept}")

# ── Step 3: Update Combined cross-refs on inpatient pages ────────────────────
cross_refs = 0
for m in menus:
    old = m.get("Combined")
    if isinstance(old, str) and old in page_id_map:
        m["Combined"] = page_id_map[old]
        cross_refs += 1

print(f"Combined cross-refs updated: {cross_refs}")

# ── Duplicate name check ──────────────────────────────────────────────────────
counts = Counter(m["Name"] for m in menus)
dupes = [(n, c) for n, c in counts.items() if c > 1]
if dupes:
    print(f"\nWARNING: {len(dupes)} duplicate Names after migration:")
    for n, c in dupes[:10]:
        print(f"  '{n}' x{c}")
else:
    print("No duplicate Names. Clean.")

# ── Save ──────────────────────────────────────────────────────────────────────
with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

# ── Update HTML combinedMenu constant ─────────────────────────────────────────
combined_main_id = page_id_map.get(COMBINED_MAIN_DISPLAY)
if combined_main_id:
    html = HTML_PATH.read_text(encoding="utf-8")
    old_val = "const combinedMenu = 'INPT MAIN';"
    new_val = f"const combinedMenu = '{combined_main_id}';"
    if old_val in html:
        html = html.replace(old_val, new_val)
        HTML_PATH.write_text(html, encoding="utf-8")
        print(f"HTML combinedMenu -> '{combined_main_id}'")
    else:
        # Try without semicolon
        old_val2 = "const combinedMenu = 'INPT MAIN'"
        new_val2 = f"const combinedMenu = '{combined_main_id}'"
        if old_val2 in html:
            html = html.replace(old_val2, new_val2)
            HTML_PATH.write_text(html, encoding="utf-8")
            print(f"HTML combinedMenu -> '{combined_main_id}'")
        else:
            print("WARNING: Could not locate combinedMenu const in HTML")

print("\nPhase 2 complete.")
print(f"Total menus: {len(menus)}")
