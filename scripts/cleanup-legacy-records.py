"""Legacy VistA record cleanup for the four CMS stations (dry run by default).

    python scripts/cleanup-legacy-records.py                    # dry run, all four stations
    python scripts/cleanup-legacy-records.py --station 541-Cleveland
    python scripts/cleanup-legacy-records.py --apply            # archive + delete legacy records

Legacy records are OMJSON records whose Name starts with "ORZ" (ORZID2 = inpatient,
ORZID3 = outpatient, ORZID = ER/UC) and that are not CMS pages. Each one is labelled:
  superseded      a combined page covers it (its Combined field, a combined page's
                  Inpt/Outpt/ERUC pointer, or a shared search Term)
  link-target     a non-legacy page's Text/Therapy link resolves through it today
                  (any tier of resolveEmbeddedLinkTarget / resolveTargetForCurrentVersion)
  search-visible  shown in combined-mode search (no Combined field and at least one Term)
  orphan-content  not superseded: deleting it loses content unless promoted or obsoleted
  safe-to-delete  not orphan-content and no link depends on it

Link resolution is simulated before and after removing the legacy records (mirrors
shared/cdss-app.js); a link whose result changes is a dependent link that must be
repointed before --apply. Reports: reports/legacy-cleanup-<station>.json.

--apply refuses to run while any dependent link or undecided orphan-content record
remains. It writes docs/legacy-archive/<station>-legacy-records.json first, then
removes the records from the station OMJSON file. (Applied 2026-11-05; the four
archives were identical, so only 001-TestStation-legacy-records.json was kept, with a note.)
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent

# (station folder, OMJSON filename, ODJSON filename)
STATIONS: list[tuple[str, str, str]] = [
    ("001-TestStation", "TestStationOMJSON.json", "TestStationODJSON.json"),
    ("506-AnnArbor", "AnnArborOMJSON.json", "AnnArborODJSON.json"),
    ("539-Cincinnati", "CincinnatiOMJSON.json", "CincinnatiODJSON.json"),
    ("541-Cleveland", "ClevelandOMJSON.json", "ClevelandODJSON.json"),
]
MAIN_MENUS = {"main-menu", "inpt-main"}
LEGACY_NAME_RE = re.compile(r"^ORZ")
TERM_KEY_RE = re.compile(r"^Term\d+$")
WORD_RE = re.compile(r"[A-Za-z0-9]+")
ARCHIVE_DIR = ROOT / "docs" / "legacy-archive"
REPORT_DIR = ROOT / "reports"

# Orphan-content records the user marked obsolete (deleted without promotion). JSON keeps
# the trailing spaces some legacy Names have.
OBSOLETE_LIST = REPORT_DIR / "legacy-obsolete-accepted.json"
OBSOLETE_ACCEPTED: set[str] = (
    set(json.loads(OBSOLETE_LIST.read_text(encoding="utf-8"))["names"]) if OBSOLETE_LIST.exists() else set()
)
# Superseded records whose topic words are less covered than this by the superseding page.
LOW_COVERAGE = 0.5

STOPWORDS = set("""
the and for with from that this are was were not but all any can may per use used using
has have had into than then when which who will within without also each other only one two
see menu click page select order orders return previous main gmenu abx orzid orzid2 orzid3
""".split())


def normalize_comparable_id(value: str) -> str:
    """Mirrors normalizeComparableId in shared/cdss-app.js."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def extract_markdown_links(text: str) -> list[tuple[str, str]]:
    """Port of extractMarkdownLinks (balanced brackets/parens, backslash escapes).

    Returns [(label, target)]; images (![alt](src)) are skipped.
    """
    links = []
    index = 0
    n = len(text)
    while index < n:
        start = text.find("[", index)
        if start == -1:
            break
        cursor, depth = start + 1, 1
        while cursor < n and depth > 0:
            ch = text[cursor]
            if ch == "\\":
                cursor += 2
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            cursor += 1
        if depth != 0 or cursor >= n or text[cursor] != "(":
            index = start + 1
            continue
        label_end = cursor - 1
        target_start = cursor + 1
        cursor, depth = target_start, 1
        while cursor < n and depth > 0:
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
            index = start + 1
            continue
        if not (start > 0 and text[start - 1] == "!"):
            links.append((text[start + 1:label_end], text[target_start:cursor - 1]))
        index = cursor
    return links


