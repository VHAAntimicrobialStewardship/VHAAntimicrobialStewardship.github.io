Project description:

We have a VA page for Antimicrobial Stewardship guidance. It was built for the Minneapolis VA using VistA menu and order data to build out the repo, which then feeds a static GitHub Pages website where users access the guidance. This project is to take the Minneapolis guidance, make it scalable to new sites, and expose the contents to a CMS like Sveltia so that site SMEs can modify the guidance accordingly. This is the original Minneapolis site: https://antimicrobialcdss.github.io/MinneapolisCDSS.html

This is the site fed by our repo: [vhaantimicrobialstewardship.github.io](https://vhaantimicrobialstewardship.github.io/)

Current state:

* Sveltia CMS installed in /admin. Collections are now station/disease-group scoped (one collection per disease group per station), with page-per-file JSON files in cms-data/001-TestStation/pages/<group>/. CMS config is at admin/config.yml. **CMS config schema rule**: each folder collection must have identifier_field, summary, and fields at the collection level (not nested under editor). editor only contains preview: false.
* File/folder structure: each station lives in its own folder under /stations/.
* Test station (001-TestStation) deployed at stations/001-TestStation/TestStationCDSS.html.
* TestStationOMJSON.json holds 1,329 menus total: original VistA inpatient/outpatient/ERUC menus plus 208 combined pages. Combined pages are identified by having an `Inpt` field pointer back to the source inpatient menu; their `Name` is a stable slug PageID (e.g. `bells-palsy`, `cns`).
* **Combined tab is now the default**: The site starts on the Combined tab and combined main menu (`main-menu`). The combined main menu ID is `main-menu` in TestStationOMJSON.json and in the HTML constant `combinedMenu`.
* **Combined tab feature**: A fourth "Combined" tab sits beside Inpatient / Outpatient / ER-UC. Combined pages carry Inpt/Outpt/ERUC cross-reference fields so navigation between tabs works in both directions. When Combined mode is active, link resolution prefers combined equivalents automatically (via Inpt/Outpt/ERUC crosswalk in `resolveTargetForCurrentVersion`).
* Canonical combined guidance source: AntimicrobialStewardshipGuidanceCombined.xlsx (Mehul tab = Dr. Mehul's entries, Minneapolis_SideBySideGuida tab = Mimi's entries; Mehul takes precedence on overlap).
* Service worker at version 1.270, using network-first for HTML files.

Key JSON data files:
* stations/001-TestStation/TestStationOMJSON.json — master menu data (1,329 menus). Rich-text format: Name, Term1, Term2, Text, LinkTargets, Outpt, ERUC, Combined, Inpt fields. Combined pages identified by presence of `Inpt` field.
* stations/001-TestStation/TestStationODJSON.json — order data (3,638 entries).
* AntimicrobialStewardshipGuidanceCombined.xlsx — source spreadsheet for combined guidance.
* stations/001-TestStation/TestStationOMJSON_VistA.json — backup of OMJSON before PageID migration.

Key scripts (in /scripts/):
* rebuild-combined-menus.py — rebuilds all combined menus from the spreadsheet; generates slug PageID Names (run after SMEs update the xlsx).
* restore-combined-links.py — restores markdown links in combined plain-text menus by label-matching against inpatient link targets (run after rebuild).
* audit-teststation.py — integrity audit: checks cross-ref validity, placeholder content. Currently: ISSUES 0, WARNINGS 308 (legacy unresolved link targets — non-blocking).
* migrate-pageids.py — one-time script used to migrate combined pages to immutable slug IDs.
* export-cms.py — exports combined pages from OMJSON into station/group/page CMS file tree and regenerates admin/config.yml.
* compile-cms.py — compiles CMS page files back into OMJSON.
* fix-teststation-json.py — copies Outpt/ERUC cross-refs from Minneapolis and fixes escaped bracket links.
* fix-broken-outpt-refs.py — corrects legacy Outpt name mismatches.

Runtime rendering (TestStationCDSS.html) — key design decisions:
* `resolveEmbeddedLinkTarget(selectedData, target, label)` — resolves markdown link targets using: (1) direct PageID lookup, (2) page LinkTargets by Item, (3) page LinkTargets by label text, (4) global normalized OM name match, (5) global normalized OD name match, (6) global label-text search across all LinkTargets.
* `resolveTargetForCurrentVersion(targetName)` — when Combined tab is active, remaps any inpatient/outpatient/ERUC target to its combined equivalent using Inpt/Outpt/ERUC crosswalk fields.
* `extractMarkdownLinks(lineText)` — balanced-bracket parser (handles nested `[R]` in link labels).
* `createCombinedMainMenuTable(selectedData)` — two-column renderer for the combined main menu page only.
* `createStructuredRichTextNavigationTable(selectedData)` — row-paired two-column renderer for navigation pages (≥4 `##` headings and ≥6 links/targets). Renders each entry (heading or link line) left/right paired, matching Minneapolis column structure. Used for pages like CNS.
* `createRichTextTable(selectedData)` — single-column renderer for guidance content pages.
* `isStructuredRichTextNavigationPage(selectedData)` — detects navigation pages by heading and link count.
* `handleRowClick` — resolves Item via `resolveTargetForCurrentVersion` before OM/OD lookup.
* `checkMatchesAndSetButtonAppearance` — sets Combined tab highlight when current page has a Combined cross-ref; sets other tab availability. Combined button is highlighted green when active.
* `currentVersion` — tracks active tab ('combined', 'inpt', 'outpt', 'eruc'). Default: 'combined'.

Recommended workflow when SMEs add new combined guidance to the spreadsheet:
1. Run scripts/rebuild-combined-menus.py
2. Run scripts/restore-combined-links.py
3. Run scripts/audit-teststation.py (should show 0 issues)
4. git add / commit / push

Recommended workflow when updating the CMS config (e.g. adding new disease groups):
1. Run scripts/export-cms.py (exports pages and regenerates admin/config.yml)
2. Verify admin/config.yml — ensure each folder collection has identifier_field, summary, fields at top level (not nested under editor)
3. git add / commit / push

Next steps:

* Continue reviewing and editing combined guidance pages via Sveltia CMS (admin/). CNS navigation structure is still being refined to match Minneapolis two-column layout.
* Continue adding combined guidance content to AntimicrobialStewardshipGuidanceCombined.xlsx and re-running the rebuild/restore pipeline.
* Apply the Combined tab feature to other real stations once the test station review is complete.
* Remaining 308 audit warnings are legacy unresolved link targets in combined page text — these point to VistA order IDs or OM menus not yet present in TestStation. Address by adding them to OMJSON or accepting as unresolvable.
