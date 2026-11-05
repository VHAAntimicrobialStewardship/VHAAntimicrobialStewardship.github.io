"""One-off (2026-11 legacy cleanup): turn approved legacy ORZ records into cms-data pages.

    python scripts/promote-legacy-pages.py                 # dry run, all four CMS stations
    python scripts/promote-legacy-pages.py --show <PageID> # print one generated page (test station)
    python scripts/promote-legacy-pages.py --apply

Per station, from that station's own OMJSON and cms-data:
  - promotes the approved legacy records (PROMOTE) to new pages: Help/Legend link removed,
    hard wraps reflowed, therapy split into Therapy, convert-markdown rules, banner H1 first
  - restores combined pages whose Text was lost from their legacy source (RESTORE)
  - creates cms-data files for pages that only existed in OMJSON (STANDALONE)
  - merges the six journal reference pages into journal-references
  - rebuilds bacteremia as a navigation page and moves its ED doses to the new
    suspected-bacteremia page; adds nav links for the new pages
  - rewrites every internal link that resolves through a legacy record to the final PageID
Existing pages are edited in place (only the touched lines change), never copied between stations.
Then run compile-cms.py and cleanup-legacy-records.py.
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

STATIONS = [
    ("001-TestStation", "TestStationOMJSON.json", "TestStationODJSON.json"),
    ("506-AnnArbor", "AnnArborOMJSON.json", "AnnArborODJSON.json"),
    ("539-Cincinnati", "CincinnatiOMJSON.json", "CincinnatiODJSON.json"),
    ("541-Cleveland", "ClevelandOMJSON.json", "ClevelandODJSON.json"),
]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cleanup = load_script("cleanup-legacy-records")
restore = load_script("restore-from-legacy")
markdown = load_script("convert-markdown")
GROUP_LABELS = load_script("set-group-labels").GROUP_LABELS
NAV_OVERRIDES = load_script("set-nav-sort-keys").NAV_OVERRIDES

# legacy record -> (PageID, Group, Term1, Term2)
PROMOTE = {
    "ORZID2 GMENU ABX C DIFFICILE 2 STEP TESTING": ("c-difficile-2-step-testing", "gi-intraabdominal", "Clostridioides difficile infection 2-step testing", "C. diff infection 2-step testing"),
    "ORZID2 GMENU ABX NON-CHOLERA": ("vibrio-non-cholerae", "gi-intraabdominal", "Vibrio non-cholerae, diarrhea/gastroenteritis", "Non-cholera vibrio"),
    "ORZID2 GMENU ABX SUSP BACT, BLD CX NOT YET POS": ("suspected-bacteremia-cultures-not-yet-positive", "system-infectious-diseases", "Suspected bacteremia, blood cultures not yet positive", "Bacteremia, suspected"),
    "ORZID2 GMENU ABX URINE CULTURE MENU": ("urine-culture", "genitourinary", "Urine culture", "Culture, urine"),
    "ORZID2 GMENU ABX APPRO TO BACTEREMIA": ("approach-to-bacteremia", "system-infectious-diseases", "Approach to bacteremia", "Bacteremia, approach to"),
    "ORZID2 GMENU INT RPT GNB": ("interim-gram-negative-bacilli", "system-infectious-diseases", "Gram-negative bacilli bacteremia", "Interim blood culture: Gram-negative bacilli"),
    "ORZID2 GMENU INT RPT GNC": ("interim-gram-negative-cocci", "system-infectious-diseases", "Gram-negative cocci bacteremia", "Interim blood culture: Gram-negative cocci"),
    "ORZID2 GMENU INT RPT GPC IN PAIRS": ("interim-gram-positive-cocci-pairs", "system-infectious-diseases", "Gram-positive cocci in pairs bacteremia", "Gram-positive cocci in pairs interim culture results"),
    "ORZID2 GMENU INT RPT GPC PAIRS/CLUSTERS": ("interim-gram-positive-cocci-clusters", "system-infectious-diseases", "Gram-positive cocci in pairs and clusters bacteremia", "Interim blood culture: Gram-positive cocci in clusters"),
    "ORZID2 GMENU INT RPT GPC PRS/CHAINS": ("interim-gram-positive-cocci-chains", "system-infectious-diseases", "Gram-positive cocci in pairs and chains bacteremia", "Interim blood culture: Gram-positive cocci in chains"),
    "ORZID2 GMENU INT RPT GPR": ("interim-gram-positive-bacilli", "system-infectious-diseases", "Gram-positive bacilli bacteremia", "Gram-positive bacilli, interim culture results"),
    "ORZID2 GMENU INT RPT YEAST": ("interim-yeast", "system-infectious-diseases", "Yeast bacteremia", "Interim blood culture: yeast"),
    "ORZID2 GMENU INT LRG RODS ANAEROBIC BOT": ("interim-large-bacilli-anaerobic-bottle", "system-infectious-diseases", "Anaerobic bottle, large uniform bacilli", "Bacilli, large uniform, anaerobic bottle"),
    "ORZID2 GMENU INT LRG UNIF RDS AEROBIC BOT": ("interim-large-bacilli-aerobic-bottle", "system-infectious-diseases", "Aerobic bottle, large uniform bacilli", "Bacilli, large uniform, aerobic bottle"),
    "ORZID2 GMENU INT SM RODS AEROBIC BOT": ("interim-small-bacilli-aerobic-bottle", "system-infectious-diseases", "Aerobic bottle, small pleomorphic bacilli", "Bacilli, small pleomorphic, aerobic bottle"),
    "ORZID2 GMENU INT SM RODS ANAEROBIC BOT": ("interim-small-bacilli-anaerobic-bottle", "system-infectious-diseases", "Anaerobic bottle, small pleomorphic bacilli", "Bacilli, small pleomorphic, anaerobic bottle"),
    "ORZID3 GMENU ABX IMMUNIZATION AGE 19-26 YEARS": ("immunizations-age-19-26", "recommended-immunizations", "Vaccines for age 19-26 years", "Immunizations for age 19-26 years"),
    "ORZID3 GMENU ABX IMMUNIZATION AGE 27-49 YEARS": ("immunizations-age-27-49", "recommended-immunizations", "Vaccines for age 27-49 years", "Immunizations for age 27-49 years"),
    "ORZID3 GMENU ABX IMMUNIZATION AGE 50-64 YEARS": ("immunizations-age-50-64", "recommended-immunizations", "Vaccines for age 50-64 years", "Immunizations for age 50-64 years"),
    # The legacy search terms said 62; the page covers 65 years or greater.
    "ORZID3 GMENU ABX IMMUNIZATION 65 YEARS OR GREATER": ("immunizations-age-65-and-older", "recommended-immunizations", "Vaccines for age 65 years and older", "Immunizations for age 65 years and older"),
    "ORZID3 GMENU ABX IMMUNIZATION IN DIABETES": ("immunizations-in-diabetes", "recommended-immunizations", "Vaccines in diabetes", "Immunizations in diabetes"),
    "ORZID3 GMENU ABX IMMUNIZATION IN HIV PTS": ("immunizations-in-hiv", "recommended-immunizations", "Vaccines in HIV", "Immunizations in HIV"),
    "ORZID3 GMENU PREGNANCY VACCINE": ("immunizations-in-pregnancy", "recommended-immunizations", "Vaccines in pregnancy", "Immunizations in pregnancy"),
    "ORZID3 GMENU ABX PEP NON-OCCUPATIONAL DRUG TX": ("pep-non-occupational-antiretrovirals", "genitourinary", "Post-exposure prophylaxis, non-occupational, antivirals", "PEP, non-occupational, antivirals"),
    "ORZID3 GMENU ABX PEP NON-OCCUPATIONAL LABORATORY ORDERS": ("pep-non-occupational-baseline-labs", "genitourinary", "Post-exposure prophylaxis, non-occupational, labs", "PEP, non-occupational, labs"),
    "ORZID3 GMENU ABX PEP NONOCCUP RISK TABLE BY EXPOSURE ACT": ("pep-non-occupational-hiv-risk-table", "genitourinary", "Post-exposure risk of HIV", "HIV risk post-exposure risk"),
    "ORZID3 GMENU ABX RABIES POST-EXPOSURE PROPHYLAXIS": ("rabies-post-exposure-prophylaxis", "organisms", "Rabies post-exposure prophylaxis", "Post-exposure prophylaxis for rabies"),
    "ORZID3 GMENU ABX RESPIRATORY PAPILLOMATOSIS": ("respiratory-papillomatosis", "head-and-neck", "Respiratory papillomatosis", ""),
    "ORZID3 GMENU PROSTATE BIOPSY PROPHYLAXIS": ("prostate-biopsy-prophylaxis", "genitourinary", "Prostate biopsy prophylaxis", "Biopsy of prostate prophylaxis"),
    "ORZID2 GMENU PD CEFAZOLIN 15MG/KG Q24H": ("pd-cefazolin-15mg-kg-q24h", "general", "PD CEFAZOLIN 15MG/KG Q24H", "Peritoneal dialysis peritonitis, cefazolin"),
    "ORZID2 GMENU PD CEFAZOLIN 15MG/KG Q24H AND GENT 0.6MG/KG Q24H": ("pd-cefazolin-15mg-kg-gentamicin-06mg-kg-q24h", "general", "PD CEFAZOLIN 15MG/KG AND GENTAMICIN 0.6MG/KG Q24H", "Peritoneal dialysis peritonitis, cefazolin and gentamicin"),
    "ORZID2 GMENU PD CEFEPIME 1 GM Q24H": ("pd-cefepime-1gm-q24h", "general", "PD CEFEPIME 1GM Q24H", "Peritoneal dialysis peritonitis, cefepime"),
    "ORZID2 GMENU PD CEFTAZIDIME 1GM Q24H": ("pd-ceftazidime-1gm-q24h", "general", "PD CEFTAZIDIME 1GM Q24H", "Peritoneal dialysis peritonitis, ceftazidime"),
    "ORZID2 GMENU PD CEFTRIAXONE 1GM Q24H": ("pd-ceftriaxone-1gm-q24h", "general", "PD CEFTRIAXONE 1GM Q24H", "Peritoneal dialysis peritonitis, ceftriaxone"),
    "ORZID2 GMENU PD VANCO 15-30MG/KG Q5-7D": ("pd-vancomycin-15-30mg-kg-q5-7d", "general", "PD VANCOMYCIN 15-30MG/KG Q5-7D", "Peritoneal dialysis peritonitis, vancomycin"),
    "ORZID3 GMENU ABX BONE MARROW SEATTLE NASHVILLE ALLOGENIC": ("bone-marrow-allogeneic-post-transplant-vaccination", "recommended-immunizations", "Allogeneic post-transplant vaccination (Seattle or Nashville)", "Bone marrow transplant vaccines, allogeneic"),
    "ORZID3 GMENU ABX BONE MARROW SEATTLE NASHVILLE AUTOLOGOUS": ("bone-marrow-autologous-post-transplant-vaccination", "recommended-immunizations", "Autologous post-transplant vaccination (Seattle or Nashville)", "Bone marrow transplant vaccines, autologous"),
    # Linked from the restored dermatologic-surgery-guidelines page.
    "ORZID2 GMENU ABX PHOTODYNAMIC THERAPY HSV-1": ("photodynamic-therapy-hsv-1-prophylaxis", "dermatologic-surgery-guidelines", "Photodynamic therapy and laser skin resurfacing HSV-1 prophylaxis", "HSV-1 prophylaxis, laser skin resurfacing"),
}

# Promoted only where this page exists (Cleveland SMEs deleted dermatologic-surgery-guidelines).
PROMOTE_REQUIRES = {"photodynamic-therapy-hsv-1-prophylaxis": "dermatologic-surgery-guidelines"}

# Links to these legacy records go to an existing page instead (None: drop the link line).
LINK_OVERRIDES = {
    "ORZID2 GMENU GRAM-NEG FIN N. MENINGITIDIS": "gram-neg-n-meningitidis",
    "ORZID2 GMENU GRAM-NEG FIN N. GONORRHOEAE": "gram-neg-n-gonorrhoeae",
    "ORZID2 GMENU GRAM-NEG FIN M. CATARRHALIS": "gram-neg-m-catarrhalis",
    "ORZID3 GMENU ABX RABIES POST-EXPOSURE VACCINATED PATIENTS": None,
    "ORZID3 GMENU ABX RABIES POST-EXPOSURE VACCINE NAIVE PATIENTS": None,
    "ORZID3 GMENU ABX PHOTODYNAMIC THERAPY HSV-1": "photodynamic-therapy-hsv-1-prophylaxis",
}

# Combined pages whose Text was lost -> legacy record holding the real content.
RESTORE = {
    "drug-allergies": "ORZID2 GMENU ABX DRUG ALLERGIES",
    "surg-ercp": "ORZID2 GMENU SURG ERCP",
    "derm-post-op-infections": "ORZID2 GMENU ABX DERM POST-OP INFECTIONS",
    "derm-prophylaxis": "ORZID2 GMENU ABX DERM PROPHYLAXIS",
    "elements-of-cdss-advice-page": "ORZID2 GMENU ABX ELEMENTS OF CDSS ADVICE PAGE",
    "surg-prophylaxis-doses-and-redosing": "ORZID2 GMENU SURG PROPHYLAXIS DOSES AND REDOSING",
    "immunocom-diabetes-mellitus": "ORZID2 GMENU IMMUNOCOM DIABETES MELLITUS",
    "dermatologic-surgery-guidelines": "ORZID2 GMENU ABX DERMATOLOGIC SURGERY GUIDELINES",
    "pros-bone-joint-s-aureus": "ORZID3 GMENU PROS B/J S. AUREUS",
}

# OMJSON-only pages that get a cms-data file -> Group.
STANDALONE = {
    "book-references": "help-page",
    "website-references": "help-page",
    "journal-references": "help-page",
    "duke-criteria-listing": "cardiovascular",
    "initial-peri-assoc-w-peri-dial": "gi-intraabdominal",
    "pep-non-occupational-labs-and-rtc": "genitourinary",
    "sepsis-meningitis-cns-infection": "system-infectious-diseases",
    "sepsis-urosepsis": "system-infectious-diseases",
}

JOURNAL_PARTS = ["A-C", "D-J", "K-N", "P-R", "S-V", "W-Z"]

# The legacy dosing page is a two-column table flattened into one heading per cell.
DOSING_TABLE_TEXT = """# RECOMMENDED DOSES AND REDOSING INTERVAL

