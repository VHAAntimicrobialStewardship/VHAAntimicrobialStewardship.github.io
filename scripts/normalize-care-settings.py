"""Apply the care-setting label rule to pages whose Therapy panel has setting labels.

Rule (user, 2026-11-06): a page with one set of therapy recommendations has no setting label; when
recommendations differ by care setting, every set gets a '## <setting>' label (settings with the same
guidance share one slash-joined label such as '## Inpatient/Outpatient'), Inpatient first, sub-headings
'###'. A short preamble that applies to every setting may sit above the labels.

The page's current sections drive the result; nothing is added for a setting the page has no section for.
A section is dropped only when it is empty or just refers to the inpatient CDSS (obsolete on the combined
site). Sections with identical guidance (ignoring Non-VA order lines and TID/q8h-style spelling) are joined
under one label. The current inpatient content is kept, unless it has visibly lost drug lines ('< OR >'
twice in a row) on a page never edited in Sveltia; an unlabeled block before the first label belongs to
Inpatient when the archived inpatient record contains it (or another section repeats it), else it stays as
a shared preamble. Outpatient and ER/UC keep their current text unless it is a lossy copy of the archived
legacy therapy (Inpt/Outpt/ERUC records), which is then rebuilt from the archive; pages edited in Sveltia
(LastUpdatedBy in OMJSON, on the station or on the test station they were copied from) are never rebuilt
and are listed instead. The result is stable: a second run changes nothing.

Dry run by default:
  python scripts/normalize-care-settings.py [--station S] [--page P] [--dump FILE] [--apply]
  python scripts/normalize-care-settings.py --station 999-NewStation --archive FILE   (wave 2)
Then run compile-cms.py, audit-teststation.py, node scripts/render-check.js and nav-snapshot.js.
"""
import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = load_script("consolidate-care-settings")
promote, cleanup = cc.promote, cc.cleanup

SETTINGS = (("Inpatient", "Inpt"), ("Outpatient", "Outpt"), ("ER/UC", "ERUC"))
ORDER = {label: i for i, (label, _) in enumerate(SETTINGS)}
TOKEN = r"(?:Inpatient|Outpatient|ER/UC|ER|ED)"
LABEL_RE = re.compile(rf"^#{{1,6}}\s*#?\s*(?:\*\*)?\s*({TOKEN}(?:\s*/\s*{TOKEN})*)\s*(?:\*\*)?:?\s*$", re.I)
# A setting marker glued into a line by the old merge: '... above ##ER ## Prophylaxis:', '... [M]Outpatient'.
GLUED_RE = re.compile(r"(?:\s*(?<=\s)#{1,2}\s*|(?<=\]))\b(ER|Outpatient|Inpatient)\b(?!/)")
# '## # ER Ceftriaxone ...' or '##ER ## Prophylaxis:': a setting label with the next line glued on.
DOUBLE_HASH_RE = re.compile(r"^(?:#{1,2}\s+#\s*|#{1,2})(ER|Outpatient|Inpatient)\b\s*(.*)$")
# Headings that run a setting label into a sub-heading (the outpatient one lost part of its text).
QUALIFIED = {
    "## Inpatient Treatment for persistent or recurrent urethritis and failure of initial doxycycline treatment":
        ("Inpatient", "Treatment for persistent or recurrent urethritis and failure of initial doxycycline treatment"),
    "## Outpatient Guidance doxycycline treatment":
        ("Outpatient", "Treatment for persistent or recurrent urethritis and failure of initial doxycycline treatment"),
    "## Outpatient Preferred treatment": ("Outpatient", "Preferred treatment"),
}
NON_VA_RE = re.compile(r"^\s*\[?Non[- ]VA order for above\]?(?:\([^)]*\))?\s*$", re.I)
NON_VA_ANY_RE = re.compile(r"[ \t]*\[?Non[- ]VA order for above\]?(?:\([^)]*\))?[ \t]*", re.I)
# The inpatient guidance is on the same page now, so pointers to a separate inpatient CDSS go.
REFER_LINE_RE = re.compile(r"^\s*(?:#+\s*)?(?:for intravenous treatment options, please )?refer to (?:the )?inpatient\b.*\bcdss\b.*$"
                           r"|^\s*refer to the inpatient or outpatient .*\bcdss\b.*$", re.I)
