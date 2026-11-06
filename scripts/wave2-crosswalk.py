"""Wave 2 crosswalk (read-only): match each wave 2 station's legacy VistA records to the original
Minneapolis records and the test station's combined pages, and classify what the station changed.

    python scripts/wave2-crosswalk.py                 # all wave 2 legacy stations
    python scripts/wave2-crosswalk.py --station 636-Omaha

The original Minneapolis data (stations/000-OriginalCDSS) is the common baseline: a line that differs
between the station's record and the original record is the station's local wording. Each test page
names its legacy sources (Inpt/Outpt/ERUC); every source is matched to the station's record by name
(the Omaha NE / Des Moines CI token removed), then by title within the same tier (ORZID = ER/UC,
ORZID2 = inpatient, ORZID3 = outpatient).

Writes reports/wave2-crosswalk-<station>.json and a readable .txt. Changes no data.
"""

import argparse
import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "stations" / "000-OriginalCDSS" / "OriginalOMJSON.json"
TEST_PAGES = ROOT / "cms-data" / "001-TestStation" / "pages"
OBSOLETE = ROOT / "reports" / "legacy-obsolete-accepted.json"
WAVE2 = ["636-Omaha", "636A6-DesMoines", "656-StCloud"]
SETTINGS = (("Inpt", "Inpatient"), ("Outpt", "Outpatient"), ("ERUC", "ER/UC"))

# VistA help-row, feedback-link and review-date lines; the new site has its own equivalents.
BOILERPLATE = re.compile(r"^(select here for )?help, legend\b|click here to (contact|send comments to) the cdss team|"
                         r"^section last (reviewed|updated)\b", re.I)
UNIT = re.compile(r"^\d|^(mg|gm|g|mcg|units?|mu|ml|l|kg|mg/kg|mcg/ml|hrs?|hours?|days?|weeks?|months?|doses?|"
                  r"q\d+h|q\d+-\d+h|qday|qd|bid|tid|qid|daily|weekly|once|iv|po|im|pr|stat|x\d+.*)$", re.I)
ORDER_PROMPT = re.compile(r"\b(ADJ(UST)? THERA|ALLERGIC TO|ALT OTHER REASON|DECREASED RENAL|DRUG INTERACTION|"
                          r"LIVER SECRETORY|MULTIPLE INFECTIONS|OTHER ADVERSE)\b|\bG?SET\b")
PLACEHOLDER = re.compile(r"UNDER CONSTRUCTION|TESTING|\bTEST\b|PLACEHOLDER|BLANK PAGE")
YEAR = re.compile(r"\b20\d\d\b")
# A station record that only says the guidance is not available locally.
NOT_AVAILABLE = re.compile(r"RECOMMENDATIONS NOT AVAILABLE|REFER TO SYNDROME OR INFECTIOUS DISEASE FOR RECOMMENDATIONS", re.I)


def norm_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip().upper())
    return re.sub(r"^(ORZID\d?) (NE|CI|IC) ", r"\1 ", name)


def tier(name: str) -> str:
    return name.split(" ")[0]


