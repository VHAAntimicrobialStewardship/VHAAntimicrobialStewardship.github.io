#!/usr/bin/env python3
"""Extract side-by-side clinical guidance from a station's OMJSON file.

Each clinical condition in the CDSS OMJSON is represented by an *inpatient*
menu object (``ORZID2 GMENU ...``) that carries the anchor metadata:

    "Name"        -> the inpatient menu name
    "DisplayText" -> the human title of the page (e.g. "Acute Sinusitis")
    "Outpt"       -> Name of the matching outpatient menu (optional)
    "ERUC"        -> Name of the matching ER/UC menu (optional)
    "Term1".."TermN" -> index/search terms (optional)

Each menu's ``Contents`` array holds the on-page text as ``Text`` entries
ordered by ``Row`` (and ``Column``). This script reconstructs the readable
body text for the inpatient, outpatient, and ER/UC pages of every condition
and writes one row per condition to a CSV for manual review.

Columns produced:
    Title, Inpatient, Outpatient, ER

Extra traceability columns (source menu names) are appended after those.

Designed to work for any station: point ``--omjson`` at the station's
OMJSON file (or ``--station`` at the station folder). Defaults to
Minneapolis (station 618).

Usage examples
--------------
    # Default: Minneapolis
    python tools/extract_cdss_guidance.py

    # Any other station by folder
    python tools/extract_cdss_guidance.py --station stations/636-Omaha

    # Explicit OMJSON + output path
    python tools/extract_cdss_guidance.py \
        --omjson stations/438-SiouxFalls/SiouxFallsOMJSON.json \
        --out SiouxFalls_guidance.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

# Repository root (this file lives in <repo>/tools/).
REPO_ROOT = Path(__file__).resolve().parent.parent

# Navigation/boilerplate lines that are not clinical guidance and are dropped.
BOILERPLATE_PREFIXES = (
    "Help, legend, allergy info",
)

# Common antimicrobial / antibiotic name stems used to detect real drug content.
# Matched case-insensitively as substrings, so stems cover salt/route variants
# (e.g. "cef" covers cefepime, ceftriaxone, cefazolin, cephalexin).
ANTIMICROBIAL_STEMS = (
    "amoxicillin", "ampicillin", "penicillin", "piperacillin", "tazobactam",
    "nafcillin", "oxacillin", "dicloxacillin", "cef", "ceph", "cepime",
    "aztreonam", "meropenem", "imipenem", "ertapenem", "doripenem",
    "vancomycin", "linezolid", "daptomycin", "dalbavancin", "telavancin",
    "clindamycin", "metronidazole", "azithromycin", "clarithromycin",
    "erythromycin", "doxycycline", "minocycline", "tetracycline", "tigecycline",
    "gentamicin", "tobramycin", "amikacin", "ciprofloxacin", "levofloxacin",
    "moxifloxacin", "ofloxacin", "trimethoprim", "sulfamethoxazole",
    "nitrofurantoin", "fosfomycin", "rifampin", "rifampicin", "colistin",
    "polymyxin", "fidaxomicin", "chloramphenicol", "bactrim", "septra",
    "zosyn", "augmentin", "unasyn", "rocephin", "flagyl", "macrobid",
    # Antifungals / antivirals commonly appearing in treatment pages.
    "fluconazole", "itraconazole", "voriconazole", "posaconazole",
    "isavuconazole", "amphotericin", "micafungin", "caspofungin",
    "anidulafungin", "acyclovir", "valacyclovir", "ganciclovir",
    "valganciclovir", "oseltamivir", "remdesivir",
)

# Dosing / regimen signals (mg, routes, frequencies, durations).
DOSING_PATTERN = re.compile(
    r"\b(\d+\s?(?:mg|gram|g|mcg|units?|million)\b"
    r"|\d+\s?mg/kg"
    r"|q\s?\d+\s?h(?:ours?|rs?)?"
    r"|\b(?:po|iv|im|bid|tid|qid|qhs|qday|qd|q8h|q12h|q24h|q6h)\b"
    r"|\bx\s?\d+\s?days?\b"
    r"|\bfor\s+\d+\s+days?\b)",
    re.IGNORECASE,
)

# Title keywords that mark informational / administrative "meta" pages about
# the tool itself (not clinical content). Matched case-insensitively as
# substrings of the title. Kept deliberately narrow so real medical topics
# (vaccines, prevention, treatment guidelines) stay classified as clinical.
INFO_TITLE_KEYWORDS = (
    "about the cdss", "acknowledg", "disclaimer", "restriction policy",
    "antimicrobial restriction", "how to use", "welcome", "instructions",
    "feedback", "contact us", "legend", "glossary", "cdss app",
    "antimicrobial shortages", "additional assistance",
)

# Title keywords marking pure navigation / structural pages (menus, submenus,
# order sets, selector rows) that hold no standalone clinical guidance.
NAV_TITLE_KEYWORDS = (
    "submenu", "order menu", "need an alternative", "main menu",
    "select here", "for table",
)


def classify_page(title: str, combined_body: str) -> tuple[str, int]:
    """Classify a condition page and return (PageType, antimicrobial_signal_count).

    Categories (in priority order):
        blank        -> no meaningful body text
        informational-> app/administrative meta pages (About, policy, how-to)
        navigation   -> menus / submenus / order sets / selector rows
        clinical     -> medical/condition content (the default)

    ``clinical`` is the default for anything with real body text that is not
    clearly app-meta or navigation. The returned signal count (drug-name stems +
    dosing matches) is a *secondary* indicator: high = the page contains actual
    treatment/dosing detail; 0 = an overview/parent page that links elsewhere.
    """
    title_l = (title or "").lower()
    body = combined_body or ""
    body_l = body.lower()

    # Count antimicrobial evidence (useful as a standalone signal column).
    drug_hits = sum(1 for stem in ANTIMICROBIAL_STEMS if stem in body_l)
    dosing_hits = len(DOSING_PATTERN.findall(body))
    signal = drug_hits + dosing_hits

    if not body.strip() or title_l.strip() == "blank page":
        return "blank", signal

    if any(kw in title_l for kw in NAV_TITLE_KEYWORDS):
        return "navigation", signal

    if any(kw in title_l for kw in INFO_TITLE_KEYWORDS):
        return "informational", signal

    # Everything else is clinical/medical content by default.
    return "clinical", signal


def find_default_omjson() -> Path:
    """Return the default Minneapolis OMJSON path."""
    return REPO_ROOT / "stations" / "618-Minneapolis" / "MinneapolisOMJSON.json"


def resolve_omjson(args: argparse.Namespace) -> Path:
    """Resolve the OMJSON path from CLI arguments."""
    if args.omjson:
        return Path(args.omjson).expanduser().resolve()

    if args.station:
        station_dir = Path(args.station).expanduser().resolve()
        candidates = sorted(station_dir.glob("*OMJSON.json"))
        if not candidates:
            sys.exit(f"No *OMJSON.json file found in {station_dir}")
        if len(candidates) > 1:
            print(
                f"Warning: multiple OMJSON files in {station_dir}; "
                f"using {candidates[0].name}",
                file=sys.stderr,
            )
        return candidates[0]

    return find_default_omjson()


def load_menus(omjson_path: Path) -> list[dict]:
    """Load the OMJSON file, returning the list of menu objects."""
    with omjson_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        sys.exit(f"Unexpected OMJSON structure in {omjson_path}: expected a list")
    return data


def is_boilerplate(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in BOILERPLATE_PREFIXES)


def render_body(menu: dict | None) -> str:
    """Reconstruct the readable body text of a menu page.

    Entries are ordered by (Row, Column) and their ``Text`` values joined with
    newlines. Header lines are prefixed with ``## `` so structure survives in a
    flat CSV cell. Navigation boilerplate is dropped.
    """
    if not menu:
        return ""

    contents = menu.get("Contents", [])
    entries = []
    for item in contents:
        text = item.get("Text")
        if not text:
            continue
        text = text.strip()
        if not text or is_boilerplate(text):
            continue
        row = item.get("Row", 0)
        col = item.get("Column", 0)
        is_header = bool(item.get("Header"))
        entries.append((row, col, is_header, text))

    entries.sort(key=lambda e: (e[0], e[1]))

    lines = []
    for _row, _col, is_header, text in entries:
        lines.append(f"## {text}" if is_header else text)
    return "\n".join(lines)


def clean_title(text: str) -> str:
    """Normalize a DisplayText into a clean title."""
    return re.sub(r"\s+", " ", text or "").strip()


def extract_rows(menus: list[dict]) -> list[dict]:
    """Build one guidance row per clinical condition."""
    by_name = {m.get("Name"): m for m in menus if m.get("Name")}

    rows = []
    for menu in menus:
        # A clinical condition anchor is an inpatient menu that references an
        # outpatient/ER counterpart or is indexed with a search Term.
        if not (menu.get("Outpt") or menu.get("ERUC") or menu.get("Term1")):
            continue

        title = clean_title(menu.get("DisplayText", "")) or menu.get("Name", "")

        outpt_name = menu.get("Outpt")
        eruc_name = menu.get("ERUC")

        rows.append(
            {
                "Title": title,
                "Inpatient": render_body(menu),
                "Outpatient": render_body(by_name.get(outpt_name)),
                "ER": render_body(by_name.get(eruc_name)),
                "InpatientMenu": menu.get("Name", ""),
                "OutpatientMenu": outpt_name or "",
                "ERMenu": eruc_name or "",
            }
        )

    rows.sort(key=lambda r: r["Title"].lower())

    # Compute pairwise similarity scores and classify each page.
    for row in rows:
        row["Sim_Inpt_Outpt"] = text_similarity(row["Inpatient"], row["Outpatient"])
        row["Sim_Inpt_ER"] = text_similarity(row["Inpatient"], row["ER"])
        row["Sim_Outpt_ER"] = text_similarity(row["Outpatient"], row["ER"])

        combined = "\n".join(
            part for part in (row["Inpatient"], row["Outpatient"], row["ER"]) if part
        )
        page_type, signal = classify_page(row["Title"], combined)
        row["PageType"] = page_type
        row["AbxSignal"] = signal
        # Whether this clinical page carries actual treatment/dosing detail
        # (vs. an overview/parent page that links to sub-topics).
        row["HasDosing"] = "yes" if (page_type == "clinical" and signal >= 2) else "no"

    return rows


def text_similarity(a: str, b: str) -> float:
    """Return similarity ratio (0.0–1.0) between two text bodies.

    If both are empty, returns 1.0 (trivially identical).
    If only one is empty, returns 0.0.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def write_csv(rows: list[dict], out_path: Path) -> None:
    # Internal field key -> plain-language column header shown in the CSV.
    # Order here is the column order in the output file.
    column_labels = {
        "Title": "Condition / Page Title",
        "PageType": "Type of Page",
        "HasDosing": "Includes Drug Dosing?",
        "AbxSignal": "Antibiotic Detail (count)",
        "Sim_Inpt_Outpt": "How Similar: Inpatient vs. Outpatient (%)",
        "Sim_Inpt_ER": "How Similar: Inpatient vs. ER (%)",
        "Sim_Outpt_ER": "How Similar: Outpatient vs. ER (%)",
        "Inpatient": "Inpatient Guidance",
        "Outpatient": "Outpatient Guidance",
        "ER": "ER Guidance",
        "InpatientMenu": "Source Menu Name (Inpatient)",
        "OutpatientMenu": "Source Menu Name (Outpatient)",
        "ERMenu": "Source Menu Name (ER)",
    }
    # Similarity keys are stored as 0.0-1.0 ratios; show them as friendly
    # percentages (e.g. 64%) for non-technical readers.
    percent_keys = {"Sim_Inpt_Outpt", "Sim_Inpt_ER", "Sim_Outpt_ER"}

    # utf-8-sig so Excel opens it with correct encoding.
    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(column_labels.values()))
        writer.writeheader()
        for row in rows:
            friendly = {}
            for key, label in column_labels.items():
                value = row.get(key, "")
                if key in percent_keys and isinstance(value, (int, float)):
                    value = f"{value:.0%}"
                friendly[label] = value
            writer.writerow(friendly)



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--omjson", help="Path to the station OMJSON file.")
    parser.add_argument("--station", help="Path to a station folder (auto-detects *OMJSON.json).")
    parser.add_argument("--out", help="Output CSV path (default: <Location>_SideBySideGuidance.csv next to OMJSON).")
    args = parser.parse_args(argv)

    omjson_path = resolve_omjson(args)
    if not omjson_path.is_file():
        sys.exit(f"OMJSON file not found: {omjson_path}")

    menus = load_menus(omjson_path)
    rows = extract_rows(menus)

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        location = omjson_path.stem.replace("OMJSON", "") or omjson_path.parent.name
        out_path = omjson_path.parent / f"{location}_SideBySideGuidance.csv"

    write_csv(rows, out_path)

    print(f"OMJSON: {omjson_path}")
    print(f"Conditions extracted: {len(rows)}")
    print(f"CSV written: {out_path}")

    # Print similarity summary.
    if rows:
        _print_similarity_summary(rows)

    return 0


