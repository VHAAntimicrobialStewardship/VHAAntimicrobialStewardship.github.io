"""Find cms-data pages where Term1 is effectively just the PageID (a slug) instead
of a human-readable title, and replace Term1 with the title derived from the
heading(s) at the top of Text.

A page is a candidate when normalizing Term1 (lowercasing, stripping a trailing
"(Navigation)" suffix, replacing whitespace/underscores with hyphens, stripping any
character that isn't a-z0-9-, collapsing repeat hyphens) produces the same string as
PageID.

Title extraction:
- Starts at the first non-blank line, which is expected to be a markdown heading
  (one or more leading '#').
- If that heading is ALL CAPS, keeps consuming subsequent heading lines (skipping
  blank lines) that are ALSO all-caps, merging them into one title with a space.
  This repairs the known "title wrapped across two physical heading lines" bug
  (e.g. "## FOO\n## BAR" meant to be one heading "FOO BAR") without touching the
  underlying Text. Stops as soon as a non-heading line or a non-all-caps heading
  (a real subsection header, e.g. "## Inpatient") is reached.
- Strips outer ++...++ banner markers if present (handles both "++ ## TITLE ++"
  and the non-conforming "# ++ TITLE ++" order found in some legacy pages).
- ALL CAPS results are converted to sentence case (first letter capitalized, rest
  lowercased); otherwise used verbatim (trimmed).
- If the old Term1 ended in "(Navigation)" (case-insensitive), that suffix is
  preserved on the new title (site convention marks nav/index pages this way).

Safety filters (excluded from auto-apply, listed separately for manual review):
- No heading found on the first non-blank line.
- Extracted title has no alphanumeric characters (e.g. "< OR >", a divider line).
- Extracted title is a duplicate of another candidate's title (a strong signal the
  heading is a generic/shared placeholder, e.g. many gram-neg-*/gram-pos-* stub
  pages all say "REFER TO SYNDROME OR INFECTIOUS DISEASE FOR RECOMMENDATIONS").

MANUAL_TITLE_OVERRIDES below hard-codes a small, explicitly-reviewed set of
PageIDs where the automatic heading extraction is known to be wrong/unusable
(e.g. content is a garbled multi-column table, or the heading is a duplicate).

Usage:
  python scripts/fix-term1-pageid-leaks.py --dry-run   (default; prints report only)
  python scripts/fix-term1-pageid-leaks.py --apply      (writes changes to cms-data)
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = REPO_ROOT / "cms-data" / "001-TestStation" / "pages"

NAV_SUFFIX_RE = re.compile(r"\s*\(navigation\)\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
OUTER_BANNER_RE = re.compile(r"^\+\+\s*(.*?)\s*\+\+$")
FULL_LINK_RE = re.compile(r"^\[(.+?)\]\(.+?\)$")

# Heading text that is just a tab/section label, never a real page title. When the
# first heading is one of these, skip it and keep scanning for the real title.
GENERIC_SECTION_LABELS = {
    "inpatient", "outpatient", "inpatient/outpatient", "outpatient/inpatient",
    "er", "er/uc", "eruc", "er/uc emergency department",
}

STOPWORDS = {"a", "an", "the", "of", "for", "in", "on", "with", "and", "or", "to", "by", "at", "is", "are", "w"}

# PageID -> hand-reviewed replacement title. Used instead of automatic extraction,
# for pages whose Text is too garbled/truncated to yield a usable title at all.
MANUAL_TITLE_OVERRIDES = {
    # Content is a garbled 3-column ICE-score table (see repo memory notes on
    # "Interleaved multi-column source pages"); first heading is just "Assessment:".
    # Reuses the existing link label used elsewhere to reach this page.
    "ice-assessment-for-icans": "Calculate ICE score",
    # Text is a single orphaned stub line unrelated to the page's real topic.
    "immunocom-diabetes-mellitus": "Diabetes mellitus",
    "drug-allergies": "Drug allergies",
    # Organism stub pages whose Text is just the shared placeholder heading
    # "REFER TO SYNDROME OR INFECTIOUS DISEASE FOR RECOMMENDATIONS"; PageID
    # reliably encodes the organism, so title is derived from that instead.
    "gram-neg-a-baumanni": "Acinetobacter baumannii",
    "gram-neg-bacteroides-spp": "Bacteroides species",
    "gram-neg-bordetella-spp": "Bordetella species",
    "gram-neg-campylobacter-spp": "Campylobacter species",
    "gram-neg-citrobacter-spp": "Citrobacter species",
    "gram-neg-e-coli": "Escherichia coli",
    "gram-neg-enterobacter-spp": "Enterobacter species",
    "gram-neg-haemophilus-spp": "Haemophilus species",
    "gram-neg-klebsiella-spp": "Klebsiella species",
    "gram-neg-legionella-spp": "Legionella species",
    "gram-neg-m-catarrhalis": "Moraxella catarrhalis",
    "gram-neg-n-gonorrhoeae": "Neisseria gonorrhoeae",
    "gram-neg-n-meningitidis": "Neisseria meningitidis",
    "gram-neg-p-multocida": "Pasteurella multocida",
    "gram-neg-proteus-spp": "Proteus species",
    "gram-neg-pseudomonas-spp": "Pseudomonas species",
    "gram-neg-salmonella-spp": "Salmonella species",
    "gram-neg-serratia-spp": "Serratia species",
    "gram-neg-shigella-spp": "Shigella species",
    "gram-negative-bacteria": "Gram-negative bacteria",
    "gram-pos-anaerobic-gpc": "Anaerobic gram-positive cocci",
    "gram-pos-clostridium-spp": "Clostridium species",
    "gram-pos-coag-neg-staph": "Coagulase-negative staphylococci",
    "gram-pos-enterococci": "Enterococci",
    "gram-pos-groups-c-f-g": "Group C, F, and G streptococci",
    "gram-pos-listeria-spp": "Listeria species",
    "gram-pos-s-agalactiae": "Streptococcus agalactiae (group B strep)",
    "gram-pos-s-anginosus": "Streptococcus anginosus group",
    "gram-pos-s-bovis": "Streptococcus bovis (gallolyticus)",
    "gram-pos-s-pneumoniae": "Streptococcus pneumoniae",
    "gram-pos-s-pyogenes": "Streptococcus pyogenes (group A strep)",
    "gram-pos-staph-lugdunensis": "Staphylococcus lugdunensis",
    "gram-pos-staphylococci": "Staphylococci",
    "gram-pos-treat-s-aureus": "Staphylococcus aureus",
    "gram-pos-viridans-strepto": "Viridans group streptococci",
    "gram-positive-bacteria": "Gram-positive bacteria",
    "int-rs-gram-neg-bacilli": "Interpreting susceptibility results for gram-negative bacilli",
    "int-rs-gram-neg-cocci": "Interpreting susceptibility results for gram-negative cocci",
    "intro-spec-pathogen": "Introduction to specific pathogens",
    "pros-bone-joint-s-aureus": "Staphylococcus aureus infections in bone or joint prostheses",
    "rock-mtn-spotted-fever": "Rocky Mountain spotted fever",
    "appro-foot-ulcer-w-infect": "Approach to infected foot ulcer",
}


def normalize_slug(value: str) -> str:
    value = NAV_SUFFIX_RE.sub("", value)
    value = value.strip().lower()
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"[^a-z0-9-]", "", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")


def strip_banner(text: str) -> str:
    match = OUTER_BANNER_RE.match(text)
    return match.group(1).strip() if match else text


def strip_full_link(text: str) -> str:
    match = FULL_LINK_RE.match(text)
    return match.group(1).strip() if match else text


def to_sentence_case(text: str) -> str:
    if text == text.upper() and any(c.isalpha() for c in text):
        text = text.lower()
        return text[0].upper() + text[1:] if text else text
    return text


def tokenize(text: str) -> set:
    words = re.split(r"[^A-Za-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 2 and w not in STOPWORDS}


def tokens_overlap(tokens_a: set, tokens_b: set) -> bool:
    """True if any token pair matches exactly, or one is a prefix of the other
    (both at least 3 chars) -- this catches VistA-style abbreviated PageIDs
    (e.g. "appro-intravas-cath") matching full-word titles ("Approach to
    intravascular catheter...")."""
    for a in tokens_a:
        for b in tokens_b:
            if a == b:
                return True
            if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)):
                return True
    return False


