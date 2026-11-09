"""Wave 2: review workbook for the legacy station records no test page uses (read-only).

    python scripts/wave2-new-page-review.py

Writes reports/wave2-new-page-review.xlsx:
  - "Decide": one row per topic (the same title at several stations is one row), with links that open the
    record on each station's legacy site, the closest existing page, a suggestion and an SME decision column;
  - "Left out": records the crosswalk dropped automatically (order prompts, menus, placeholders, records equal
    to or already accepted as obsolete in the original data), with the reason, for completeness.
Run scripts/wave2-crosswalk.py first.
"""

import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://vhaantimicrobialstewardship.github.io"
STATIONS = {"636-Omaha": ("Omaha", "Omaha"), "636A6-DesMoines": ("Des Moines", "DesMoines"),
            "656-StCloud": ("St. Cloud", "StCloud")}
DECIDE = {"new-page-candidate", "similar-to-page", "title-matches-page"}
LEFT_OUT = {
    "same-as-original": "Same text as the original Minneapolis record (not used by any current page)",
    "obsolete-accepted": "Original record already accepted as obsolete in the 2026-11 legacy cleanup",
    "order-prompt": "VistA order-dialog prompt",
    "navigation": "Menu page (menu structure comes from the test station)",
    "placeholder": "Placeholder, test or under-construction page",
    "dated": "Dated page (old season or year in the name)",
    "duplicate-of-original": "Same text as another original record",
    "changed-unused-original": "Changed copy of an original record no current page uses",
}
COVID = re.compile(r"COVID|\bEUA\b|BAMLANIVIMAB|CASIRIVIMAB|BEBTELOVIMAB|SOTROVIMAB|MOLNUPIRAVIR|PAXLOVID|"
                   r"NIRMATRELVIR|REMDESIVIR|TOCILIZUMAB|BARICITINIB", re.I)
CHOICES = ["New page", "Add to existing page", "Obsolete - leave out", "Not sure"]
# Pages that list many topics; their wording overlaps everything.
AGGREGATE = {"index", "main-menu", "inpt-main", "journal-references", "general-information-inpatient",
             "general-information-outpatient", "help-page"}
NAV_LINK_LINE = re.compile(r"^\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)\)$")


def is_nav(text: str) -> bool:
    lines = [l.strip() for l in text.split("\n")]
    lines = [l for l in lines if l and not l.startswith("<!--") and not re.match(r"^#{1,6}\s+", l)]
    links = sum(1 for l in lines if NAV_LINK_LINE.match(l))
    return links >= 2 and links / len(lines) >= 0.5


