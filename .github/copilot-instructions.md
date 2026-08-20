Project description:

We have a VA page for Antimicrobial Stewardship guidance. It was built for the Minneapolis VA using VistA menu and order data to build out the repo, which then feeds a static GitHub Pages website where users access the guidance. This project is to take the Minneapolis guidance, make it scalable to new sites, and expose the contents to a CMS like Sveltia so that site SMEs can modify the guidance accordingly. This is the original Minneapolis site: https://antimicrobialcdss.github.io/MinneapolisCDSS.html

This is the site fed by our repo: [vhaantimicrobialstewardship.github.io](https://vhaantimicrobialstewardship.github.io/)

Current state:

* Sveltia CMS installed in /admin.
* File/folder structure reorganised — each station lives in its own folder under /stations/.
* Test station (001-TestStation) built from Minneapolis data and deployed at stations/001-TestStation/TestStationCDSS.html.
* The test station loads the full Minneapolis-derived guidance (1,118 menus) from TestStationOMJSON.json, plus 208 Combined menus (ORZC prefix) generated from two SME spreadsheet tabs (Mimi + Dr. Mehul).
* **Combined tab feature**: A fourth "Combined" tab sits beside Inpatient / Outpatient / ER-UC. Combined pages (ORZC menus) carry Inpt/Outpt/ERUC cross-reference fields so navigation between tabs works in both directions.
* Canonical combined guidance source: AntimicrobialStewardshipGuidanceCombined.xlsx (Mehul tab = Dr. Mehul's entries, Minneapolis_SideBySideGuida tab = Mimi's entries; Mehul takes precedence on overlap).
* Inpatient/Outpatient/ER content remains unchanged from Minneapolis.
* Service worker updated to use network-first for HTML files to avoid stale first-load pages (version 1.269).
* All 173 Combined menus that have navigable sub-links have had their markdown links restored by label-matching against inpatient LinkTargets (scripts/restore-combined-links.py).

Key JSON data files:
* stations/001-TestStation/TestStationOMJSON.json — master menu data (1,329 menus including ORZC combined pages). Rich-text format with Name, Term1, Term2, Text, LinkTargets, Outpt, ERUC, Combined, Inpt fields.
* stations/001-TestStation/TestStationODJSON.json — order data.
* AntimicrobialStewardshipGuidanceCombined.xlsx — source spreadsheet for combined guidance (both tabs).

Key scripts (in /scripts/):
* rebuild-combined-menus.py — rebuilds all ORZC menus from the spreadsheet (run after SMEs update the xlsx).
* restore-combined-links.py — restores markdown links in ORZC plain-text menus by matching against inpatient link targets (run after rebuild).
* fix-teststation-json.py — copies Outpt/ERUC cross-refs from Minneapolis and fixes escaped bracket links.
* audit-teststation.py — integrity audit: checks cross-ref validity, placeholder content, HTML wiring.
* fix-broken-outpt-refs.py — corrects legacy Outpt name mismatches.

Recommended workflow when SMEs add new combined guidance to the spreadsheet:
1. Run scripts/rebuild-combined-menus.py
2. Run scripts/restore-combined-links.py
3. Run scripts/audit-teststation.py (should show 0 issues)
4. git add / commit / push

Next steps:

* Subset the Sveltia CMS collections — the JSON files are too big to edit directly. Group pages by the same logical disease/syndrome categories used on the homepage.
* Apply the Combined tab feature to other real stations once the test station review is complete.
* Continue adding combined guidance content to AntimicrobialStewardshipGuidanceCombined.xlsx and re-running the rebuild/restore pipeline.
