"""
scripts/link-plaintext-mentions.py

Combined-page remediation pass: finds plain-text disease/topic mentions in
combined page Text (cms-data/001-TestStation/pages/**/*.json) that correspond
to a real combined page, but were never turned into a markdown link, and
converts them to [Label](slug) links.

Why this exists: earlier passes (fix-missing-nav-pages.py, review-skipped-
variants.py, rewrite-links-to-combined.py) rewrote or created links that
already existed in some markdown/LinkTargets form. This pass targets mentions
that were never linked at all -- e.g. a combined page whose Inpatient/Outpatient
source menu links "Chlamydia" -> a real combined page, but the combined page's
own Text just says the word "Chlamydia" with no link.

Rules followed (per repo conventions):
  - LinkTargets is legacy/deprecated. It is read here ONLY as reference data
    (to learn what a mention *should* link to, from the Inpt/Outpt/ERUC
    source menus in TestStationOMJSON.json). No LinkTargets are written.
  - The only output is markdown-format links using combined-page slug IDs,
    written into the "Text" field of cms-data page files.
  - Ambiguous or generic anchor text (different targets for the same label,
    boilerplate like "Non-VA order for above") is skipped rather than guessed.

Usage:
  python scripts/link-plaintext-mentions.py            # apply fixes
  python scripts/link-plaintext-mentions.py --dry-run  # report only, no writes

Run scripts/compile-cms.py and scripts/audit-teststation.py afterward.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
OMJSON_PATH = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"
CMS_ROOT = ROOT / "cms-data" / "001-TestStation" / "pages"
REPORT_PATH = ROOT / "cms-data" / "001-TestStation" / "documents" / "plaintext-link-pass-report.json"

DRY_RUN = "--dry-run" in sys.argv

GENERIC_TEXTS = {
    "help and legend",
    "non-va order for above",
    "guidance",
    "consult",
    "lab menu",
}

LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
WORD_CHAR_RE = re.compile(r"[A-Za-z0-9]")
DRUG_ORDER_RE = re.compile(
    r"\d+\s*(mg|gm|mcg|units?)\b|\[(R|M|DI|H|O|C)\]|<AND>|<OR>|\(\$\)",
    re.IGNORECASE,
)


def is_generic(text: str) -> bool:
    t = text.strip().lower()
    if not t or len(t) < 4:
        return True
    if len(text) > 80:
        return True
    if t in GENERIC_TEXTS:
        return True
    if t.startswith("[consult") or "non-va order" in t:
        return True
    if DRUG_ORDER_RE.search(text):
        return True
    return False


def main():
    with OMJSON_PATH.open(encoding="utf-8") as f:
        omjson = json.load(f)
    menus = omjson["menus"]
    by_name = {m["Name"]: m for m in menus}

    page_files = sorted(CMS_ROOT.rglob("*.json"))
    combined_pageids = set()
    pages = []
    for pf in page_files:
        try:
            rec = json.loads(pf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  SKIP (JSON error): {pf.name}: {e}")
            continue
        pid = rec.get("PageID") or pf.stem
        combined_pageids.add(pid)
        pages.append((pf, rec))

    def resolve_item_to_slug(item: str):
        if not item:
            return None
        rec = by_name.get(item)
        if rec:
            combined = rec.get("Combined")
            if isinstance(combined, str) and combined.strip() and combined in combined_pageids:
                return combined
        if item in combined_pageids:
            return item
        return None

    report = {"pages_changed": 0, "links_added": 0, "details": [], "skipped_ambiguous": [], "unresolved": []}

    for pf, rec in pages:
        page_id = rec.get("PageID") or pf.stem
        text = rec.get("Text", "")
        if not text:
            continue

        # Gather candidate (Text -> Item) pairs from this page's source menus.
        source_names = []
        for field in ("Inpt", "Outpt", "ERUC"):
            v = rec.get(field)
            if isinstance(v, str) and v.strip():
                source_names.append(v)

        candidates = {}  # anchor text -> resolved slug
        ambiguous_texts = set()
        for source_name in source_names:
            source_menu = by_name.get(source_name)
            if not source_menu:
                continue
            for lt in source_menu.get("LinkTargets", []) or []:
                anchor = (lt.get("Text") or "").strip()
                item = lt.get("Item") or ""
                if is_generic(anchor):
                    continue
                slug = resolve_item_to_slug(item)
                if not slug or slug == page_id:
                    continue
                if anchor in candidates and candidates[anchor] != slug:
                    ambiguous_texts.add(anchor)
                    continue
                candidates[anchor] = slug

        for a in ambiguous_texts:
            candidates.pop(a, None)
            report["skipped_ambiguous"].append({"page": page_id, "text": a})

        if not candidates:
            continue

        # Protect existing markdown link spans.
        protected = [m.span() for m in LINK_RE.finditer(text)]

        def overlaps(a_start, a_end, spans):
            return any(not (a_end <= s or a_start >= e) for s, e in spans)

        accepted = []  # (start, end, anchor, slug)
        for anchor, slug in sorted(candidates.items(), key=lambda kv: -len(kv[0])):
            for m in re.finditer(re.escape(anchor), text):
                start, end = m.span()
                if overlaps(start, end, protected):
                    continue
                if overlaps(start, end, [(s, e) for s, e, _, _ in accepted]):
                    continue
                before = text[start - 1] if start > 0 else ""
                after = text[end] if end < len(text) else ""
                if before == "[" or WORD_CHAR_RE.match(before or ""):
                    continue
                if WORD_CHAR_RE.match(after or ""):
                    continue
                accepted.append((start, end, anchor, slug))
                break  # one replacement per anchor is enough for menu-style lists

        if not accepted:
            continue

        accepted.sort(key=lambda t: t[0], reverse=True)
        new_text = text
        for start, end, anchor, slug in accepted:
            new_text = new_text[:start] + f"[{anchor}]({slug})" + new_text[end:]

        if new_text != text:
            report["pages_changed"] += 1
            report["links_added"] += len(accepted)
            report["details"].append({
                "page": page_id,
                "links_added": [{"text": a, "slug": s} for _, _, a, s in sorted(accepted, key=lambda t: t[0])],
            })
            if not DRY_RUN:
                rec["Text"] = new_text
                pf.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Pages changed: {report['pages_changed']}")
    print(f"Links added: {report['links_added']}")
    print(f"Ambiguous anchors skipped: {len(report['skipped_ambiguous'])}")
    print(f"Report written to {REPORT_PATH}")
    if DRY_RUN:
        print("(dry run - no files written)")


if __name__ == "__main__":
    main()
