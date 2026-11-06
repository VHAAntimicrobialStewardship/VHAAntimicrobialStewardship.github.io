"""Wave 2: build each wave 2 station's pages from the test station pages plus the station's local wording
(dry run by default).

    python scripts/wave2-apply-local.py                       # dry run, Omaha, Des Moines, St. Cloud
    python scripts/wave2-apply-local.py --station 636-Omaha --show <PageID>
    python scripts/wave2-apply-local.py --apply

Each station page = the test station page (dead order links removed, as the station has no order dialogs)
with the changes scripts/wave2-crosswalk.py found between the station's legacy record and the original
Minneapolis record (user decisions, 2026-11-06):
  - a change whose surrounding original text is on the page is applied in place (replace, insert, delete);
    a change for one care setting inside a section shared by several settings splits that section;
  - a change that cannot be placed goes into an italic "Local guidance (<Station> CDSS, <Setting>):" block,
    in the Therapy panel for clinical changes, otherwise in Text before the References separator;
  - a page the station marked "RECOMMENDATIONS NOT AVAILABLE" shows "<Station> Guidance:" with that text at the
    top, then "Minneapolis Guidance:" and the test page content, for SME review.
A page is only written while it is still the scaffold copy or this script's own earlier output, so SME edits
are never overwritten and re-runs change nothing.

Writes reports/wave2-review-<station>.csv (every change, for SME sign-off) and .txt (summary and the
opt-out page list). Then run compile-cms.py, audit-teststation.py, render-check.js and nav-snapshot.js.
"""

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import station_registry  # noqa: E402


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cw = load_script("wave2-crosswalk")
cm = load_script("convert-markdown")
nc = load_script("normalize-care-settings")
dead = load_script("strip-dead-order-links")

SETTING_ORDER = {"Inpatient": 0, "Outpatient": 1, "ER/UC": 2}
FIELD_OF = {"Inpt": "Inpatient", "Outpt": "Outpatient", "ERUC": "ER/UC"}
TOK = re.compile(r"[a-z0-9]+(?:[./-][a-z0-9]+)*")
LINK = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)]*)\)")
SEPARATOR = re.compile(r"^(?:---|\*\*\*|___)\s*$")
SITE = "https://vhaantimicrobialstewardship.github.io"
NAV_LINK_LINE = re.compile(r"^\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)\)$")
# Text that reads like a reference entry (may be added inside the References list).
REF_LIKE = re.compile(r"\b(?:19|20)\d\d\b|et al|Sanford|Mandell|Up-?To-?Date|Guidelines?|MMWR|Clin |J Infect|"
                      r"Lancet|N Engl|NEJM|CDC|IDSA|Accessed", re.I)
COLUMN = re.compile(r"<!--\s*(?:COLUMN \d+|RIGHT COLUMN)\s*-->")
LINE_LINKS: dict[str, str] = {}  # station link-row text -> PageID of the page its target record became


def station_line_links(records: dict, res: dict) -> dict[str, str]:
    page_of = {s["station_record"]: p["page"] for p in res["pages"] for s in p["sources"] if s.get("station_record")}
    links = {}
    for r in records.values():
        for row in r.get("Contents") or []:
            text = re.sub(r"\s+", " ", str(row.get("Text") or row.get("DisplayText") or "")).strip()
            if text and row.get("Item") in page_of:
                links.setdefault(text, page_of[row["Item"]])
    return links


def is_nav(text: str) -> bool:
    """isNavPage() in shared/cdss-sidebar.js: mostly pure link lines (headings and comments excluded)."""
    lines = [l.strip() for l in (text or "").split("\n")]
    lines = [l for l in lines if l and not re.match(r"^<!--.*-->$", l) and not re.match(r"^#{1,6}\s+", l)]
    links = sum(1 for l in lines if NAV_LINK_LINE.match(l))
    return links >= 2 and links / len(lines) >= 0.5


def label(settings) -> str:
    return "/".join(sorted(settings, key=SETTING_ORDER.get))


