import os
import re
import sys
from urllib.parse import unquote, urlparse

repo_root = os.path.abspath(os.path.dirname(__file__) + os.sep + '..')
pattern = re.compile(r'(?:href|src|action|URL)=["\']([^"\']+)["\']', re.IGNORECASE)

missing = {}
checked = 0

for dirpath, dirnames, filenames in os.walk(repo_root):
    # skip .git and node_modules
    if '.git' in dirpath or 'node_modules' in dirpath:
        continue
    for fn in filenames:
        if not fn.lower().endswith(('.html', '.htm', '.txml', '.json', '.md')):
            continue
        path = os.path.join(dirpath, fn)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                text = fh.read()
        except Exception as e:
            print(f"Could not read {path}: {e}")
            continue
        for m in pattern.finditer(text):
            checked += 1
            link = m.group(1).strip()
            if not link:
                continue
            # ignore mailto and tel and anchors and externals
            if link.startswith(('http://', 'https://', 'mailto:', 'tel:', 'view.officeapps.live.com', 'javascript:')):
                continue
            # strip query/fragment
            link = urlparse(link).path
            link = unquote(link)
            link = link.lstrip('/')
            target = os.path.join(repo_root, link)
            if not os.path.exists(target):
                missing.setdefault(link, set()).add(path)

report = os.path.join(repo_root, 'tools', 'check_links_report.txt')
with open(report, 'w', encoding='utf-8') as out:
    out.write(f'Checked {checked} links.\n')
    out.write(f'Missing local targets: {len(missing)}\n\n')
    for tgt, sources in sorted(missing.items()):
        out.write(f'{tgt}\n')
        for s in sorted(sources):
            out.write(f'  referenced-in: {os.path.relpath(s, repo_root)}\n')
        out.write('\n')

print(f'Checked {checked} links. Missing {len(missing)} local targets. Report: {report}')
if missing:
    print('Top missing targets:')
    for i, (t, s) in enumerate(missing.items()):
        print(f'{i+1}. {t} referenced in {len(s)} files')
        if i >= 9:
            break
sys.exit(0 if not missing else 2)
