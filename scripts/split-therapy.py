#!/usr/bin/env python3
"""
split-therapy.py

Moves therapy sections out of a page's Text into its Therapy field (the
right-hand panel of the sidebar layout) for the 001-TestStation CMS pages in
cms-data/001-TestStation/pages/<group>/<pageid>.json.

Pages that already have a Therapy value are never touched, so hand-edited
splits are safe and the script can be re-run.

A section (a heading and the lines below it, up to the next heading or
separator line) is moved when:

  1. Its heading is "strong": Empiric/Empirical Therapy|Treatment|..., Oral
     switch/step-down, IV-to-oral, Preferred treatment/therapy.
  2. Its heading contains Treatment/Therapy/Treat/Regimen (but is not a
     "Duration ..." or consult heading) AND drug content appears immediately
     below (a dose, frequency, cost marker, drug-order link, <AND>/<OR>, or a
     drug name from AbxLinks.json) or Preferred/Alternative lines appear.
     Drug-class headings (Antibiotics, Antivirals, ...) need a drug signal below.
  3. It contains "Preferred:" / "Alternative:" lines. From the first such line
     to the end of the section is moved; the heading goes along only when
     nothing but blank lines sits between it and the "Preferred:" line.
  4. It directly follows a moved section and is a setting heading (Inpatient,
     Outpatient, ...), a heading with a strong signal or Preferred lines, a
     headless drug body, or a short label that precedes more therapy.

An empty "Treatment" heading is moved only when the section after it moves.
Separator lines between two moved sections are dropped. The References
section (including "[References](references)" links and glued "... References:"
lines) and everything after it always stays in Text; a split that would put a
References line in Therapy is reported as an error and never applied. Pages
whose Text would be left with only the title are skipped unless --include-empty.

Every page is verified to be lossless (every non-blank line of the original
ends up in Text or Therapy, apart from dropped separator lines and heading
levels), and the Therapy headings are re-levelled to start at "##".

Usage:
  python scripts/split-therapy.py                 # dry run: report only
  python scripts/split-therapy.py --apply         # rewrite page JSON files
  python scripts/split-therapy.py --show <PageID> # print before/after for a page
  python scripts/split-therapy.py --page <PageID> # restrict to given page(s)

After --apply:
  python scripts/compile-cms.py
  python scripts/audit-teststation.py

Report: reports/therapy-split-report.json
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "cms-data" / "001-TestStation" / "pages"
ABX_LINKS = ROOT / "AbxLinks.json"
REPORT = ROOT / "reports" / "therapy-split-report.json"

SKIP_PAGES = {"welcome", "main-menu", "inpt-main"}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
SEP_RE = re.compile(r"^\s*[_\-=*]{8,}\s*$")
SEP_TITLE_RE = re.compile(r"^[_\-=*\s]{8,}$")
REF_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:"
    r"\[\s*references?\s*:?\s*\]\([^)]*\)\s*:?\s*$"  # [References](references)
    r"|\**references?\**\s*$"  # References / ## References
    r"|\**references?\**\s*:.*$"  # References: ... (text may follow on the same line)
    r")",
    re.I,
)
FENCE_RE = re.compile(r"^\s*```")

# "Preferred:" / "Alternative:" style label lines (no sentence punctuation).
PREF_RE = re.compile(
    r"^[\s*_>\-]*(?:preferred|alternatives?|primary alternative|secondary alternative|"
    r"first[- ]line|second[- ]line)\b[^.\n]{0,90}$",
    re.I,
)

STRONG_HEAD_RE = re.compile(
    r"\bempiric(?:al)?\b.*\b(?:therapy|treatment|antibiotics?|antimicrobials?|regimens?|coverage)\b"
    r"|\boral\s+(?:switch|step-?down)\b"
    r"|\bstep-?down\b"
    r"|\biv[\s-]+to[\s-]+(?:oral|po)\b"
    r"|\bpreferred\s+(?:treatment|therapy)\b",
    re.I,
)
WEAK_HEAD_RE = re.compile(r"\b(?:treatment|treat|therapy|regimens?)\b", re.I)
# Drug-class headings ("Antibiotics:") count only when drugs are listed right below.
CLASS_HEAD_RE = re.compile(r"\b(?:antibiotics?|antimicrobials?|antivirals?|antifungals?)\b", re.I)
DURATION_RE = re.compile(r"\bduration\b|\bhow long\b|\bconsult", re.I)
SETTING_RE = re.compile(
    r"^(?:in-?patient|out-?patient|adults?|pediatrics?|paediatrics?|children|pregnan\w*|"
    r"non-?pregnant|ward|icu|general ward|critically ill|mild|moderate|severe|"
    r"first[- ]line|alternatives?|preferred|primary|secondary)\b.{0,40}$",
    re.I,
)

DOSE_RE = re.compile(
    r"\b\d[\d.,]*\s?(?:mg|mcg|gm|g|units?|mL|IU|million)\b|\bq\s?\d{1,2}\s?h\b"
    r"|\b(?:BID|TID|QID|QD|QDAY|QHS|PRN)\b"
    r"|\\?\(\\?[$]+\\?\)"  # cost marker, e.g. ($$) or \($$\)
    r"|\[(?:[RMHO]|DI)(?:,\s?(?:[RMHO]|DI))*\]",  # restriction tags, e.g. [R,DI]
    re.I,
)
ROUTE_RE = re.compile(r"\b(?:PO|IV|IM|IVPB)\b")  # case-sensitive; needs a digit on the line
GLUED_REF_RE = re.compile(r"^(.*\S)\s+((?:#{1,6}\s*)?References:.*|\[References\]\([^)]*\):?)\s*$")
ORDER_LINK_RE = re.compile(r"\]\((?:orz-set-abx|ps[a-z]{1,2}i?zid\d*-|psj)", re.I)
ANDOR_RE = re.compile(r"<\s*(?:AND|OR)\s*>", re.I)


def load_abx_regex():
    try:
        data = json.loads(ABX_LINKS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    names = sorted(
        {str(d.get("Name", "")).strip() for d in data if isinstance(d, dict) and d.get("Name")},
        key=len,
        reverse=True,
    )
    if not names:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.I)


ABX_RE = load_abx_regex()


def line_signal(line):
    """'strong' (dose / order link / <AND>/<OR>), 'weak' (drug name only) or None."""
    if (
        DOSE_RE.search(line)
        or ORDER_LINK_RE.search(line)
        or ANDOR_RE.search(line)
        or (ROUTE_RE.search(line) and re.search(r"\d", line))
    ):
        return "strong"
    if (
        ABX_RE
        and ABX_RE.search(line)
        and len(line) <= 100
        and not line.rstrip().endswith(".")
    ):
        return "weak"
    return None


def body_signal(lines, limit=8):
    """Best signal in the first `limit` non-blank lines."""
    best = None
    for line in [l for l in lines if l.strip()][:limit]:
        sig = line_signal(line)
        if sig == "strong":
            return "strong"
        if sig == "weak":
            best = "weak"
    return best


def parse_sections(lines):
    """Split lines into sections. kind: head | body | sep | ref (| title for the page title)."""
    sections = []
    cur = None
    in_fence = False
    in_ref = False
    first_idx = next((i for i, l in enumerate(lines) if l.strip()), -1)

    def start(kind, line, level=0, title=""):
        nonlocal cur
        cur = {"kind": kind, "level": level, "title": title, "lines": [line], "cls": None}
        sections.append(cur)

    for idx, line in enumerate(lines):
        if in_ref:
            cur["lines"].append(line)
            continue
        if FENCE_RE.match(line):
            in_fence = not in_fence
        if not in_fence:
            if idx > 0 and REF_RE.match(line):
                in_ref = True
                start("ref", line)
                continue
            m = HEADING_RE.match(line)
            if m and SEP_TITLE_RE.match(m.group(2)):
                start("sep", line)
                continue
            if SEP_RE.match(line):
                start("sep", line)
                continue
            if m:
                level, title = len(m.group(1)), m.group(2)
                kind = "head"
                if level == 1 and idx == first_idx:
                    kind = "title"  # the page title (first non-blank line)
                start(kind, line, level, title)
                continue
        if cur is None:
            start("body", line)
        elif cur["kind"] == "sep":
            if line.strip() == "":
                cur["lines"].append(line)
            else:
                start("body", line)
        else:
            cur["lines"].append(line)
    return sections


def body_of(section):
    return section["lines"][1:] if section["kind"] in ("head", "title") else section["lines"]


def first_pref_index(section):
    """Index into section['lines'] of the first Preferred/Alternative label line, or None."""
    start = 1 if section["kind"] in ("head", "title") else 0
    in_fence = False
    for i in range(start, len(section["lines"])):
        line = section["lines"][i]
        if FENCE_RE.match(line):
            in_fence = not in_fence
        if in_fence or line.lstrip().startswith("#"):
            continue
        if PREF_RE.match(line):
            return i
    return None


def is_short_label_section(nonblank):
    """A few short non-sentence lines (a link, a label) - not a paragraph of prose."""
    return len(nonblank) <= 3 and all(len(l) <= 80 and not l.rstrip().endswith(".") for l in nonblank)


def classify(sections):
    """Set section['cls'] to therapy | partial | tentative | text and record a reason."""
    state = None  # previous non-sep section: 'therapy' | 'tentative' | None
    for s in sections:
        kind = s["kind"]
        if kind == "sep":
            continue
        if kind == "ref":
            s["cls"] = "text"
            state = None
            continue

        body = body_of(s)
        nonblank = [l for l in body if l.strip()]
        pref_idx = first_pref_index(s)
        title = s["title"]
        is_head = kind == "head"
        duration = bool(DURATION_RE.search(title))
        strong = is_head and bool(STRONG_HEAD_RE.search(title)) and not duration
        pref_head = is_head and bool(PREF_RE.match(title))
        weak = is_head and bool(WEAK_HEAD_RE.search(title)) and not duration
        class_head = is_head and bool(CLASS_HEAD_RE.search(title)) and not duration
        setting = is_head and bool(SETTING_RE.match(title)) and not duration
        signal = body_signal(body)
        chain = state in ("therapy", "tentative")

        cls, reason = "text", ""
        if strong or pref_head:
            label = "strong heading" if strong else "Preferred/Alternative heading"
            cls, reason = ("therapy", label) if nonblank else ("tentative", label + ", empty body")
        elif weak:
            if signal or pref_idx is not None:
                cls, reason = "therapy", "heading + drugs (%s)" % (signal or "preferred/alternative")
            else:
                cls, reason = "tentative", "treatment heading, no drugs below"
        elif class_head and (signal or pref_idx is not None):
            cls, reason = "therapy", "drug-class heading + drugs"
        elif is_head and chain and not duration and (signal == "strong" or pref_idx is not None):
            cls, reason = "therapy", "sub-section of moved section"
        elif is_head and state == "therapy" and setting:
            cls, reason = "therapy", "sub-section of moved section (setting)"
        elif is_head and chain and not duration and is_short_label_section(nonblank):
            cls, reason = "tentative", "short section between moved sections"
        elif kind == "body" and chain and (signal == "strong" or pref_idx is not None):
            cls, reason = "therapy", "continuation of moved section"
        elif pref_idx is not None:
            before = [l for l in s["lines"][(1 if is_head else 0):pref_idx] if l.strip()]
            if is_head and not before:
                cls, reason = "therapy", "Preferred/Alternative block"
            else:
                cls, reason = "partial", "Preferred/Alternative lines"
                s["split_at"] = pref_idx

        s["cls"], s["reason"] = cls, reason
        state = "therapy" if cls in ("therapy", "partial") else ("tentative" if cls == "tentative" else None)

    # Tentative headings are kept only when the next section moves (resolved
    # back to front so chains of headings work).
    nonsep = [s for s in sections if s["kind"] != "sep"]
    for i in range(len(nonsep) - 1, -1, -1):
        s = nonsep[i]
        # An empty heading is a label for the section below it.
        empty_label = (
            s["cls"] == "text"
            and s["kind"] == "head"
            and not any(l.strip() for l in s["lines"][1:])
            and not DURATION_RE.search(s["title"])
        )
        if s["cls"] == "tentative" or empty_label:
            nxt = nonsep[i + 1] if i + 1 < len(nonsep) else None
            if nxt is not None and nxt["cls"] == "therapy":
                s["cls"] = "therapy"
                s["reason"] = (s["reason"] or "label heading") + " (followed by moved section)"
            else:
                s["cls"] = "text"

    # Separators between two moved sections go with them (dropped).
    prev = None
    for i, s in enumerate(sections):
        if s["kind"] != "sep":
            prev = s
            continue
        nxt = next((t for t in sections[i + 1:] if t["kind"] != "sep"), None)
        if prev is not None and nxt is not None and prev["cls"] in ("therapy", "partial") and nxt["cls"] == "therapy":
            s["cls"] = "drop"
        else:
            s["cls"] = "text"


def trim_blank(lines):
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def build(sections):
    """Return (text_lines, therapy_blocks, moved_info)."""
    text = []
    blocks = []
    moved = []
    pending = False  # a removal just happened; tidy the blank line at the junction

    def add_text(lines):
        nonlocal pending
        if not lines:
            return
        if pending:
            while text and not text[-1].strip():
                text.pop()
            lines = list(lines)
            while lines and not lines[0].strip():
                lines.pop(0)
            if not lines:
                return
            if text:
                text.append("")
            pending = False
        text.extend(lines)

    for s in sections:
        cls = s["cls"]
        if cls == "therapy":
            blocks.append(trim_blank(s["lines"]))
            moved.append({"heading": s["title"] or "(no heading)", "reason": s["reason"], "lines": len(trim_blank(s["lines"]))})
            pending = True
        elif cls == "partial":
            k = s["split_at"]
            add_text(s["lines"][:k])
            blocks.append(trim_blank(s["lines"][k:]))
            moved.append({"heading": (s["title"] + " [from first Preferred/Alternative line]") if s["title"] else "(from first Preferred/Alternative line)", "reason": s["reason"], "lines": len(trim_blank(s["lines"][k:]))})
            pending = True
        elif cls == "drop":
            pending = True
        else:
            add_text(s["lines"])
    if pending:
        while text and not text[-1].strip():
            text.pop()
    return text, blocks, moved


def relevel(blocks):
    """Shift therapy headings so the shallowest one is '##'."""
    levels = []
    for block in blocks:
        in_fence = False
        for line in block:
            if FENCE_RE.match(line):
                in_fence = not in_fence
            m = None if in_fence else HEADING_RE.match(line)
            if m:
                levels.append(len(m.group(1)))
    if not levels:
        return blocks
    shift = 2 - min(levels)
    out = []
    for block in blocks:
        new_block = []
        in_fence = False
        for line in block:
            if FENCE_RE.match(line):
                in_fence = not in_fence
            m = None if in_fence else HEADING_RE.match(line)
            if m:
                level = max(2, min(6, len(m.group(1)) + shift))
                line = "#" * level + " " + m.group(2)
            new_block.append(line)
        out.append(new_block)
    return out


def norm(line):
    return re.sub(r"^\s*#{1,6}\s*", "", line).strip()


def content_lines(lines):
    return Counter(
        norm(l) for l in lines if l.strip() and not SEP_RE.match(l) and not SEP_TITLE_RE.match(norm(l))
    )


def split_lines(text):
    """Split text into lines; a 'References:' glued to the end of a line goes on its own line."""
    out = []
    for idx, line in enumerate(text.split("\n")):
        m = GLUED_REF_RE.match(line) if idx else None
        if m:
            out.extend([m.group(1), m.group(2)])
        else:
            out.append(line)
    return out


def split_page(text):
    """Return (new_text, therapy, moved) or None when nothing moves / verification fails."""
    lines = split_lines(text)
    sections = parse_sections(lines)
    classify(sections)
    new_lines, blocks, moved = build(sections)
    if not blocks:
        return None
    blocks = relevel(blocks)
    therapy_lines = []
    for i, block in enumerate(blocks):
        if i:
            therapy_lines.append("")
        therapy_lines.extend(block)
    new_text = "\n".join(new_lines)
    therapy = "\n".join(therapy_lines)

    if content_lines(lines) != content_lines(new_lines) + content_lines(therapy_lines):
        raise ValueError("lossless check failed")
    return new_text, therapy, moved


def has_body_content(text):
    """True if anything other than the title / separators / References remains."""
    lines = text.split("\n")
    sections = parse_sections(lines)
    for s in sections:
        if s["kind"] in ("sep", "ref", "title"):
            if s["kind"] == "title" and any(l.strip() for l in s["lines"][1:]):
                return True
            continue
        if any(l.strip() for l in s["lines"][(1 if s["kind"] == "head" else 0):]) or s["kind"] == "head":
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="rewrite page JSON files")
    parser.add_argument("--show", metavar="PAGEID", help="print before/after for one page")
    parser.add_argument("--page", action="append", metavar="PAGEID", help="only process these pages")
    parser.add_argument("--include-empty", action="store_true",
                        help="with --apply, also rewrite pages whose Text would be left with only the title")
    args = parser.parse_args()

    only = set(args.page or [])
    if args.show:
        only.add(args.show)

    files = sorted(PAGES_DIR.glob("*/*.json"))
    report = {"split": [], "skipped_existing_therapy": [], "empty_text_after_split": [],
              "treatment_heading_without_drugs": [], "dosing_but_not_split": [], "errors": []}
    written = 0

    for path in files:
        try:
            page = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            report["errors"].append({"file": str(path.relative_to(ROOT)), "error": str(exc)})
            continue
        pid = page.get("PageID", path.stem)
        if pid in SKIP_PAGES or (only and pid not in only):
            continue
        text = page.get("Text", "") or ""
        if page.get("Therapy", "").strip():
            report["skipped_existing_therapy"].append(pid)
            continue
        if not text.strip():
            continue

        try:
            result = split_page(text)
        except ValueError as exc:
            report["errors"].append({"page": pid, "error": str(exc)})
            continue

        if result is None:
            # Straggler review hints.
            sections = parse_sections(text.split("\n"))
            for s in sections:
                if s["kind"] == "head" and WEAK_HEAD_RE.search(s["title"]) and not DURATION_RE.search(s["title"]):
                    if re.search(r"\btreatment\b", s["title"], re.I):
                        report["treatment_heading_without_drugs"].append({"page": pid, "heading": s["title"]})
            if DOSE_RE.search(text):
                hits = sum(1 for l in text.split("\n") if DOSE_RE.search(l))
                report["dosing_but_not_split"].append({"page": pid, "group": page.get("Group", ""), "dose_lines": hits})
            continue

        new_text, therapy, moved = result
        entry = {
            "page": pid,
            "group": page.get("Group", ""),
            "moved": moved,
            "therapy_lines": therapy.count("\n") + 1,
            "therapy_preview": therapy.split("\n")[:8],
        }
        if not has_body_content(new_text):
            entry["empty_text_after_split"] = True
            report["empty_text_after_split"].append(pid)
        if any(REF_RE.match(l) for l in therapy.split("\n")):
            entry["references_in_therapy"] = True
            report["errors"].append({"page": pid, "error": "a References line ended up in Therapy"})
        report["split"].append(entry)

        if args.show and pid == args.show:
            print("===== TEXT (after) =====")
            print(new_text)
            print("\n===== THERAPY =====")
            print(therapy)
            print()

        if args.apply:
            if entry.get("empty_text_after_split") and not args.include_empty:
                continue  # leave for manual review
            if entry.get("references_in_therapy"):
                continue  # never apply a split that swallowed the References
            rebuilt = {}
            for key, value in page.items():
                rebuilt[key] = new_text if key == "Text" else value
                if key == "Text":
                    rebuilt["Therapy"] = therapy
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rebuilt, f, indent=2, ensure_ascii=False)
                f.write("\n")
            written += 1

    if not only:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Pages split:                         {len(report['split'])}")
    print(f"  of which text would be empty:      {len(report['empty_text_after_split'])}")
    print(f"Skipped (already have Therapy):      {len(report['skipped_existing_therapy'])}")
    print(f"Treatment heading, no drugs below:   {len(report['treatment_heading_without_drugs'])}")
    print(f"Dosing present but not split:        {len(report['dosing_but_not_split'])}")
    print(f"Errors:                              {len(report['errors'])}")
    if not only:
        print(f"Report: {REPORT.relative_to(ROOT)}")
    if args.apply:
        print(f"Page files rewritten: {written}")
    else:
        print("Dry run: no page files were changed (use --apply).")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
