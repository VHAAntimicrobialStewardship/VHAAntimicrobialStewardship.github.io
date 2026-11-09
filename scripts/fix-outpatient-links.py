"""Repoint links that were built from the outpatient (ORZID3) VistA menus to the inpatient/combined root page.

Commit b0ac8d43 (2026-08-27) rebuilt some navigation pages, and the A-Z index, from the Minneapolis
outpatient menus, so their links went to outpatient-only copies (for example Lungs > Community-acquired
pneumonia went to the oral CAP page instead of ORZID2 GMENU ABX COM-ACQ PNEUMONIA). This script:
  - REPOINT: every link (Text and Therapy, any page) to an outpatient-only copy goes to the page that has the
    same content from the inpatient record (equal or more complete; checked by diff on 2026-11-09);
  - LABEL_RULES: links whose label points at the wrong page for that label (taken from the original inpatient
    menus ORZID2 GMENU ABX LUNG AND MEDIASTINUM and ORZID2 GMENU ABX INDEX INPATIENT);
  - EDITS: cleans up com-acq-pneumonia, cap-oral-treatment, pneumonia and the index title;
  - deletes each REPOINT source page (cms-data file and OMJSON record; compile-cms.py never deletes) once no
    page links to it any more (user decision 2026-11-09).
Edits apply only where the expected text is present, so SME-edited pages are reported, not overwritten.

Dry run by default:  python scripts/fix-outpatient-links.py [--station S] [--apply]
Then run compile-cms.py, audit-teststation.py, node scripts/render-check.js and nav-snapshot.js.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import station_registry  # noqa: E402

REPOINT = {
    "bone-joint-muscle-infections-2": "bone-joint-muscle-infections",
    "cap-treated-in-outpt-setting": "cap-oral-treatment",
    "cap-outpatient-treated-setting": "cap-oral-treatment",
    "foot-ulcer-in-pt-w-dm": "foot-ulcer-with-dm",
    "gram-neg-brucella-spp": "brucella-infections-general",
    "gram-pos-actinomyces-spp": "gram-pos-fi-actinomyces-spp",
    "gram-pos-bacilli-spp": "bacillus-infections-general",
    "gram-pos-corynebacterium-spp": "corynebacterium-infections-general",
    "gram-pos-propionibact-spp": "propionibacterium-infections-general",
    "hepb-vaccine-information-old-page": "hepb-vaccine-information-page",
    "infect-diarrhea-gastroent": "infect-diarrhea-gastro",
    "influenza-recommendations-outpatient": "influenza-recommendations",
    "orzid3-gmenu-cdifficile-colitis": "clostridiodes-difficile-infection",
    "orzid3-gmenu-comm-viral-gastroenteritis": "viral-diarrhea-gastroenteritis",
    "orzid3-gmenu-influenza-chemoprophylaxis": "influenza-chemoprophylaxis",
    "parainfluenza": "parainfluenza-2",
    "rsv": "respiratory-syncytial-virus",
    "sa-decolonization": "decolonization-of-staphylococcus-aureus",
    "splenectomy-daily-antibiotic": "splenectomy-daily-antibiotics",
    "tuberculosis": "tuberculosis-2",
}

_CATH = "intravas-cath-s-aureus"
_ENTERO = "enterococcal-intravascular-catheter-associated-infection"
# (page, label, old target, new target); applied before REPOINT.
LABEL_RULES = [
    ("lung-and-mediastinum", "Community-acquired pneumonia (CAP)", "cap-oral-treatment", "com-acq-pneumonia"),
    ("index", "CAP", "cap-outpatient-treated-setting", "com-acq-pneumonia"),
    ("index", "Community-acquired pneumonia", "cap-outpatient-treated-setting", "com-acq-pneumonia"),
    ("index", "Pneumonia, community-acquired", "cap-outpatient-treated-setting", "com-acq-pneumonia"),
    ("index", "Asplenia, antimicrobial prophylaxis", "splenectomy-vaccines-prophy", "splenectomy-daily-antibiotics"),
    ("index", "Bacteremia, Gram-negative bacilli", "interim-gram-negative-bacilli", "other-gram-negative-rods-bacteremia"),
    ("index", "Gram-negative bacilli bacteremia", "interim-gram-negative-bacilli", "other-gram-negative-rods-bacteremia"),
    ("index", "Bronchitis", "copd-exacerbation", "bronchitis"),
    ("index", "Bite wounds, Staphylococcus aureus", "bite-wounds", "bite-wnds-s-aureus"),
    ("index", "Methicillin-resistant Staphylococcus aureus bite wounds", "bite-wounds", "bite-wnds-s-aureus"),
    ("index", "Methicillin-sensitive Staphylococcus aureus bite wounds", "bite-wounds", "bite-wnds-s-aureus"),
    ("index", "MRSA bite wounds", "bite-wounds", "bite-wnds-s-aureus"),
    ("index", "MSSA bite wounds", "bite-wounds", "bite-wnds-s-aureus"),
    ("index", "Wound, bite, Staphylococcus aureus", "bite-wounds", "bite-wnds-s-aureus"),
    ("index", "Candida intravascular catheter-associated infection", _CATH, "intravas-cath-candida-spp"),
    ("index", "Catheter-associated infection, intravascular, candida", _CATH, "intravas-cath-candida-spp"),
    ("index", "Intravascular catheter-associated infection, candida", _CATH, "intravas-cath-candida-spp"),
    ("index", "Coagulase-neg staph intravascular catheter-associated infection", _CATH, "intravas-cath-coag-neg-staph"),
    ("index", "Catheter-associated infection, intravascular, coag-neg staph", _CATH, "intravas-cath-coag-neg-staph"),
    ("index", "Intravascular catheter-associated infection, coagulase-neg staph", _CATH, "intravas-cath-coag-neg-staph"),
    ("index", "Enterococcal intravascular catheter-associated infection", _CATH, _ENTERO),
    ("index", "Catheter-associated infection, intravascular, enterococci", _CATH, _ENTERO),
    ("index", "Intravascular catheter-associated infection, enterococci", _CATH, _ENTERO),
    ("index", "Gram-negative bacilli intravascular catheter-associated infection", _CATH, "intravas-cath-gnb"),
    ("index", "Catheter-associated infection, intravascular, gram-negative bacilli", _CATH, "intravas-cath-gnb"),
    ("index", "Intravascular catheter-associated infection, gram-negative bacilli", _CATH, "intravas-cath-gnb"),
]

PSI_JOINED = ("Use the CAP Pneumonia Severity Index (PSI) to assist with level of care decision "
              "CAP Pneumonia Severity Index (PSI) Calculator")
PSI = "Use the CAP Pneumonia Severity Index (PSI) to assist with level of care decision\nCAP Pneumonia Severity Index (PSI) Calculator"
EMPIRICAL = ("Empirical regimens listed here cover the usual pathogens associated with CAP, including atypical "
             "pathogens. Specific therapy should be guided by culture results.")
CAP_TITLE_LINK = "## [COMMUNITY-ACQUIRED PNEUMONIA (CAP)](cap-treated-in-outpt-setting)"
CAP_OLD_BODY = (
    f"\n\n{EMPIRICAL}\n\n## Diagnosis\n\n{PSI_JOINED}\n\n---\n\n"
    "## CAP treated in an Inpatient setting:\n\n"
    "[CAP NON-SEVERE treated in an Inpatient Ward setting](cap-inpatient-treated-setting-non-severe-cap)\n"
    "[CAP SEVERE treated in an ICU setting](cap-inpatient-treated-setting-severe-cap)\n\n"
    "## CAP treated in an Outpatient setting:\n\n"
    "**Link below will exit user from the ER/UC Antimicrobial CDSS "
    "[Treatment of CAP in an outpatient setting (outpatient)](cap-treated-in-outpt-setting)"
    "## _______________________________________________________________________________\n"
    "References:\n\n- Fine MJ, et al. N Engl J Med (1997) 336:243-250"
)
CAP_NEW_BODY = (
    f"\n\n{EMPIRICAL}\n\n## Diagnosis\n\n{PSI}\n\n"
    "## CAP treated in an Inpatient setting:\n\n"
    "[CAP NON-SEVERE treated in an Inpatient Ward setting](cap-inpatient-treated-setting-non-severe-cap)\n"
    "[CAP SEVERE treated in an ICU setting](cap-inpatient-treated-setting-severe-cap)\n\n"
    "## CAP treated in an Outpatient setting:\n\n"
    "[Treatment of CAP in an outpatient setting](cap-oral-treatment)\n\n"
    "---\n\nReferences:\n\n- Fine MJ, et al. N Engl J Med (1997) 336:243-250"
)
ORAL_TITLE = "# COMMUNITY-ACQUIRED PNEUMONIA (CAP) TREATED WITH ORAL ANTIBIOTICS"
ORAL_HEALTHY = (
    "## Previously healthy patients (i.e. no comorbidities):\n\n"
    "(WITHOUT chronic obstructive pulmonary disease, diabetes, renal failure, congestive heart failure, "
    "malignancy, alcoholism, asplenia, immunosuppressing conditions, or use of immunosuppressing drugs)"
)
ORAL_OLD_TEXT = (f"{ORAL_TITLE}\n\n{ORAL_HEALTHY}\n\n## COMMUNITY-ACQUIRED PNEUMONIA (CAP) TREATED WITH ORAL ANTIBIOTICS"
                 f"\n\n{EMPIRICAL}\n\n{PSI_JOINED}\n\n---")
ORAL_NEW_TEXT = f"{ORAL_TITLE}\n\n{EMPIRICAL}\n\n## Diagnosis\n\n{PSI}\n\n---"


def edit_com_acq(page):
    text = page.get("Text", "")
    if CAP_OLD_BODY not in text or CAP_TITLE_LINK not in text:
        return False
    title = "# COMMUNITY-ACQUIRED PNEUMONIA (CAP)" if text.startswith(CAP_TITLE_LINK) else "## COMMUNITY-ACQUIRED PNEUMONIA (CAP)"
    page["Text"] = text.replace(CAP_TITLE_LINK, title, 1).replace(CAP_OLD_BODY, CAP_NEW_BODY, 1)
    return True


def edit_cap_oral(page):
    text, therapy = page.get("Text", ""), page.get("Therapy", "")
    if not text.startswith(ORAL_OLD_TEXT) or not therapy.startswith("Preferred:"):
        return False
    page["Text"] = ORAL_NEW_TEXT + text[len(ORAL_OLD_TEXT):]
    page["Therapy"] = f"{ORAL_HEALTHY}\n{therapy}"
    return True


def edit_pneumonia(page):
    text = page.get("Text", "")
    new = text.replace("# PNEUMONIA - INPATIENT\n", "# PNEUMONIA\n", 1)
    new = new.replace("\nCommunity-acquired pneumonia (CAP)\n", "\n[Community-acquired pneumonia (CAP)](com-acq-pneumonia)\n", 1)
    if new == text:
        return False
    page["Text"] = new
    return True


def edit_index(page):
    text = page.get("Text", "")
    if not text.startswith("# OUTPATIENT INDEX\n"):
        return False
    page["Text"] = "# INDEX\n" + text[len("# OUTPATIENT INDEX\n"):]
    if page.get("Term1") == "Outpatient index":
        page["Term1"] = "Index"
    return True


EDITS = {
    "com-acq-pneumonia": edit_com_acq,
    "cap-oral-treatment": edit_cap_oral,
    "pneumonia": edit_pneumonia,
    "index": edit_index,
}

LINK_RE = re.compile(r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(([^)\s]+)\)")


def repoint(page_id, value, existing, counts):
    def sub(m):
        label, target = m.group(1), m.group(2)
        for rule_page, rule_label, old, new in LABEL_RULES:
            if page_id == rule_page and target == old and label.replace("\\", "") == rule_label and new in existing:
                counts[f"{page_id}: [{rule_label}] {old} -> {new}"] += 1
                return f"[{label}]({new})"
        new = REPOINT.get(target)
        if new and new in existing and new != page_id:
            counts[f"{target} -> {new}"] += 1
            return f"[{label}]({new})"
        return m.group(0)
    return LINK_RE.sub(sub, value)


def write_json(path, data, raw):
    out = json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")
    if "\r\n" in raw:
        out = out.replace("\n", "\r\n")
    path.write_bytes(out.encode("utf-8"))


def delete_unlinked(station, pages, paths, apply):
    inbound = {t for page_id, page in pages.items() for field in ("Text", "Therapy")
               for _, t in LINK_RE.findall(page.get(field) or "")}
    delete, kept = [], []
    for old, new in REPOINT.items():
        if old in pages and new in pages:
            (kept if old in inbound else delete).append(old)
    if apply and delete:
        for page_id in delete:
            paths[page_id][0].unlink()
        om_path = ROOT / "stations" / station["folder"] / station["omjson"]
        raw = om_path.read_bytes().decode("utf-8")
        data = json.loads(raw)
        data["menus"] = [m for m in data["menus"] if m.get("Name") not in delete]
        write_json(om_path, data, raw)
    return delete, kept


def run_station(station, apply):
    folder = station["folder"]
    paths = {}
    for path in sorted((ROOT / "cms-data" / folder / "pages").glob("*/*.json")):
        raw = path.read_bytes().decode("utf-8")
        paths[json.loads(raw)["PageID"]] = (path, raw)
    existing = set(paths)
    missing = sorted({n for n in REPOINT.values() if n not in existing} | {r[3] for r in LABEL_RULES if r[3] not in existing})
    counts, edited, skipped, changed, pages = Counter(), [], [], 0, {}
    for page_id, (path, raw) in paths.items():
        page = pages[page_id] = json.loads(raw)
        before = json.dumps(page, ensure_ascii=False)
        if page_id in EDITS:
            (edited if EDITS[page_id](page) else skipped).append(page_id)
        for field in ("Text", "Therapy"):
            if page.get(field):
                page[field] = repoint(page_id, page[field], existing, counts)
        if json.dumps(page, ensure_ascii=False) == before:
            continue
        changed += 1
        if apply:
            write_json(path, page, raw)
    deleted, kept = delete_unlinked(station, pages, paths, apply)
    print(f"=== {folder}: {changed} pages {'changed' if apply else 'would change'}, "
          f"{len(deleted)} {'deleted' if apply else 'would be deleted'}")
    if deleted:
        print(f"  deleted: {', '.join(deleted)}")
    if kept:
        print(f"  not deleted (still linked): {', '.join(kept)}")
    print(f"  edits applied: {', '.join(edited) or '-'}")
    if skipped:
        print(f"  edits skipped (text not as expected or already done): {', '.join(skipped)}")
    if missing:
        print(f"  targets missing on this station (links left alone): {', '.join(missing)}")
    for key, n in sorted(counts.items()):
        print(f"  {n:3} x {key}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", help="station folder, e.g. 506-AnnArbor (default: all registered stations)")
    ap.add_argument("--apply", action="store_true", help="write cms-data and OMJSON (default: dry run)")
    args = ap.parse_args()
    stations = station_registry.load()
    if args.station:
        stations = [s for s in stations if s["folder"] == args.station]
        if not stations:
            sys.exit(f"unknown station {args.station}")
    for station in stations:
        run_station(station, args.apply)


if __name__ == "__main__":
    main()
