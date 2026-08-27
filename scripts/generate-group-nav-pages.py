"""
scripts/generate-group-nav-pages.py

For each inpatient group root that is missing a combined navigation page,
generate one by walking the inpatient root's rich-text and remapping
inpatient link targets to their combined equivalents.

Idempotent: skips any group that already has a combined nav page
(i.e., any combined page whose Inpt pointer equals the inpt group root).

Run order:
  1. python scripts/generate-group-nav-pages.py
  2. python scripts/export-cms.py        (regenerate CMS files + config.yml)
  3. python scripts/audit-teststation.py (verify integrity)
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
JSON_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"

# ── Group roots that have no Combined nav page and need one generated ─────────
# Keys are inpatient root menu names, values are the slug PageIDs to use for
# the new combined nav page.  Must match MANUAL_INPT_ROOT_GROUPS in export-cms.py.
MANUAL_INPT_ROOT_GROUPS: dict[str, str] = {
    "ORZID2 GMENU ABX HEAD AND NECK": "head-and-neck",
}

# Human-readable Term1 for each generated nav page
NAV_PAGE_TERM1: dict[str, str] = {
    "head-and-neck": "Head and Neck",
}

# ── Load data ─────────────────────────────────────────────────────────────────
with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

menus: list[dict] = data["menus"]
by_name: dict[str, dict] = {m["Name"]: m for m in menus}

# Build combined-page lookups
combined_by_page_id: dict[str, dict] = {}   # slug -> combined menu record
inpt_to_combined_id: dict[str, str] = {}    # inpt_name -> combined PageID (slug)
for m in menus:
    if m.get("Inpt"):
        combined_by_page_id[m["Name"]] = m
        inpt_to_combined_id[m["Inpt"]] = m["Name"]


# ── Markdown link parser (mirrors extractMarkdownLinks in HTML runtime) ────────
def extract_markdown_links(text: str) -> list[dict]:
    """Return list of {index, end, label, target} dicts found in text."""
    links = []
    i = 0
    while i < len(text):
        lb = text.find("[", i)
        if lb == -1:
            break
        cursor = lb + 1
        depth = 1
        while cursor < len(text) and depth > 0:
            ch = text[cursor]
            if ch == "\\":
                cursor += 2
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            cursor += 1
        if depth != 0 or cursor >= len(text) or text[cursor] != "(":
            i = lb + 1
            continue
        label_end = cursor - 1
        t_start = cursor + 1
        cursor = t_start
        depth = 1
        while cursor < len(text) and depth > 0:
            ch = text[cursor]
            if ch == "\\":
                cursor += 2
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            cursor += 1
        if depth != 0:
            i = lb + 1
            continue
        links.append({
            "index": lb,
            "end": cursor,
            "label": text[lb + 1: label_end],
            "target": text[t_start: cursor - 1],
        })
        i = cursor
    return links


def resolve_to_combined(target: str) -> str | None:
    """
    Given an inpatient link target (VistA name or slug), return the combined
    page's PageID slug, or None if no combined equivalent exists yet.
    """
    t = target.strip()
    # Already a combined slug (e.g. PageID like 'otitis-externa')
    if t in combined_by_page_id:
        return t
    # Direct Combined pointer on the inpt page
    inpt_page = by_name.get(t)
    if inpt_page:
        direct = inpt_page.get("Combined", "")
        if direct and direct in combined_by_page_id:
            return direct
        # Reverse lookup
        reverse = inpt_to_combined_id.get(t)
        if reverse:
            return reverse
    return None


def build_nav_text(inpt_root_name: str) -> tuple[str, list[dict]]:
    """
    Parse the inpatient root's Text, remap links to combined equivalents,
    and return (nav_text, link_targets).

    Lines that reference an inpatient page with no combined equivalent are
    kept as plain text (label only, no hyperlink) so the nav is complete.
    """
    root_page = by_name.get(inpt_root_name)
    if not root_page:
        print(f"  ERROR: inpt root not found: {inpt_root_name}", file=sys.stderr)
        return "", []

    source_text = root_page.get("Text", "").strip()
    if not source_text:
        print(f"  WARNING: inpt root has no Text: {inpt_root_name}", file=sys.stderr)
        return "", []

    out_lines: list[str] = []
    link_targets: list[dict] = []
    skipped: list[str] = []

    for line in source_text.splitlines():
        # ── Heading line → keep verbatim (## heading)
        heading_match = re.match(r"^(\s{0,3}#{1,6}\s+)(.*)$", line)
        if heading_match:
            out_lines.append(line)
            continue

        # ── Parse markdown links in this line
        links = extract_markdown_links(line)
        if not links:
            # Plain text line — keep as-is
            if line.strip():
                out_lines.append(line)
            continue

        # Rebuild the line, remapping each link target
        rebuilt = ""
        cursor = 0
        for link in links:
            rebuilt += line[cursor: link["index"]]
            label = link["label"]
            target = link["target"]
            combined_id = resolve_to_combined(target)
            if combined_id:
                rebuilt += f"[{label}]({combined_id})"
                # Add to LinkTargets registry for the nav page
                if not any(lt["Item"] == combined_id for lt in link_targets):
                    link_targets.append({"Text": label, "Item": combined_id})
            else:
                # No combined equivalent yet — emit label as plain text
                rebuilt += label
                skipped.append(f"    {label} (target={target})")
            cursor = link["end"]
        rebuilt += line[cursor:]
        stripped = rebuilt.strip()
        if stripped:
            out_lines.append(stripped)

    if skipped:
        print(f"  INFO: {len(skipped)} link(s) have no combined equivalent (kept as plain text):")
        for s in skipped:
            print(s)

    return "\n".join(out_lines), link_targets


# ── Main generation loop ──────────────────────────────────────────────────────
generated = 0
skipped_existing = 0

for inpt_root_name, nav_page_id in MANUAL_INPT_ROOT_GROUPS.items():
    # Check if a combined nav page already exists for this root
    if inpt_to_combined_id.get(inpt_root_name):
        existing = inpt_to_combined_id[inpt_root_name]
        print(f"SKIP (already exists): {inpt_root_name} → {existing}")
        skipped_existing += 1
        continue

    if nav_page_id in by_name:
        # PageID already taken by a different page
        print(f"SKIP (PageID conflict): {nav_page_id} already in OMJSON")
        skipped_existing += 1
        continue

    print(f"\nGenerating nav page: {nav_page_id}")
    print(f"  Inpt root: {inpt_root_name}")

    nav_text, link_targets = build_nav_text(inpt_root_name)
    if not nav_text:
        print(f"  SKIP: empty nav text produced, aborting for {nav_page_id}")
        continue

    term1 = NAV_PAGE_TERM1.get(nav_page_id, nav_page_id.replace("-", " ").title())

    new_page: dict = {
        "Name": nav_page_id,
        "Term1": term1,
        "Term2": "",
        "Text": nav_text,
        "LinkTargets": link_targets,
        "Inpt": inpt_root_name,
    }

    # Add to menus list
    menus.append(new_page)
    by_name[nav_page_id] = new_page
    inpt_to_combined_id[inpt_root_name] = nav_page_id
    combined_by_page_id[nav_page_id] = new_page

    # Update the inpatient root's Combined crossref
    inpt_root_page = by_name.get(inpt_root_name)
    if inpt_root_page:
        inpt_root_page["Combined"] = nav_page_id
        print(f"  Set {inpt_root_name}[Combined] = {nav_page_id}")

    print(f"  Generated {nav_page_id}: {len(nav_text)} chars, {len(link_targets)} link targets")
    generated += 1

# ── Save ──────────────────────────────────────────────────────────────────────
if generated > 0:
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nSaved {JSON_PATH.name}: {generated} new nav page(s) added")
    print("Next: run scripts/export-cms.py to regenerate CMS files and config.yml")
else:
    print(f"\nNothing to generate ({skipped_existing} already exist).")
