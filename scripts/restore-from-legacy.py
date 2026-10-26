#!/usr/bin/env python3
"""
restore-from-legacy.py

Repairs 001-TestStation CMS pages whose combined Text is blank, truncated or
wrong (stray spreadsheet fragments such as "< OR >") by rebuilding it from the
converted legacy record (the markdown version of the Minneapolis menu that is
still stored in TestStationOMJSON.json under the page's Inpt name).

A page is flagged when its Text+Therapy has under 60% of the legacy word count
or shares under 50% of the legacy vocabulary. Restored text gets the standard
clean-ups (Help and Legend link removed, hard-wrap blank lines reflowed) and
the therapy sections are moved into the Therapy field the same way
split-therapy.py does.

Usage:
  python scripts/restore-from-legacy.py                      # dry run, syndrome groups
  python scripts/restore-from-legacy.py --page ec-gnb        # restrict / add pages (any group)
  python scripts/restore-from-legacy.py --show ec-gnb        # print the rebuilt page
  python scripts/restore-from-legacy.py --apply              # write page JSON files

After --apply:
  python scripts/compile-cms.py
  python scripts/audit-teststation.py

Report: reports/restore-from-legacy-report.json
"""

import argparse
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "cms-data" / "001-TestStation" / "pages"
OMJSON = ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json"
REPORT = ROOT / "reports" / "restore-from-legacy-report.json"

# Groups under "Syndromes and Diseases, by Body Systems" on the main menu.
SYNDROME_GROUPS = {
    "bone-joint-muscle-infections", "cardiovascular", "cns", "gi-intraabdominal",
    "head-and-neck", "lung-and-mediastinum", "ssti-main-menu",
    "system-infectious-diseases", "genitourinary",
}

# Pages whose Inpt pointer is an outpatient stub; use the inpatient record instead.
SOURCE_OVERRIDES = {
    "pyomyositis": {"Inpt": "ORZID2 GMENU PYOMYOSITIS", "Outpt": "ORZID3 GMENU PYOMYOSITIS"},
}

# Heading where the therapy starts, for pages split-therapy's heuristics cannot split
# (the therapy runs from that heading to the separator / References).
THERAPY_FROM = {
    "ec-enterococci": "Organism Susceptibility",
}

# Pages deliberately left alone.
SKIP_PAGES = {"main-menu", "welcome", "drug-allergies"}

MIN_LEGACY_WORDS = 5
MAX_RATIO = 0.6
MIN_COVERAGE = 0.5


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


helplegend = load_script("remove-help-legend-links")
hardwrap = load_script("fix-hardwrap-blank-lines")
splitter = load_script("split-therapy")

LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
REF_LINE_RE = re.compile(r"^\s*(?:#{1,6}\s*)?references?\s*:?\s*$", re.I | re.M)


def words(text):
    """Lower-case word tokens of the body (links reduced to labels, References dropped)."""
    text = LINK_RE.sub(r"\1", text or "")
    m = REF_LINE_RE.search(text)
    if m:
        text = text[:m.start()]
    return re.findall(r"[a-z0-9]{3,}", text.lower())


def page_words(page):
    return words(page.get("Text", "")) + words(page.get("Therapy", ""))


def split_from_heading(text, heading):
    """Move the section starting at `heading` (up to the separator/References) into Therapy."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines)
                  if splitter.HEADING_RE.match(l) and splitter.HEADING_RE.match(l).group(2).strip() == heading), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines))
                if splitter.SEP_RE.match(lines[i]) or splitter.SEP_TITLE_RE.match(splitter.norm(lines[i]))
                or splitter.REF_RE.match(lines[i])), len(lines))
    block = splitter.trim_blank(lines[start:end])
    rest = splitter.trim_blank(lines[:start]) + [""] + lines[end:]
    therapy = "\n".join(splitter.relevel([block])[0])
    return "\n".join(rest), therapy


def rebuild(legacy_text, therapy_from=None):
    """Return (text, therapy) built from a legacy record's markdown text."""
    text, _ = helplegend.strip_help_legend(legacy_text)
    text = hardwrap.reflow(text).strip("\n")
    if therapy_from:
        result = split_from_heading(text, therapy_from)
        if result:
            return result
    try:
        result = splitter.split_page(text)
    except ValueError:
        result = None
    if result:
        new_text, therapy, _ = result
        if splitter.has_body_content(new_text):
            return new_text, therapy
    return text, ""