def _print_similarity_summary(rows: list[dict]) -> None:
    """Print a console summary of similarity scores."""
    # Page-type breakdown first.
    from collections import Counter

    type_counts = Counter(r.get("PageType", "other") for r in rows)
    print("\n── Page-type breakdown ──")
    for ptype in ("clinical", "informational", "navigation", "blank"):
        if type_counts.get(ptype):
            extra = ""
            if ptype == "clinical":
                with_dosing = sum(
                    1 for r in rows if r.get("PageType") == "clinical" and r.get("HasDosing") == "yes"
                )
                extra = f"  ({with_dosing} with dosing detail)"
            print(f"  {ptype:<14} {type_counts[ptype]}{extra}")

    pairs = [
        ("Inpatient ↔ Outpatient", "Sim_Inpt_Outpt"),
        ("Inpatient ↔ ER",        "Sim_Inpt_ER"),
        ("Outpatient ↔ ER",       "Sim_Outpt_ER"),
    ]
    print("\n── Similarity summary ──")
    for label, key in pairs:
        vals = [r[key] for r in rows if r[key] is not None]
        # Skip pair if no rows have both sides populated.
        real = [v for v in vals if v > 0 or (v == 0 and _both_present(rows, key))]
        if not real:
            continue
        avg = sum(real) / len(real)
        lo = min(real)
        hi = max(real)
        identical = sum(1 for v in real if v == 1.0)
        print(f"  {label}:  avg {avg:.0%}  min {lo:.0%}  max {hi:.0%}  identical {identical}/{len(real)}")

    # Flag divergent *clinical* conditions only (any pair < 50%). Meta/blank
    # pages are excluded so the list focuses on real antimicrobial guidance.
    divergent = [
        r["Title"]
        for r in rows
        if r.get("PageType") == "clinical"
        and any(
            0 < r[k] < 0.5
            for k in ("Sim_Inpt_Outpt", "Sim_Inpt_ER", "Sim_Outpt_ER")
        )
    ]
    if divergent:
        print(f"\n  ⚠ Low-similarity clinical conditions ({len(divergent)}):")
        for title in divergent:
            print(f"    • {title}")


def _both_present(rows: list[dict], key: str) -> bool:
    """Check if a similarity key corresponds to both sides being present."""
    col_map = {
        "Sim_Inpt_Outpt": ("Inpatient", "Outpatient"),
        "Sim_Inpt_ER": ("Inpatient", "ER"),
        "Sim_Outpt_ER": ("Outpatient", "ER"),
    }
    a, b = col_map.get(key, ("", ""))
    return any(r.get(a) and r.get(b) for r in rows)


if __name__ == "__main__":
    raise SystemExit(main())
