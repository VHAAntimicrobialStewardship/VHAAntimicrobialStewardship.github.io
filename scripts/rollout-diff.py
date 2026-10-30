#!/usr/bin/env python3
"""
rollout-diff.py

Classifies every page of each production station against the test station so the
redesigned content (formatting + Therapy split) can be rolled out without losing
SME edits.

Three versions are compared per page: the fork point (the commit that copied the
test station into the production stations), the current production page, and the
current test-station page.

Categories (per station):
  A       production page unchanged since fork, page exists in test
          -> safe to overwrite with the test-station page
  A-held  would be A, but the test page links to a page that exists in test only
          (not in production), so rolling it out would create broken links
  B       SME-edited; test page is only reformatted/split (same lines, same titles)
  C       SME-edited; test page was changed beyond formatting/splitting
  D       page-ID differences: production-only, test-only, or deleted from
          production since fork

Usage:
  python scripts/rollout-diff.py                 # report only
  python scripts/rollout-diff.py --apply-a       # copy category A test pages into production

Report: reports/rollout-review.json
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORK_COMMIT = "b9498ed8"
TEST = "001-TestStation"
PROD_STATIONS = ["506-AnnArbor", "539-Cincinnati", "541-Cleveland"]
REPORT = ROOT / "reports" / "rollout-review.json"

CONTENT_FIELDS = ("Term1", "Term2", "Inpt", "Outpt", "ERUC")
SEP_RE = re.compile(r"^[_\-=*\s]{8,}$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def norm(value) -> str:
    text = str(value if value is not None else "").replace("\r\n", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def rec_equal(a: dict, b: dict) -> bool:
    keys = set(a) | set(b)
    return all(norm(a.get(k)) == norm(b.get(k)) for k in keys)


def line_bag(rec: dict) -> Counter:
    """Multiset of content lines: ignores order, heading levels, separators, blanks."""
    bag: Counter = Counter()
    for field in ("Text", "Therapy"):
        for line in norm(rec.get(field)).split("\n"):
            line = re.sub(r"^\s*#{1,6}\s*", "", line.strip())
            line = re.sub(r"\s+", " ", line)
            if line and not SEP_RE.match(line):
                bag[line] += 1
    return bag


def run_git(args: list[str], stdin: bytes | None = None) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, input=stdin, check=True,
                          stdout=subprocess.PIPE).stdout


def load_fork(station: str) -> dict[str, dict]:
    """Page records for a station at the fork commit, keyed by PageID."""
    listing = run_git(["ls-tree", "-r", "-z", FORK_COMMIT, "--", f"cms-data/{station}/pages"])
    entries = []
    for item in listing.decode("utf-8").split("\0"):
        if item:
            meta, path = item.split("\t", 1)
            if path.endswith(".json"):
                entries.append((meta.split()[2], path))
    out = run_git(["cat-file", "--batch"], ("\n".join(s for s, _ in entries) + "\n").encode())
    pages, pos = {}, 0
    for sha, path in entries:
        header_end = out.index(b"\n", pos)
        size = int(out[pos:header_end].split()[2])
        body = out[header_end + 1: header_end + 1 + size]
        pos = header_end + 1 + size + 1
        rec = json.loads(body.decode("utf-8"))
        pages[rec.get("PageID", Path(path).stem)] = rec
    return pages


def load_current(station: str) -> dict[str, tuple[dict, Path]]:
    pages = {}
    for f in sorted((ROOT / "cms-data" / station / "pages").rglob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        pages[rec.get("PageID", f.stem)] = (rec, f)
    return pages


def link_targets(rec: dict) -> set[str]:
    targets = set()
    for field in ("Text", "Therapy"):
        for t in LINK_RE.findall(rec.get(field) or ""):
            if not re.match(r"^(?:[a-z]+:|#|/)", t, re.I):
                targets.add(t)
    return targets


def hint_for(rec: dict, others: dict[str, dict]) -> str:
    """Likely rename counterpart: same Inpt pointer, else same Term1."""
    for key in ("Inpt", "Term1"):
        val = norm(rec.get(key))
        if val:
            for pid, o in others.items():
                if norm(o.get(key)) == val:
                    return pid
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply-a", action="store_true", help="overwrite category A production pages with the test pages")
    args = parser.parse_args()

    test = load_current(TEST)
    test_fork = load_fork(TEST)
    test_recs = {pid: r for pid, (r, _) in test.items()}
    report: dict = {}

    for station in PROD_STATIONS:
        prod = load_current(station)
        prod_fork = load_fork(station)
        prod_recs = {pid: r for pid, (r, _) in prod.items()}
        cats: dict[str, list] = {"A": [], "A-held": [], "B": [], "C": [], "D": []}
        ws_only = 0

        for pid, (prec, pfile) in sorted(prod.items()):
            if pid not in test:
                cats["D"].append({"PageID": pid, "kind": "production-only (not in test)",
                                  "sme_edited": pid in prod_fork and not rec_equal(prec, prod_fork[pid]),
                                  "likely_test_counterpart": hint_for(prec, {k: v for k, v in test_recs.items() if k not in prod_recs})})
                continue
            trec = test_recs[pid]
            if pid not in prod_fork:
                cats["D"].append({"PageID": pid, "kind": "new in production since fork"})
                continue
            pfork = prod_fork[pid]
            if rec_equal(prec, pfork):
                if prec != pfork:
                    ws_only += 1
                broken = sorted(t for t in link_targets(trec) if t in test_recs and t not in prod_recs)
                if broken:
                    cats["A-held"].append({"PageID": pid, "links_to_test_only_pages": broken})
                else:
                    cats["A"].append(pid)
                continue
            changed = [k for k in sorted(set(prec) | set(pfork)) if norm(prec.get(k)) != norm(pfork.get(k))]
            tfork = test_fork.get(pid)
            split_only = (tfork is not None
                          and all(norm(trec.get(f)) == norm(tfork.get(f)) for f in CONTENT_FIELDS)
                          and line_bag(trec) == line_bag(tfork))
            cats["B" if split_only else "C"].append({"PageID": pid, "sme_changed_fields": changed})

        for pid in sorted(set(test) - set(prod)):
            cats["D"].append({"PageID": pid, "kind": "test-only (not in production)",
                              "likely_production_counterpart": hint_for(test_recs[pid], {k: v for k, v in prod_recs.items() if k not in test_recs})})
        for pid in sorted(set(prod_fork) - set(prod)):
            cats["D"].append({"PageID": pid, "kind": "in production at fork, deleted since",
                              "in_test": pid in test})

        report[station] = {"counts": {k: len(v) for k, v in cats.items()},
                           "A_whitespace_only_differences": ws_only, **cats}

        if args.apply_a:
            moved = copied = 0
            for pid in cats["A"]:
                tfile = test[pid][1]
                pfile = prod[pid][1]
                src = tfile.read_bytes()
                dest = ROOT / "cms-data" / station / "pages" / tfile.parent.name / tfile.name
                if dest != pfile:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    pfile.unlink()
                    moved += 1
                if not dest.exists() or dest.read_bytes() != src:
                    dest.write_bytes(src)
                    copied += 1
            print(f"{station}: category A applied, {copied} files written, {moved} moved to a new group folder")

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for station, r in report.items():
        print(f"\n=== {station} {r['counts']} (A whitespace-only differences: {r['A_whitespace_only_differences']}) ===")
        for cat in ("B", "C"):
            for item in r[cat]:
                print(f"  {cat}  {item['PageID']}  fields: {', '.join(item['sme_changed_fields'])}")
        for item in r["A-held"]:
            print(f"  A-held  {item['PageID']}  -> {', '.join(item['links_to_test_only_pages'])}")
        for item in r["D"]:
            extra = {k: v for k, v in item.items() if k not in ("PageID", "kind")}
            print(f"  D   {item['PageID']}  [{item['kind']}] {extra if extra else ''}")
    print(f"\nReport written to {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