## Antimicrobial surgical prophylaxis

Existing renal or hepatic dysfunction: for single dose, no modification usually necessary.

| Antimicrobial | Recommended dose | Redosing interval** (from initiation of preop dose) |
| --- | --- | --- |
| Ampicillin | 2 grams | 2 hours |
| Ampicillin sulbactam | 3 grams | 2 hours |
| Aztreonam | 2 grams | 4 hours |
| Cefazolin | 2 grams (recommend 3 gm dose in patients >=120 kg) | 4 hours |
| Cefuroxime | 1.5 grams | 4 hours |
| Cefoxitin | 2 grams | 2 hours |
| Cefotetan | 2 grams | 6 hours |
| Ceftriaxone | 2 grams | N/A |
| Ciprofloxacin | 400 mg | Do not redose |
| Clindamycin | 900 mg | 6 hours |
| Gentamicin | 5 mg/kg based on dosing weight* | Do not redose |
| Levofloxacin | 500 mg | Do not redose |
| Metronidazole | 500 mg | 12 hours |
| Piperacillin tazobactam | 3.375 grams | 2 hours |
| Vancomycin | 15 mg/kg based on dosing weight* | 12 hours |

[Select for Gentamicin doses](surg-gentamicin-weight-based-dosing)
[Select for Vancomycin doses](orzid2-gmenu-surg-vancomycin-weight-based-dosing)

