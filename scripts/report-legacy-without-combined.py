"""Report every legacy (non-combined) menu record that has no Combined equivalent yet,
along with the shortest link-based navigation path to reach it from each of the four
main menus (Combined, Inpatient, Outpatient, ER/UC).

This is a read-only reporting script (no data is modified). Intended to help decide
which legacy content can be safely dropped once the site moves to combined-only.

Usage:
    python scripts/report-legacy-without-combined.py
Writes:
    reports/legacy-without-combined-report.json
"""
import json
import re
from collections import deque
from pathlib import Path

JSON_PATH = Path("stations/001-TestStation/TestStationOMJSON.json")
REPORT_PATH = Path("reports/legacy-without-combined-report.json")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")


def normalize_comparable_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").strip().lower())


def is_slug_name(name: str) -> bool:
    return bool(SLUG_RE.match(name or ""))


def main():
    with JSON_PATH.open(encoding="utf-8") as f:
        menus = json.load(f)["menus"]

    by_name = {m["Name"]: m for m in menus}

    normalized_to_name = {}
    for m in menus:
        norm = normalize_comparable_id(m["Name"])
        normalized_to_name.setdefault(norm, m["Name"])

    # Build the directed link graph from markdown links in every record's Text.
    # A link is a real graph edge only if its target resolves (case/punctuation
    # insensitively) to an actual existing record Name -- this naturally excludes
    # VistA order-dialog/lab/consult links (they simply don't resolve to anything
    # in omData) without needing any prefix-based heuristic. NOTE: do not reuse
    # audit-teststation.py's is_non_menu_link()/NON_MENU_GMENU_RE heuristic here --
    # it assumes real CDSS content is always namespaced "-gmenu-abx-", but ER/UC
    # content is namespaced "-gmenu-er-uc-" (no "abx"), so that heuristic
    # incorrectly treats real ER/UC internal links as non-menu noise and silently
    # drops real navigation edges, producing false "orphaned" results.
    graph = {m["Name"]: set() for m in menus}
    for m in menus:
        txt = m.get("Text", "")
        if not txt:
            continue
        for _label, target in LINK_RE.findall(txt):
            t = target.strip()
            tl = t.lower()
            if tl.startswith(("http://", "https://", "cdss:", "/")):
                continue
            resolved = normalized_to_name.get(normalize_comparable_id(t))
            if resolved and resolved != m["Name"]:
                graph[m["Name"]].add(resolved)

    roots = {
        "combined": "main-menu",
        "inpatient": "ORZID2 GMENU ABX INPT MAIN",
        "outpatient": "ORZID3 GMENU ABX OUTPT MAIN",
        "eruc": "ORZID GMENU ER/UC EMERGENCY DEPARTMENT MAIN MENU",
    }

    def bfs(root):
        """Return dict: Name -> path (list of Names) from root to Name, shortest hops."""
        if root not in graph:
            return {}
        paths = {root: [root]}
        queue = deque([root])
        while queue:
            cur = queue.popleft()
            for nxt in graph.get(cur, ()):
                if nxt not in paths:
                    paths[nxt] = paths[cur] + [nxt]
                    queue.append(nxt)
        return paths

    paths_by_root = {label: bfs(name) for label, name in roots.items()}

    def label_for(name):
        rec = by_name.get(name)
        if not rec:
            return name
        return rec.get("Term1") or rec.get("Term2") or name

    def breadcrumb(path):
        return [{"name": n, "label": label_for(n)} for n in path]

    # Legacy = non-slug Name (i.e. a raw VistA/order-menu record), with no Combined equivalent.
    legacy_without_combined = [
        m for m in menus
        if not is_slug_name(m.get("Name", "")) and not (m.get("Combined") or "").strip()
    ]

    report = []
    priority = ["combined", "inpatient", "outpatient", "eruc"]
    for m in legacy_without_combined:
        name = m["Name"]
        reachable = {}
        for label in priority:
            path = paths_by_root[label].get(name)
            reachable[label] = {
                "reachable": path is not None,
                "hops": (len(path) - 1) if path else None,
            }

        primary_label = next((lbl for lbl in priority if reachable[lbl]["reachable"]), None)
        primary_path = paths_by_root[primary_label].get(name) if primary_label else None

        report.append({
            "name": name,
            "term1": m.get("Term1") or "",
            "term2": m.get("Term2") or "",
            "reachableFromCombinedMainMenu": reachable["combined"]["reachable"],
            "primaryMenu": primary_label,
            "hops": reachable[primary_label]["hops"] if primary_label else None,
            "breadcrumb": breadcrumb(primary_path) if primary_path else None,
            "reachability": reachable,
            "orphaned": primary_label is None,
        })

    # Sort: live-site exposure (reachable from combined) first, then by menu, then by hops, then name.
    menu_sort_key = {label: i for i, label in enumerate(priority)}
    menu_sort_key[None] = len(priority)
    report.sort(key=lambda r: (
        0 if r["reachableFromCombinedMainMenu"] else 1,
        menu_sort_key[r["primaryMenu"]],
        r["hops"] if r["hops"] is not None else 9999,
        r["name"],
    ))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump({
            "totalLegacyWithoutCombined": len(report),
            "counts": {
                "reachableFromCombinedMainMenu": sum(1 for r in report if r["reachableFromCombinedMainMenu"]),
                "reachableOnlyFromLegacyMenus": sum(
                    1 for r in report if not r["reachableFromCombinedMainMenu"] and r["primaryMenu"]
                ),
                "orphaned": sum(1 for r in report if r["orphaned"]),
            },
            "records": report,
        }, f, indent=2)

    print(f"Legacy records without a Combined equivalent: {len(report)}")
    print(f"  Reachable from Combined Main Menu (live-site exposure): "
          f"{sum(1 for r in report if r['reachableFromCombinedMainMenu'])}")
    print(f"  Reachable only from a legacy tab's main menu: "
          f"{sum(1 for r in report if not r['reachableFromCombinedMainMenu'] and r['primaryMenu'])}")
    print(f"  Orphaned (not reachable from any main menu): "
          f"{sum(1 for r in report if r['orphaned'])}")
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
