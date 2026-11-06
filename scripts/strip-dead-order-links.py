#!/usr/bin/env python3
"""Replace VistA order-dialog links in cms-data page Text/Therapy with their plain label.

The site already shows these as plain text, but Sveltia previews them as links. A link
[label](target) is rewritten when its target is not a page (PageID/OM name) and either
resolves to an order dialog (ODJSON name) or is unresolved with a VistA order/document
prefix (see audit-teststation.NON_MENU_LINK_PREFIXES). Rewriting it to the label makes
the editor and the site agree.

Unresolved links to anything else (possible broken page links) are left alone and listed.

Dry run by default.  Usage:
    python scripts/strip-dead-order-links.py --station 001-TestStation [--apply] [--show PageID]
After --apply run compile-cms.py, audit-teststation.py and node scripts/render-check.js.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("audit", ROOT / "scripts" / "audit-teststation.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

FIELDS = ("Text", "Therapy")
# Targets the runtime or CMS handles itself.
KEEP_PREFIXES = ("http://", "https://", "mailto:", "cdss:", "/", "#")
# Non-VA medication order dialogs (pshzid, pshzid2, ...) are missing from audit's prefix list.
EXTRA_ORDER_PREFIXES = ("pshzid",)


def station_entry(station):
    for entry in audit.STATIONS:
        if entry[0] == station:
            return entry
    sys.exit(f"Unknown station {station}; known: {[e[0] for e in audit.STATIONS]}")


def known_names(station):
    """(OM names, OD names), normalized."""
    _, om_file, od_file, _ = station_entry(station)
    base = ROOT / "stations" / station
    norm = audit.normalize_comparable_id
    om = {norm(m["Name"]) for m in json.loads((base / om_file).read_text(encoding="utf-8"))["menus"]}
    # GMENU names pass isGuidanceTargetName in cdss-app.js, so the runtime still links them.
    od = {norm(m["Name"]) for m in json.loads((base / od_file).read_text(encoding="utf-8"))
          if "GMENU" not in m["Name"].upper()}
    return om, od


def unescape_label(label):
    # The VistA import escaped the parentheses around cost markers: \($$\)
    return label.replace("\\(", "(").replace("\\)", ")")


def rewrite(text, names, od_names, page_ids, kept):
    count = 0

    def repl(match):
        nonlocal count
        label, target = match.group(1), match.group(2).strip()
        tl = target.lower()
        if tl.startswith(KEEP_PREFIXES) or target in page_ids:
            return match.group(0)
        normalized = audit.normalize_comparable_id(target)
        if normalized in names:
            return match.group(0)
        # Links resolving only to an order dialog are suppressed in combined mode
        # (shouldSuppressCombinedInternalLink in cdss-app.js), so the site shows plain text.
        is_order = audit.is_non_menu_link(tl) or tl.startswith(EXTRA_ORDER_PREFIXES)
        if normalized not in od_names and (audit.LEGACY_LINK_RE.match(tl) or not is_order):
            kept.append((label, target))
            return match.group(0)
        count += 1
        return unescape_label(label)

    return audit.LINK_RE.sub(repl, text), count


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--station", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show", metavar="PAGEID", help="print the rewritten fields of one page")
    args = ap.parse_args()

    names, od_names = known_names(args.station)
    files = sorted((ROOT / "cms-data" / args.station / "pages").rglob("*.json"))
    page_ids = {json.loads(f.read_text(encoding="utf-8")).get("PageID") for f in files}

    total_links = changed_pages = 0
    kept_all = []
    for f in files:
        raw = f.read_bytes().decode("utf-8")
        data = json.loads(raw)
        kept = []
        page_count = 0
        for field in FIELDS:
            value = data.get(field)
            if not value:
                continue
            data[field], n = rewrite(value, names, od_names, page_ids, kept)
            page_count += n
        kept_all += [(data.get("PageID"), label, target) for label, target in kept]
        if not page_count:
            continue
        total_links += page_count
        changed_pages += 1
        print(f"{data.get('PageID')}: {page_count} link(s)")
        if args.show == data.get("PageID"):
            for field in FIELDS:
                if data.get(field):
                    print(f"--- {field} ---\n{data[field]}\n")
        if args.apply:
            out = json.dumps(data, indent=2, ensure_ascii=False)
            if raw.endswith("\n"):
                out += "\n"
            if "\r\n" in raw:
                out = out.replace("\n", "\r\n")
            f.write_bytes(out.encode("utf-8"))

    print(f"\n{args.station}: {total_links} dead order link(s) in {changed_pages} page(s)"
          f"{'' if args.apply else ' (dry run, nothing written)'}")
    if kept_all:
        print(f"{len(kept_all)} other unresolved/legacy link(s) left unchanged:")
        for pid, label, target in kept_all:
            print(f"  {pid}: [{label}]({target})")


if __name__ == "__main__":
    main()
