"""
scripts/strip-order-links.py

Strips VistA order-style markdown links from all TestStation combined CMS pages.

Combined pages should only have:
  - Navigation links to GMENU pages  (orzid2-gmenu-..., etc.)
  - Navigation links to combined PageIDs  (validated against OMJSON)
  - External URLs  (http:// / https://)
  - cdss: scheme links

Everything else (PSJ order mnemonics, ORZ SET order sets, LRTZ lab orders,
GMRCTZ consults, RAZ radiology orders, etc.) has the markdown link syntax
removed so the label text remains but is no longer a broken hyperlink.
Drug names in the resulting plain text are then auto-linked green by AbxLinks.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
CMS_ROOT = ROOT / "cms-data/001-TestStation/pages"
OMJSON_PATH = ROOT / "stations/001-TestStation/TestStationOMJSON.json"

# Build set of all known OM names (normalised to lowercase) for target validation
with open(OMJSON_PATH, encoding="utf-8") as f:
    om_menus = json.load(f)["menus"]

def _norm(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (v or "").strip().lower())

known_om_names: set[str] = {_norm(m["Name"]) for m in om_menus}


def is_keep_target(target: str) -> bool:
    """Return True if this markdown link target should be preserved."""
    t = target.strip()
    tl = t.lower()
    if not t:
        return False
    # External URLs
    if tl.startswith("http://") or tl.startswith("https://"):
        return True
    # cdss: scheme
    if tl.startswith("cdss:"):
        return True
    # Must resolve to a known OM menu name (normalised)
    if _norm(t) in known_om_names:
        return True
    return False


def strip_order_links(text: str) -> str:
    """
    Replace [label](order-target) with just label when target is not a known page.
    Uses a balanced-bracket parser to handle nested [R], [DI] etc. in labels.
    """
    result = []
    i = 0
    while i < len(text):
        if text[i] != '[':
            result.append(text[i])
            i += 1
            continue

        # Try to parse [label](target)
        cursor = i + 1
        depth = 1
        while cursor < len(text) and depth > 0:
            if text[cursor] == '\\':
                cursor += 2
                continue
            if text[cursor] == '[':
                depth += 1
            elif text[cursor] == ']':
                depth -= 1
            cursor += 1

        if depth != 0 or cursor >= len(text) or text[cursor] != '(':
            result.append(text[i])
            i += 1
            continue

        label_end = cursor - 1
        label = text[i + 1:label_end]

        target_start = cursor + 1
        cursor = target_start
        tdepth = 1
        while cursor < len(text) and tdepth > 0:
            if text[cursor] == '\\':
                cursor += 2
                continue
            if text[cursor] == '(':
                tdepth += 1
            elif text[cursor] == ')':
                tdepth -= 1
            cursor += 1

        if tdepth != 0:
            result.append(text[i])
            i += 1
            continue

        target_end = cursor - 1
        target = text[target_start:target_end]
        full_match_end = cursor

        if is_keep_target(target):
            result.append(text[i:full_match_end])
        else:
            # Strip the link, keep only label text
            result.append(label)

        i = full_match_end

    return ''.join(result)


changed = 0
skipped = 0

for page_file in sorted(CMS_ROOT.rglob("*.json")):
    try:
        data = json.loads(page_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  SKIP (JSON error): {page_file.name}: {e}")
        skipped += 1
        continue

    original_text = data.get("Text", "")
    if not original_text:
        continue

    new_text = strip_order_links(original_text)

    if new_text != original_text:
        data["Text"] = new_text
        page_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )
        changed += 1
        print(f"  Updated: {page_file.relative_to(CMS_ROOT)}")

print(f"\nDone. Pages updated: {changed}, skipped: {skipped}")



def strip_order_links(text: str) -> str:
    """
    Replace [label](order-target) with just label when target is an order slug.
    Uses the balanced-bracket approach to handle nested [R], [DI] etc. in labels.
    """
    result = []
    i = 0
    while i < len(text):
        if text[i] != '[':
            result.append(text[i])
            i += 1
            continue

        # Try to parse [label](target)
        # Find label end with balanced brackets
        cursor = i + 1
        depth = 1
        while cursor < len(text) and depth > 0:
            if text[cursor] == '\\':
                cursor += 2
                continue
            if text[cursor] == '[':
                depth += 1
            elif text[cursor] == ']':
                depth -= 1
            cursor += 1

        # cursor is now one past the closing ]
        if depth != 0 or cursor >= len(text) or text[cursor] != '(':
            # Not a valid link; keep the [
            result.append(text[i])
            i += 1
            continue

        label_end = cursor - 1  # position of closing ]
        label = text[i + 1:label_end]

        # Parse target
        target_start = cursor + 1
        cursor = target_start
        tdepth = 1
        while cursor < len(text) and tdepth > 0:
            if text[cursor] == '\\':
                cursor += 2
                continue
            if text[cursor] == '(':
                tdepth += 1
            elif text[cursor] == ')':
                tdepth -= 1
            cursor += 1

        if tdepth != 0:
            result.append(text[i])
            i += 1
            continue

        target_end = cursor - 1
        target = text[target_start:target_end]
        full_match_end = cursor

        if is_keep_target(target):
            # Keep the full markdown link
            result.append(text[i:full_match_end])
        else:
            # Strip the link, keep only label text
            result.append(label)

        i = full_match_end

    return ''.join(result)


changed = 0
skipped = 0

for page_file in sorted(CMS_ROOT.rglob("*.json")):
    try:
        data = json.loads(page_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  SKIP (JSON error): {page_file.name}: {e}")
        skipped += 1
        continue

    original_text = data.get("Text", "")
    if not original_text:
        continue

    new_text = strip_order_links(original_text)

    if new_text != original_text:
        data["Text"] = new_text
        page_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )
        changed += 1
        print(f"  Updated: {page_file.relative_to(CMS_ROOT)}")

print(f"\nDone. Pages updated: {changed}, skipped: {skipped}")
