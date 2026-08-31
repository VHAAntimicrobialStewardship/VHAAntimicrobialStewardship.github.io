#!/usr/bin/env python3
"""Sync absolute document URLs and markdown helpers for CMS document entries."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

BASE_URL = "https://vhaantimicrobialstewardship.github.io"
DOCS_DIR = Path("cms-data/001-TestStation/documents")


def to_absolute_url(file_path: str) -> str:
    file_path = (file_path or "").strip()
    if not file_path:
        return ""
    if file_path.startswith("http://") or file_path.startswith("https://"):
        return file_path
    if not file_path.startswith("/"):
        file_path = "/" + file_path
    encoded_path = quote(file_path, safe="/")
    return BASE_URL + encoded_path


def build_markdown_link(title: str, link_label: str, absolute_url: str) -> str:
    label = (link_label or "").strip() or (title or "").strip() or "Download file"
    return f"[{label}]({absolute_url})" if absolute_url else ""


def sync_file(path: Path) -> bool:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    file_path = data.get("File", "")
    title = data.get("Title", "")
    link_label = data.get("LinkLabel", "")

    absolute_url = to_absolute_url(file_path)
    markdown_link = build_markdown_link(title, link_label, absolute_url)

    changed = False
    if data.get("AbsoluteURL", "") != absolute_url:
        data["AbsoluteURL"] = absolute_url
        changed = True
    if data.get("MarkdownLink", "") != markdown_link:
        data["MarkdownLink"] = markdown_link
        changed = True

    if changed:
        with path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return changed


def main() -> int:
    if not DOCS_DIR.exists():
        print(f"Directory not found: {DOCS_DIR}")
        return 0

    changed_files = 0
    for path in sorted(DOCS_DIR.glob("*.json")):
        if sync_file(path):
            changed_files += 1
            print(f"Updated {path}")

    print(f"Done. Updated {changed_files} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