REFER_REPLACE = [
    ("suspected urinary tract infection: Refer to Inpatient Antimicrobial CDSS",
     "suspected urinary tract infection: see [Sepsis, urinary tract infection](sepsis-urosepsis)"),
    ("\n# Fulminant CDI: Refer to Inpatient Antimicrobial CDSS\n", "\n"),
]
CONNECTOR_RE = re.compile(r"^\s*<\s*(?:OR|AND)\s*>\s*$", re.I)
DOSE_RE = re.compile(r"\b(?:mg|gm|g|mcg|units?|tablets?|drops?|cream|ointment|IV|PO|IM)\b", re.I)
HEAD_RE = re.compile(r"^(#{1,6})\s+\S")
DEFER_RE = re.compile(r"refer to (?:the )?inpatient", re.I)
COVERED = 0.95
LOSSY_SUBSET = 0.98
# Drug lines lost by the old merge leave bare connectors behind: '< OR >' twice in a row, a trailing 'OR >'.
BROKEN_RE = re.compile(r"^\s*<\s*OR\s*>\s*\n\s*<\s*OR\s*>\s*$|[^<\s]\s*OR\s*>\s*$", re.M)


def tokens(label_text):
    out = []
    for tok in re.findall(TOKEN, label_text, re.I):
        tok = tok.upper()
        out.append({"INPATIENT": "Inpatient", "OUTPATIENT": "Outpatient"}.get(tok, "ER/UC"))
    return tuple(sorted(set(out), key=ORDER.get))


def bag(text):
    return Counter(cc.norm_words(text))


def contain(part, whole):
    p, w = bag(part), bag(whole)
    total = sum(p.values())
    return sum(min(v, w[k]) for k, v in p.items()) / total if total else 1.0


def strip_obsolete(text):
    """Drops 'Non-VA order for above' and 'refer to the inpatient CDSS' lines, with the connector, the
    'Label:' line or the heading that is left without content."""
    if not text:
        return text
    for old, new in REFER_REPLACE:
        text = text.replace(old, new)
    # The Non-VA order dialogs are gone; the phrase can sit alone, end a line or precede a glued marker.
    lines = []
    for line in text.split("\n"):
        if NON_VA_RE.match(line):
            continue
        lines.append(NON_VA_ANY_RE.sub(" ", line).rstrip() if NON_VA_ANY_RE.search(line) else line)
    lines = [l.lstrip() if l.startswith(" ##") else l for l in lines]
    out, removed_at = [], []
    for line in lines:
        if REFER_LINE_RE.match(line):
            removed_at.append(len(out))
            continue
        out.append(line)
    if not removed_at:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n") if lines != text.split("\n") else text

    drop = set()

    def near(i, step):
        """Index of the nearest non-blank, not yet dropped line from i in direction step."""
        while 0 <= i < len(out):
            if out[i].strip() and i not in drop:
                return i
            i += step
        return None

    def is_end(j, level):
        if j is None or out[j].strip() in ("---", "***") or promote.REF_HEAD_RE.match(out[j]):
            return True
        m = HEAD_RE.match(out[j])
        return bool(m) and len(m.group(1)) <= level

    for at in removed_at:
        # A connector left without a regimen on one side.
        for j in (near(at - 1, -1), near(at, 1)):
            if j is not None and CONNECTOR_RE.match(out[j]):
                before, after = near(j - 1, -1), near(j + 1, 1)
                if (before is None or after is None or not DOSE_RE.search(out[before])
                        or not DOSE_RE.search(out[after]) or CONNECTOR_RE.match(out[after])):
                    drop.add(j)
        # A heading or 'Label:' line left without content (setting labels are left to normalize()).
        before = near(at - 1, -1)
        if before is None or LABEL_RE.match(out[before].strip()):
            continue
        head = HEAD_RE.match(out[before])
        if head and not DOSE_RE.search(out[before]) and is_end(near(at, 1), len(head.group(1))):
            drop.add(before)
        elif not head and out[before].rstrip().endswith(":") and is_end(near(at, 1), 6):
            drop.add(before)
    out = [l for i, l in enumerate(out) if i not in drop]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n")