def norm_title(title: str) -> str:
    title = re.sub(r"\((inpt|inpatient|opt|outpt|outpatient|er/uc|er|uc|ed)\)", " ", title or "", flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def lines_of(record: dict) -> list[str]:
    """Display lines of a raw VistA record in row/column order, without the help boilerplate."""
    rows = sorted(record.get("Contents") or [], key=lambda r: (r.get("Row", 0), r.get("Column", 0)))
    out = []
    for row in rows:
        text = re.sub(r"\s+", " ", str(row.get("Text") or row.get("DisplayText") or "")).strip()
        if text and not BOILERPLATE.search(text):
            out.append(text)
    return out


def flat(text: str) -> str:
    """Lower-case words only, for substring checks against markdown pages."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return " ".join(re.findall(r"[a-z0-9]+(?:[./-][a-z0-9]+)*", text.lower()))


def words(lines: list[str]) -> list[str]:
    return flat(" ".join(lines)).split()


def load_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data["menus"]


def drug_names() -> list[str]:
    links = json.loads((ROOT / "AbxLinks.json").read_text(encoding="utf-8"))
    return sorted({flat(e["Name"]) for e in links if e.get("Name")}, key=len, reverse=True)


DRUGS = drug_names()


def is_clinical(removed: list[str], added: list[str]) -> bool:
    a, b = Counter(words(removed)), Counter(words(added))
    if any(UNIT.match(w) for w in (a - b) + (b - a)):
        return True
    ra, rb = flat(" ".join(removed)), flat(" ".join(added))
    return any((d in ra) != (d in rb) for d in DRUGS)


def context(lines: list[str], start: int, step: int) -> str:
    """Nearest line of at least three words from start in direction step (up to three lines away)."""
    for k in range(3):
        i = start + step * k
        if 0 <= i < len(lines) and len(flat(lines[i]).split()) >= 3:
            return lines[i]
    return ""


def hunks(orig: list[str], station: list[str], page_flat: str) -> list[dict]:
    """Station changes against the original record, with where they could be placed on the test page."""
    o_key = [flat(x) for x in orig]
    s_key = [flat(x) for x in station]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, o_key, s_key, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        removed, added = orig[i1:i2], station[j1:j2]
        if words(removed) == words(added):
            continue  # line wrap only
        before, after = context(orig, i1 - 1, -1), context(orig, i2, 1)
        found = [bool(c) and flat(c) in page_flat for c in (before, after)]
        removed_on_page = bool(removed) and all(flat(x) in page_flat for x in removed if flat(x))
        if not added and not removed_on_page:
            continue  # the station dropped lines the test page no longer has
        out.append({
            "kind": "replace" if removed and added else "insert" if added else "delete",
            "removed": removed,
            "added": added,
            "clinical": is_clinical(removed, added),
            "dated": bool(YEAR.search(" ".join(added))),
            "anchor_before": before,
            "anchor_after": after,
            "placement": "both" if all(found) else "one" if any(found) else "none",
            "removed_on_page": removed_on_page,
        })
    return out


def test_pages() -> list[dict]:
    pages = []
    for f in sorted(TEST_PAGES.rglob("*.json")):
        page = json.loads(f.read_text(encoding="utf-8"))
        page["_group"] = f.parent.name
        page["_file"] = f.relative_to(TEST_PAGES).as_posix()
        pages.append(page)
    return pages


def crosswalk(folder: str, original: list[dict], pages: list[dict], obsolete: set[str]) -> dict:
    station_file = next((ROOT / "stations" / folder / "legacy").glob("*OMJSON.json"))
    station = load_records(station_file)
    orig_by = {norm_name(r["Name"]): r for r in original}
    st_by = {norm_name(r["Name"]): r for r in station}
    st_by_title = defaultdict(list)
    for r in station:
        st_by_title[(tier(norm_name(r["Name"])), norm_title(r.get("DisplayText")))].append(r)

    used = set()  # station record names matched to a test page source
    matches = {}  # (PageID, field) -> (original record, station record or None, how)
    for page in pages:
        for field, _ in SETTINGS:
            legacy = page.get(field)
            o = orig_by.get(norm_name(legacy)) if legacy else None
            if not o:
                continue
            s, how = st_by.get(norm_name(legacy)), "name"
            if not s:
                cands = [r for r in st_by_title.get((tier(o["Name"]), norm_title(o.get("DisplayText"))), [])
                         if r["Name"] not in used and norm_name(r["Name"]) not in orig_by]
                s, how = (cands[0], "title") if len(cands) == 1 else (None, "none")
            if s:
                used.add(s["Name"])
            matches[(page["PageID"], field)] = (o, s, how)
    # Renamed records: same tier, not an original name, mostly the same words as the original record.
    spare = [r for r in station if r["Name"] not in used and norm_name(r["Name"]) not in orig_by]
    spare_words = {r["Name"]: set(words(lines_of(r))) for r in spare}
    for key, (o, s, how) in matches.items():
        if s:
            continue
        ow = set(words(lines_of(o)))
        best, score = None, 0.0
        for r in spare:
            if r["Name"] in used or tier(norm_name(r["Name"])) != tier(o["Name"]) or not ow:
                continue
            sw = spare_words[r["Name"]]
            j = len(ow & sw) / len(ow | sw) if sw else 0.0
            if j > score:
                best, score = r, j
        if best and score >= 0.5:
            used.add(best["Name"])
            matches[key] = (o, best, f"content {score:.2f}")

    result_pages = []
    for page in pages:
        page_flat = flat((page.get("Text") or "") + "\n" + (page.get("Therapy") or ""))
        sources = []
        for field, setting in SETTINGS:
            legacy = page.get(field)
            if not legacy:
                continue
            if (page["PageID"], field) not in matches:
                sources.append({"setting": setting, "legacy": legacy, "status": "no-source"})
                continue
            o, s, how = matches[(page["PageID"], field)]
            src = {"setting": setting, "legacy": legacy, "station_record": s["Name"] if s else None, "match": how}
            if not s:
                src["status"] = "missing"
            elif (NOT_AVAILABLE.search(" ".join(lines_of(s)))
                  and not NOT_AVAILABLE.search(" ".join(lines_of(o)))):
                src["status"] = "station-placeholder"
            else:
                h = hunks(lines_of(o), lines_of(s), page_flat)
                src["status"] = "changed" if h else "identical"
                if h:
                    src["hunks"] = h
            sources.append(src)
        statuses = {s["status"] for s in sources}
        if "changed" in statuses:
            all_h = [h for s in sources for h in s.get("hunks", [])]
            cls = "local-clinical" if any(h["clinical"] for h in all_h) else "local-text"
            place = ("auto" if all(h["placement"] == "both" for h in all_h)
                     else "fallback" if any(h["placement"] == "none" for h in all_h) else "partial")
        elif "identical" in statuses:
            cls, place = "inherit-identical", ""
        elif statuses & {"missing", "station-placeholder"}:
            cls, place = "inherit-missing", ""
        else:
            cls, place = "no-legacy-source", ""
        result_pages.append({"page": page["PageID"], "group": page["_group"], "title": page.get("Term1", ""),
                             "class": cls, "placement": place, "sources": sources})

    # Station records no test page uses.
    orig_lines = {tuple(flat(x) for x in lines_of(r)): r["Name"] for r in original}
    page_titles = {norm_title(p.get("Term1")): p["PageID"] for p in pages if p.get("Term1")}
    page_words = {p["PageID"]: set(flat((p.get("Text") or "") + " " + (p.get("Therapy") or "")).split())
                  for p in pages}
    station_only = []
    for r in station:
        if r["Name"] in used:
            continue
        n, lines = norm_name(r["Name"]), lines_of(r)
        o = orig_by.get(n)
        entry = {"name": r["Name"], "title": r.get("DisplayText", ""), "lines": len(lines)}
        key = tuple(flat(x) for x in lines)
        link_rows = sum(1 for c in r.get("Contents") or [] if c.get("Item"))
        if o and key == tuple(flat(x) for x in lines_of(o)):
            entry["category"], entry["detail"] = "same-as-original", o["Name"]
        elif o and n in obsolete:
            entry["category"], entry["detail"] = "obsolete-accepted", o["Name"]
        elif ORDER_PROMPT.search(n):
            entry["category"] = "order-prompt"
        elif PLACEHOLDER.search(n) or PLACEHOLDER.search((r.get("DisplayText") or "").upper()) or not lines:
            entry["category"] = "placeholder"
        elif YEAR.search(n):
            entry["category"] = "dated"
        elif link_rows >= 2 and link_rows * 2 >= len(lines):
            entry["category"] = "navigation"
        elif key in orig_lines:
            entry["category"], entry["detail"] = "duplicate-of-original", orig_lines[key]
        elif norm_title(r.get("DisplayText")) in page_titles:
            entry["category"], entry["detail"] = "title-matches-page", page_titles[norm_title(r.get("DisplayText"))]
        elif o:
            entry["category"], entry["detail"] = "changed-unused-original", o["Name"]
        else:
            rw = set(words(lines))
            best, score = "", 0.0
            for pid, pw in page_words.items():
                j = len(rw & pw) / len(rw | pw) if rw and pw else 0.0
                if j > score:
                    best, score = pid, j
            if score >= 0.4:
                entry["category"], entry["detail"] = "similar-to-page", f"{best} ({score:.2f})"
            else:
                entry["category"] = "new-page-candidate"
        station_only.append(entry)

    summary = {
        "records": len(station),
        "pages": Counter(p["class"] for p in result_pages),
        "local_placement": Counter(p["placement"] for p in result_pages if p["placement"]),
        "station_only": Counter(e["category"] for e in station_only),
        "match_by_title": sum(1 for p in result_pages for s in p["sources"] if s.get("match") == "title"),
        "match_by_content": sum(1 for p in result_pages for s in p["sources"]
                                if str(s.get("match", "")).startswith("content")),
    }
    return {"station": folder, "legacy_file": station_file.relative_to(ROOT).as_posix(),
            "summary": summary, "pages": result_pages, "station_only": station_only}


def mark_shared(results: list[dict]) -> None:
    """Flag hunks whose change appears identically in another wave 2 station (older shared baseline)."""
    seen = defaultdict(set)
    for res in results:
        for p in res["pages"]:
            for s in p["sources"]:
                for h in s.get("hunks", []):
                    seen[(tuple(words(h["removed"])), tuple(words(h["added"])))].add(res["station"])
    for res in results:
        for p in res["pages"]:
            for s in p["sources"]:
                for h in s.get("hunks", []):
                    others = seen[(tuple(words(h["removed"])), tuple(words(h["added"])))] - {res["station"]}
                    h["shared_with"] = sorted(others)


def write_text(res: dict, path: Path) -> None:
    out = [f"Wave 2 crosswalk: {res['station']} ({res['legacy_file']})", ""]
    for k, v in res["summary"].items():
        out.append(f"{k}: {dict(v) if isinstance(v, Counter) else v}")
    for p in res["pages"]:
        if not p["class"].startswith("local"):
            continue
        out += ["", f"=== {p['page']} [{p['class']}, {p['placement']}] {p['title']}"]
        for s in p["sources"]:
            if s["status"] != "changed":
                continue
            out.append(f"  -- {s['setting']}: {s['station_record']} (matched by {s['match']})")
            for h in s["hunks"]:
                flags = [h["kind"]] + [f for f in ("clinical", "dated") if h[f]] + ([f"shared:{','.join(h['shared_with'])}"]
                                                                      if h.get("shared_with") else [])
                out.append(f"     [{h['placement']} {' '.join(flags)}]")
                out += [f"       - {x}" for x in h["removed"]] + [f"       + {x}" for x in h["added"]]
    out += ["", "=== Station records not used by any test page"]
    for e in sorted(res["station_only"], key=lambda e: (e["category"], e["name"])):
        out.append(f"  {e['category']:<24} {e['name']} | {e['title']} ({e['lines']} lines)"
                   + (f" -> {e['detail']}" if e.get("detail") else ""))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", action="append", choices=WAVE2, help="default: all wave 2 legacy stations")
    args = ap.parse_args()
    original = load_records(ORIGINAL)
    pages = test_pages()
    obsolete = {norm_name(n) for n in json.loads(OBSOLETE.read_text(encoding="utf-8"))["names"]}
    # Shared-change flags need every station, so all are computed; only the selected ones are written.
    results = [crosswalk(folder, original, pages, obsolete) for folder in WAVE2]
    mark_shared(results)
    for res in results:
        if args.station and res["station"] not in args.station:
            continue
        base = ROOT / "reports" / f"wave2-crosswalk-{res['station']}"
        base.with_suffix(".json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_text(res, base.with_suffix(".txt"))
        s = res["summary"]
        print(f"=== {res['station']}: {s['records']} legacy records")
        print(f"  test pages: {dict(s['pages'])} (sources matched by title: {s['match_by_title']},"
              f" by content: {s['match_by_content']})")
        print(f"  local-change placement: {dict(s['local_placement'])}")
        print(f"  unused station records: {dict(s['station_only'])}")
        print(f"  report: {base.relative_to(ROOT).as_posix()}.json / .txt")


if __name__ == "__main__":
    main()
