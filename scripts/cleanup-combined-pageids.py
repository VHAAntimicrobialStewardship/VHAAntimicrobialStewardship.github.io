"""
Cleanup combined page IDs and display terms by removing VistA-style tokens.

What this script does:
- Renames combined page Name (PageID) when it contains tokens like orzid/gmenu/abx
- Keeps IDs stable and unique by deriving clean slugs and de-duplicating collisions
- Rewrites markdown link targets in Text for renamed combined pages
- Rewrites markdown targets that use LinkTargets Key aliases when those aliases map to combined pages
- Rewrites LinkTargets Item when they point to renamed combined pages
- Rewrites Combined/Outpt/ERUC cross-reference fields when they point to renamed pages
- Normalizes Term1 for all combined pages when Term1 still contains VistA token text
- Writes a report to cms-data/001-TestStation/documents/pageid-cleanup-report.json
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
JSON_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"
REPORT_PATH = ROOT / "cms-data" / "001-TestStation" / "documents" / "pageid-cleanup-report.json"

TOKEN_RE = re.compile(r"\b(?:orz[a-z0-9]*|gmenu|abx)\b", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def has_vista_tokens(value: str) -> bool:
    return bool(TOKEN_RE.search((value or "").lower()))


def normalize_slug(value: str) -> str:
    slug = (value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9\-\s_/]", "", slug)
    slug = re.sub(r"[\s_/]+", "-", slug)
    tokens = [
        t
        for t in slug.split("-")
        if t
        and not re.fullmatch(r"orz[a-z0-9]*", t)
        and t not in {"gmenu", "abx"}
    ]
    slug = "-".join(tokens)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def strip_nav_noise(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"(?:\s*\(navigation\)\s*)+$", "", text, flags=re.IGNORECASE)
    while True:
        updated = re.sub(r"^\s*\d+(?:\.\d+)*\.\s*", "", text, count=1)
        if updated == text:
            break
        text = updated.strip()
    return text.strip()


def derive_new_page_id(menu: dict) -> str:
    name = menu.get("Name", "")
    term1 = strip_nav_noise(menu.get("Term1", ""))
    text = menu.get("Text", "")

    candidates = [normalize_slug(name), normalize_slug(term1)]

    m = re.search(r"^\s*#+\s+(.+)$", text, flags=re.MULTILINE)
    if m:
        candidates.append(normalize_slug(m.group(1)))

    for cand in candidates:
        if cand and not has_vista_tokens(cand):
            return cand

    forced = normalize_slug(name)
    return forced or "combined-page"


def make_unique(base: str, reserved: set[str]) -> str:
    candidate = base
    n = 2
    while candidate in reserved:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

menus: list[dict] = data["menus"]
combined = [m for m in menus if m.get("Inpt")]
combined_old_ids = {m.get("Name", "") for m in combined}
all_names = {m.get("Name", "") for m in menus}

# Build key alias map before any rewrites.
key_to_item: dict[str, str] = {}
for m in menus:
    for lt in m.get("LinkTargets", []) or []:
        key = (lt.get("Key") or "").strip()
        item = (lt.get("Item") or "").strip()
        if key and item:
            key_to_item[key] = item

rename_map: dict[str, str] = {}
reserved = set(all_names)

for m in combined:
    old = m.get("Name", "")
    if not old or not has_vista_tokens(old):
        continue

    base = derive_new_page_id(m)
    reserved.discard(old)
    new = make_unique(base, reserved)
    reserved.add(new)

    if new != old:
        rename_map[old] = new


# Apply page ID renames.
for m in menus:
    old = m.get("Name", "")
    if old in rename_map:
        m["Name"] = rename_map[old]

# Lookup for current combined page IDs after rename.
combined_current_ids = {m.get("Name", "") for m in menus if m.get("Inpt")}
menu_by_name = {m.get("Name", ""): m for m in menus}


def item_to_combined(item: str) -> str:
    if item in rename_map:
        return rename_map[item]
    if item in combined_current_ids:
        return item

    menu = menu_by_name.get(item)
    if menu:
        combined = menu.get("Combined")
        if isinstance(combined, str) and combined in combined_current_ids:
            return combined

    return ""


def resolve_combined_target(target: str) -> str:
    # Direct rename/current combined id
    direct = item_to_combined(target)
    if direct:
        return direct

    # Resolve via LinkTargets Key alias -> Item (often VistA key), then map to combined.
    resolved_item = key_to_item.get(target)
    if resolved_item:
        mapped = item_to_combined(resolved_item)
        if mapped:
            return mapped

    return target


def rewrite_markdown_targets(text: str) -> tuple[str, int]:
    if not text:
        return text, 0

    changes = 0

    def repl(m: re.Match) -> str:
        nonlocal changes
        label = m.group(1)
        target = m.group(2).strip()
        new_target = resolve_combined_target(target)
        if new_target != target:
            changes += 1
        return f"[{label}]({new_target})"

    new_text = MARKDOWN_LINK_RE.sub(repl, text)
    return new_text, changes


# Rewrite references and normalize Term1 for all combined pages.
menus_with_text_rewrites = 0
markdown_target_rewrites = 0
linktarget_rewrites = 0
field_rewrites = 0
term1_normalized = 0

for m in menus:
    old_text = m.get("Text", "")
    new_text, c = rewrite_markdown_targets(old_text)
    if c > 0:
        m["Text"] = new_text
        menus_with_text_rewrites += 1
        markdown_target_rewrites += c

    for lt in m.get("LinkTargets", []) or []:
        item = lt.get("Item", "")
        new_item = resolve_combined_target(item)
        if new_item != item:
            lt["Item"] = new_item
            linktarget_rewrites += 1

    for field in ("Combined", "Outpt", "ERUC"):
        val = m.get(field)
        if isinstance(val, str) and val:
            new_val = resolve_combined_target(val)
            if new_val != val:
                m[field] = new_val
                field_rewrites += 1

    if m.get("Inpt"):
        term1 = strip_nav_noise(m.get("Term1", ""))
        if not term1 or has_vista_tokens(term1):
            m["Term1"] = m.get("Name", "")
            term1_normalized += 1


with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")


combined_after = [m for m in menus if m.get("Inpt")]
remaining_bad_ids = sorted(
    m.get("Name", "") for m in combined_after if has_vista_tokens(m.get("Name", ""))
)
remaining_bad_term1 = sorted(
    m.get("Name", "")
    for m in combined_after
    if has_vista_tokens(strip_nav_noise(m.get("Term1", "")))
)
remaining_bad_text_targets = []
for m in combined_after:
    pid = m.get("Name", "")
    text = m.get("Text", "")
    for _, target in MARKDOWN_LINK_RE.findall(text):
        t = target.strip()
        if has_vista_tokens(t):
            remaining_bad_text_targets.append({"page_id": pid, "target": t})
            if len(remaining_bad_text_targets) >= 200:
                break
    if len(remaining_bad_text_targets) >= 200:
        break

report = {
    "summary": {
        "combined_pages_total": len(combined_after),
        "renamed_pages": len(rename_map),
        "menus_with_text_link_rewrites": menus_with_text_rewrites,
        "markdown_targets_rewritten": markdown_target_rewrites,
        "linktargets_rewritten": linktarget_rewrites,
        "crossref_fields_rewritten": field_rewrites,
        "term1_normalized": term1_normalized,
        "remaining_combined_pageids_with_vista_tokens": len(remaining_bad_ids),
        "remaining_combined_term1_with_vista_tokens": len(remaining_bad_term1),
        "remaining_combined_markdown_targets_with_vista_tokens_sampled": len(remaining_bad_text_targets),
    },
    "rename_map": rename_map,
    "remaining_bad_pageids": remaining_bad_ids,
    "remaining_bad_term1_pageids": remaining_bad_term1,
    "remaining_bad_text_targets_sample": remaining_bad_text_targets,
}

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"Combined pages total: {len(combined_after)}")
print(f"Renamed combined pages: {len(rename_map)}")
print(f"Menus with text rewrites: {menus_with_text_rewrites}")
print(f"Markdown targets rewritten: {markdown_target_rewrites}")
print(f"LinkTargets rewritten: {linktarget_rewrites}")
print(f"Cross-ref fields rewritten: {field_rewrites}")
print(f"Term1 normalized: {term1_normalized}")
print(f"Remaining bad combined page IDs: {len(remaining_bad_ids)}")
print(f"Remaining bad combined Term1 pages: {len(remaining_bad_term1)}")
print(f"Sampled remaining bad markdown targets: {len(remaining_bad_text_targets)}")
print(f"Report: {REPORT_PATH}")