def split_glued(text):
    out = []
    for line in text.split("\n"):
        pieces = []
        if line.strip() in QUALIFIED:
            label, heading = QUALIFIED[line.strip()]
            out += [f"## {label}", "", f"## {heading}"]
            continue
        m = DOUBLE_HASH_RE.match(line)
        if m:
            pieces += ["## " + m.group(1), ""]
            line = m.group(2)
        while not LABEL_RE.match(line.strip()):
            m = next((m for m in GLUED_RE.finditer(line) if line[:m.start()].strip("# ")), None)
            if not m:
                break
            pieces += [line[:m.start()].rstrip(), "", "## " + m.group(1), ""]
            line = re.sub(r"^Guidance\b\s*", "", line[m.end():].strip())
        if line or not pieces:
            pieces.append(line)
        out += pieces
    return "\n".join(out)


def parse(therapy):
    """(preamble, [[labels, body]]) with consecutive sections of the same labels joined."""
    pre, sections = [], []
    for line in split_glued(therapy).split("\n"):
        m = LABEL_RE.match(line.strip())
        if m:
            labels = tokens(m.group(1))
            if sections and sections[-1][0] == labels:
                continue
            sections.append([labels, []])
        else:
            (sections[-1][1] if sections else pre).append(line)
    clean = lambda ls: re.sub(r"\n{3,}", "\n\n", "\n".join(ls)).strip("\n")
    return clean(pre), [[labels, clean(body)] for labels, body in sections]


def shift_headings(body, top):
    """Shifts the headings of body so the highest one is at level top."""
    levels = heading_levels(body)
    if not levels:
        return body
    delta = top - min(levels)
    return re.sub(r"^(#{1,6})(?=\s)", lambda m: "#" * min(6, max(1, len(m.group(1)) + delta)), body, flags=re.M)


def heading_levels(body):
    return [len(m.group(1)) for m in (HEAD_RE.match(l) for l in body.split("\n")) if m]


def join_blocks(first, second):
    """first + second, with first's headings moved to second's top level."""
    levels = heading_levels(second)
    if levels:
        first = shift_headings(first, min(levels))
    return first + "\n\n" + second


def archive_therapy(legacy, pid, name):
    if not name or name not in cc.ARCHIVE:
        return None
    _, therapy = legacy.parts(pid, name)
    therapy = cc.compact(cc.unlink_orders(therapy))
    therapy = "\n".join(l for l in therapy.split("\n") if not NON_VA_RE.match(l))
    # Order labels lost their brackets around the restriction codes: '($) R,DI' -> '($) [R,DI]'.
    therapy = re.sub(r"(\(\$+\))\s*((?:R|M|DI|O|H)(?:,\s?(?:R|M|DI|O|H))*)(?=\s|$)", r"\1 [\2]", therapy)
    therapy = re.sub(r"^(.*\b(?:mg|gm|g|units?|tablets?|cream|ointment|PO|IV|IM|days?|q\w+|QDay|BID|TID|QID|Regimen)\b.*?)\s+"
                     r"((?:R|M|DI|O|H)(?:,\s?(?:R|M|DI|O|H))*)\s*$", r"\1 [\2]", therapy, flags=re.M)
    therapy = re.sub(r"(?<![<\s])\s+OR\s*>\s*$", "\n< OR >", therapy, flags=re.M)
    therapy = re.sub(r"^(\s*<\s*OR\s*>\s*\n)(?:\s*<\s*OR\s*>\s*\n)+", r"\1", therapy + "\n", flags=re.M)
    therapy = re.sub(r"<\s*OR\s*>[ \t]*\n\s*<\s*OR\s*>[ \t]*(?=\n)", "< OR >", therapy)
    therapy = strip_obsolete(therapy)
    return re.sub(r"\n{3,}", "\n\n", therapy).strip("\n")


def usable(reference):
    """Archived therapy worth restoring: not empty and not just 'refer to the inpatient CDSS'."""
    if not reference:
        return None
    words = cc.norm_words(reference)
    if len(words) < 4 or (DEFER_RE.search(reference) and len(words) < 40):
        return None
    return reference


def strip_non_va(body):
    return "\n".join(l for l in body.split("\n") if not NON_VA_RE.match(l))


