"""
fix-combined-link-headings.py

Fixes two formatting artifacts in ORZC combined menus:

1. "## Inpatient [drug order](...)" - drug link was matched mid-heading.
   Fix: split into "## Inpatient" heading + "[drug order](...)" on its own line.

2. "[some link](...) ##Outpatient" - heading fragment appended after a link.
   Fix: split into "[some link](...)" + "## Outpatient" on separate lines.
"""
import json
import re
from pathlib import Path

JSON_PATH = Path(r"stations/001-TestStation/TestStationOMJSON.json")

with JSON_PATH.open(encoding="utf-8") as f:
    data = json.load(f)

# Patterns
# Pattern 1: "## Inpatient/Outpatient/ER [link]..." or "## Inpatient/... plain text"
INPT_HEADING_LINK = re.compile(
    r'^(#{1,6}\s+(?:Inpatient|Outpatient|ER(?:/UC)?|Inpatient\s*/\s*(?:##\s*)?Outpatient)(?:\s+Preferred)?)\s+'
    r'(.+)$',
    re.IGNORECASE,
)

# Pattern 2: "[link](...) ##Something" - trailing heading after link
TRAILING_HEADING = re.compile(
    r'^(\[.+?\]\([^)]+\))\s*(#{1,6}\s*.+)$',
)

# Pattern 3: "[link](...) ##Something" with no space - no space variant
TRAILING_HEADING_NOSPACE = re.compile(
    r'^(\[.+?\]\([^)]+\))(#{1,6}\S.*)$',
)

fixed_menus = 0
fixed_lines = 0


def fix_text(text: str) -> tuple[str, int]:
    lines = text.split("\n")
    new_lines = []
    changes = 0

    for line in lines:
        stripped = line.strip()

        # Pattern 1: heading with content after it
        m1 = INPT_HEADING_LINK.match(stripped)
        if m1:
            heading_part = m1.group(1).strip()
            content_part = m1.group(2).strip()
            if content_part:  # only split if there's something after the heading
                new_lines.append(f"## {heading_part.lstrip('#').strip()}")
                new_lines.append("")
                new_lines.append(content_part)
                changes += 1
                continue

        # Pattern 2+3: link followed by ##heading
        m2 = TRAILING_HEADING.match(stripped) or TRAILING_HEADING_NOSPACE.match(stripped)
        if m2:
            link_part = m2.group(1).strip()
            head_part = m2.group(2).strip()
            # Normalise the heading marker spacing
            head_part = re.sub(r'^(#{1,6})(\S)', r'\1 \2', head_part)
            new_lines.append(link_part)
            new_lines.append("")
            new_lines.append(head_part)
            changes += 1
            continue

        new_lines.append(line)

    return "\n".join(new_lines), changes


for m in data["menus"]:
    if not m["Name"].startswith("ORZC "):
        continue
    text = m.get("Text", "")
    new_text, n = fix_text(text)
    if n > 0:
        m["Text"] = new_text
        fixed_menus += 1
        fixed_lines += n

with JSON_PATH.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Menus fixed  : {fixed_menus}")
print(f"Lines fixed  : {fixed_lines}")