def assess(page, legacy_text):
    legacy = words(helplegend.strip_help_legend(legacy_text)[0])
    cms = page_words(page)
    if len(legacy) < MIN_LEGACY_WORDS:
        return None
    ratio = len(cms) / len(legacy)
    coverage = len(set(cms) & set(legacy)) / len(set(legacy))
    if ratio < MAX_RATIO or coverage < MIN_COVERAGE:
        return {"legacy_words": len(legacy), "cms_words": len(cms),
                "ratio": round(ratio, 2), "coverage": round(coverage, 2)}
    return None


def write_page(path, page):
    path.write_text(json.dumps(page, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="rewrite page JSON files")
    parser.add_argument("--show", metavar="PAGEID", help="print the rebuilt Text/Therapy for one page")
    parser.add_argument("--page", action="append", metavar="PAGEID",
                        help="process these pages (any group) in addition to the syndrome groups' flagged pages")
    args = parser.parse_args()

    extra = set(args.page or [])
    legacy_by_name = {m["Name"]: m for m in json.loads(OMJSON.read_text(encoding="utf-8"))["menus"]}

    report = {"restored": [], "not_in_scope": [], "no_legacy_source": [], "unchanged": []}
    for path in sorted(PAGES_DIR.glob("*/*.json")):
        page = json.loads(path.read_text(encoding="utf-8"))
        pid = page.get("PageID", path.stem)
        if pid in SKIP_PAGES or (args.show and args.show != pid):
            continue
        override = SOURCE_OVERRIDES.get(pid, {})
        source_name = override.get("Inpt") or page.get("Inpt", "")
        legacy = legacy_by_name.get(source_name)
        if not legacy:
            if source_name:
                report["no_legacy_source"].append({"page": pid, "inpt": source_name})
            continue

        legacy_text = legacy.get("Text", "")
        found = assess(page, legacy_text)
        if pid in override and not found:
            found = {"note": "source override"}
        if not found and pid != args.show:
            continue
        found = found or {}
        entry = {"page": pid, "group": page.get("Group"), "inpt": source_name, **found}

        in_scope = page.get("Group") in SYNDROME_GROUPS or pid in extra or pid == args.show
        if not in_scope:
            report["not_in_scope"].append(entry)
            continue

        new_text, new_therapy = rebuild(legacy_text, THERAPY_FROM.get(pid))
        if new_text == page.get("Text", "") and new_therapy == page.get("Therapy", ""):
            report["unchanged"].append(entry)
            continue
        entry["new_text_words"] = len(words(new_text))
        entry["new_therapy_words"] = len(words(new_therapy))
        report["restored"].append(entry)

        if args.show:
            print("TEXT:\n" + new_text + "\n\nTHERAPY:\n" + new_therapy)

        if args.apply:
            rebuilt = {}
            for key, value in page.items():
                if key in ("Text", "Therapy"):
                    continue
                if key == "Inpt":
                    value = source_name
                rebuilt[key] = value
                if key == "Term2":
                    rebuilt["Text"] = new_text
                    if new_therapy:
                        rebuilt["Therapy"] = new_therapy
            for key, value in override.items():
                rebuilt[key] = value
            write_page(path, rebuilt)

    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    verb = "restored" if args.apply else "would restore"
    print(f"{verb}: {len(report['restored'])}")
    for e in report["restored"]:
        print(f"  {e['group']}/{e['page']}  legacy={e.get('legacy_words')} cms={e.get('cms_words')} "
              f"ratio={e.get('ratio')} cov={e.get('coverage')} -> text={e['new_text_words']}w therapy={e['new_therapy_words']}w")
    print(f"flagged but out of scope: {len(report['not_in_scope'])}")
    for e in report["not_in_scope"]:
        print(f"  {e['group']}/{e['page']}  ratio={e.get('ratio')} cov={e.get('coverage')}")
    print(f"already match source: {len(report['unchanged'])}; no legacy record: {len(report['no_legacy_source'])}")


if __name__ == "__main__":
    main()