def to_markdown(lines: list[str]) -> str:
    """Station VistA lines as markdown: wrapped lines joined, stacked lines kept, menu links as page links."""
    # Labels may keep one level of balanced brackets ([R]); extractMarkdownLinks handles that.
    escape = lambda s: s if re.fullmatch(r"(?:[^\[\]]|\[[^\[\]]*\])*", s) else s.replace("[", "\\[").replace("]", "\\]")
    lines = [f"[{escape(l)}]({LINE_LINKS[l]})" if l in LINE_LINKS else l for l in lines]
    md = cm.convert("\n".join(lines))[0].strip() if lines else ""
    md = nc.strip_obsolete(md)  # no "refer to the inpatient CDSS" or Non-VA order lines (user, 2026-11-06)
    first = re.search(r"(?m)^(\d+)\.\s", md)
    if first and first.group(1) != "1":  # "2. ..." alone would render as an ordered list starting at 2
        md = re.sub(r"(?m)^(\d+)\.(?=\s)", r"\1\\.", md)
    return md


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """(word, start, end) for the words of text as wave2-crosswalk.flat() sees them (link targets skipped)."""
    skip = [(m.start(2) - 1, m.end()) for m in LINK.finditer(text)]
    out = []
    for m in TOK.finditer(text.lower()):
        if not any(a <= m.start() < b for a, b in skip):
            out.append((m.group(0), m.start(), m.end()))
    return out


def find(text: str, wordseq: list[str], lo: int = 0, hi: int | None = None, after: int = -1):
    """Char span of the first occurrence of wordseq inside text[lo:hi] (preferring one starting after `after`)."""
    if not wordseq:
        return None
    hi = len(text) if hi is None else hi
    toks = [t for t in tokenize(text) if lo <= t[1] and t[2] <= hi]
    words_ = [t[0] for t in toks]
    hits = [i for i in range(len(words_) - len(wordseq) + 1) if words_[i:i + len(wordseq)] == wordseq]
    if not hits:
        return None
    i = next((h for h in hits if toks[h][1] > after), hits[0])
    return toks[i][1], toks[i + len(wordseq) - 1][2]


def widen(text: str, start: int, end: int) -> tuple[int, int]:
    """Grow a word span over adjoining punctuation ([R], ($$), trailing period) and whole markdown links."""
    for m in LINK.finditer(text):
        if m.start() < start < m.end():
            start = m.start()
        if m.start() < end < m.end():
            end = m.end()
    while start > 0 and not text[start - 1].isspace() and text[start - 1] not in "#":
        start -= 1
    while end < len(text) and not text[end].isspace():
        end += 1
    return start, end


def line_bounds(text: str, pos: int) -> tuple[int, int]:
    return text.rfind("\n", 0, pos) + 1, (text.find("\n", pos) if text.find("\n", pos) >= 0 else len(text))


