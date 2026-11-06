"""Merge care-setting variants of the same guidance into one page (applied to 001/506/539/541 on 2026-11-05).

    python scripts/consolidate-care-settings.py --survey        # list pages still needing a merge
    python scripts/consolidate-care-settings.py                 # dry run, all four CMS stations
    python scripts/consolidate-care-settings.py --station 999-NewStation --archive FILE
    python scripts/consolidate-care-settings.py --dump FILE     # write the first station's result for review
    python scripts/consolidate-care-settings.py --apply

The Minneapolis inpatient (ORZID2), outpatient (ORZID3) and ER/UC (ORZID) pages for one topic share
their narrative and differ only in the therapy (maintenance doses vs single STAT doses). Earlier merges
left the variants pasted after References, truncated or jumbled inside the Therapy panel, or behind
"PENDING CARE SETTING CONSOLIDATION" / "NEED SME REVIEW" placeholders. Each page here gets one
narrative in Text and a Therapy panel with "## Inpatient" / "## Outpatient" / "## ER/UC" sections
(identical sections share one heading).

  SEPSIS_ER        current narrative and Inpatient therapy kept (SME edited); the ER/UC section is
                   rebuilt from the archived ER/UC record because the pasted copies lost lines
  REBUILD          narrative and all sections rebuilt from the archived variants (current page is a raw merge)
  REBUILD_THERAPY  current narrative kept; Therapy rebuilt from the archived variants (current one corrupted)
  fix_mismerged    duplicated or mis-merged pages fixed by hand-written rules
  merge_copd       two separate pages (inpatient copd-exacerbation, outpatient exacerbation-of-copd) merged

DELETE_PAGES are removed from cms-data and OMJSON (compile never deletes); links to them are repointed
(REPOINT). sepsis-protocol-antimicrobials' link list moves into sepsis-and-shock, which loses its
Therapy panel (it has no drug recommendations).
--archive names the JSON ({"menus": [{"Name", "Text"}, ...]}, OMJSON record shape with markdown links)
holding the station's legacy ORZ records. The default, docs/legacy-archive, is the Minneapolis content in
that shape; the raw stations/618-Minneapolis OMJSON (Contents/DisplayText) does not work here. Pages
already in the new shape are skipped, so a
re-run is safe. Then run compile-cms.py.
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


promote = load_script("promote-legacy-pages")
cleanup = load_script("cleanup-legacy-records")

STATIONS = [(s, om, od) for s, om, od in promote.STATIONS]
DEFAULT_ARCHIVE = ROOT / "docs" / "legacy-archive" / "001-TestStation-legacy-records.json"
ARCHIVE = {}  # legacy record name -> record; loaded in main()

DELETE_PAGE = "sepsis-protocol-antimicrobials"
DELETE_PAGES = [DELETE_PAGE, "exacerbation-of-copd"]
REPOINT = {"exacerbation-of-copd": "copd-exacerbation"}

SEPSIS_ER = {
    "sepsis-empiric-therapy-site-unk": "ORZID GMENU ER/UC SEPSIS EMPIRIC THERAPY SITE UNK",
    "sepsis-pneumonia": "ORZID GMENU ER/UC SEPSIS PNEUMONIA",
    "sepsis-susp-endocarditis": "ORZID GMENU ER/UC SEPSIS SUSP ENDOCARDITIS",
    "sepsis-suspected-skin-soft-tissue": "ORZID GMENU ER/UC SEPSIS SUSPECTED SKIN SOFT TISSUE",
    "sepsis-severe-beta-lactam-reaction": "ORZID GMENU ER/UC SEPSIS SEVERE BETA-LACTAM REACTION",
    "sepsis-susp-c-difficile": "ORZID GMENU ER/UC SEPSIS SUSP C. DIFFICILE",
}

# page -> [(section label, legacy record)]; narrative from the first record. These records have no
# headings in their narrative, so the therapy starts at the first heading after the banner.
REBUILD = {
    "sepsis-meningitis-cns-infection": [("Inpatient", "ORZID2 GMENU SEPSIS SUSPECTED MENINGITIS"),
                                        ("ER/UC", "ORZID GMENU ER/UC SEPSIS SUSPECTED MENINGITIS")],
    "sepsis-urosepsis": [("Inpatient", "ORZID2 GMENU SEPSIS SUSPECTED URO SEPSIS"),
                         ("ER/UC", "ORZID GMENU ER/UC SEPSIS SUSPECTED URO SEPSIS")],
}

REBUILD_THERAPY = {
    "furuncles-and-carbuncles": [("Inpatient", "ORZID2 GMENU FURUNCLES AND CARBUNCLES"),
                                 ("Outpatient", "ORZID3 GMENU FURUNCLES AND CARBUNCLES"),
                                 ("ER/UC", "ORZID GMENU ER/UC FURUNCLES, CARBUNCLES, CUT ABSCESS")],
    "severe-sinusitis": [("Inpatient", "ORZID2 GMENU SEVERE SINUSITIS"),
                         ("Outpatient", "ORZID3 GMENU ACUTE SINUSITIS SEVERE"),
                         ("ER/UC", "ORZID GMENU ER/UC SEVERE SINUSITIS")],
    "foot-ulcer-w-infect": [("Inpatient", "ORZID2 GMENU FOOT ULCER W/ INFECT SURR TISSUES"),
                            ("Outpatient", "ORZID3 GMENU FOOT ULCERS W/ INFECT SURR TISSUES"),
                            ("ER/UC", "ORZID GMENU ER/UC FOOT ULCER W/ INFECT SURR TISSUES")],
}

# Pointer fixes (field -> value; None removes the field).
POINTERS = {
    "sepsis-meningitis-cns-infection": {"ERUC": "ORZID GMENU ER/UC SEPSIS SUSPECTED MENINGITIS"},
    # The wrong pointer named bronchitis; the outpatient COPD guidance is merged in by merge_copd.
    "copd-exacerbation": {"Outpt": "ORZID3 GMENU ABX COPD EXACERBATION"},
}

SEPSIS_LINKS_HEADING = "## Initial empiric antibiotic guidelines for sepsis"

ER_HEAD_RE = re.compile(r"^#{1,6}\s*(?:ER|ER/UC|ER Guidance)\s*$")
# The target shape: '## Inpatient', '## Outpatient/ER/UC', ... in Therapy (' and ' is the older join).
SECTION_HEAD_RE = re.compile(r"^## (?:Inpatient|Outpatient|ER/UC)(?:(?:/| and )(?:Inpatient|Outpatient|ER/UC))*$")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
PENDING_RE = re.compile(r"^#{1,6}\s*PENDING CARE SETTING CONSOLIDATION", re.M)
ORDER_TARGET_RE = re.compile(r"^(?:ps[a-z]*zid|orz-)")


def norm_words(text):
    return re.findall(r"[a-z0-9]+", re.sub(r"\]\([^)]*\)", "]", text or "").lower())


def heading_key(line):
    m = HEAD_RE.match(line.strip())
    return " ".join(norm_words(m.group(2))) if m else None


def join_split_headings(text):
    """'# Clinically unstable ... multi-' + '# drug resistant ...': one heading split over two lines."""
    lines = text.split("\n")
    out = []
    for line in lines:
        m = HEAD_RE.match(line)
        prev_i = len(out) - 1
        while prev_i >= 0 and not out[prev_i].strip():
            prev_i -= 1
        pm = HEAD_RE.match(out[prev_i]) if prev_i >= 0 else None
        if m and pm and prev_i >= len(out) - 2:
            prev, cur = pm.group(2), m.group(2)
            if (prev.count("(") > prev.count(")") or prev.endswith(("-", ",")) or cur[:1] == "<"
                    or cur[:1].islower()):
                glue = "" if prev.endswith("-") and cur[:1].islower() and not prev.endswith(" -") else " "
                out[prev_i] = f"{pm.group(1)} {prev}{glue}{cur}"
                del out[prev_i + 1:]
                continue
        out.append(line)
    return re.sub(r"multi- drug", "multi-drug", "\n".join(out))


def demote(block):
    """Section bodies sit under a '## <setting>' heading, so their headings become '###' or lower."""
    return re.sub(r"^(#{1,5}) ", lambda m: "#" * max(3, len(m.group(1)) + 1) + " ", block, flags=re.M)


def therapy_sections(sections):
    """[(label, body)] -> Therapy markdown; identical bodies share one heading ('Inpatient/Outpatient')."""
    merged = []
    for label, body in sections:
        body = join_split_headings((body or "").strip("\n"))
        if not body.strip():
            continue
        same = next((m for m in merged if norm_words(m[1]) == norm_words(body)), None)
        if same:
            same[0].append(label)
        else:
            merged.append([[label], body])
    return "\n\n".join(f"## {'/'.join(labels)}\n\n{demote(body)}" for labels, body in merged)


def split_er_block(text):
    """(text without the pasted ER block, ER block body)."""
    lines = text.split("\n")
    idx = next((i for i, l in enumerate(lines) if ER_HEAD_RE.match(l.strip())), None)
    if idx is None:
        return text, ""
    return "\n".join(lines[:idx]).rstrip("\n"), "\n".join(lines[idx + 1:]).strip("\n")


def unlink_orders(text):
    """Plain text instead of order-dialog links, for pages whose inpatient therapy has no order links."""
    out = []
    for line in text.split("\n"):
        pieces, cursor, unlinked = [], 0, False
        for start, end, label, target in promote.link_spans(line):
            if ORDER_TARGET_RE.match(target.strip()):
                pieces += [line[cursor:start], re.sub(r"\\([()\[\]$])", r"\1", label)]
                cursor, unlinked = end, True
        pieces.append(line[cursor:])
        line = "".join(pieces)
        # A wrapped order label continues on the next line ("... vancomycin 15mg/kg IV" + "once STAT").
        if out and out[-1].endswith("\x00") and line[:1].islower():
            out[-1] = out[-1][:-1] + " " + line
            continue
        if out and out[-1].endswith("\x00"):
            out[-1] = out[-1][:-1]
        out.append(line + ("\x00" if unlinked else ""))
    if out and out[-1].endswith("\x00"):
        out[-1] = out[-1][:-1]
    return "\n".join(out)


def has_order_links(text):
    return any(ORDER_TARGET_RE.match(t.strip()) for _, _, _, t in promote.link_spans(text or ""))


def section_from(markdown, first_heading_keys):
    """Lines from the first heading in first_heading_keys up to the separator/References."""
    lines = markdown.split("\n")
    start = next((i for i, l in enumerate(lines) if heading_key(l) in first_heading_keys), None)
    if start is None:
        return ""
    end = next((i for i in range(start, len(lines))
                if lines[i].strip() in ("---", "***") or promote.REF_HEAD_RE.match(lines[i])), len(lines))
    return "\n".join(lines[start:end]).strip("\n")


def drop_headings_in(section, text):
    """Drops body-less headings that the page Text already carries (e.g. 'Consider selecting ...')."""
    keys = {heading_key(l) for l in text.split("\n")} - {None}
    lines = section.split("\n")
    keep = []
    for i, line in enumerate(lines):
        nxt = next((l for l in lines[i + 1:] if l.strip()), None)
        if heading_key(line) in keys and (nxt is None or HEAD_RE.match(nxt)):
            continue
        keep.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip("\n")


def compact(section):
    """Legacy double spacing -> stacked lines under each heading, as in the Inpatient sections;
    a hard-wrapped tail ('STAT', or a lowercase continuation) rejoins its line."""
    out = []
    for line in section.split("\n"):
        prev = next((l for l in reversed(out) if l.strip()), "")
        if line.strip() and not HEAD_RE.match(line) and prev and not HEAD_RE.match(prev):
            while out and not out[-1].strip():
                out.pop()
            if line.strip() == "STAT" or line[:1].islower():
                out[-1] = out[-1].rstrip() + " " + line.strip()
                continue
        out.append(line)
    return "\n".join(out)


def after_narrative(markdown):
    """(narrative with References, therapy) split at the first heading after the banner."""
    body, sep, refs = markdown.partition("\n---\n")
    lines = body.split("\n")
    cut = next((i for i in range(1, len(lines)) if HEAD_RE.match(lines[i])), len(lines))
    narrative = "\n".join(lines[:cut]).strip("\n") + ("\n\n---\n" + refs if sep else "")
    return narrative.strip("\n"), "\n".join(lines[cut:]).strip("\n")


def split_reference_runs(text):
    """'... PMID: 32374861 Rhodes et al., ...': two reference entries joined into one bullet."""
    return re.sub(r"(PMID: \d+) (?=[A-Z][a-z]+ et al)", r"\1\n- ", text)


NON_VA_RE = re.compile(r"^\s*\[Non[- ]VA order for above\]\(([^)]*)\)\s*$", re.I)


def drop_dead_non_va(text, od_names):
    """'Non-VA order for above' links whose order dialog this station does not have would render as
    a stray line of plain text under the regimen."""
    keep = [l for l in text.split("\n")
            if not (NON_VA_RE.match(l) and cleanup.normalize_comparable_id(NON_VA_RE.match(l).group(1)) not in od_names)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep))


class Legacy:
    """Builds markdown from archived legacy records, with legacy page links mapped to PageIDs."""

    def __init__(self, pages, od_names):
        self.od_names = od_names
        self.by_norm = {cleanup.normalize_comparable_id(n): n for n in ARCHIVE}
        self.pointed = {}
        for page in pages.values():
            for field in ("Inpt", "Outpt", "ERUC"):
                value = (page.data.get(field) or "").strip()
                if value:
                    self.pointed.setdefault(value, page.data["PageID"])
        for pid, name in SEPSIS_ER.items():
            self.pointed.setdefault(name, pid)
        for pid, variants in REBUILD.items():
            for _, name in variants:
                self.pointed.setdefault(name, pid)
        self.page_ids = set(pages)
        self.log = []

    def map_target(self, target):
        name = self.by_norm.get(cleanup.normalize_comparable_id(target))
        if not name:
            return None
        pid = self.pointed.get(name) or (ARCHIVE[name].get("Combined") or "").strip()
        if pid not in self.page_ids:
            # orzid2-gmenu-osteomyelitis-evaluation -> osteomyelitis-evaluation
            pid = re.sub(r"^orzid\d?-gmenu-(?:abx-)?(?:er-uc-)?", "", target.strip().lower())
        return ("set", pid) if pid in self.page_ids else ("unlink", None)

    def parts(self, page_id, name):
        """(text, therapy) as promote-legacy-pages builds them."""
        text, therapy = promote.build_from_legacy(page_id, ARCHIVE[name]["Text"], page_id.upper())
        therapy = drop_dead_non_va(therapy, self.od_names)
        return (promote.rewrite_links(text, self.map_target, self.log, page_id),
                promote.rewrite_links(therapy, self.map_target, self.log, page_id))

    def full(self, page_id, name):
        text, therapy = self.parts(page_id, name)
        if not therapy:
            return text
        body, sep, refs = text.partition("\n---\n")
        return body.rstrip("\n") + "\n\n" + therapy + ("\n\n---\n" + refs if sep else "")


def first_block(text, start_heading, end_pattern):
    """Lines after the heading matching start_heading up to the first line matching end_pattern."""
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(start_heading, l))
    end = next((i for i in range(start + 1, len(lines)) if re.match(end_pattern, lines[i])), len(lines))
    return "\n".join(lines[start + 1:end]).strip("\n")


def is_done(page):
    return page.data.get("Therapy", "").startswith(("## Inpatient", "## Outpatient"))


def edit_station(station_dir, od_file):
    pages_dir = ROOT / "cms-data" / station_dir / "pages"
    pages = {}
    for path in sorted(pages_dir.glob("*/*.json")):
        page = promote.Page.load(path)
        pages[page.data.get("PageID", path.stem)] = page
    od_data = json.loads((ROOT / "stations" / station_dir / od_file).read_text(encoding="utf-8"))
    legacy = Legacy(pages, {cleanup.normalize_comparable_id(m["Name"]) for m in od_data})
    problems = []

    def page(pid):
        p = pages.get(pid)
        if not p and pid not in DELETE_PAGES:  # already deleted on a re-run
            problems.append(f"{pid}: page missing")
        return p

    fix_sepsis_and_shock(page)

    for pid, er_name in SEPSIS_ER.items():
        p = page(pid)
        if not p or is_done(p):
            continue
        text, _ = split_er_block(p.data["Text"])
        inpatient, _ = split_er_block(p.data.get("Therapy", ""))
        keys = {heading_key(l) for l in inpatient.split("\n")} - {None}
        er = section_from(legacy.full(pid, er_name), keys)
        if not er:
            problems.append(f"{pid}: ER/UC therapy not found in {er_name}")
            continue
        if not has_order_links(inpatient):
            er = compact(unlink_orders(er))
        if pid == "sepsis-susp-c-difficile":
            text = text.replace("for recommendations.\nUnclear Infectious Source", "for recommendations.")
        p.data["Text"] = text.strip("\n")
        p.data["Therapy"] = therapy_sections([("Inpatient", inpatient), ("ER/UC", drop_headings_in(er, text))])

    for pid, variants in REBUILD.items():
        p = page(pid)
        if not p or is_done(p):
            continue
        built = [(label, after_narrative(legacy.full(pid, name))) for label, name in variants]
        p.data["Text"] = split_reference_runs(built[0][1][0])
        p.data["Therapy"] = therapy_sections([(label, therapy) for label, (_, therapy) in built])

    for pid, variants in REBUILD_THERAPY.items():
        p = page(pid)
        if not p or is_done(p):
            continue
        if pid == "foot-ulcer-w-infect":
            text = legacy.parts(pid, variants[0][1])[0]
        else:
            text, _ = split_er_block(p.data["Text"])
        if pid == "severe-sinusitis":
            text = text.replace("## Outpatient\n\nTreatment\n\n", "")
        if pid == "furuncles-and-carbuncles" and "\nReferences:" not in text:
            text = text.rstrip("\n") + "\n\n---\n\nReferences:" + p.data["Text"].split("\nReferences:", 1)[1]
        p.data["Text"] = text.strip("\n")
        p.data["Therapy"] = therapy_sections([(label, legacy.parts(pid, name)[1]) for label, name in variants])

    fix_mismerged(page, problems)
    merge_copd(page)

    for p in pages.values():
        if p.data["PageID"] in DELETE_PAGES:
            continue
        for field in ("Text", "Therapy"):
            if p.data.get(field):
                p.data[field] = repoint_links(p.data[field])
    for pid, changes in POINTERS.items():
        p = pages.get(pid)
        for field, value in (changes.items() if p else []):
            if value is None:
                p.data.pop(field, None)
            else:
                p.data[field] = value
    problems += sorted({l for l in legacy.log if "unlinked" in l})
    return pages, problems


def fix_sepsis_and_shock(page):
    """No Therapy panel (no drug recommendations); the protocol page's link list moves into Text."""
    shock, protocol = page("sepsis-and-shock"), page(DELETE_PAGE)
    if not (shock and protocol) or SEPSIS_LINKS_HEADING in shock.data["Text"]:
        return
    proto = protocol.data["Text"]
    intro = re.search(r"Empirical antimicrobial choice for sepsis.*?recommendations\.", proto, re.S).group(0)
    links = []
    for line in first_block(proto, r"^#+\s*INITIAL EMPIRIC ANTIBIOTIC GUIDELINES", r"^#+\s*ER/UC").split("\n"):
        if promote.LINK_LINE_RE.match(line) and line.strip() not in links:
            links.append(line.strip())
    bundle = shock.data.get("Therapy", "").replace(
        "The link below is provided to view antimicrobial recommendations as a reference.",
        "The antimicrobial recommendations below are provided as a reference.")
    bundle = "\n".join(l for l in bundle.split("\n") if f"]({DELETE_PAGE})" not in l).strip("\n")
    body, sep, refs = shock.data["Text"].partition("\n---\n")
    shock.data["Text"] = (body.rstrip("\n") + "\n\n" + bundle + "\n\n" + SEPSIS_LINKS_HEADING + "\n\n"
                          + re.sub(r"\s+", " ", intro) + "\n\n" + "\n".join(links) + "\n" + sep + refs)
    shock.data.pop("Therapy", None)