class Resolver:
    """Simulates resolveEmbeddedLinkTarget + resolveTargetForCurrentVersion (combined mode)."""

    def __init__(self, records: list[dict], od_records: list[dict]):
        self.by_lower: dict[str, dict] = {}
        self.by_norm: dict[str, dict] = {}
        self.reverse: dict[str, dict] = {}
        for rec in records:
            name = rec.get("Name", "")
            self.by_lower.setdefault(name.strip().lower(), rec)
            self.by_norm.setdefault(normalize_comparable_id(name), rec)
            for field in ("Inpt", "Outpt", "ERUC"):
                value = (rec.get(field) or "").strip().lower()
                if value:
                    self.reverse.setdefault(value, rec)
        self.od_by_norm: dict[str, str] = {}
        for od in od_records:
            self.od_by_norm.setdefault(normalize_comparable_id(od.get("Name", "")), od.get("Name", ""))

    def for_current_version(self, name: str) -> tuple[str, list[str]]:
        """Returns (final name, names of records consulted on the way)."""
        name = (name or "").strip()
        direct = self.by_lower.get(name.lower())
        if direct and (direct.get("Inpt") or "").strip():
            return direct["Name"], [direct["Name"]]
        if direct and direct.get("Combined"):
            mapped = self.by_lower.get(direct["Combined"].strip().lower())
            if mapped:
                return mapped["Name"], [direct["Name"], mapped["Name"]]
        reverse = self.reverse.get(name.lower())
        if reverse:
            return reverse["Name"], ([direct["Name"]] if direct else []) + [reverse["Name"]]
        return name, ([direct["Name"]] if direct else [])

    def resolve(self, target: str) -> dict | None:
        """Returns {final, tier, via} or None when nothing matches."""
        t = (target or "").strip()
        if not t:
            return None
        if t.lower().startswith("cdss:"):
            final, via = self.for_current_version(t[5:].strip())
            return {"final": final, "tier": "cdss", "via": via}
        direct = self.by_lower.get(t.lower())
        if direct:
            final, via = self.for_current_version(direct["Name"])
            return {"final": final, "tier": 1, "via": via}
        by_norm = self.by_norm.get(normalize_comparable_id(t))
        if by_norm:
            final, via = self.for_current_version(by_norm["Name"])
            return {"final": final, "tier": 2, "via": [by_norm["Name"], *via]}
        od_name = self.od_by_norm.get(normalize_comparable_id(t))
        if od_name:
            return {"final": od_name, "tier": "od", "via": []}
        return None


def terms(rec: dict) -> list[str]:
    return [v for k, v in rec.items() if TERM_KEY_RE.match(k) and isinstance(v, str) and v.strip()]


def plain_words(text: str) -> list[str]:
    """Words of a page with link targets removed (labels kept)."""
    stripped = text or ""
    for label, target in extract_markdown_links(stripped):
        stripped = stripped.replace(f"[{label}]({target})", f" {label} ", 1)
    return WORD_RE.findall(stripped)


def topic_words(text: str) -> set[str]:
    return {w.lower() for w in plain_words(text) if len(w) >= 3 and w.lower() not in STOPWORDS}


def load_station(station_dir: str, om_file: str, od_file: str) -> dict:
    station_path = ROOT / "stations" / station_dir
    om_path = station_path / om_file
    data = json.loads(om_path.read_text(encoding="utf-8"))
    od = json.loads((station_path / od_file).read_text(encoding="utf-8"))
    cms_ids = set()
    for page_file in (ROOT / "cms-data" / station_dir / "pages").rglob("*.json"):
        page = json.loads(page_file.read_text(encoding="utf-8"))
        cms_ids.add(page.get("PageID") or page_file.stem)
    return {"om_path": om_path, "data": data, "od": od, "cms_ids": cms_ids}


def is_legacy(rec: dict, cms_ids: set[str]) -> bool:
    name = rec.get("Name", "")
    return bool(LEGACY_NAME_RE.match(name)) and name not in cms_ids and not (rec.get("Inpt") or "").strip()


