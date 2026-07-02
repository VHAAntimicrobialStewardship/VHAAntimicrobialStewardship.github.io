from pathlib import Path

root = Path(__file__).resolve().parent.parent
stations = root / 'stations'
rename_map = {
    '437 - Fargo': '437-Fargo',
    '438 - SiouxFalls': '438-SiouxFalls',
    '442 - Cheyenne': '442-Cheyenne',
    '568 - BlackHills': '568-BlackHills',
    '618 - Minneapolis': '618-Minneapolis',
    '636 - Omaha': '636-Omaha',
    '636A6 - DesMoines': '636A6-DesMoines',
    '656 - StCloud': '656-StCloud',
}

replace_pairs = []
for old, new in rename_map.items():
    old_encoded = old.replace(' ', '%20')
    replace_pairs.append((f'stations/{old}/', f'stations/{new}/'))
    replace_pairs.append((f'stations/{old_encoded}/', f'stations/{new}/'))
    replace_pairs.append((f'/stations/{old}/', f'/stations/{new}/'))
    replace_pairs.append((f'/stations/{old_encoded}/', f'/stations/{new}/'))
    replace_pairs.append((f'stations/{old}', f'stations/{new}'))
    replace_pairs.append((f'stations/{old_encoded}', f'stations/{new}'))
    replace_pairs.append((f'/stations/{old}', f'/stations/{new}'))
    replace_pairs.append((f'/stations/{old_encoded}', f'/stations/{new}'))

replace_pairs.extend([
    ('href="../manifest.webmanifest"', 'href="/manifest.webmanifest"'),
    ("href='../manifest.webmanifest'", "href='/manifest.webmanifest'"),
    ('href="../CDSSLogoApp.png"', 'href="/CDSSLogoApp.png"'),
    ("href='../CDSSLogoApp.png'", "href='/CDSSLogoApp.png'"),
    ("url('../Fonts/", "url('/Fonts/"),
    ('url("../Fonts/', 'url("/Fonts/'),
    ('url(../Fonts/', 'url(/Fonts/'),
])

# Fix ItemLinkjson for Fargo only
replace_pairs.append(("const ItemLinkjson = 'stations/437 - Fargo/FargoItemLinks.json';", "const ItemLinkjson = 'stations/437-Fargo/FargoItemLinks.json';"))

# Rename station directories
print('Renaming station directories...')
for old, new in rename_map.items():
    old_dir = stations / old
    new_dir = stations / new
    if old_dir.exists() and not new_dir.exists():
        print(f'  {old_dir.name} -> {new_dir.name}')
        old_dir.rename(new_dir)
    elif old_dir.exists() and new_dir.exists():
        print(f'  Warning: target exists, skipping {new_dir.name}')
    else:
        print(f'  No directory to rename: {old_dir.name}')

# Update text files
updated_files = []
for path in root.rglob('*'):
    if not path.is_file():
        continue
    if path.suffix.lower() not in {'.html', '.js', '.md'}:
        continue
    text = path.read_text(encoding='utf-8')
    new_text = text
    for old, new in replace_pairs:
        new_text = new_text.replace(old, new)
    if new_text != text:
        path.write_text(new_text, encoding='utf-8')
        updated_files.append(path.relative_to(root))

print('Updated files:')
for f in updated_files:
    print('  ', f)
print('Done: updated', len(updated_files), 'files.')