def fix_mismerged(page, problems):
    """Pages left behind 'PENDING CARE SETTING CONSOLIDATION' or with a cross-CDSS ER block."""
    # Identical inpatient and outpatient copies: keep one.
    for pid in ("influenza-chemoprophylaxis", "antiviral-stem-cell-malignancy"):
        p = page(pid)
        if not p or not PENDING_RE.search(p.data["Text"]):
            continue
        inpatient = first_block(p.data["Text"], r"^#+\s*INPATIENT:", r"^#+\s*OUTPATIENT:")
        outpatient = p.data["Text"].split("OUTPATIENT:", 1)[1]
        if norm_words(inpatient) != norm_words(outpatient):
            problems.append(f"{pid}: inpatient and outpatient copies differ, not merged")
            continue
        text = inpatient.replace("# **", "# ")
        p.data["Text"] = re.sub(r"\n#+ References:", "\n---\n\nReferences:", text).strip("\n")

    # COPD: the "outpatient" copy was the bronchitis page; keep the COPD guidance.
    p = page("copd-exacerbation")
    if p and PENDING_RE.search(p.data["Text"]):
        text = first_block(p.data["Text"], r"^#+\s*INPATIENT:", r"^#+\s*OUTPATIENT:")
        p.data["Text"] = text.replace("sputum worsening over\n\n< 14 days.", "sputum worsening over < 14 days.")

    # Bronchitis: the ER copy only repeated the same links with "exits the ER CDSS" notes.
    p = page("bronchitis")
    if p and p.data["Text"].startswith("## Inpatient/Outpatient"):
        text = p.data["Text"].replace("## Inpatient/Outpatient\n\n## BRONCHITIS", "# BRONCHITIS", 1)
        head, _, rest = text.partition("\n## ER\n")
        refs = rest[rest.index("References:"):] if "References:" in rest else ""
        p.data["Text"] = head.rstrip("\n") + "\n\n---\n\n" + refs.strip("\n")

    # HAP: ER copy in Text, whole inpatient page in Therapy; the narrative is shared.
    p = page("pneumonia-hap-new")
    if p and PENDING_RE.search(p.data["Text"]):
        refs = p.data["Text"].split("---\n\n", 1)[1].split("\n\n## ER/UC:", 1)[0].strip("\n")
        er = p.data["Text"].split("## ER/UC:", 1)[1].split("\n---\n", 1)[0].strip("\n")
        inpatient = p.data["Therapy"].split("### INPATIENT:", 1)[1].strip("\n")
        narrative, _, inpt_ther = inpatient.partition("\nPreferred:")
        _, _, er_ther = er.partition("\nPreferred:")
        narrative = re.sub(r"^## EMPIRIC TREATMENT: HOSPITAL ACQUIRED", "# EMPIRIC TREATMENT: HOSPITAL ACQUIRED",
                           narrative.strip("\n"))
        p.data["Text"] = narrative + "\n\n---\n\n" + refs
        p.data["Therapy"] = therapy_sections([("Inpatient", "Preferred:" + inpt_ther),
                                              ("ER/UC", "Preferred:" + er_ther)])