def analyse_station(station_dir: str, loaded: dict) -> dict:
    menus: list[dict] = loaded["data"]["menus"]
    od = loaded["od"]
    cms_ids = loaded["cms_ids"]

    legacy = [m for m in menus if is_legacy(m, cms_ids)]
    legacy_names = {m["Name"] for m in legacy}
    current = [m for m in menus if m["Name"] not in legacy_names]
    current_names = {m["Name"] for m in current}
    unclassified = sorted(
        m["Name"] for m in current
        if m["Name"] not in cms_ids and m["Name"] not in MAIN_MENUS
    )

    before = Resolver(menus, od)
    after = Resolver(current, od)
    by_name = {m["Name"]: m for m in menus}

    # ── Coverage by combined pages ──
    pointed_by: dict[str, tuple[str, str]] = {}
    for page in current:
        for field in ("Inpt", "Outpt", "ERUC"):
            value = (page.get(field) or "").strip()
            if value in legacy_names:
                pointed_by.setdefault(value, (page["Name"], field))
    term_owner: dict[str, str] = {}
    for page in current:
        for term in terms(page):
            term_owner.setdefault(normalize_comparable_id(term), page["Name"])

    superseded: dict[str, tuple[str, str]] = {}
    for rec in legacy:
        name = rec["Name"]
        combined = (rec.get("Combined") or "").strip()
        if combined in current_names:
            superseded[name] = (combined, "Combined field")
        elif name in pointed_by:
            superseded[name] = (pointed_by[name][0], f"combined page {pointed_by[name][1]} pointer")
        else:
            for term in terms(rec):
                owner = term_owner.get(normalize_comparable_id(term))
                if owner:
                    superseded[name] = (owner, f"shared Term '{term}'")
                    break
    # A legacy Combined that names another legacy record (ER/UC -> inpatient) is followed one more hop.
    for rec in legacy:
        combined = (rec.get("Combined") or "").strip()
        if rec["Name"] not in superseded and combined in superseded:
            superseded[rec["Name"]] = (superseded[combined][0], f"Combined field via {combined}")

    # ── Links on non-legacy pages, resolved with and without the legacy records ──
    links_total = unresolved_before = unresolved_after = 0
    dependent = []
    linked_from: dict[str, list[dict]] = {}
    for page in current:
        for field in ("Text", "Therapy"):
            for label, target in extract_markdown_links(page.get(field) or ""):
                t = target.strip()
                if not t or t.lower().startswith(("http://", "https://", "mailto:", "/")):
                    continue
                links_total += 1
                res_before = before.resolve(t)
                res_after = after.resolve(t)
                if res_before is None:
                    unresolved_before += 1
                if res_after is None:
                    unresolved_after += 1
                via_legacy = [n for n in (res_before or {}).get("via", []) if n in legacy_names]
                for name in dict.fromkeys(via_legacy):
                    linked_from.setdefault(name, []).append(
                        {"page": page["Name"], "field": field, "target": t, "tier": res_before["tier"]}
                    )
                final_before = res_before["final"] if res_before else None
                final_after = res_after["final"] if res_after else None
                kind_before = (res_before or {}).get("tier") == "od"
                kind_after = (res_after or {}).get("tier") == "od"
                if final_before == final_after and kind_before == kind_after:
                    continue
                if final_before in current_names:
                    fix = {"action": "repoint", "to": final_before}
                elif final_before in superseded:
                    fix = {"action": "repoint", "to": superseded[final_before][0],
                           "note": f"runtime opens legacy {final_before} today"}
                else:
                    fix = {"action": "needs-decision", "legacy": final_before}
                dependent.append({
                    "page": page["Name"], "field": field, "label": label, "target": t,
                    "tierBefore": res_before["tier"] if res_before else None,
                    "viaLegacy": list(dict.fromkeys(via_legacy)),
                    "before": final_before, "after": final_after,
                    "afterIsOrderDialog": kind_after, "fix": fix,
                })

    candidates_pool = [
        (p["Name"], p.get("Term1") or p["Name"], topic_words(p.get("Text", "") + "\n" + p.get("Therapy", "")),
         topic_words(" ".join(terms(p)) + " " + p["Name"].replace("-", " ")))
        for p in current if p["Name"] not in MAIN_MENUS
    ]

    def suggest(rec: dict) -> list[dict]:
        words = topic_words(rec.get("Text", ""))
        title = topic_words(" ".join(terms(rec)) + " " + rec["Name"])
        if not words:
            return []
        scored = []
        for name, label, cwords, ctitle in candidates_pool:
            if not cwords:
                continue
            shared = len(words & cwords)
            containment = shared / len(words)
            jaccard = shared / len(words | cwords)
            title_overlap = len(title & ctitle) / len(title) if title else 0.0
            score = 0.5 * containment + 0.3 * jaccard + 0.2 * title_overlap
            scored.append((score, name, label, containment, jaccard, title_overlap))
        scored.sort(reverse=True)
        return [
            {"page": name, "title": label, "score": round(s, 3), "containment": round(c, 3),
             "jaccard": round(j, 3), "titleOverlap": round(t, 3)}
            for s, name, label, c, j, t in scored[:3]
        ]

    depended_on = {n for d in dependent for n in d["viaLegacy"]}
    # Legacy pages that link to each legacy page (shows which orphans hang under which).
    legacy_parents: dict[str, list[str]] = {}
    for rec in legacy:
        for _label, target in extract_markdown_links(rec.get("Text") or ""):
            res = before.resolve(target)
            for n in dict.fromkeys((res or {}).get("via", [])):
                if n in legacy_names and n != rec["Name"] and rec["Name"] not in legacy_parents.get(n, []):
                    legacy_parents.setdefault(n, []).append(rec["Name"])
    records = []
    for rec in legacy:
        name = rec["Name"]
        labels = []
        superseded_by, how = superseded.get(name, (None, None))
        rec_terms = terms(rec)
        search_visible = not rec.get("Combined") and bool(rec_terms)
        if superseded_by:
            labels.append("superseded")
        if name in linked_from:
            labels.append("link-target")
        if search_visible:
            labels.append("search-visible")
        orphan = not superseded_by and name not in OBSOLETE_ACCEPTED
        if orphan:
            labels.append("orphan-content")
        if not orphan and name not in depended_on:
            labels.append("safe-to-delete")
        entry = {
            "name": name,
            "terms": rec_terms,
            "words": len(plain_words(rec.get("Text", ""))),
            "labels": labels,
            "supersededBy": superseded_by,
            "supersededHow": how,
            "linkedFrom": linked_from.get(name, []),
            "legacyParents": legacy_parents.get(name, []),
        }
        if orphan:
            entry["candidates"] = suggest(rec)
        else:
            # Share of the legacy page's topic words found on the superseding page (low = review).
            words = topic_words(rec.get("Text", ""))
            target = by_name.get(superseded_by, {})
            covered = topic_words((target.get("Text") or "") + "\n" + (target.get("Therapy") or ""))
            entry["coverage"] = round(len(words & covered) / len(words), 3) if words else None
        records.append(entry)

    def count(label: str) -> int:
        return sum(1 for r in records if label in r["labels"])

    return {
        "station": station_dir,
        "generated": date.today().isoformat(),
        "counts": {
            "records": len(menus),
            "legacy": len(legacy),
            "afterDelete": len(current),
            "superseded": count("superseded"),
            "linkTarget": count("link-target"),
            "searchVisible": count("search-visible"),
            "searchVisibleOrphan": sum(1 for r in records if {"search-visible", "orphan-content"} <= set(r["labels"])),
            "orphanContent": count("orphan-content"),
            "safeToDelete": count("safe-to-delete"),
            "supersededLowCoverage": sum(
                1 for r in records if r.get("coverage") is not None and r["coverage"] < LOW_COVERAGE
            ),
        },
        "links": {
            "total": links_total,
            "unresolvedBefore": unresolved_before,
            "unresolvedAfter": unresolved_after,
            "dependent": len(dependent),
            "dependentRepoint": sum(1 for d in dependent if d["fix"]["action"] == "repoint"),
            "dependentNeedsDecision": sum(1 for d in dependent if d["fix"]["action"] == "needs-decision"),
        },
        "unclassifiedNonCmsRecords": unclassified,
        "dependentLinks": dependent,
        "records": records,
    }