**For those marked N/A: based on typical case length; for unusually long procedures, redosing may be needed.

*Doses based on Dosing Weight (DW). Calculate Dosing Weight: DW = IBW + 0.4 (ABW - IBW)
IBW = Ideal Body Wt, ABW = Actual Body Wt
Male IBW (kg) = 50 + 2.3 * (Ht - 60 inches)
Female IBW (kg) = 45.5 + 2.3 * (Ht - 60 inches)

---

References:

- Am J Health-Syst Pharm. 2013, 70: 195-283
- John Hopkins Antibiotic Guide Online Oct2021"""
SPECIAL_TEXT = {"surg-prophylaxis-doses-and-redosing": DOSING_TABLE_TEXT}
# Restored nav page: "click here" pairs now share one target, and wrapped labels end on the next line.
TEXT_FIXES = {
    "dermatologic-surgery-guidelines": [
        ("Oral mucosa or infected skin surgical site with high risk of infective endocarditis\n"
         "[click here for inpatients](prev-of-bact-endocarditis)\n\n[click here for outpatients](prev-of-bact-endocarditis)",
         "[Oral mucosa or infected skin surgical site with high risk of infective endocarditis](prev-of-bact-endocarditis)"),
        ("hematogenous prosthetic joint](prevention-of-prosthetic-joint-infection-in-dental-surgery)\ninfection",
         "hematogenous prosthetic joint infection](prevention-of-prosthetic-joint-infection-in-dental-surgery)"),
        ("hematogenous prosthetic joint](prevention-of-prosthetic-joint-infection-with-dirty-operation-site)\ninfection",
         "hematogenous prosthetic joint infection](prevention-of-prosthetic-joint-infection-with-dirty-operation-site)"),
        ("Photodynamic therapy and laser skin resurfacing HSV-1 prophylaxis\n"
         "[click here for inpatients](photodynamic-therapy-hsv-1-prophylaxis)\n\n"
         "[click here for outpatients](photodynamic-therapy-hsv-1-prophylaxis)",
         "[Photodynamic therapy and laser skin resurfacing HSV-1 prophylaxis](photodynamic-therapy-hsv-1-prophylaxis)"),
    ],
}

# (page, exact existing line, replacement lines) added per station; a missing anchor is reported.
NAV_EDITS = [
    ("recommended-immunizations", "19-26 years", ["[19-26 years](immunizations-age-19-26)"]),
    ("recommended-immunizations", "27-49 years", ["[27-49 years](immunizations-age-27-49)"]),
    ("recommended-immunizations", "50-64 years", ["[50-64 years](immunizations-age-50-64)"]),
    ("recommended-immunizations", "/= 65 years", ["[65 years or greater](immunizations-age-65-and-older)"]),
    ("recommended-immunizations", "Diabetes", ["[Diabetes](immunizations-in-diabetes)"]),
    ("recommended-immunizations", "HIV", ["[HIV](immunizations-in-hiv)"]),
    ("recommended-immunizations", "Pregnancy", ["[Pregnancy](immunizations-in-pregnancy)"]),
    ("infect-diarrhea-gastro", "[Vibrio cholerae](cholera)", ["[Vibrio cholerae](cholera)", "", "[Vibrio, non-cholerae](vibrio-non-cholerae)"]),
    ("genitourinary", "[Uncomplicated UTI (infection confined to the bladder)](uncomp-uti)",
     ["[Uncomplicated UTI (infection confined to the bladder)](uncomp-uti)", "[Urine culture](urine-culture)"]),
    ("head-and-neck", "[Pharyngitis](pharyngitis)", ["[Pharyngitis](pharyngitis)", "[Respiratory Papillomatosis](respiratory-papillomatosis)"]),
    # bacteremia was only reachable from the index; this puts it (and the interim pages) in the menu tree.
    ("system-infectious-diseases", "## Blood stream infection",
     ["## Blood stream infection", "[Bacteremia: approach, empirical therapy and interim culture results](bacteremia)"]),
]

BACTEREMIA_NAV = """# BACTEREMIA