def same(a, b):
    """Same guidance: identical words apart from Non-VA order lines (q8h and TID differ on purpose)."""
    return bag(strip_non_va(a)) == bag(strip_non_va(b))


def lossy_copy(body, reference):
    """The section is a damaged copy of the archived text: it misses part of it and adds nothing."""
    return contain(reference, body) < COVERED and contain(strip_non_va(body), reference) >= LOSSY_SUBSET


def rebuilt(reference, text, shared_pre):
    """Archived therapy for a section, without headings the Text has or the shared preamble it repeats."""
    body = cc.drop_headings_in(reference, text)
    target = cc.norm_words(shared_pre)
    if target:
        lines = body.split("\n")
        for i in range(1, len(lines) + 1):
            seen = cc.norm_words("\n".join(lines[:i]))
            if seen == target:
                return "\n".join(lines[i:]).strip("\n")
            if len(seen) > len(target):
                break
    return body


def normalize(pid, page, legacy, edited, notes):
    """(new Therapy, sources) or None; repeated until stable (a rebuilt section can repeat the preamble)."""
    result = normalize_once(pid, page, legacy, edited, notes)
    for _ in range(3):
        if not result:
            return result
        again = normalize_once(pid, {**page, "Therapy": result[0]}, legacy, edited, [])
        if not again or again[0] == result[0]:
            return result
        result = (again[0], result[1])
    return result


def normalize_once(pid, page, legacy, edited, notes):
    pre, sections = parse(page.get("Therapy") or "")
    if not sections:
        return None
    arch, full = {}, {}
    for label, field in SETTINGS:
        name = (page.get(field) or "").strip()
        if field != "Inpt" and name == (page.get("Inpt") or "").strip():
            continue
        therapy = archive_therapy(legacy, pid, name)
        if therapy is not None:
            arch[label], full[label] = therapy, cc.ARCHIVE[name]["Text"]
    text = page.get("Text", "")

    # [labels, body, source]; the current inpatient content is always kept.
    groups, shared_pre = [], pre
    has_pre = bool(cc.norm_words(pre))
    inpatient = [s for s in sections if "Inpatient" in s[0]]
    if inpatient:
        labels = sorted({l for s in inpatient for l in s[0]}, key=ORDER.get)
        body = "\n\n".join(s[1] for s in inpatient if s[1].strip())
        # A preamble that another section repeats in its own copy is the inpatient version of it.
        if has_pre and any(contain(pre, b) >= 0.8 for ls, b in sections if "Inpatient" not in ls):
            body, shared_pre = join_blocks(pre, body), ""
        groups.append([labels, body, "current"])
    elif has_pre and ("Inpatient" not in full or contain(pre, full["Inpatient"]) >= 0.8):
        groups.append([["Inpatient"], pre, "current"])
        shared_pre = ""
    ref = usable(arch.get("Inpatient"))
    if groups and ref and lossy_copy(groups[0][1], ref) and BROKEN_RE.search(groups[0][1]):
        if edited:
            notes.append(f"{pid}: Inpatient has lost lines (edited in Sveltia; not rebuilt)")
        else:
            groups[0][1:] = [rebuilt(ref, text, shared_pre), "archive"]

    for labels, body in sections:
        if "Inpatient" in labels:
            continue
        name = "/".join(labels)
        ref, source = usable(arch.get(labels[0])), "current"
        words = cc.norm_words(strip_non_va(body))
        if words and len(words) < 15 and DEFER_RE.search(body):
            notes.append(f"{pid}: {name} only referred to the inpatient CDSS; dropped")
            continue
        if not words or len(words) < 4:
            if edited or not ref:
                notes.append(f"{pid}: empty {name} section dropped")
                continue
            body, source = rebuilt(ref, text, shared_pre), "archive"
        elif ref and lossy_copy(body, ref):
            if edited:
                notes.append(f"{pid}: {name} keeps {contain(ref, body):.0%} of the archived text (edited in Sveltia; not rebuilt)")
            else:
                body, source = rebuilt(ref, text, shared_pre), "archive"
        match = next((g for g in groups if same(g[1], body)), None)
        if match:
            match[0] = sorted(set(match[0]) | set(labels), key=ORDER.get)
        else:
            groups.append([list(labels), body, source])
    groups.sort(key=lambda g: ORDER[g[0][0]])

    pre_part = [shift_headings(shared_pre, 2)] if shared_pre.strip() else []
    if len(groups) == 1:
        new = "\n\n".join(pre_part + [shift_headings(groups[0][1], 2)])
    else:
        new = "\n\n".join(pre_part + [f"## {'/'.join(g)}\n\n{shift_headings(b, 3)}" for g, b, _ in groups])
    new = re.sub(r"\n{3,}", "\n\n", new).strip("\n")
    new = re.sub(r"(?:\n\s*(?:---|\*\*\*|___)\s*)+$", "", new)
    sources = ", ".join(f"{'/'.join(g)}={src}" for g, _, src in groups) or "-"
    return new, sources