def repoint_links(text):
    pieces, cursor = [], 0
    for start, end, label, target in promote.link_spans(text):
        if target.strip() in REPOINT:
            pieces += [text[cursor:start], f"[{label}]({REPOINT[target.strip()]})"]
            cursor = end
    return "".join(pieces) + text[cursor:]


def paragraphs(text):
    """(body paragraphs, reference bullets) of a page Text."""
    body, _, refs = text.partition("\n---\n")
    bullets = []
    for line in refs.split("\n"):
        if line.startswith("- "):
            bullets.append(line[2:].strip())
        elif line.strip() and bullets and not promote.REF_HEAD_RE.match(line):
            bullets[-1] += " " + line.strip()
    return [p.strip("\n") for p in body.split("\n\n") if p.strip()], bullets


def merge_copd(page):
    """Inpatient copd-exacerbation + outpatient exacerbation-of-copd -> copd-exacerbation with Inpatient
    and Outpatient sections. The setting-specific guidance (when antibiotics help, the fluoroquinolone
    note that only fits the inpatient regimens, the home action plan) goes with its setting's therapy."""
    inp, out = page("copd-exacerbation"), page("exacerbation-of-copd")
    if not (inp and out):
        return
    in_paras, in_refs = paragraphs(inp.data["Text"])
    out_paras, out_refs = paragraphs(out.data["Text"])

    def take(paras, prefix):
        found = next(p for p in paras if p.startswith(prefix))
        paras.remove(found)
        return found

    title, definition, bullets = (take(in_paras, "# "), take(in_paras, "Exacerbation of COPD"),
                                  take(in_paras, "- "))
    differential = take(in_paras, "Dyspnea differential")
    out_differential = take(out_paras, "Dyspnea differential")
    action_plan = out_differential.split("medication non-adherence", 1)[1].strip()
    differential = differential.replace("medication non-adherence Test", "medication non-adherence. Test")
    if not differential.endswith("."):
        differential += "."
    inpatient_notes = [p.replace("[COPD exacerbation](exacerbation-of-copd)", "COPD exacerbation") for p in in_paras]
    outpatient_notes = [p for p in out_paras if not p.startswith(("[Select here for help", "# ", "Exacerbation of COPD", "- "))]
    outpatient_notes.append(action_plan)

    first_words = {r.split()[0] for r in in_refs}
    refs = [r for r in in_refs if not r.startswith("Access:")]
    access = next((r for r in in_refs if r.startswith("Access:")), None)
    if access:
        refs = [f"{r} {access}" if r.startswith("Global Initiative") else r for r in refs]
    refs += [r for r in out_refs if r.split()[0] not in first_words]

    inp.data["Text"] = ("\n\n".join([title, definition, bullets, differential]) + "\n\n---\n\nReferences:\n\n"
                        + "\n".join(f"- {r}" for r in refs))
    inp.data["Therapy"] = therapy_sections([
        ("Inpatient", "\n\n".join(inpatient_notes) + "\n\n" + inp.data["Therapy"]),
        ("Outpatient", "\n\n".join(outpatient_notes) + "\n\n" + out.data["Therapy"]),
    ])