def load_cw():
    spec = importlib.util.spec_from_file_location("wave2_crosswalk", ROOT / "scripts" / "wave2-crosswalk.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def group_of(name: str, title: str) -> str:
    if re.search(r"\bIDP\b", name):
        return "Drug information page"
    if COVID.search(name) or COVID.search(title):
        return "COVID-19 treatment (emergency-authorization era)"
    if cw.tier(cw.norm_name(name)) == "ORZID":
        return "ER/UC version of a topic"
    if cw.tier(cw.norm_name(name)) == "ORZID3":
        return "Outpatient version of a topic"
    return "Other topic"


def suggestion(group: str, closest: tuple[str, float] | None) -> str:
    if group == "Drug information page":
        return "Group decision: keep drug information pages on the new site, or point to Micromedex/UpToDate"
    if group.startswith("COVID"):
        return "Likely obsolete; current COVID-19 guidance is on covid-19-mpls-antimicrobial-guideline"
    if closest and closest[1] < 0.5:
        return f"Similar title to {closest[0]}, different wording ({closest[1]:.0%} overlap); compare"
    if closest and closest[1] >= 0.8:
        return f"Mostly covered by {closest[0]} ({closest[1]:.0%} of the old wording is there); likely leave out"
    if closest and closest[1] >= 0.5:
        return f"Partly covered by {closest[0]} ({closest[1]:.0%}); compare and add missing local content there"
    if group.startswith(("ER/UC", "Outpatient")):
        return f"Add as the {group.split(' version')[0]} section of the matching page, or leave out"
    return "No matching page found: new page or leave out"


cw = load_cw()


def main() -> None:
    pages = cw.test_pages()
    page_words = {p["PageID"]: set(cw.flat((p.get("Text") or "") + " " + (p.get("Therapy") or "")).split())
                  for p in pages}
    page_title = {p["PageID"]: p.get("Term1", p["PageID"]) for p in pages}
    nav_pages = {p["PageID"] for p in pages if is_nav(p.get("Text") or "")}
    topics = defaultdict(lambda: {"stations": {}, "names": set()})
    left_out = []
    for folder, (label, prefix) in STATIONS.items():
        res = json.loads((ROOT / "reports" / f"wave2-crosswalk-{folder}.json").read_text(encoding="utf-8"))
        records = {r["Name"]: r for r in cw.load_records(ROOT / res["legacy_file"])}
        for e in res["station_only"]:
            link = f"{SITE}/stations/{folder}/legacy/{prefix}CDSS.html?dropdown={quote(e['name'])}"
            title = (e["title"] or "").strip() or e["name"]
            if e["category"] not in DECIDE:
                left_out.append([label, title, e["name"], LEFT_OUT.get(e["category"], e["category"]), link])
                continue
            lines = cw.lines_of(records[e["name"]])
            key = (group_of(e["name"], title), cw.norm_title(e["title"]) or cw.norm_name(e["name"]).lower())
            t = topics[key]
            t["title"] = t.get("title") or title
            t["stations"][label] = (link, lines)
            t["names"].add(e["name"])
            if e["category"] == "title-matches-page":
                t["same_title"] = e["detail"]

    rows = []
    for (group, _), t in topics.items():
        lines = max((v[1] for v in t["stations"].values()), key=len)
        words = set(cw.words(lines))
        title_words = set(cw.norm_title(t["title"]).split())
        best, score, by_title = None, (0.0, 0.0), (None, 0.0)
        for pid, pw in page_words.items():
            if pid in AGGREGATE or pid in nav_pages:
                continue
            cover = len(words & pw) / len(words) if words else 0.0
            tw = set(cw.norm_title(page_title[pid]).split())
            tsim = len(title_words & tw) / len(title_words | tw) if title_words | tw else 0.0
            if (cover, tsim) > score:
                best, score = pid, (cover, tsim)
            if tsim > by_title[1]:
                by_title = (pid, tsim)
        closest = (best, score[0]) if best and score[0] >= 0.5 else None
        if t.get("same_title") or (not closest and by_title[1] >= 0.5):
            pid = t.get("same_title") or by_title[0]
            closest = (pid, len(words & page_words[pid]) / len(words) if words else 0.0)
        preview = " ".join(lines)[:400]
        rows.append([group, t["title"], ", ".join(l for l in ("Omaha", "Des Moines", "St. Cloud") if l in t["stations"]),
                     *[t["stations"].get(l, ("", None))[0] for l in ("Omaha", "Des Moines", "St. Cloud")],
                     f"{page_title[closest[0]]} ({closest[0]})" if closest else "",
                     f"{SITE}/stations/618-Minneapolis/MinneapolisCDSS.html#{closest[0]}" if closest else "",
                     suggestion(group, closest), "", "", preview, "; ".join(sorted(t["names"]))])
    order = {"Other topic": 0, "Outpatient version of a topic": 1, "ER/UC version of a topic": 2,
             "Drug information page": 3, "COVID-19 treatment (emergency-authorization era)": 4}
    rows.sort(key=lambda r: (order[r[0]], -len(r[2].split(", ")), r[1].lower()))

    wb = Workbook()
    info = wb.active
    info.title = "How to review"
    for line in [
        "Wave 2: old station pages that are not on the new site yet",
        "",
        "Each row on the 'Decide' sheet is one topic from the old (VistA) CDSS of Omaha, Des Moines and/or St. Cloud",
        "that no page on the new site was built from. Nothing from these pages is on the new site.",
        "",
        "1. Filter the Stations column to your station, or the Group column to one group.",
        "2. 'Open' in the station columns shows the old page on that station's old site.",
        "3. 'Open' under Existing page link shows the closest page on the new site (standard Minneapolis content),",
        "   with how much of the old wording it already contains.",
        "4. Choose an SME decision: New page / Add to existing page / Obsolete - leave out / Not sure; add notes.",
        "",
        "Groups: Drug information pages and COVID-19 emergency-authorization pages can be decided once for the",
        "whole group. ER/UC and Outpatient versions are usually added as a section of an existing page.",
        "The 'Left out' sheet lists old records that were dropped automatically (order prompts, menus,",
        "placeholders, unchanged or already-retired records), for reference only.",
    ]:
        info.append([line])
    info["A1"].font = Font(bold=True, size=13)
    info.column_dimensions["A"].width = 110
    ws = wb.create_sheet("Decide")
    head = ["Group", "Topic", "Stations", "Omaha (old site)", "Des Moines (old site)", "St. Cloud (old site)",
            "Closest existing page", "Existing page link", "Suggestion", "SME decision", "Notes",
            "Old page text (start)", "VistA record names"]
    ws.append(head)
    for r in rows:
        ws.append(r)
    link_cols = {4: "Open", 5: "Open", 6: "Open", 8: "Open"}
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if cell.column in link_cols and cell.value:
                cell.hyperlink, cell.value, cell.font = cell.value, link_cols[cell.column], Font(color="0563C1",
                                                                                                underline="single")
    dv = DataValidation(type="list", formula1='"' + ",".join(CHOICES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"J2:J{len(rows) + 1}")
    widths = [22, 40, 18, 10, 12, 10, 40, 10, 50, 20, 30, 70, 40]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions

    lo = wb.create_sheet("Left out")
    lo.append(["Station", "Title", "VistA record name", "Why it was left out", "Old site link"])
    for r in sorted(left_out, key=lambda r: (r[3], r[0], r[1])):
        lo.append(r)
    for row in lo.iter_rows(min_row=2):
        if row[4].value:
            row[4].hyperlink, row[4].value, row[4].font = row[4].value, "Open", Font(color="0563C1", underline="single")
    for i, w in enumerate([12, 45, 50, 60, 10]):
        lo.column_dimensions[chr(65 + i)].width = w
    for cell in lo[1]:
        cell.font = Font(bold=True)
    lo.freeze_panes = "A2"
    lo.auto_filter.ref = lo.dimensions

    out = ROOT / "reports" / "wave2-new-page-review.xlsx"
    wb.save(out)
    counts = defaultdict(int)
    for r in rows:
        counts[r[0]] += 1
    print(f"{len(rows)} topics to decide: {dict(counts)}; {len(left_out)} records left out automatically")
    print(f"written: {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
