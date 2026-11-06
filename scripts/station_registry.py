"""The CMS station list (scripts/stations.json), shared by the pipeline scripts."""

import json
from pathlib import Path

REGISTRY = Path(__file__).with_name("stations.json")


def load() -> list[dict]:
    """Stations in registry order (test station first), with omjson/odjson/html file names added."""
    stations = json.loads(REGISTRY.read_text(encoding="utf-8"))["stations"]
    for s in stations:
        s["omjson"] = f"{s['prefix']}OMJSON.json"
        s["odjson"] = f"{s['prefix']}ODJSON.json"
        s["html"] = f"{s['prefix']}CDSS.html"
    return stations


def collection_name(folder: str) -> str:
    """Sveltia collection id, e.g. 506-AnnArbor -> 506ann, 636A6-DesMoines -> 636a6des (same rule as cdss-sidebar.js)."""
    number, _, name = folder.partition("-")
    return number.lower() + name[:3].lower()
