"""Scaffold a new CMS station from an existing one (dry run by default).

    python scripts/new-station.py --folder 636-Omaha --prefix Omaha --label Omaha
    python scripts/new-station.py --folder 636-Omaha --prefix Omaha --label Omaha --apply

Creates, without overwriting anything that exists:
  - cms-data/<folder>/pages/   byte copy of the source station's pages (default 001-TestStation)
  - cms-data/<folder>/documents/.gitkeep
  - stations/<folder>/<prefix>OMJSON.json   source OMJSON without the Last-updated fields
    (compile-cms.py stamps them from this station's own git history once committed)
  - stations/<folder>/<prefix>ODJSON.json   empty, like the production stations
  - stations/<folder>/<prefix>CDSS.html     the first production station's page with this station's names
  - the station's Documents and pages collections in admin/config.yml (cloned from that production station)
  - the station's entry in scripts/stations.json (which every pipeline script reads)

Afterwards: compile-cms.py, audit-teststation.py, render-check.js, nav-snapshot.js (review, then --write),
strip-dead-order-links.py --station <folder> for order-dialog links copied from the test station (the new
ODJSON is empty), commit with a plain subject (not "Create <station> ..."), recompile and check git status is clean.
Links on index.html and the service worker precache list are left for go-live.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import station_registry

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "admin" / "config.yml"
LAST_UPDATED_FIELDS = ("LastUpdatedBy", "LastUpdated", "InitialLoaded")


def config_blocks(text: str) -> dict[str, str]:
    """Top-level collection blocks of config.yml keyed by label (trailing blank lines stripped)."""
    starts = [m.start() for m in re.finditer(r"(?m)^  - label: ", text)]
    blocks = {}
    for i, start in enumerate(starts):
        block = text[start:starts[i + 1] if i + 1 < len(starts) else len(text)]
        label = re.match(r'  - label: "?([^"\n]*)', block).group(1)
        blocks[label] = block.rstrip() + "\n"
    return blocks


def station_html(template: str, tpl: dict, folder: str, prefix: str, label: str) -> str:
    replacements = [
        (r"var CDSSlocation = '[^']*';", f"var CDSSlocation = '{label}';"),
        (r"var Title = '[^']*';", f"var Title = '{label} Antimicrobial CDSS';"),
        (r"var MainMenuButton = '[^']*';", f"var MainMenuButton = '{label} Home';"),
        (r"const OMjson = '[^']*';", f"const OMjson = '/stations/{folder}/{prefix}OMJSON.json';"),
        (r"const ODjson = '[^']*';", f"const ODjson = '/stations/{folder}/{prefix}ODJSON.json';"),
        (r"const txmlFile = '[^']*';", f"const txmlFile = '/stations/{folder}/{prefix}.txml';"),
        (r'<button id="mainMenuButton">[^<]*</button>', f'<button id="mainMenuButton">{label} Home</button>'),
    ]
    out = template
    for pattern, new in replacements:
        out, n = re.subn(pattern, lambda _m, new=new: new, out)
        if n != 1:
            sys.exit(f"Template {tpl['html']}: expected one match for {pattern}, found {n}")
    if tpl["folder"] in out or f"'{tpl['label']}" in out:
        sys.exit(f"Template {tpl['html']} still names {tpl['folder']} / {tpl['label']} after substitution")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", required=True, help="station folder, e.g. 636A6-DesMoines")
    ap.add_argument("--prefix", required=True, help="file name prefix, e.g. DesMoines")
    ap.add_argument("--label", required=True, help="display name, e.g. 'Des Moines'")
    ap.add_argument("--source", default="001-TestStation", help="station whose pages are copied")
    ap.add_argument("--apply", action="store_true", help="write the files (default: dry run)")
    args = ap.parse_args()
    folder, prefix, label = args.folder, args.prefix, args.label

    if not re.fullmatch(r"\d+[A-Za-z0-9]*-[A-Za-z]+", folder):
        sys.exit("--folder must look like 618-Minneapolis or 636A6-DesMoines")
    if not re.fullmatch(r"[A-Za-z]+", prefix):
        sys.exit("--prefix must be letters only")
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", label):
        sys.exit("--label must be letters, spaces, dots, apostrophes or hyphens")

    stations = station_registry.load()
    by_folder = {s["folder"]: s for s in stations}
    if args.source not in by_folder:
        sys.exit(f"Unknown --source {args.source}; registered: {list(by_folder)}")
    source = by_folder[args.source]
    tpl = next(s for s in stations if s["role"] == "production")
    collection = station_registry.collection_name(folder)

    problems = []
    if folder in by_folder:
        problems.append(f"{folder} is already in scripts/stations.json")
    if any(station_registry.collection_name(s["folder"]) == collection for s in stations):
        problems.append(f"collection id {collection} is already used")
    station_dir, cms_dir = ROOT / "stations" / folder, ROOT / "cms-data" / folder
    targets = [cms_dir, station_dir / f"{prefix}OMJSON.json", station_dir / f"{prefix}ODJSON.json",
               station_dir / f"{prefix}CDSS.html"]
    problems += [f"{p.relative_to(ROOT)} already exists" for p in targets if p.exists()]
    config_text = CONFIG.read_text(encoding="utf-8")
    blocks = config_blocks(config_text)
    if folder in blocks or f"{folder} Documents" in blocks or f'"{collection}_' in config_text:
        problems.append(f"admin/config.yml already has a collection for {folder}")
    if problems:
        sys.exit("Refusing to scaffold:\n  " + "\n  ".join(problems))

    pages = sorted((ROOT / "cms-data" / source["folder"] / "pages").rglob("*.json"))
    om = json.loads((ROOT / "stations" / source["folder"] / source["omjson"]).read_text(encoding="utf-8"))
    stripped = 0
    for record in om["menus"]:
        for field in LAST_UPDATED_FIELDS:
            stripped += record.pop(field, None) is not None
    html = station_html((ROOT / "stations" / tpl["folder"] / tpl["html"]).read_text(encoding="utf-8"),
                        tpl, folder, prefix, label)
    new_blocks = []
    for suffix in (" Documents", ""):
        block = blocks[tpl["folder"] + suffix]
        block = block.replace(tpl["folder"], folder)
        block = block.replace(f'"{station_registry.collection_name(tpl["folder"])}_', f'"{collection}_')
        new_blocks.append(block)

    print(f"Station {folder} ({label}), collection {collection}_all_pages / {collection}_documents")
    print(f"  cms-data/{folder}/pages: {len(pages)} page files copied from {source['folder']}")
    print(f"  stations/{folder}/{prefix}OMJSON.json: {len(om['menus'])} records from {source['omjson']}"
          f" ({stripped} Last-updated fields removed)")
    print(f"  stations/{folder}/{prefix}ODJSON.json: empty")
    print(f"  stations/{folder}/{prefix}CDSS.html: from {tpl['html']}")
    print(f"  admin/config.yml: 2 collections cloned from {tpl['folder']}")
    print("  scripts/stations.json: entry added")
    if not args.apply:
        print("Dry run; re-run with --apply to write.")
        return

    for page in pages:
        dest = cms_dir / "pages" / page.relative_to(ROOT / "cms-data" / source["folder"] / "pages")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(page, dest)
    (cms_dir / "documents").mkdir(parents=True, exist_ok=True)
    (cms_dir / "documents" / ".gitkeep").write_bytes(b"")
    station_dir.mkdir(parents=True, exist_ok=True)
    with open(station_dir / f"{prefix}OMJSON.json", "w", encoding="utf-8") as f:
        json.dump(om, f, indent=2, ensure_ascii=False)
        f.write("\n")
    (station_dir / f"{prefix}ODJSON.json").write_bytes(b"[]")
    (station_dir / f"{prefix}CDSS.html").write_text(html, encoding="utf-8")

    with open(CONFIG, "w", encoding="utf-8") as f:
        f.write(config_text.rstrip() + "\n" + "".join(new_blocks))

    registry = station_registry.REGISTRY.read_text(encoding="utf-8")
    entry = json.dumps({"folder": folder, "prefix": prefix, "label": label, "role": "production"})
    entry = "    " + entry.replace('{"', '{ "').replace('"}', '" }')
    registry, n = re.subn(r"( \}\n)(  \]\n\}\s*)$", lambda m: m.group(1)[:-1] + ",\n" + entry + "\n" + m.group(2),
                          registry)
    if n != 1:
        sys.exit("Could not add the station to scripts/stations.json; add it by hand")
    station_registry.REGISTRY.write_text(registry, encoding="utf-8")
    print("Written.")


if __name__ == "__main__":
    main()