def tidy(text: str) -> str:
    lines = [l for l in text.split("\n") if l.strip() not in ("-", "*", "<", ">") and not re.fullmatch(r"\s+", l)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")


def refs_start(text: str) -> int:
    """Index where the trailing separator/References block starts (len(text) when there is none)."""
    lines = text.split("\n")
    pos, at = 0, len(text)
    offsets = []
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    for i, line in enumerate(lines):
        if SEPARATOR.match(line.strip()) or re.match(r"^(?:#+\s*)?\**references?\**:?\s*$", line.strip(), re.I):
            return offsets[i]
    return at


class Therapy:
    """Therapy split into an optional preamble and care-setting sections."""

    def __init__(self, text: str, page_settings: set[str]):
        self.pre, self.sections, self.labeled = [], [], False
        cur = None
        for line in (text or "").split("\n"):
            m = nc.LABEL_RE.match(line.strip())
            if m:
                self.labeled = True
                cur = [set(nc.tokens(m.group(1))), []]
                self.sections.append(cur)
            elif cur is None:
                self.pre.append(line)
            else:
                cur[1].append(line)
        self.pre = "\n".join(self.pre).strip("\n")
        self.sections = [[s, "\n".join(b).strip("\n")] for s, b in self.sections]
        if not self.labeled and self.pre:
            self.sections, self.pre = [[set(page_settings), self.pre]], ""

    def render(self) -> str:
        if not self.labeled:
            return self.sections[0][1] if self.sections else self.pre
        parts = [self.pre] if self.pre else []
        for settings, body in sorted(self.sections, key=lambda s: min(SETTING_ORDER[x] for x in s[0])):
            parts += [f"## {label(settings)}", body]
        return tidy("\n\n".join(p for p in parts if p))

    def split(self, idx: int, scope: set[str]) -> int:
        """Separates the scope settings out of section idx; returns the index of the scope copy."""
        settings, body = self.sections[idx]
        keep, take = settings - scope, settings & scope
        if not keep:
            return idx
        if not self.labeled:
            self.labeled = True
            if nc.heading_levels(body) and min(nc.heading_levels(body)) < 3:
                body = nc.shift_headings(body, 3)
        self.sections[idx] = [keep, body]
        self.sections.append([take, body])
        return len(self.sections) - 1


def relink(new: str, links: list[tuple[str, str]], lost: list[str]) -> str:
    """Puts back links whose label text is still in the replacement; records the others in lost."""
    for lab, target in links:
        if f"]({target})" in new:
            continue
        plain = re.sub(r"\\(.)", r"\1", lab)
        hit = re.search(re.escape(plain), new, re.I) if plain.strip() else None
        if hit and not any(m.start() <= hit.start() < m.end() for m in LINK.finditer(new)):
            new = new[:hit.start()] + f"[{hit.group(0)}]({target})" + new[hit.end():]
        else:
            lost.append(target)
    return new


def apply_change(change: dict, text: str, therapy: Therapy, page_settings: set[str], lost: list[str]):
    """Applies one change in place; returns (text, where) or (text, None) when it cannot be placed."""
    scope = change["settings"] & page_settings or set(page_settings)
    removed, added_md = cw.words(change["removed"]), to_markdown(change["added"])
    refs_md = re.sub(r"^References:\s*", "", to_markdown(["References:"] + change["added"])).strip()
    ref_like = not change["clinical"] and bool(REF_LIKE.search(" ".join(change["added"])))
    before, after = cw.words([change["anchor_before"]]), cw.words([change["anchor_after"]])
    has_refs = bool(re.search(r"(?mi)^(?:#+\s*)?\**references?\**:?\s*$", added_md))

    def edit(body: str, is_text: bool):
        limit = refs_start(body) if is_text else len(body)
        if removed:
            anchor = find(body, before)
            span = find(body, removed, after=anchor[0] if anchor else -1)
            if not span:
                return None
            s, e = widen(body, *span)
            new = added_md
            if s >= limit:  # inside the References block: reference entries only
                if added_md and not ref_like:
                    return None
                new = refs_md
            if re.fullmatch(r"\s*(?:[-*+]|\d+\\?\.|#{1,6})\s+", body[line_bounds(body, s)[0]:s]):
                new = re.sub(r"^(?:[-*+]|\d+\\?\.|#{1,6})\s+", "", new)  # the line already has its marker
            new = relink(new, [(m.group(1), m.group(2)) for m in LINK.finditer(body[s:e])], lost)
            return tidy(body[:s] + new + body[e:]) if new else tidy(body[:s] + body[e:])
        span = find(body, before)
        if span:
            _, at = line_bounds(body, span[1] - 1)
            gap = "\n"
        else:
            span = find(body, after)
            if not span:
                return None
            at, _ = line_bounds(body, span[0])
            if at == 0:
                return added_md + "\n" + body if (added_md and limit > 0) else None
            at, gap = at - 1, "\n"
        new = added_md
        if at >= limit:
            if not ref_like:
                return None
            new = refs_md
        return body[:at] + gap + new + body[at:]

    if not has_refs:
        for idx, (settings, body) in enumerate(list(therapy.sections)):
            if not settings & scope or edit(body, False) is None:
                continue
            split = bool(settings - scope)
            if split:
                saved = [list(s) for s in therapy.sections], therapy.labeled
                idx = therapy.split(idx, scope)
            new = edit(therapy.sections[idx][1], False)
            if new is None:  # the heading shift after the split broke the match
                therapy.sections, therapy.labeled = saved
                continue
            therapy.sections[idx][1] = new
            where = f"Therapy ({label(therapy.sections[idx][0])}{', section split' if split else ''})"
            return text, where if therapy.labeled else "Therapy"
        if therapy.pre:
            new = edit(therapy.pre, False)
            if new is not None:
                therapy.pre = new
                return text, "Therapy (shared)"
    new = edit(text, True) if text else None
    return (new, "Text") if new is not None else (text, None)


def add_block(text: str, therapy: Therapy, station: str, settings: set[str], lines: list[str], clinical: bool,
              top: bool = False):
    head = f"*Local guidance ({station} CDSS, {label(settings)}):*"
    block = head + "\n" + to_markdown(lines)
    if top:
        first, _, rest = text.partition("\n")
        if first.startswith("# "):
            return f"{first}\n\n{block}\n\n{rest.lstrip(chr(10))}".rstrip("\n"), "top of page (Local guidance block)"
        return f"{block}\n\n{text}".rstrip("\n"), "top of page (Local guidance block)"
    if clinical and therapy.sections:
        exact = [i for i, (s, _) in enumerate(therapy.sections) if s <= settings]
        touching = [i for i, (s, _) in enumerate(therapy.sections) if s & settings]
        idx = (exact or touching or [len(therapy.sections) - 1])[0]
        therapy.sections[idx][1] = therapy.sections[idx][1].rstrip("\n") + "\n\n" + block
        return text, "Therapy (Local guidance block)"
    at = refs_start(text)
    return (text[:at].rstrip("\n") + "\n\n" + block + "\n\n" + text[at:].lstrip("\n")).rstrip("\n"), \
        "Text (Local guidance block)"


def opt_out(text: str, therapy_text: str, station: str, blocks: list[tuple[set[str], list[str]]], all_out: bool):
    first, _, rest = text.partition("\n")
    title, body = (first, rest.lstrip("\n")) if first.startswith("# ") else ("", text)
    parts = [title] if title else []
    for settings, lines in blocks:
        name = f"{station} Guidance" + ("" if all_out else f" ({label(settings)})")
        parts += [f"**{name}:**", to_markdown(lines)]
    parts += ["**Minneapolis Guidance:**", body]
    new_text = "\n\n".join(p for p in parts if p)
    new_therapy = f"**Minneapolis Guidance:**\n\n{therapy_text}" if therapy_text else therapy_text
    return new_text, new_therapy


def build_page(page: dict, base_text: str, base_therapy: str, xpage: dict, station: str, records: dict):
    """(Text, Therapy, log) for one station page."""
    page_settings = {FIELD_OF[f] for f in FIELD_OF if page.get(f)} or {"Inpatient"}
    text, therapy = base_text, Therapy(base_therapy, page_settings)
    log = []
    if page["PageID"] in ("main-menu", "inpt-main") or is_nav(base_text):
        outs = sorted({src["setting"] for src in xpage["sources"] if src["status"] == "station-placeholder"},
                      key=SETTING_ORDER.get)
        if outs:
            log.append({"settings": label(outs), "kind": "opt-out", "clinical": False, "dated": False,
                        "shared_with": [], "removed": [], "added": [],
                        "applied": "not shown (navigation page; its linked pages carry their own notes)"})
        return base_text, base_therapy, log
    groups = {}
    for src in xpage["sources"]:
        for h in src.get("hunks", []):
            key = (tuple(h["removed"]), tuple(h["added"]))
            g = groups.setdefault(key, dict(h, settings=set(), shared_with=set()))
            g["settings"].add(src["setting"])
            g["clinical"] |= h["clinical"]
            g["dated"] |= h["dated"]
            g["shared_with"] |= set(h.get("shared_with", []))
    pending = defaultdict(list)
    columns = bool(COLUMN.search(base_text))  # line-per-row column layout: changes go in one block on top
    for g in groups.values():
        lost = []
        text, where = (text, None) if columns else apply_change(g, text, therapy, page_settings, lost)
        entry = {"settings": label(g["settings"]), "kind": g["kind"], "clinical": g["clinical"], "dated": g["dated"],
                 "shared_with": sorted(g["shared_with"]), "removed": g["removed"], "added": g["added"]}
        if where:
            entry["applied"] = where + (f"; link removed: {', '.join(lost)}" if lost else "")
            log.append(entry)
        elif g["added"]:
            pending[(frozenset(g["settings"]), g["clinical"] and not columns)].append(entry)
        else:
            entry["applied"] = ("not applied (column page)" if columns else
                                "not applied (lines to delete not found together on the page)")
            log.append(entry)
    for (settings, clinical), entries in pending.items():
        lines = [x for e in entries for x in e["added"]]
        text, where = add_block(text, therapy, station, set(settings), lines, clinical, top=columns)
        for e in entries:
            e["applied"] = where
            log.append(e)
    therapy_text = therapy.render()
    outs = [(src["setting"], cw.lines_of(records[src["station_record"]]))
            for src in xpage["sources"] if src["status"] == "station-placeholder"]
    if outs:
        merged = defaultdict(set)
        for setting, lines in outs:
            merged[tuple(lines)].add(setting)
        blocks = [(s, list(lines)) for lines, s in merged.items()]
        all_out = {s for s, _ in outs} >= page_settings
        text, therapy_text = opt_out(text, therapy_text, station, blocks, all_out)
        for s, lines in blocks:
            log.insert(0, {"settings": label(s), "kind": "opt-out", "clinical": False, "dated": False,
                           "shared_with": [], "removed": [], "added": lines, "applied": "top of page (opt-out)"})
    return text, therapy_text, log


def patch(raw: str, page: dict, text: str, therapy: str) -> str:
    """Page JSON with new Text/Therapy, formatting of untouched fields kept."""
    out = raw
    for field, new in (("Text", text), ("Therapy", therapy)):
        old = page.get(field)
        if old == new or (not old and not new):
            continue
        if old:
            enc = json.dumps(old, ensure_ascii=False)
            if out.count(enc) == 1:
                out = out.replace(enc, json.dumps(new, ensure_ascii=False))
                continue
        data = json.loads(out)
        data[field] = new
        body = json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")
        out = body.replace("\n", "\r\n") if "\r\n" in raw else body
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", action="append", choices=cw.WAVE2)
    ap.add_argument("--show", metavar="PAGEID")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    registry = {s["folder"]: s for s in station_registry.load()}
    original = cw.load_records(cw.ORIGINAL)
    pages = cw.test_pages()
    obsolete = {cw.norm_name(n) for n in json.loads(cw.OBSOLETE.read_text(encoding="utf-8"))["names"]}
    results = [cw.crosswalk(folder, original, pages, obsolete) for folder in cw.WAVE2]
    cw.mark_shared(results)
    test_om = json.loads((ROOT / "stations" / "001-TestStation" / "TestStationOMJSON.json").read_text(encoding="utf-8"))
    om_names = {dead.audit.normalize_comparable_id(m["Name"]) for m in test_om["menus"]}
    page_ids = {p["PageID"] for p in pages}

    for res in results:
        folder = res["station"]
        if args.station and folder not in args.station:
            continue
        if folder not in registry:
            sys.exit(f"{folder} is not a registered station; run scripts/new-station.py first")
        st = registry[folder]
        records = {r["Name"]: r for r in cw.load_records(ROOT / res["legacy_file"])}
        LINE_LINKS.clear()
        LINE_LINKS.update(station_line_links(records, res))
        xpages = {p["page"]: p for p in res["pages"]}
        rows, changed, skipped, opt_outs = [], 0, [], []
        for page in pages:
            pid = page["PageID"]
            path = ROOT / "cms-data" / folder / "pages" / page["_file"]
            if not path.exists():
                skipped.append(f"{pid} (no station page)")
                continue
            raw = path.read_bytes().decode("utf-8")
            current = json.loads(raw)
            base = {f: dead.rewrite(page.get(f) or "", om_names, set(), page_ids, [])[0] for f in ("Text", "Therapy")}
            text, therapy, log = build_page(page, base["Text"], base["Therapy"], xpages[pid], st["label"], records)
            scaffold = ((page.get("Text") or ""), (page.get("Therapy") or ""))
            now = ((current.get("Text") or ""), (current.get("Therapy") or ""))
            if now not in (scaffold, (base["Text"], base["Therapy"]), (text, therapy)):
                skipped.append(f"{pid} (edited on the station; not overwritten)")
                continue
            url = f"{SITE}/stations/{folder}/{st['html']}#{pid}"
            for e in log:
                rows.append([page.get("Term1", pid), pid, url, e["kind"], e["settings"], e["applied"],
                             "yes" if e["clinical"] else "", "yes" if e["dated"] else "", ", ".join(e["shared_with"]),
                             "\n".join(e["removed"]), "\n".join(e["added"])])
                if e["kind"] == "opt-out":
                    opt_outs.append((page.get("Term1", pid), pid, e["settings"], url))
            if args.show == pid:
                print(f"--- {pid} Text ---\n{text}\n--- Therapy ---\n{therapy}\n--- log ---")
                for e in log:
                    print(f"  {e['kind']} {e['settings']} -> {e['applied']}")
            if (text, therapy) != (base["Text"], base["Therapy"]):
                changed += 1
            if now != (text, therapy) and args.apply:
                path.write_bytes(patch(raw, current, text, therapy).encode("utf-8"))

        base_name = ROOT / "reports" / f"wave2-review-{folder}"
        with open(base_name.with_suffix(".csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Page", "PageID", "Link", "Change", "Care setting", "Applied as", "Clinical", "Dated",
                        "Same change at", "Original (Minneapolis) text", "Local text"])
            w.writerows(rows)
        kinds = defaultdict(int)
        for r in rows:
            kinds[r[5].split(" (")[0] if r[3] != "opt-out" else "opt-out"] += 1
        summary = [f"Wave 2 local wording: {st['label']} ({folder})", "",
                   f"Pages changed from the test station: {changed}",
                   f"Changes logged: {len(rows)} on {len({r[1] for r in rows})} pages "
                   f"(in place: {sum(1 for r in rows if not r[5].endswith('block)') and r[3] != 'opt-out' and not r[5].startswith('not'))}, "
                   f"Local guidance blocks: {sum(1 for r in rows if r[5].endswith('block)'))}, "
                   f"not applied: {sum(1 for r in rows if r[5].startswith('not'))}, opt-out pages: {len(opt_outs)})",
                   f"Clinical changes: {sum(1 for r in rows if r[6])}; changes also made by another wave 2 station: "
                   f"{sum(1 for r in rows if r[8])}", ""]
        summary += ["Pages the station marked RECOMMENDATIONS NOT AVAILABLE (shown as "
                    f"'{st['label']} Guidance' above 'Minneapolis Guidance'):"]
        summary += [f"  {t} [{pid}] ({s}) {u}" for t, pid, s, u in opt_outs] or ["  none"]
        if skipped:
            summary += ["", "Skipped:"] + [f"  {s}" for s in skipped]
        base_name.with_suffix(".txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
        print("\n".join(summary[:6]))
        print(f"  opt-out pages: {len(opt_outs)}; skipped: {len(skipped)}; review list: "
              f"{base_name.relative_to(ROOT).as_posix()}.csv{'' if args.apply else ' (dry run, no pages written)'}\n")


if __name__ == "__main__":
    main()
