#!/usr/bin/env python3
"""Remove the legacy "[Help and Legend](general-information-legend)" markdown
link from cms-data page Text fields, now that the Help and Legend link lives
permanently in the site header (TestStationCDSS.html).

Handles two shapes found in the data:
  1. A standalone line consisting solely of the link (optionally preceded by
     other whitespace) - the whole line is dropped, along with one adjacent
     blank line so no orphaned double-blank-line is left behind.
  2. The link embedded inline within a longer line (e.g. a heading line that
     also contains other text) - only the link substring is stripped from the
     line, the rest of the line's content is preserved.

Usage:
  python scripts/remove-help-legend-links.py --dry-run   # preview only
  python scripts/remove-help-legend-links.py --apply     # write changes
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "cms-data" / "001-TestStation" / "pages"
LINK = "[Help and Legend](general-information-legend)"


def strip_help_legend(text):
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    changed = False
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped == LINK:
            changed = True
            if i + 1 < n and lines[i + 1].strip() == "":
                i += 2
                continue
            elif out and out[-1].strip() == "":
                out.pop()
                i += 1
                continue
            else:
                i += 1
                continue
        elif LINK in line:
            changed = True
            newline = line.replace(LINK, "")
            newline = re.sub(r"[ \t]{2,}", " ", newline).rstrip()
            out.append(newline)
            i += 1
        else:
            out.append(line)
            i += 1
    return "\n".join(out), changed


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    changed_files = []
    for path in sorted(PAGES_DIR.glob("**/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        text = data.get("Text")
        if not isinstance(text, str) or LINK not in text:
            continue
        new_text, changed = strip_help_legend(text)
        if changed and new_text != text:
            changed_files.append(str(path.relative_to(ROOT)))
            if args.apply:
                data["Text"] = new_text
                path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

    print(f"{'Would change' if args.dry_run else 'Changed'} {len(changed_files)} files")
    for f in changed_files:
        print(f"  {f}")


if __name__ == "__main__":
    main()