def extract_title(text_field: str):
    if not text_field:
        return None
    lines = text_field.split("\n")
    n = len(lines)

    def next_nonblank(idx):
        while idx < n and not lines[idx].strip():
            idx += 1
        return idx

    i = next_nonblank(0)
    skips_used = 0
    while i < n:
        heading_match = HEADING_RE.match(lines[i].strip())
        if not heading_match:
            return None

        text = strip_full_link(strip_banner(heading_match.group(2).strip()))
        if text.lower() in GENERIC_SECTION_LABELS and skips_used < 2:
            skips_used += 1
            i = next_nonblank(i + 1)
            continue

        title_parts = [text]
        is_all_caps = text == text.upper() and any(c.isalpha() for c in text)
        j = next_nonblank(i + 1)

        if is_all_caps:
            while j < n:
                line = lines[j].strip()
                if not line:
                    j += 1
                    continue
                next_heading = HEADING_RE.match(line)
                if not next_heading:
                    break
                next_text = strip_full_link(strip_banner(next_heading.group(2).strip()))
                if next_text != next_text.upper() or not any(c.isalpha() for c in next_text):
                    break
                title_parts.append(next_text)
                j += 1

        title = " ".join(title_parts).strip()
        return to_sentence_case(title)

    return None


def main():
    apply_changes = "--apply" in sys.argv

    candidates = []
    skipped_no_heading = []
    skipped_no_alnum = []
    topic_mismatch = []

    for path in sorted(PAGES_DIR.glob("**/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        page_id = data.get("PageID", "")
        term1 = data.get("Term1", "")
        if not page_id or not term1:
            continue
        if normalize_slug(term1) != page_id:
            continue

        had_nav_suffix = bool(NAV_SUFFIX_RE.search(term1))

        if page_id in MANUAL_TITLE_OVERRIDES:
            base_title = MANUAL_TITLE_OVERRIDES[page_id]
        else:
            base_title = extract_title(data.get("Text", ""))
            if not base_title:
                skipped_no_heading.append({"path": str(path.relative_to(REPO_ROOT)), "PageID": page_id, "Term1": term1})
                continue
            if not re.search(r"[A-Za-z0-9]", base_title):
                skipped_no_alnum.append({"path": str(path.relative_to(REPO_ROOT)), "PageID": page_id, "Term1": term1, "extracted": base_title})
                continue

            page_id_tokens = tokenize(page_id.replace("-", " "))
            title_tokens = tokenize(base_title)
            if page_id_tokens and not tokens_overlap(page_id_tokens, title_tokens):
                topic_mismatch.append({
                    "path": str(path.relative_to(REPO_ROOT)), "PageID": page_id,
                    "Term1": term1, "extracted": base_title,
                })
                continue

        final_title = base_title
        if had_nav_suffix and not final_title.rstrip().lower().endswith("(navigation)"):
            final_title = f"{final_title} (Navigation)"

        candidates.append({
            "path": path,
            "PageID": page_id,
            "old_Term1": term1,
            "base_title": base_title,
            "new_Term1": final_title,
        })

    # Duplicate detection: exclude candidates whose BASE title (before the
    # "(Navigation)" suffix is appended) collides with another candidate's base
    # title (case-insensitive) from auto-apply.
    title_counts = Counter(c["base_title"].strip().lower() for c in candidates)
    duplicates = [c for c in candidates if title_counts[c["base_title"].strip().lower()] > 1]
    unique_candidates = [c for c in candidates if title_counts[c["base_title"].strip().lower()] == 1]

    print(f"Total slug-leak candidates found: {len(candidates)}")
    print(f"  Safe to auto-apply (unique title): {len(unique_candidates)}")
    print(f"  Excluded as duplicate/generic title: {len(duplicates)}")
    print(f"  Skipped, no heading found: {len(skipped_no_heading)}")
    print(f"  Skipped, extracted title has no alphanumeric content: {len(skipped_no_alnum)}")
    print(f"  Excluded, title shares no words with PageID (topic mismatch): {len(topic_mismatch)}\n")

    for c in unique_candidates:
        rel = c["path"].relative_to(REPO_ROOT)
        print(f"[{'APPLY' if apply_changes else 'DRY-RUN'}] {rel}")
        print(f"    old Term1: {c['old_Term1']!r}")
        print(f"    new Term1: {c['new_Term1']!r}")

    if duplicates:
        print("\n=== EXCLUDED: duplicate/generic titles (needs manual, per-file titles) ===")
        by_title = {}
        for c in duplicates:
            by_title.setdefault(c["base_title"].strip().lower(), []).append(c)
        for title, group in sorted(by_title.items()):
            print(f"  {title!r} ({len(group)} pages):")
            for c in group:
                print(f"    {c['path'].relative_to(REPO_ROOT)}  (PageID={c['PageID']})")

    if skipped_no_heading:
        print("\n=== SKIPPED: no heading found on first non-blank line ===")
        for s in skipped_no_heading:
            print(f"  {s['path']}  Term1={s['Term1']!r}")

    if skipped_no_alnum:
        print("\n=== SKIPPED: extracted title has no alphanumeric content ===")
        for s in skipped_no_alnum:
            print(f"  {s['path']}  Term1={s['Term1']!r}  extracted={s['extracted']!r}")

    if topic_mismatch:
        print("\n=== EXCLUDED: extracted title shares no words with PageID (needs manual review) ===")
        for s in topic_mismatch:
            print(f"  {s['path']}  Term1={s['Term1']!r}  extracted={s['extracted']!r}")

    if apply_changes:
        for c in unique_candidates:
            data = json.loads(c["path"].read_text(encoding="utf-8"))
            data["Term1"] = c["new_Term1"]
            c["path"].write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nApplied {len(unique_candidates)} change(s).")


if __name__ == "__main__":
    main()