def edited_pages(station_dir, om_file):
    data = json.loads((ROOT / "stations" / station_dir / om_file).read_text(encoding="utf-8"))
    return {m["Name"] for m in data["menus"] if m.get("LastUpdatedBy")}


def patch_file(path, changes):
    """Replaces whole field values in the raw file so untouched lines stay byte-identical."""
    raw = path.read_bytes().decode("utf-8")
    for old, new in changes:
        old_enc, new_enc = json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False)
        if raw.count(old_enc) != 1:
            return False
        raw = raw.replace(old_enc, new_enc)
    path.write_bytes(raw.encode("utf-8"))
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", action="append", help="station folder (repeatable); default: the four CMS stations")
    ap.add_argument("--page", action="append", help="limit to these PageIDs")
    ap.add_argument("--archive", default=str(cc.DEFAULT_ARCHIVE), help="JSON with the legacy ORZ records")
    ap.add_argument("--dump", metavar="FILE", help="write every changed Therapy of the first station")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    cc.ARCHIVE.update({m["Name"]: m for m in json.loads(Path(args.archive).read_text(encoding="utf-8"))["menus"]})

    stations = [s for s in cc.STATIONS if not args.station or s[0] in args.station]
    # Production stations were copied from the test station, so its Sveltia edits count for them too.
    test_edited = edited_pages(*cc.STATIONS[0][:2])
    dump = []
    for n, (station_dir, om_file, od_file) in enumerate(stations):
        paths = sorted((ROOT / "cms-data" / station_dir / "pages").glob("*/*.json"))
        pages = {p.data.get("PageID", p.path.stem): p for p in map(promote.Page.load, paths)}
        od = json.loads((ROOT / "stations" / station_dir / od_file).read_text(encoding="utf-8"))
        legacy = cc.Legacy(pages, {cleanup.normalize_comparable_id(m["Name"]) for m in od})
        edited = edited_pages(station_dir, om_file) | test_edited
        notes, changed, cleaned = [], 0, 0
        for pid, page in sorted(pages.items()):
            if args.page and pid not in args.page:
                continue
            original = {f: page.data[f] for f in ("Text", "Therapy") if page.data.get(f)}
            for field, value in original.items():
                page.data[field] = strip_obsolete(value)
            result = normalize(pid, page.data, legacy, pid in edited, notes)
            if result and result[0] != (page.data.get("Therapy") or "").strip("\n"):
                new, sources = result
                changed += 1
                old_labels = [l.strip() for l in split_glued(original["Therapy"]).split("\n") if LABEL_RE.match(l.strip())]
                new_labels = [l for l in new.split("\n") if LABEL_RE.match(l)]
                print(f"  {pid}{' [edited]' if pid in edited else ''}: {old_labels} -> {new_labels} ({sources})")
                if n == 0:
                    dump.append(f"################ {pid}  ({sources})\n{new}")
                page.data["Therapy"] = new
            edits = [(old, page.data[f]) for f, old in original.items() if page.data[f] != old]
            if not edits:
                continue
            cleaned += 1
            if args.apply and not patch_file(page.path, edits):
                notes.append(f"{pid}: could not patch the file (encoding differs); skipped")
        print(f"=== {station_dir}: {cleaned} page(s) {'changed' if args.apply else 'to change'} "
              f"({changed} with care-setting changes)")
        for note in notes:
            print(f"    NOTE {note}")
    if args.dump:
        Path(args.dump).write_text("\n\n".join(dump) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