def update_omjson(station_dir, om_file):
    """Deletes the DELETE_PAGES records and removed pointer fields (compile-cms never deletes either)."""
    paths = [p for pid in DELETE_PAGES for p in (ROOT / "cms-data" / station_dir / "pages").glob(f"*/{pid}.json")]
    for path in paths:
        path.unlink()
    om_path = ROOT / "stations" / station_dir / om_file
    raw = om_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    before = json.dumps(data)
    count = len(data["menus"])
    data["menus"] = [m for m in data["menus"] if m["Name"] not in DELETE_PAGES]
    for m in data["menus"]:
        for field, value in POINTERS.get(m["Name"], {}).items():
            if value is None:
                m.pop(field, None)
    if json.dumps(data) != before:
        out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if b"\r\n" in raw:
            out = out.replace("\n", "\r\n")
        om_path.write_bytes(out.encode("utf-8"))
    return len(paths), count - len(data["menus"])


def survey(station_dir):
    """Pages that still carry unmerged care-setting variants (candidates for this script's tables)."""
    found = []
    for path in sorted((ROOT / "cms-data" / station_dir / "pages").glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        text, therapy = data.get("Text", ""), data.get("Therapy", "")
        marks = []
        if PENDING_RE.search(text + "\n" + therapy):
            marks.append("PENDING CARE SETTING CONSOLIDATION")
        if re.search(r"^#{1,6}\s*NEED SME REVIEW", text + "\n" + therapy, re.M):
            marks.append("NEED SME REVIEW")
        for field, value in (("Text", text), ("Therapy", therapy)):
            lines = [l.strip() for l in value.split("\n")]
            if field == "Therapy":
                lines = [l for l in lines if not SECTION_HEAD_RE.match(l)]
            if any(ER_HEAD_RE.match(l) for l in lines):
                marks.append(f"ER heading in {field}")
            if re.search(r"^#{1,6}\s*(?:INPATIENT|OUTPATIENT|ER/UC):", value, re.M):
                marks.append(f"pasted setting block in {field}")
        if marks:
            found.append(f"{data.get('PageID', path.stem)}: {', '.join(marks)} (Inpt/Outpt/ERUC: "
                         f"{data.get('Inpt', '-')} | {data.get('Outpt', '-')} | {data.get('ERUC', '-')})")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dump", metavar="FILE")
    parser.add_argument("--station", action="append", help="station folder (repeatable); default: the four CMS stations")
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE), help="JSON with the legacy ORZ records")
    parser.add_argument("--survey", action="store_true", help="only list pages with unmerged care-setting variants")
    args = parser.parse_args()
    ARCHIVE.update({m["Name"]: m for m in json.loads(Path(args.archive).read_text(encoding="utf-8"))["menus"]})
    stations = STATIONS
    if args.station:
        stations = [(s, next((ROOT / "stations" / s).glob("*OMJSON.json")).name,
                     next((ROOT / "stations" / s).glob("*ODJSON.json")).name) for s in args.station]
    dumps = {}
    if args.survey:
        for station_dir, _, _ in stations:
            found = survey(station_dir)
            print(f"=== {station_dir}: {len(found)} page(s)")
            for line in found:
                print(f"    {line}")
        return
    for station_dir, om_file, od_file in stations:
        pages, problems = edit_station(station_dir, od_file)
        changed = [p for p in pages.values() if p.changed()]
        print(f"=== {station_dir}: {len(changed)} pages changed")
        for line in problems:
            print(f"  PROBLEM: {line}")
        dump = "".join(
            f"{'#' * 30} {p.data['PageID']}\n{p.data.get('Text', '')}\n"
            + (f"---------- THERAPY ----------\n{p.data['Therapy']}\n" if p.data.get("Therapy") else "")
            for p in changed)
        dumps[station_dir] = dump
        if dump != next(iter(dumps.values())):
            print("  NOTE: result differs from the first station")
        if args.apply:
            for p in changed:
                p.write()
            files, records = update_omjson(station_dir, om_file)
            print(f"  deleted {', '.join(DELETE_PAGES)}: {files} cms file(s), {records} OMJSON record(s)")
    if args.dump:
        Path(args.dump).write_text(next(iter(dumps.values())), encoding="utf-8")
    print("Written." if args.apply else "Dry run; nothing written.")


if __name__ == "__main__":
    main()
