import json
from pathlib import Path

P = Path(r"stations/001-TestStation/TestStationOMJSON.json")
with P.open(encoding="utf-8") as f:
    data = json.load(f)

menus = data["menus"]
name_set = {m["Name"] for m in menus}

# Explicit one-off corrections for known legacy/typo names.
EXACT_MAP = {
    "ORZID3 GMENU COMM ACQ PNEUMONIA": "ORZID3 GMENU COMM INFECT PNEUMO",
    "ORZID3 GMENU PROPHYLAXIS PROSTATE BIOPSY": "ORZID3 GMENU PROSTATE BIOPSY PROPHYLAXIS",
    "ORZID3 GMENU ABX MALARIA TREATMENT EDUC: ORZID GMENU ED/UC MALARIA TREATMENT": "ORZID3 GMENU ABX MALARIA TREATMENT",
}


def resolve(target: str):
    if not target:
        return target

    t = target.strip()

    # 1) Already valid after trim.
    if t in name_set:
        return t

    # 2) Exact known legacy mapping.
    if t in EXACT_MAP and EXACT_MAP[t] in name_set:
        return EXACT_MAP[t]

    # 3) Remove appended EDUC suffix patterns.
    if " EDUC:" in t:
        t2 = t.split(" EDUC:", 1)[0].strip()
        if t2 in name_set:
            return t2

    # 4) Remove ABX token from ORZID3 names where target exists.
    if t.startswith("ORZID3 GMENU ABX "):
        t2 = t.replace("ORZID3 GMENU ABX ", "ORZID3 GMENU ", 1)
        if t2 in name_set:
            return t2

    # 5) Common trailing-space issues.
    if (t + " ") in name_set:
        return t + " "

    return target


fixed = 0
still_broken = []

for m in menus:
    outpt = m.get("Outpt")
    if outpt and outpt not in name_set:
        new_t = resolve(outpt)
        m["Outpt"] = new_t
        if new_t != outpt:
            fixed += 1
        if new_t not in name_set:
            still_broken.append((m["Name"], outpt, new_t))

with P.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Outpt refs fixed:", fixed)
print("Still broken:", len(still_broken))
for src, old, new in still_broken[:20]:
    print(" -", src)
    print("    old:", old)
    print("    new:", new)
