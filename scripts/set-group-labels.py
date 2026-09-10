"""
scripts/set-group-labels.py

Populates the CMS-only "GroupLabel" field on every cms-data/001-TestStation/pages
page file with the human-readable label for that page's Group slug (e.g. "cns"
-> "Central Nervous System"), matching the labels used in the Group select
field's options list in admin/config.yml.

GroupLabel is NOT copied into OMJSON by compile-cms.py (it only reads Term1,
Term2, Text, Inpt, Outpt, ERUC), so this has zero effect on the live site --
it only affects the text shown in Sveltia's "Group by Clinical Group" section
headers (view_groups), which is configured in admin/config.yml to group by
GroupLabel instead of the raw Group slug.

Safe to re-run any time a new Group is added; keep GROUP_LABELS in sync with
the options list in admin/config.yml.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
CMS_ROOT = ROOT / "cms-data" / "001-TestStation" / "pages"

# Must stay in sync with the Group field's `options` list in admin/config.yml.
GROUP_LABELS = {
    "bone-joint-muscle-infections": "Bone, Muscle & Joint Infections",
    "cardiovascular": "Cardiovascular",
    "cns": "Central Nervous System",
    "gi-intraabdominal": "GI & Intraabdominal",
    "head-and-neck": "Head and Neck",
    "lung-and-mediastinum": "Lungs & Mediastinum",
    "ssti-main-menu": "Skin & Soft Tissue Infections",
    "system-infectious-diseases": "Systemic Infections",
    "genitourinary": "Urogenital",
    "organisms": "Organisms",
    "dermatologic-surgery-guidelines": "Dermatological Guidelines",
    "device-related-infections": "Device-Related Infections",
    "hiv-aids": "HIV / AIDS",
    "immunocompromised-patient": "Immunocompromised Patients",
    "tpoxx-monkeypox-treatment": "MPox Treatment",
    "prevention-of-infection": "Prevention of Infection",
    "recommended-immunizations": "Recommended Adult Immunizations",
    "surgical-antimicrobial-prophylaxis": "Surgical Antimicrobial Prophylaxis",
    "surgical-site-infections": "Surgical Site Infections",
    "bispecific-antibody": "Bispecific Antibody",
    "help-page": "Help & Resources",
    "important-antimicrobial": "Important Antimicrobial Information",
    "general": "General / Miscellaneous",
}


def main() -> None:
    changed = 0
    missing_labels = set()
    for group_dir in sorted(p for p in CMS_ROOT.iterdir() if p.is_dir()):
        group = group_dir.name
        label = GROUP_LABELS.get(group)
        if label is None:
            missing_labels.add(group)
            continue
        for fp in sorted(group_dir.glob("*.json")):
            data = json.loads(fp.read_text(encoding="utf-8"))

            if data.get("GroupLabel") == label:
                continue

            new_data = {}
            inserted = False
            for k, v in data.items():
                if k == "GroupLabel":
                    continue  # will be re-inserted in the right spot
                new_data[k] = v
                if k == "Group":
                    new_data["GroupLabel"] = label
                    inserted = True
            if not inserted:
                new_data["GroupLabel"] = label

            fp.write_text(
                json.dumps(new_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            changed += 1

    print(f"Files changed: {changed}")
    if missing_labels:
        print(f"WARNING: no label mapping for groups: {sorted(missing_labels)}")


if __name__ == "__main__":
    main()
