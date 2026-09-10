"""
scripts/set-nav-sort-keys.py

Populates the CMS-only "SortKey" field on every cms-data/001-TestStation/pages
page file so that Sveltia's entry list shows each group's designated nav/index
page first, followed by the rest of that group's pages in alphabetical order
by Term1.

SortKey is NOT copied into OMJSON by compile-cms.py (it only reads Term1,
Term2, Text, Inpt, Outpt, ERUC), so this has zero effect on the live site —
it only affects ordering in the Sveltia CMS entry list, which is configured
in admin/config.yml to sort by SortKey ascending by default.

Safe to re-run any time a group's nav page changes or new pages are added;
it recomputes every SortKey from scratch based on NAV_OVERRIDES below and
each file's own Group/Term1/PageID values.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
CMS_ROOT = ROOT / "cms-data" / "001-TestStation" / "pages"

# Groups whose designated nav/index page's PageID does NOT match the Group
# slug. Any group not listed here defaults to the page whose PageID equals
# the group folder name.
NAV_OVERRIDES = {
    "bispecific-antibody": "bispecific-disease-specific-management",
    "general": "main-menu",
    "important-antimicrobial": "susceptibilities-antibiogram",
    "organisms": "bacteria",
    "surgical-antimicrobial-prophylaxis": "surgical-pre-op-antibiotics",
}


def main() -> None:
    changed = 0
    for group_dir in sorted(p for p in CMS_ROOT.iterdir() if p.is_dir()):
        group = group_dir.name
        nav_page_id = NAV_OVERRIDES.get(group, group)
        for fp in sorted(group_dir.glob("*.json")):
            data = json.loads(fp.read_text(encoding="utf-8"))
            page_id = data.get("PageID", fp.stem)
            term1 = data.get("Term1", "")
            if page_id == nav_page_id:
                sort_key = f"{group}~0"
            else:
                sort_key = f"{group}~1~{term1.lower()}"

            if data.get("SortKey") == sort_key:
                continue

            new_data = {}
            inserted = False
            for k, v in data.items():
                if k == "SortKey":
                    continue  # will be re-inserted in the right spot
                new_data[k] = v
                if k == "Group":
                    new_data["SortKey"] = sort_key
                    inserted = True
            if not inserted:
                new_data["SortKey"] = sort_key

            fp.write_text(
                json.dumps(new_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            changed += 1

    print(f"Files changed: {changed}")


if __name__ == "__main__":
    main()
