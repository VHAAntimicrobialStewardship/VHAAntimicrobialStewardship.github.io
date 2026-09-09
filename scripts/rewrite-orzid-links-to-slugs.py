#!/usr/bin/env python3
"""
Rewrite legacy/ORZID-style link targets (including pseudo-slugified variants
like 'orzid2-gmenu-osteomyelitis') in combined pages' Text to their exact
combined page slug, wherever a combined page exists for that legacy name.

Matching mirrors the runtime's normalizeComparableId() fallback: lowercase
and strip all non-alphanumeric characters, so 'ORZID2 GMENU OSTEOMYELITIS'
and 'orzid2-gmenu-osteomyelitis' both normalize to 'orzid2gmenuosteomyelitis'.
This keeps the static export-cms.py adjacency graph in sync with what the
runtime already resolves dynamically.

Usage:
    python rewrite-orzid-links-to-slugs.py --dry-run   (default; prints report)
    python rewrite-orzid-links-to-slugs.py --apply     (writes changes to OMJSON)
"""
import json
import re
import sys

JSON_PATH = "stations/001-TestStation/TestStationOMJSON.json"

MANUAL_OVERRIDES = {
    "ORZID2 GMENU ABX CMV MAIN PAGE": "cmv-main-page",
    "ORZID2 GMENU ABX ROSACEA": "rosacea",
}


def normalize_comparable_id(value: str) -> str:
    """Mirror runtime normalizeComparableId(): lowercase, strip non-alnum."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def extract_links(text: str):
    """Extract (start, end, target) for [label](target), handling balanced
    parens in target."""
    results = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "[":
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if text[j] == "[":
                    depth += 1
                elif text[j] == "]":
                    depth -= 1
                j += 1
            if depth != 0:
                break
            if j < n and text[j] == "(":
                depth2 = 1
                k = j + 1
                while k < n and depth2 > 0:
                    if text[k] == "(":
                        depth2 += 1
                    elif text[k] == ")":
                        depth2 -= 1
                    k += 1
                if depth2 == 0:
                    target = text[j + 1 : k - 1]
                    results.append((i, k, target))
                    i = k
                    continue
        i += 1
    return results


def build_rewrite_map(menus: list[dict]) -> tuple[dict[str, str], set[str]]:
    """Map normalize_comparable_id(legacy_name) -> exact combined page slug.
    Also returns the set of existing exact combined slugs, which must always
    take priority over normalized matching (mirrors runtime tier-1 exact
    match before tier-2 normalized fallback), so already-correct links are
    never rewritten due to an unrelated normalization collision."""
    by_name = {m["Name"]: m for m in menus}
    existing_slugs = {m["Name"] for m in menus if m.get("Inpt")}
    normalized_to_slug: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for m in menus:
        if not m.get("Inpt"):
            continue
        slug = m["Name"]
        for field in ("Name", "Inpt", "Outpt", "ERUC"):
            value = m.get(field)
            if not value:
                continue
            norm = normalize_comparable_id(value)
            if norm in normalized_to_slug and normalized_to_slug[norm] != slug:
                collisions.setdefault(norm, [normalized_to_slug[norm]]).append(slug)
                continue
            normalized_to_slug.setdefault(norm, slug)
    for legacy, slug in MANUAL_OVERRIDES.items():
        if slug in by_name:
            normalized_to_slug.setdefault(normalize_comparable_id(legacy), slug)
    if collisions:
        print(f"WARNING: {len(collisions)} normalized-name collisions detected (first-writer-wins):")
        for norm, slugs in collisions.items():
            print(f"  {norm!r} -> candidates: {slugs}")
    return normalized_to_slug, existing_slugs


def rewrite_text(
    text: str, normalized_to_slug: dict[str, str], existing_slugs: set[str]
) -> tuple[str, int]:
    links = extract_links(text)
    count = 0
    result = []
    last_end = 0
    for start, end, target in links:
        if target in existing_slugs:
            continue
        norm = normalize_comparable_id(target)
        new_target = normalized_to_slug.get(norm)
        if new_target is None or new_target == target:
            continue
        segment = text[start:end]
        old_paren = f"]({target})"
        new_paren = f"]({new_target})"
        if old_paren not in segment:
            continue
        new_segment = segment.replace(old_paren, new_paren, 1)
        result.append(text[last_end:start])
        result.append(new_segment)
        last_end = end
        count += 1
    result.append(text[last_end:])
    return "".join(result), count


def main():
    apply_changes = "--apply" in sys.argv

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    menus = data["menus"]
    normalized_to_slug, existing_slugs = build_rewrite_map(menus)

    total_rewrites = 0
    pages_changed = 0
    for page in menus:
        if not page.get("Inpt"):
            continue
        text = page.get("Text", "")
        new_text, count = rewrite_text(text, normalized_to_slug, existing_slugs)
        if count > 0:
            total_rewrites += count
            pages_changed += 1
            if apply_changes:
                page["Text"] = new_text

    print(f"Distinct normalized rewrite mappings available: {len(normalized_to_slug)}")
    print(f"Pages with rewritten links: {pages_changed}")
    print(f"Total link occurrences rewritten: {total_rewrites}")

    if apply_changes:
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Changes WRITTEN to OMJSON.")
    else:
        print("Dry run only - no changes written. Use --apply to write.")


if __name__ == "__main__":
    main()
