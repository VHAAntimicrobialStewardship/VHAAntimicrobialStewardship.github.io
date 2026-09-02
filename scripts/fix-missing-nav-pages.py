#!/usr/bin/env python3
"""
Create missing combined pages from inpatient sources and fix broken nav page links.
Targets: pages referenced in nav pages that exist in inpatient but not combined.
"""
import json
import re
from pathlib import Path

OMJSON_PATH = 'stations/001-TestStation/TestStationOMJSON.json'

with open(OMJSON_PATH) as f:
    data = json.load(f)

menus = data['menus']
menu_dict = {m['Name']: m for m in menus}

# Identify nav pages: combined pages with markdown links (indicated by having Inpt)
# and 3+ markdown links in Text
markdown_link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'

print("Scanning for combined nav pages with missing child pages...")
nav_pages = []
for m in menus:
    if not m.get('Inpt'):
        continue
    links = re.findall(markdown_link_pattern, m.get('Text', ''))
    if len(links) >= 3:
        nav_pages.append(m)

print(f"Found {len(nav_pages)} combined nav pages")

# For each nav page, find missing inpatient child pages
missing_inpt = {}  # inpt_item_name => (slug_candidate, display_label)
nav_page_fixes = {}  # nav_page_name => [(plain_text_line, slug), ...]

for nav in nav_pages:
    inpt_name = nav['Inpt']
    inpt_nav = menu_dict.get(inpt_name)
    if not inpt_nav:
        continue
    
    # Get all link targets and their labels from inpatient nav
    inpt_targets = {}
    for lt in inpt_nav.get('LinkTargets', []):
        if 'Item' in lt and 'Text' in lt:
            inpt_targets[lt['Item']] = lt['Text']
    
    # Scan combined nav text for plain-text lines (unlinked)
    text_lines = nav['Text'].split('\n')
    nav_page_fixes[nav['Name']] = []
    
    for line in text_lines:
        line_stripped = line.strip()
        # Skip empty, headers, already linked, and special lines
        if not line_stripped or line_stripped.startswith('[') or line_stripped.startswith('#') or line_stripped.startswith('*'):
            continue
        
        # Find if this plain-text line matches an inpatient link target
        matching_inpt_item = None
        for inpt_item, label in inpt_targets.items():
            if label == line_stripped:
                matching_inpt_item = inpt_item
                break
        
        if not matching_inpt_item:
            continue
        
        # Check if already has a combined equivalent
        if any(m.get('Inpt') == matching_inpt_item for m in menus):
            # Already has combined page, skip
            continue
        
        # Find the inpatient page
        inpt_page = menu_dict.get(matching_inpt_item)
        if not inpt_page:
            continue
        
        # Generate slug
        slug = re.sub(r'[^\w\s-]', '', line_stripped).strip().lower()
        slug = re.sub(r'\s+', '-', slug)
        
        if not slug or slug in menu_dict:
            continue
        
        # Record this as needing a combined page
        if matching_inpt_item not in missing_inpt:
            missing_inpt[matching_inpt_item] = (slug, line_stripped)
        
        # Record the nav page fix
        nav_page_fixes[nav['Name']].append((line_stripped, slug))

print(f"Found {len(missing_inpt)} missing combined pages to create")

# Create combined pages
created = []
for inpt_name, (slug, label) in missing_inpt.items():
    if slug in menu_dict:
        continue
    
    inpt_page = menu_dict[inpt_name]
    combined_page = {
        'Name': slug,
        'Term1': label,
        'Term2': '',
        'Text': inpt_page.get('Text', ''),
        'LinkTargets': inpt_page.get('LinkTargets', []),
        'Inpt': inpt_name
    }
    if 'Outpt' in inpt_page:
        combined_page['Outpt'] = inpt_page['Outpt']
    if 'ERUC' in inpt_page:
        combined_page['ERUC'] = inpt_page['ERUC']
    
    menus.append(combined_page)
    menu_dict[slug] = combined_page
    created.append(f"{slug} <- {inpt_name}")

print(f"\nCreated {len(created)} combined pages:")
for c in sorted(created)[:15]:
    print(f"  {c}")
if len(created) > 15:
    print(f"  ... and {len(created) - 15} more")

# Update nav pages with new links
updated_navs = 0
updated_lines = 0

for nav in nav_pages:
    nav_name = nav['Name']
    if nav_name not in nav_page_fixes or not nav_page_fixes[nav_name]:
        continue
    
    fixes = {label: slug for label, slug in nav_page_fixes[nav_name]}
    text_lines = nav['Text'].split('\n')
    new_lines = []
    
    for line in text_lines:
        if line.strip() in fixes:
            new_lines.append(f"[{line.strip()}]({fixes[line.strip()]})")
            updated_lines += 1
        else:
            new_lines.append(line)
    
    nav['Text'] = '\n'.join(new_lines)
    updated_navs += 1

print(f"\nUpdated {updated_navs} navigation pages ({updated_lines} lines converted to links)")

# Save back
with open(OMJSON_PATH, 'w') as f:
    json.dump(data, f, indent=2)

print(f"\nSaved to {OMJSON_PATH}")