def compare_stations(loaded_by_station: dict[str, dict]) -> dict:
    """Are the legacy records identical (same names, same field values) in every station?"""
    canon: dict[str, dict[str, str]] = {}
    for station, loaded in loaded_by_station.items():
        canon[station] = {
            m["Name"]: json.dumps(m, sort_keys=True, ensure_ascii=False)
            for m in loaded["data"]["menus"] if is_legacy(m, loaded["cms_ids"])
        }
    stations = list(canon)
    if not stations:
        return {"identical": True, "differences": []}
    base = stations[0]
    differences = []
    for other in stations[1:]:
        for name in sorted(set(canon[base]) | set(canon[other])):
            a, b = canon[base].get(name), canon[other].get(name)
            if a == b:
                continue
            if a is None or b is None:
                differences.append({"name": name, "stations": [base, other],
                                    "issue": f"missing in {other if b is None else base}"})
                continue
            ra, rb = json.loads(a), json.loads(b)
            fields = sorted(k for k in set(ra) | set(rb) if ra.get(k) != rb.get(k))
            differences.append({"name": name, "stations": [base, other], "fields": fields})
    return {"identical": not differences, "base": base, "compared": stations, "differences": differences}


def write_orphan_review(station_dir: str, report: dict) -> None:
    """Plain-text review list of orphan-content records, grouped by how they are reached."""
    records = {r["name"]: r for r in report["records"]}
    orphans = [r for r in report["records"] if "orphan-content" in r["labels"]]
    groups = {"A. search-visible": [], "B. linked from a combined page": [],
              "C. reachable only from legacy pages": [], "D. unreachable (no links, no Terms)": []}
    for r in orphans:
        if "search-visible" in r["labels"]:
            groups["A. search-visible"].append(r)
        elif "link-target" in r["labels"]:
            groups["B. linked from a combined page"].append(r)
        elif r["legacyParents"]:
            groups["C. reachable only from legacy pages"].append(r)
        else:
            groups["D. unreachable (no links, no Terms)"].append(r)
    lines = [f"Legacy orphan-content review: {station_dir} ({len(orphans)} records)", ""]
    for title, items in groups.items():
        lines.append(f"== {title}: {len(items)}")
        for r in sorted(items, key=lambda x: x["name"]):
            best = (r.get("candidates") or [{}])[0]
            match = f" | best match {best['page']} ({best['containment']:.0%} of words)" if best else ""
            parents = [p for p in r["legacyParents"] if p in records]
            via = f" | from {', '.join(parents[:3])}{' ...' if len(parents) > 3 else ''}" if parents else ""
            lines.append(f"  {r['name']} | {r['words']} words{match}{via}")
        lines.append("")
    (REPORT_DIR / f"legacy-cleanup-orphans-{station_dir}.txt").write_text("\n".join(lines), encoding="utf-8")