## Approach and empirical therapy

[Approach to bacteremia](approach-to-bacteremia)
[Suspected bacteremia, blood cultures not yet positive](suspected-bacteremia-cultures-not-yet-positive)

## Interim blood culture results (Gram stain)

[Gram-positive cocci in pairs](interim-gram-positive-cocci-pairs)
[Gram-positive cocci in pairs and clusters](interim-gram-positive-cocci-clusters)
[Gram-positive cocci in pairs and chains](interim-gram-positive-cocci-chains)
[Gram-positive bacilli](interim-gram-positive-bacilli)
[Gram-negative bacilli](interim-gram-negative-bacilli)
[Gram-negative cocci](interim-gram-negative-cocci)
[Yeast](interim-yeast)

## Rapid PCR blood culture results

"""

LINK_LINE_RE = re.compile(r"^\s*\[[^\]]*(?:\][^(]*\[[^\]]*)*\]\([^)]*\)\s*$")


class Page:
    """A cms-data page file; remembers its newline style so untouched lines stay byte-identical."""

    def __init__(self, path, data, crlf, new=False):
        self.path, self.data, self.crlf, self.new = path, data, crlf, new
        self.original = json.dumps(data, sort_keys=True, ensure_ascii=False)

    @classmethod
    def load(cls, path):
        raw = path.read_bytes()
        return cls(path, json.loads(raw.decode("utf-8")), b"\r\n" in raw)

    def changed(self):
        return self.new or json.dumps(self.data, sort_keys=True, ensure_ascii=False) != self.original

    def write(self):
        out = json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
        if self.crlf:
            out = out.replace("\n", "\r\n")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(out.encode("utf-8"))


def sort_key(group, page_id, term1):
    """Same rule as set-nav-sort-keys.py."""
    nav = NAV_OVERRIDES.get(group, group)
    return f"{group}~0" if page_id == nav else f"{group}~1~{term1.lower()}"


def convert_field(page_id, text, force=False):
    """convert-markdown rules; nav/flattened pages are skipped unless forced, column pages always."""
    reason = markdown.skip_reason(page_id, text) if text.strip() else "empty"
    if reason and not (force and reason in ("nav-page", "flattened-table")):
        return text
    new, _ = markdown.convert(text)
    return new if markdown.tokens(new) == markdown.tokens(text) else text


REF_HEAD_RE = re.compile(r"^\s*(?:#{1,6}\s*)?\**references?\**:?\s*$", re.I)


def join_reference_wraps(legacy_text):
    """Joins hard-wrapped reference entries: a line continues when its first word would not
    have fitted on the previous (filled) line."""
    lines = legacy_text.split("\n")
    start = next((i for i, l in enumerate(lines) if REF_HEAD_RE.match(l)), None)
    if start is None:
        return legacy_text
    width = max(len(l.rstrip()) for l in lines if "](" not in l)
    entries = []
    prev = ""
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        first = line.split()[0]
        wrapped = len(prev) + 1 + len(first) > width - 2 and "](" not in prev and "](" not in line
        if entries and wrapped:
            glue = "" if prev.endswith("-") and first[:1].isalnum() and not first[:1].isupper() else " "
            entries[-1] += glue + line.strip()
        else:
            entries.append(line.strip())
        prev = line.rstrip()
    return "\n".join(lines[:start + 1] + [""] + "\n\n".join(entries).split("\n"))


AUTHOR_START_RE = re.compile(
    r"^(?:Anonymous\.|Center for |Interagency |Pharmacy Benefits |(?:Van der |De )?"
    r"(?!(?:Clin|Med|Infect|Crit|Ann|Dis|Int|Curr|Inf|Perit|Dermatol|Ortho|Clev)\b)"
    r"[A-Z][A-Za-z'\-]{2,},? (?:[A-Z]{1,4}[,.]?(?:\s|$)|et al))"
)


def reference_entries(legacy_text):
    """One bullet per journal reference: a new entry starts at an 'Author AB' line."""
    entries = []
    for line in [l.strip() for l in legacy_text.split("\n")[1:] if l.strip()]:
        if entries and not AUTHOR_START_RE.match(line):
            glue = "" if entries[-1].endswith("-") and line[:1].isdigit() else " "
            entries[-1] += glue + line
        else:
            entries.append(line)
    return "\n".join("- " + re.sub(r"\s{2,}", " ", e) for e in entries)


def tidy(text):
    """Clean-ups for generated pages: empty headings, doubled/trailing separators, a blank
    line between a wrapped link label and its continuation."""
    text = "\n".join(l.rstrip() for l in text.split("\n") if not re.match(r"^#{1,6}\s*$", l))
    text = re.sub(r"^#{1,6}\s*_{5,}\s*$", "---", text, flags=re.M)
    text = re.sub(r"(\]\([^)\n]*\))\n\n(?=[a-z0-9($<]|IV |\[[A-Z,]+\] )", r"\1\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?:^|\n)---\n\n(?=---(?:\n|$))", "\n", text)
    text = re.sub(r"(?:\n\s*---\s*)+$", "", text.strip("\n"))
    return text.strip("\n")


def ensure_banner(text, fallback_title):
    """The first line must be the '# Title' banner (moved up when a stray line precedes it)."""
    lines = text.split("\n")
    first = next((i for i, l in enumerate(lines) if l.strip()), None)
    if first is None:
        return f"# {fallback_title}"
    if re.match(r"^# \S", lines[first]):
        return text
    h1 = next((i for i in range(first, min(first + 4, len(lines))) if re.match(r"^# \S", lines[i])), None)
    if h1 is not None:
        title = lines.pop(h1)
        return "\n".join([title, ""] + lines[first:]).replace("\n\n\n", "\n\n").strip("\n")
    heading = re.match(r"^#{2,6}\s+(.*)$", lines[first])
    lines[first] = f"# {heading.group(1) if heading else lines[first].strip()}"
    return "\n".join(lines[first:])


def build_from_legacy(page_id, legacy_text, title):
    text, therapy = restore.rebuild(join_reference_wraps(legacy_text))
    text = tidy(ensure_banner(convert_field(page_id, text, force=True), title))
    therapy = tidy(convert_field(page_id, therapy, force=True))
    return text, therapy


def new_page_data(page_id, group, term1, term2, text, therapy, extra=None):
    data = {
        "PageID": page_id,
        "Group": group,
        "GroupLabel": GROUP_LABELS[group],
        "SortKey": sort_key(group, page_id, term1),
        "Term1": term1,
        "Term2": term2,
        "Text": text,
    }
    if therapy.strip():
        data["Therapy"] = therapy
    data.update(extra or {})
    return data


def link_spans(text):
    """[(start, end, label, target)] for markdown links (same scanner as the runtime), images skipped."""
    spans = []
    index = 0
    while True:
        start = text.find("[", index)
        if start == -1:
            return spans
        found = cleanup.extract_markdown_links(text[start:])
        if not found or not text[start:].startswith(f"[{found[0][0]}]({found[0][1]})"):
            index = start + 1
            continue
        label, target = found[0]
        end = start + len(label) + len(target) + 4
        if not (start > 0 and text[start - 1] == "!"):
            spans.append((start, end, label, target))
        index = end


def rewrite_links(text, resolve_target, log, where):
    """Rewrites link targets that resolve through a legacy record; drops lines whose link maps to None."""
    if not text:
        return text
    out_lines = []
    dropped = False
    for line in text.split("\n"):
        drop = False
        pieces, cursor = [], 0
        for start, end, label, target in link_spans(line):
            action = resolve_target(target.strip())
            if action is None:
                continue
            kind, value = action
            pieces.append(line[cursor:start])
            if kind == "drop":
                drop = True
            elif kind == "unlink":
                pieces.append(label)
                log.append(f"{where}: unlinked [{label}]({target}) (obsolete legacy target)")
            else:
                pieces.append(f"[{label}]({value})")
                log.append(f"{where}: {target} -> {value}")
            cursor = end
        if drop:
            log.append(f"{where}: dropped line {line.strip()[:80]!r}")
            dropped = True
            continue
        pieces.append(line[cursor:])
        out_lines.append("".join(pieces))
    result = "\n".join(out_lines)
    return tidy(result) if dropped else result


def edit_station(station_dir, om_file, od_file, show=None):
    om_path = ROOT / "stations" / station_dir / om_file
    menus = json.loads(om_path.read_text(encoding="utf-8"))["menus"]
    od = json.loads((ROOT / "stations" / station_dir / od_file).read_text(encoding="utf-8"))
    by_name = {m["Name"]: m for m in menus}
    pages_dir = ROOT / "cms-data" / station_dir / "pages"
    pages = {}
    for path in sorted(pages_dir.glob("*/*.json")):
        page = Page.load(path)
        pages[page.data.get("PageID", path.stem)] = page
    cms_ids = set(pages)
    legacy_names = {m["Name"] for m in menus if cleanup.is_legacy(m, cms_ids)}
    log, problems = [], []

    def add_page(page_id, group, data):
        path = pages_dir / group / f"{page_id}.json"
        if page_id in pages or path.exists():
            problems.append(f"{page_id}: already exists, not created")
            return None
        pages[page_id] = Page(path, data, crlf=False, new=True)
        return pages[page_id]

    # 1. cms-data files for pages that only existed in OMJSON.
    for page_id, group in STANDALONE.items():
        rec = by_name.get(page_id)
        if not rec or page_id in pages:
            continue
        text = tidy(ensure_banner(convert_field(page_id, rec.get("Text", "")), rec.get("Term1") or page_id))
        extra = {k: rec[k] for k in ("Inpt", "Outpt", "ERUC") if rec.get(k)}
        add_page(page_id, group, new_page_data(page_id, group, rec.get("Term1", page_id), rec.get("Term2", ""),
                                               text, rec.get("Therapy", ""), extra))

    # 2. Journal references: the six A-Z pages become sections of journal-references.
    journal = pages.get("journal-references")
    if journal:
        lines = []
        for line in journal.data["Text"].split("\n"):
            part = next((p for p in JOURNAL_PARTS if f"(Author Lastname: {p}\\)" in line and LINK_LINE_RE.match(line)), None)
            if not part:
                lines.append(line)
                continue
            rec = by_name.get(f"ORZID2 GMENU ABX REF JOURN ({part})")
            if not rec:
                problems.append(f"journal-references: legacy part {part} missing")
                lines.append(line)
                continue
            body = f"## Author last name: {part}\n\n" + reference_entries(rec["Text"])
            lines += ["", body, ""]
        journal.data["Text"] = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")

    # 3. Promoted legacy records.
    promoted_ids = {}
    for legacy_name, (page_id, group, term1, term2) in PROMOTE.items():
        rec = by_name.get(legacy_name)
        if not rec:
            problems.append(f"{page_id}: legacy record {legacy_name!r} missing")
            continue
        if PROMOTE_REQUIRES.get(page_id) and PROMOTE_REQUIRES[page_id] not in pages:
            log.append(f"{page_id}: not created ({PROMOTE_REQUIRES[page_id]} is not a page here)")
            continue
        text, therapy = build_from_legacy(page_id, rec.get("Text", ""), term1.upper())
        if page_id == "pep-non-occupational-hiv-risk-table":
            text, therapy = risk_table(rec["Text"]), ""
        if add_page(page_id, group, new_page_data(page_id, group, term1, term2, text, therapy, {"Inpt": legacy_name})):
            promoted_ids[legacy_name] = page_id

    # 4. Restore combined pages that lost their Text.
    for page_id, source in RESTORE.items():
        page, rec = pages.get(page_id), by_name.get(source)
        if not page or not rec:
            problems.append(f"{page_id}: page or legacy source missing, not restored")
            continue
        text, therapy = build_from_legacy(page_id, rec.get("Text", ""), page.data.get("Term1", page_id).upper())
        if page_id in SPECIAL_TEXT:
            text, therapy = SPECIAL_TEXT[page_id], ""
        page.data["Text"] = text
        if therapy.strip():
            page.data["Therapy"] = therapy
        else:
            page.data.pop("Therapy", None)

    # 5. Bacteremia becomes a navigation page; its ED doses move to the suspected-bacteremia page.
    bact, susp = pages.get("bacteremia"), pages.get("suspected-bacteremia-cultures-not-yet-positive")
    if bact and susp:
        section = bact.data["Text"].split("## Rapid PCR blood culture results:", 1)
        pcr = section[1].split("##Outpatient", 1)[0] if len(section) == 2 else ""
        pcr_links = [m.group(0) for m in re.finditer(r"\[[^\]]+\]\([a-z0-9\-]+\)", pcr)]
        if not pcr_links:
            problems.append("bacteremia: rapid PCR links not found, not rebuilt")
        else:
            bact.data["Text"] = BACTEREMIA_NAV + "\n".join(pcr_links)
            ed = bact.data.pop("Therapy", "")
            ed_lines = [l for l in ed.split("\n") if "intravascular" not in l and l.strip() != "## Antimicrobial CDSS"]
            ed_body = "\n".join(re.sub(r"^## ", "### ", l) for l in ed_lines).strip("\n")
            if ed_body:
                susp.data["Therapy"] = (susp.data.get("Therapy", "").rstrip("\n")
                                        + "\n\n## Emergency department: initial STAT doses\n\n" + ed_body).strip("\n")

    # 6. Nav links for the new pages.
    for page_id, anchor, replacement in NAV_EDITS:
        page = pages.get(page_id)
        lines = page.data["Text"].split("\n") if page else []
        hits = [i for i, l in enumerate(lines) if l.strip() == anchor]
        if len(hits) != 1:
            problems.append(f"{page_id}: nav anchor {anchor!r} found {len(hits)} times, not edited")
            continue
        lines[hits[0]:hits[0] + 1] = replacement
        page.data["Text"] = "\n".join(lines)

    # 7. cholera's ERUC pointer named the ER/UC cholecystitis page.
    cholera = pages.get("cholera")
    if cholera and cholera.data.get("ERUC") == "ORZID GMENU ER/UC CHOLECYSTITIS":
        del cholera.data["ERUC"]

    # 8. Links that resolve through a legacy record point straight at the final page.
    resolver = cleanup.Resolver(menus, od)
    current_ids = {m["Name"] for m in menus if m["Name"] not in legacy_names} | set(pages)
    pointed_by = {}
    for page in pages.values():
        for field in ("Inpt", "Outpt", "ERUC"):
            pointed_by.setdefault((page.data.get(field) or "").strip(), page.data["PageID"])

    def resolve_target(target):
        res = resolver.resolve(target)
        if not res:
            return None
        via = [n for n in res["via"] if n in legacy_names]
        if not via:
            return None
        hit = via[0]
        if hit in LINK_OVERRIDES:
            return ("drop", None) if LINK_OVERRIDES[hit] is None else ("set", LINK_OVERRIDES[hit])
        final = res["final"]
        # An ER/UC record's Combined can name another legacy record; follow it to its page.
        for _ in range(3):
            if final not in legacy_names:
                break
            final = (by_name[final].get("Combined") or "").strip() or pointed_by.get(final, final)
        if final in current_ids:
            return ("set", final)
        if final in promoted_ids:
            return ("set", promoted_ids[final])
        return ("unlink", None)

    for page_id, page in pages.items():
        for field in ("Text", "Therapy"):
            if page.data.get(field):
                page.data[field] = rewrite_links(page.data[field], resolve_target, log, f"{page_id}.{field}")
        for old, new in TEXT_FIXES.get(page_id, []):
            page.data["Text"] = page.data["Text"].replace(old, new)

    if show:
        page = pages.get(show)
        print(json.dumps(page.data, indent=2, ensure_ascii=False) if page else f"{show}: not found")
    return pages, log, problems


def risk_table(legacy_text):
    """The legacy risk table is a two-column page; rebuilt as one markdown table."""
    left, right = legacy_text.split("<!-- COLUMN 2 -->")
    lab = [l.strip() for l in left.strip().split("\n")]
    val = [l.strip() for l in right.strip().split("\n")]
    rows = ["| Exposure type | Rate for HIV acquisition per 10,000 exposures |", "| --- | --- |"]
    exposures = [l for l in lab[3:] if l]
    values = [l for l in val[2:] if l]
    for exposure, value in zip(exposures, values):
        if exposure.startswith("## "):
            rows.append(f"| **{exposure[3:].rstrip(':')}** | |")
        else:
            rows.append(f"| {exposure} | {value} |")
    if len(exposures) != len(values):
        raise ValueError("risk table columns do not line up")
    return "# ESTIMATED PER-ACT RISK FOR ACQUIRING HIV FROM AN INFECTED SOURCE, BY EXPOSURE ACT\n\n" + "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--show", metavar="PAGEID")
    parser.add_argument("--dump", metavar="FILE", help="write every changed test-station page to FILE for review")
    args = parser.parse_args()
    if args.show:
        edit_station(*STATIONS[0], show=args.show)
        return
    if args.dump:
        pages, _, _ = edit_station(*STATIONS[0])
        with open(args.dump, "w", encoding="utf-8") as f:
            for p in sorted((p for p in pages.values() if p.changed()), key=lambda p: (not p.new, str(p.path))):
                f.write(f"{'#' * 30} {'NEW' if p.new else 'CHANGED'} {p.path.relative_to(ROOT).as_posix()}\n")
                f.write(f"Term1: {p.data.get('Term1')} | Term2: {p.data.get('Term2')} | Inpt: {p.data.get('Inpt')}\n")
                f.write(p.data.get("Text", "") + "\n")
                if p.data.get("Therapy"):
                    f.write("---------- THERAPY ----------\n" + p.data["Therapy"] + "\n")
        return
    for station in STATIONS:
        pages, log, problems = edit_station(*station)
        changed = [p for p in pages.values() if p.changed()]
        created = [p for p in changed if p.new]
        print(f"\n=== {station[0]} ===")
        print(f"  pages created {len(created)}, existing pages changed {len(changed) - len(created)}, link edits {len(log)}")
        for p in sorted(changed, key=lambda p: str(p.path)):
            if not p.new:
                print(f"    changed {p.path.relative_to(ROOT).as_posix()}")
        for line in log:
            if "unlinked" in line or "dropped" in line:
                print(f"    {line}")
        for line in problems:
            print(f"  PROBLEM: {line}")
        if args.apply:
            for p in changed:
                p.write()
    print("\n" + ("Written." if args.apply else "Dry run; nothing written."))


if __name__ == "__main__":
    main()
