import glob
import os
import re

root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
updated = []

for path in glob.glob(os.path.join(root, 'stations', '*', '*CDSS.html')):
    station = os.path.basename(path).replace('CDSS.html', '')
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()
    original = content

    # file data references should be relative to station folder
    content = re.sub(r"const OMjson = 'stations/[^']+/[^']+';", f"const OMjson = '{station}OMJSON.json';", content)
    content = re.sub(r"const ODjson = 'stations/[^']+/[^']+';", f"const ODjson = '{station}ODJSON.json';", content)
    content = re.sub(r"const txmlFile = 'stations/[^']+/[^']+';", f"const txmlFile = '{station}.txml';", content)

    # root assets referenced from station page
    content = content.replace("const AbxLinkjson = 'AbxLinks.json';", "const AbxLinkjson = '../AbxLinks.json';")
    content = content.replace('<link rel="manifest" href="manifest.webmanifest">', '<link rel="manifest" href="../manifest.webmanifest">')
    content = content.replace('<link rel="icon" href="CDSSLogoApp.png" type="image/x-icon">', '<link rel="icon" href="../CDSSLogoApp.png" type="image/x-icon">')
    content = content.replace("url('Fonts/", "url('../Fonts/")
    content = content.replace("href='manifest.webmanifest'", "href='../manifest.webmanifest'")
    content = content.replace('href="manifest.webmanifest"', 'href="../manifest.webmanifest"')
    content = content.replace('href="CDSSLogoApp.png"', 'href="../CDSSLogoApp.png"')

    # fix common relative plugin paths if needed
    content = content.replace('href="../CDSSLogoApp.png" type="image/x-icon"', 'href="../CDSSLogoApp.png" type="image/x-icon"')

    if content != original:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(content)
        updated.append(path)

for p in updated:
    print('Updated', os.path.relpath(p, root))
print('Done: updated', len(updated), 'station HTML files.')