def apply_station(station_dir: str, loaded: dict, report: dict) -> None:
    blocking = report["links"]["dependent"] + report["counts"]["orphanContent"]
    if blocking:
        print(f"  REFUSED: {report['links']['dependent']} dependent links and "
              f"{report['counts']['orphanContent']} orphan-content records remain")
        return
    menus = loaded["data"]["menus"]
    cms_ids = loaded["cms_ids"]
    legacy = [m for m in menus if is_legacy(m, cms_ids)]
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"{station_dir}-legacy-records.json"
    archive_path.write_text(
        json.dumps({"station": station_dir, "archived": date.today().isoformat(),
                    "source": loaded["om_path"].relative_to(ROOT).as_posix(), "menus": legacy},
                   indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    loaded["data"]["menus"] = [m for m in menus if not is_legacy(m, cms_ids)]
    with open(loaded["om_path"], "w", encoding="utf-8") as f:
        json.dump(loaded["data"], f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  Archived {len(legacy)} records to {archive_path.relative_to(ROOT).as_posix()}; "
          f"OMJSON now has {len(loaded['data']['menus'])} records")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--station", help="station folder, e.g. 541-Cleveland (default: all four)")
    parser.add_argument("--apply", action="store_true", help="archive and delete the legacy records")
    args = parser.parse_args()

    selected = [s for s in STATIONS if not args.station or s[0] == args.station]
    if not selected:
        print(f"Unknown station: {args.station}")
        return 1

    loaded_all = {s[0]: load_station(*s) for s in STATIONS}
    comparison = compare_stations(loaded_all)
    print(f"Legacy records identical across stations: {comparison['identical']}"
          + ("" if comparison["identical"] else f" ({len(comparison['differences'])} differences)"))

    REPORT_DIR.mkdir(exist_ok=True)
    for station_dir, _, _ in selected:
        loaded = loaded_all[station_dir]
        report = analyse_station(station_dir, loaded)
        report["crossStation"] = comparison
        report_path = REPORT_DIR / f"legacy-cleanup-{station_dir}.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_orphan_review(station_dir, report)
        c, links = report["counts"], report["links"]
        print(f"\n=== {station_dir} ===")
        print(f"  records {c['records']}, legacy {c['legacy']}, after delete {c['afterDelete']}")
        print(f"  superseded {c['superseded']}, link-target {c['linkTarget']}, search-visible {c['searchVisible']} "
              f"({c['searchVisibleOrphan']} orphan), orphan-content {c['orphanContent']}, safe-to-delete {c['safeToDelete']}")
        print(f"  links {links['total']}: unresolved before {links['unresolvedBefore']}, after {links['unresolvedAfter']}; "
              f"dependent {links['dependent']} ({links['dependentRepoint']} repoint, {links['dependentNeedsDecision']} need decision)")
        if report["unclassifiedNonCmsRecords"]:
            print(f"  non-CMS, non-legacy records kept: {', '.join(report['unclassifiedNonCmsRecords'])}")
        print(f"  report: {report_path.relative_to(ROOT).as_posix()}")
        if args.apply:
            apply_station(station_dir, loaded, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
