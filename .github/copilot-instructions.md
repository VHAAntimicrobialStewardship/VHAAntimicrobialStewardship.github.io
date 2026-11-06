Project purpose

This repository powers a VA Antimicrobial Stewardship static site with station-specific guidance, originally derived from Minneapolis VistA menu/order data and now evolving toward scalable multi-station and CMS-managed content.

Primary references:
- Minneapolis source site: https://antimicrobialcdss.github.io/MinneapolisCDSS.html
- Current site: https://vhaantimicrobialstewardship.github.io/

Project status and current increment

- MVP complete: the three production stations (Ann Arbor, Cincinnati, Cleveland) have been delivered and validated with customers. Treat the combined-guidance runtime/CMS/pipeline model as production-proven, not experimental.
- Current increment focus: scalability and usability. Prioritize feature work that:
	- Reduces manual/per-station effort to onboard additional stations (station scaffolding, config generation, repeatable pipelines).
	- Improves content-editor (SME) usability in the CMS (Sveltia) workflow — e.g. clearer field guidance, validation, preview fidelity.
	- Improves end-user (clinician) usability of the site itself — navigation, search, mobile/responsive behavior, accessibility.
	- Reduces script/pipeline friction (fewer manual steps, better error messages, safer re-runs) as more stations are added.
- New feature ideas should be evaluated against this increment's goals first; purely cosmetic or one-off station requests remain lower priority unless explicitly requested by the user.
- Completed (2026-10-30): the opt-in sidebar redesign (left menu tree + right therapy panel) is rolled out to the test station and the three production stations (506/539/541). Clean pages were overwritten from the test station; SME-edited pages were held back and split by hand in Sveltia. See invariant 11. Post-rollout cleanup (2026-10-30): the redundant osteom-empirical-therapy page and its index link were removed from all four stations, and the Therapy-rule breaks (References inside Therapy, level-1 first heading, empty Text on empirical-therapy) were fixed; audit-teststation.py reports 0 issues. Remaining follow-up: the production welcome page is still the test-station placeholder until each station's SME supplies text.
- Completed (2026-11-05): the markdown page renderer (marked + DOMPurify) and the converted Sveltia-style markdown data are live on the test station and the three production stations. See invariant 13. Remaining follow-up: convert the column pages, nav-like pages and flattened-table pages that the conversion skipped (lists in reports/markdown-migration-review-<station>.txt), and hand-fix the review-list items (removed `>` blockquote indentation, wraps left unjoined next to link lines, possible wrapped reference entries).
- Completed (2026-11-05): legacy record cleanup. The 1,121 legacy VistA records (Name starting ORZ: ORZID2 = inpatient, ORZID3 = outpatient, ORZID = ER/UC) were removed from the four CMS stations' OMJSON (records per station 1711/1711/1711/1712 -> 628 each) and archived in docs/legacy-archive/001-TestStation-legacy-records.json (identical copies in 506/539/541, see the note in the file). Before deletion, 38 pages were promoted to cms-data (interim blood culture set, approach to bacteremia, suspected bacteremia, immunizations by age/diabetes/HIV/pregnancy, nPEP sub-pages, rabies PEP, PD dosing pages, bone marrow Seattle/Nashville, C. diff 2-step testing, urine culture, Vibrio non-cholerae, prostate biopsy, respiratory papillomatosis, photodynamic HSV-1 prophylaxis; Cleveland has no photodynamic page because its parent was deleted by SMEs), 9 combined pages whose Text had been lost were restored from their legacy source, the six journal reference pages were merged into journal-references, bacteremia became a nav page, and the 8 pages that only existed in OMJSON got cms-data files. Every link that depended on a legacy record was repointed to a PageID. The rest (215 records) were approved as obsolete (reports/legacy-obsolete-accepted.json). Scripts: scripts/cleanup-legacy-records.py (analysis/deletion), scripts/promote-legacy-pages.py (one-off, applied). Remaining follow-up: Cleveland still has 7 SME-deleted pages in its OMJSON because compile-cms.py never deletes records (to be handled when compile-cms.py is revisited).
- Completed (2026-11-05): care-setting consolidation. 17 pages per station where the inpatient/outpatient/ER-UC variants had been pasted together (ER block after References, jumbled Therapy, "PENDING CARE SETTING CONSOLIDATION" / "NEED SME REVIEW" placeholders) now have one narrative in Text and a Therapy panel split into `## Inpatient` / `## Outpatient` / `## ER/UC` sections (settings with identical guidance share one slash-joined heading, e.g. `## Inpatient/Outpatient` followed by a separate `## ER/UC` when ER/UC differs; no setting headings at all when every setting is the same; subsection headings are `###`). New pages with care-setting differences, including wave 2 pages, follow the same convention. sepsis-and-shock has no Therapy panel (no drug recommendations) and now carries the source-infection link list; sepsis-protocol-antimicrobials was deleted. copd-exacerbation (inpatient) and exacerbation-of-copd (outpatient) were merged into copd-exacerbation (Outpt pointer ORZID3 GMENU ABX COPD EXACERBATION; the lung-and-mediastinum link and the menu tree were repointed). Script: scripts/consolidate-care-settings.py (applied; reusable for wave 2, see "Wave 2 station onboarding"). 2026-11-06: one-to-one setting labels were renamed in Therapy on all four stations (`## ER` / `## ER Guidance` -> `## ER/UC`, `## Outpatient Guidance` -> `## Outpatient`, typo `## Inpatient/##Outpatient` -> `## Inpatient/Outpatient`); combined labels such as `## Inpatient/Outpatient` are intentional and kept. Care-setting rule (user, 2026-11-06): a page with one set of therapy recommendations has no setting label at all; when recommendations differ by setting, every set gets a label, Inpatient first, sub-headings `###`; a short shared preamble may sit above the labels. Applied to the 14 survey pages (necrot-infect-direct-therapy and ssti-purulent-infections had their ER/UC section rebuilt from the archived ER/UC record because the pasted copy had lost lines; endoscopic-ultrasound-fna-procedures' identical Inpatient/Outpatient blocks were collapsed). Remaining: about 60 more pages per station do not follow the rule yet (an unlabeled inpatient block before a lone label, a lone label on a single-recommendation page, identical sections, Outpatient before Inpatient, near-empty sections, setting labels glued to prose in Text, `##` sub-headings under setting labels). 2026-11-06 (later): applied to those pages with scripts/normalize-care-settings.py (79 Therapy panels per station: labels, Inpatient first, identical sections joined, empty or refer-to-inpatient-only sections dropped, lossy pasted Outpatient/ER copies rebuilt from the archive on pages never edited in Sveltia) and a one-off Text pass on 21 pages (all-settings labels such as `## Inpatient/Outpatient/ER` removed with their glued prose kept, refer-to-inpatient-only Text sections removed). 2026-11-06 (final pass, user decisions): no guidance below References (References always last in Text); the pasted outpatient/ER copies after References on 19 pages (osteom-with-*, bite-wnds-*, pd-*, surg-gentamicin, antiviral-immunosuppressive-malignancy, cap-outpatient-treated-setting, prev-*, splenectomy-chart, more-about-cellulitis, postseptal-cellulitis, mild-to-moderate-sinusitis, otitis-externa) were moved: treatment into Therapy under setting labels, narrative into Text (inpatient lines lost in the paste were restored from the archive on osteom-with-streptococci, bite-wnds-streptococci, surg-gentamicin-weight-based-dosing). "Refer to (the) Inpatient ... CDSS" lines and "Non-VA order for above" lines were removed everywhere, and the placeholder page refer-to-inpatient-cdss was deleted (its 174 outpatient-index links repointed to the real pages). Frequency wording is NOT a synonym: q8h (inpatient standard) vs TID (outpatient standard) sections stay separate unless SMEs decide to merge them. Remaining SME review: 16 Sveltia-edited pages per station whose outpatient/ER-UC sections are lossy pasted copies (normalize-care-settings.py prints them as NOTE lines); Cincinnati septic-bursitis keeps its local "Refer to Inpatient guidance above" (points to the same page).
- Next increment step: wave 2 station onboarding.
- This status note should be revisited/updated as the increment progresses or a new increment begins — ask the user before assuming it is still current if there is a large time gap since the note was last updated (last updated 2026-11-05).

Station roles (do not conflate these)

- Production stations — stations/506-AnnArbor/, stations/539-Cincinnati/, stations/541-Cleveland/: live stations where real SME-driven content changes are expected and should be made freely per station request.
- Test station — stations/001-TestStation/: for testing runtime/CMS/pipeline changes before they reach production stations. Safe to modify experimentally.
- Original CDSS (reference only) — stations/000-OriginalCDSS/ (OriginalCDSS.html, OriginalOMJSON.json, OriginalODJSON.json, Original.txml): the original Minneapolis source-of-truth classic site, moved from stations/618-Minneapolis/ on 2026-11-06 and labeled "Original CDSS". Kept only to check new work against. Do not make changes here (including incidental/cosmetic ones like footer buttons) unless the user explicitly asks. Its records keep `Version: "Minneapolis"` as provenance. Wherever this file says "the Minneapolis reference page", it means this page.
- Wave 2 stations (being onboarded) — 618-Minneapolis (folder now free for the new CMS station), 636-Omaha, 636A6-DesMoines, 656-StCloud. Their old classic pages and data were moved to stations/<id>/legacy/ (e.g. stations/636-Omaha/legacy/OmahaCDSS.html, titled "(legacy)") so the new station files cannot overwrite them; the legacy pages still open and are the source of local wording. Do not edit the legacy files. Minneapolis' legacy source is 000-OriginalCDSS.
- All other station folders (437-Fargo, 438-SiouxFalls, 442-Cheyenne, 568-BlackHills) are obsolete: do not touch, build features for, or treat as in-scope for changes unless the user explicitly says otherwise. Their hidden station-switcher buttons still name the old wave 2 paths and were deliberately left alone.

When a request says "all stations" or is otherwise ambiguous about scope, ask which of the above groups it applies to rather than assuming the Original CDSS, wave 2 legacy pages or the obsolete stations are included.

Stability-first operating rule

When making any change, preserve behavior across three coupled systems:
1. Runtime navigation and rendering in shared/cdss-app.js (loaded by the test station AND the three production stations; each station HTML only holds its configuration block)
2. CMS schema and content files (admin/config.yml and cms-data/)
3. OMJSON compile/export pipelines in scripts/

If a change fixes one area but regresses another, the change is incomplete.

Critical files and ownership

- Runtime UI behavior (all stations): shared/cdss-app.js. Any edit here reaches production stations (506/539/541) on push to main; smoke-test a production station after changes.
- Optional sidebar layout (opt-in per station page): shared/cdss-sidebar.js and shared/cdss-sidebar.css
- Markdown page renderer (opt-in per station page): shared/cdss-markdown.js and shared/cdss-markdown.css, with vendored libraries in shared/vendor/ (marked.umd.js, purify.min.js)
- Station configuration and entry page: stations/001-TestStation/TestStationCDSS.html (and the equivalent HTML in each production station)
- Design reference: docs/CDSS_wire_10092026.pdf (sidebar wireframe). docs/ is deliberately outside station folders, cms-data/ and assets/uploads/ so Sveltia does not see it; keep non-site documents there.
- Legacy record archive: docs/legacy-archive/001-TestStation-legacy-records.json (the removed ORZ records in converted Name/Text form; read by scripts/restore-from-legacy.py and, as the default `--archive`, by scripts/consolidate-care-settings.py). The raw stations/000-OriginalCDSS/OriginalOMJSON.json uses a different record shape (Contents/DisplayText) and cannot replace it.
- Master menu/order data: stations/001-TestStation/TestStationOMJSON.json and stations/001-TestStation/TestStationODJSON.json
- CMS config and schema: admin/config.yml
- CMS page content source: cms-data/001-TestStation/pages/<group>/<pageid>.json
- Abx link registry source: cms-data/abx-links.cms.json
- Runtime Abx link lookup: AbxLinks.json
- Combined guidance spreadsheet source: AntimicrobialStewardshipGuidanceCombined.xlsx

Non-negotiable invariants (do not break)

1) Combined tab default and entry page
- Combined is default mode at startup.
- currentVersion defaults to combined.
- combinedMenu constant is main-menu.
- Initial dropdown selection in combined mode lands on main-menu (or documented fallback if unavailable).

2) Combined-only future direction
- The site is transitioning to combined guidance as the exclusive navigation surface.
- Inpatient (inpt), outpatient (outpt), and ER/UC (eruc) tabs will eventually be removed; do not add new features or dependencies on them.
- All new page development is in the combined model with stable PageID slugs and Inpt source pointers.
- When editing runtime or CMS, assume the long-term target is combined-only; any cross-tab or legacy tab code is transitional.

3) Combined pages and the removed legacy records
- The four CMS stations are combined-only in data: their OMJSON holds no legacy ORZ records (removed 2026-11-05). Never re-add ORZ records; audit-teststation.py reports any that reappear, and any link to a removed legacy page (orzid/orzid2/orzid3-gmenu-... target), as an issue.
- Combined pages are identified by the presence of Inpt. Inpt (and the optional Outpt/ERUC) are kept as plain strings naming the archived legacy record; they no longer point at an OMJSON record and are not checked as references. Keep Inpt on every combined page and on new pages (for pages created from scratch, name the legacy record they replace, or the page's own source).
- No record has a Combined field any more; getVisibleOmData() therefore hides nothing, which is correct.
- handleRowClick must still resolve requested Item through resolveTargetForCurrentVersion before OM/OD lookup. Its reverse Inpt/Outpt/ERUC lookup maps a legacy name to its combined page if one is ever passed in; it is harmless to keep.
- Old URL hashes naming a legacy record (#ORZID2 GMENU ...) fall back to the welcome page.
- The legacy tab constants in station HTML (MainMenu, outptMenu, erucMenu, outptIndex) name records that no longer exist; no CMS station shows the Inpatient/Outpatient/ER-UC/Combined tab buttons (test station buttons removed 2026-11-05), so those code paths are unreachable there. Do not add features that depend on them.

4) Embedded link resolution: markdown-only
- resolveEmbeddedLinkTarget uses a three-tier fallback for active workflows:
	1. Direct PageID lookup (combined page IDs)
	2. Global normalized OM name match
	3. Global normalized OD name match
- LinkTargets metadata is legacy and no longer used in active link resolution; do not add new LinkTargets dependencies in runtime or CMS.
- Markdown links in Text are the canonical internal-link source; all new links are added as [label](page-id) in Text field.
- extractMarkdownLinks must keep balanced-bracket handling for labels with nested bracket text.
- Do not attempt to resolve links via LinkTargets fallback or metadata lookup in new code.

5) Layout mode detection and rendering
- createCombinedMainMenuTable is dedicated to combined main menu rendering.
- createStructuredRichTextNavigationTable remains row-paired multi-column navigation rendering for heading/link-heavy nav pages.
- isStructuredRichTextNavigationPage detection thresholds are part of functional behavior (navigation pages vs guidance pages) and should not be casually changed.
- createRichTextTable / buildRichTextTable is the single-column guidance renderer. On stations with `var Renderer = 'markdown'` (all four CMS stations) it delegates to buildMarkdownTable (shared/cdss-markdown.js); the line-per-row code path is only used when the station does not opt in or the URL has `?renderer=classic`. The line-based helpers (parseRichTextLineSyntax, appendRichTextLineContent, stripBlankLinesAroundTightLines) are still needed by the column-delimiter pages and the main menu.
- Column delimiter compatibility must preserve both modern and legacy markers:
	- <!-- COLUMN 2 -->, <!-- COLUMN 3 -->, ...
	- <!-- RIGHT COLUMN --> (backward compatibility)
- Sidebar menu tree: a page is a navigation page when it has at least 2 pure link lines and link lines are at least half of its non-heading lines (isNavPage in shared/cdss-sidebar.js). Only nav pages reachable from main-menu expand in the tree, so a new page appears in the tree only when a nav page on that path links to it (example: bacteremia was rebuilt as a nav page and linked from system-infectious-diseases). Pages linked only from guidance pages (e.g. recommended-immunizations, which is not nav-like) are reachable by link and search but not in the tree.
- With the legacy records gone, the line-per-row (classic) renderer and legacy tab displays have no legacy pages left to show on the CMS stations.

6) Abx links behavior
- Drug links are injected in two paths:
	- legacy row-based path for older tab displays
	- combined markdown text path via appendTextWithAbxLinks
- Markdown renderer path: decorate() in shared/cdss-markdown.js injects drug links on text nodes through the same appendPlainTextWithAbxLinks (skipping links and code), combined mode only.
- Matching remains case-insensitive and word-boundary based.
- RouteFilter exists in data but is not currently enforced as a runtime filter.

7) CMS schema shape requirements
- For folder collections in admin/config.yml:
	- identifier_field, summary, and fields must be at collection level
	- editor should only contain preview: false
- Do not move collection fields under editor.
- Keep station/group-scoped collection structure aligned to cms-data/001-TestStation/pages/<group>/.

8) Combined main menu identity
- Combined main menu ID is main-menu. It is the only menu audit-teststation.py requires; the legacy tab main menus (ORZID2 GMENU ABX INPT MAIN, ORZID3 GMENU ABX OUTPT MAIN, ORZID GMENU ER/UC EMERGENCY DEPARTMENT MAIN MENU) were removed with the other legacy records.
- Some scripts support legacy fallback inpt-main for compatibility; leave that fallback in place (it is harmless and some older data used it).

9) LinkTargets deprecated: markdown-only link management
- LinkTargets field is removed from active CMS workflows (export-cms.py does not write LinkTargets to exported page JSON).
- LinkTargets may still exist in historical OMJSON records but are not authoritative for future edits.
- For active workflows, treat markdown targets in Text as canonical.
- Do not add new LinkTargets dependencies in runtime, CMS schema, or export pipeline logic.
- When updating links or pages, always use markdown format in Text field, never rely on LinkTargets metadata.

10) Service worker and cache behavior
- Service worker strategy is network-first for HTML.
- Any caching rule changes must include explicit version bump and regression check for content freshness.
- .js and .css are network-first along with HTML so a page and its shared scripts/styles stay in sync. New shared assets (e.g. cdss-sidebar.js/.css) must be added to the precache list in service-worker.js together with a VERSION bump (currently 1.276).

11) Sidebar layout (opt-in per station page; live on the test station and the three production stations)
- Opt-in mechanism: a station page enables the layout by setting `var Layout = 'sidebar'` (and optionally `var WelcomePage = '<pageid>'`) in its configuration block and loading /shared/cdss-sidebar.css and /shared/cdss-sidebar.js before /shared/cdss-app.js. The test station and the 506/539/541 production station pages do this; the Minneapolis reference page and obsolete stations stay classic. `?layout=classic` on the URL restores the original layout for that visit.
- shared/cdss-sidebar.js sets `window.CDSSSidebar.enabled`; shared/cdss-app.js reads it into `SIDEBAR_LAYOUT`. All sidebar behavior in cdss-app.js (hooks such as beforeRender, afterRender, syncUrl, onDataReady) is behind `SIDEBAR_LAYOUT`; stations without the flag must behave exactly as before, so never remove that gating or let sidebar code run unconditionally.
- Production rollout (done 2026-10-30) used scripts/rollout-diff.py, a one-time three-way classification against the fork commit b9498ed8 (the commit that copied the test station into the production stations). Pages unchanged by SMEs since the fork were overwritten from the test station (`--apply-a`); SME-edited pages were held and split by hand. The script's FORK_COMMIT is fixed, so re-running it now only reports test-vs-production drift. Before any future bulk copy from the test station to a production station, classify first and never overwrite SME-edited pages. Onboarding a new station: copy a production station's cms-data, add its HTML (Layout/WelcomePage variables and the sidebar css/js tags), add its collection (including the Therapy field) to admin/config.yml, and add it to the STATIONS lists in compile-cms.py and audit-teststation.py. split-therapy.py and export-cms.py remain hard-wired to 001-TestStation; export-cms.py regenerates admin/config.yml, so check that the production collections still have their Therapy field before committing if it is ever run.
- The menu tree is derived at runtime from main-menu plus nav-like pages (no separate menu data). Nav pages are detected by link-line ratio; bold-only lines act as sub-headings.
- Optional per-page `Therapy` field (markdown, CMS label "Therapy Panel", present in all four station collections in admin/config.yml) renders in the right-hand therapy panel; the panel is absent when the field is empty. Data flow: cms-data page JSON `Therapy` -> compile-cms.py writes it to the OMJSON record -> runtime renders it in the panel. export-cms.py writes it back out only when present and emits the field definition into admin/config.yml (edit the generator, not just config.yml, or the next export loses it); audit-teststation.py checks markdown links in both Text and Therapy.
- Therapy markdown must not start with a level-1 heading (`# ` becomes a page banner); therapy headings start at `##`. Keep Therapy free of References; References always stay in Text.
- The classic layout (`?layout=classic`, no sidebar) is no longer maintained: the sidebar is the way forward. The Therapy-merge fallback (`withTherapyInText`) remains only so content is never hidden when the sidebar is off.
- scripts/split-therapy.py (test station only, already applied; do not re-run) bulk-moved therapy sections from Text into Therapy. It refused splits that would put a References line in Therapy.
- The welcome page (PageID `welcome`) is a standalone page kept by export-cms.py (STANDALONE_PAGES). Production stations carry the placeholder welcome page until their SMEs supply text.

12) Last-updated line (all four CMS stations)
- compile-cms.py derives per-page metadata from git history of cms-data/<station>/pages and writes it onto OMJSON records: `LastUpdatedBy` + `LastUpdated` (newest Sveltia commit, matched by the default subject `Update|Create <station> “group/page”`) or, when a page was never edited in Sveltia, `InitialLoaded` (oldest commit touching the file, renames followed). `main-menu`/`inpt-main` are skipped. In a shallow clone or without git the existing values are kept, so CI checkout in compile-cms.yml must stay `fetch-depth: 0`.
- shared/cdss-app.js (`withLastUpdatedInText`) inserts an italic "Last updated by X on DATE" / "No local edits found. Initial page loaded on DATE" line above the trailing separator/References block of a page's Text (findContentEnd treats `---`, `***`, `___` and the older `# ____` lines as the separator; the stamp is italic markdown). It is data-gated (records without these fields render unchanged), skips column-delimited navigation pages and the main menu. These fields are not CMS fields and are never written to cms-data page JSON.
- admin/config.yml station collection summaries show `{{commit_author}}, {{commit_date}}` in the Sveltia entry list. The summary and view_groups in config.yml are hand-edited and no longer match export-cms.py's generator; do not run export-cms.py without diffing config.yml first.

13) Markdown renderer (live on the test station and the three production stations since 2026-11-05)
- Guidance page Text and Therapy are rendered with standard markdown (marked + DOMPurify, the libraries Sveltia previews with) so the Sveltia editor and the site agree. Column-delimiter pages, nav-like pages, flattened-table pages and the main menu were NOT converted and still use the line-based renderers (see the review lists).
- Opt-in: station page sets `var Renderer = 'markdown'` and loads /shared/cdss-markdown.css and, before cdss-app.js, /shared/vendor/marked.umd.js, /shared/vendor/purify.min.js and /shared/cdss-markdown.js. `?renderer=classic` restores the old renderer for that visit (a debugging aid, not maintained). cdss-app.js `buildRichTextTable` delegates to `buildMarkdownTable` only when `MARKDOWN_RENDERER` is set. A new station needs the same variable, css link and script tags.
- Config lives in shared/cdss-markdown.js (also required by scripts/render-check.js, which therefore sees exactly what the browser renders): `breaks:true` (Sveltia shows a single newline as a line break), raw HTML is never parsed (literal `<AND>`/`<OR>` stay text), internal links are emitted as data-cdss-target and wired up by `decorate()` using the existing resolveEmbeddedLinkTarget/handleRowClick/Abx logic, a table saved without a header row (Sveltia writes bare pipe rows) gets a synthetic empty header that is removed after parsing, and the leading `# Title` is shown as the blue banner row. Vendored library copies come from scripts/node_modules (`npm install` in scripts/, then copy marked/lib/marked.umd.js and dompurify/dist/purify.min.js to shared/vendor/); bump the service worker VERSION when they change.
- Data conventions (what Sveltia writes and the converter produces): blank line between paragraphs, wrapped prose joined into one line, a single newline is a deliberate line break (stacked lines such as `Preferred:` then a link or `< OR >`), `---` for separators (Sveltia saves rules as `***`), References as a bullet list after the separator, no `>` blockquote markers (VistA `>>` indentation was removed), GFM tables with at most one divider row. Never put a divider row after every table row; Sveltia then marks every row as a shaded header.
- Converting more pages (a new station, or the skipped pages once hand-prepared): scripts/classify-lines.py (report), then scripts/convert-markdown.py (dry run by default, `--station`, `--apply`, `--show <PageID>`). It verifies words and link targets are unchanged, skips column/nav/flattened pages and main-menu, and writes reports/markdown-migration-review.txt (copy it per station). Then compile-cms.py, audit-teststation.py, `node scripts/render-check.js` (hard errors must stay confined to skipped pages), `node scripts/nav-snapshot.js` (menu tree must match reports/nav-model-baseline.json; refresh with `--write` only when a change is accepted). Joining wrapped lines changes the sidebar's link-line ratio, which can turn a guidance page into a nav page. Convert each station from its own data, never copy pages between stations.
- Commit data conversions with a plain subject, not `Update|Create <station> “…”`, so Last-updated attribution is untouched.
Script workflows to protect

Combined guidance rebuild flow (spreadsheet-driven) — retired 2026-11-05
- scripts/rebuild-combined-menus.py rebuilt combined pages from the legacy inpatient menus in the OMJSON. Those records are gone (and a rebuild would overwrite CMS edits), so do not run it.

CMS export/compile flow
1. python scripts/export-cms.py
2. Review admin/config.yml schema shape and collection metadata
3. Edit content in CMS if needed
4. python scripts/compile-cms.py
5. python scripts/audit-teststation.py

Markdown conversion flow (see invariant 13)
1. python scripts/convert-markdown.py --station <station> (dry run; review the output and reports/markdown-migration-review.txt)
2. python scripts/convert-markdown.py --station <station> --apply
3. python scripts/compile-cms.py
4. python scripts/audit-teststation.py
5. node scripts/render-check.js and node scripts/nav-snapshot.js
6. Verify in the browser (sidebar layout): a guidance page, its Therapy panel, an internal link, Abx links, a page with a table

Wave 2 station onboarding
- Decide the starting point first and confirm it with the user:
	- From a copy of a production station's cms-data (invariant 11 onboarding steps): the data is already markdown, legacy-free and care-setting merged; only registration and validation are needed.
	- From the station's own legacy-derived data (combined pages with pasted inpatient/outpatient/ER-UC variants, ORZ records in OMJSON): run the chain below per station, from that station's own data.
- Registration (both cases): station HTML (Layout/WelcomePage/Renderer variables, sidebar and markdown css/js tags), admin/config.yml collection with the Therapy field, and the station lists in compile-cms.py (STATIONS and GIT_META_STATIONS), audit-teststation.py, cleanup-legacy-records.py, promote-legacy-pages.py (consolidate-care-settings.py uses it as its default list), scripts/render-check.js and scripts/nav-snapshot.js.
- Chain, in the order used for the first stations (each step: dry run, review, `--apply`, compile-cms.py, audit-teststation.py):
	1. Markdown conversion flow (above). consolidate-care-settings.py expects converted pages (`---` separator, References bullets, `##` headings).
	2. Legacy cleanup: `python scripts/cleanup-legacy-records.py --station <station>` (dry run; review reports/legacy-cleanup-orphans-<station>.txt and the accepted-obsolete list reports/legacy-obsolete-accepted.json). Before deleting legacy records, keep them: consolidate-care-settings.py rebuilds ER/UC and outpatient sections from them. If the station's legacy text equals Minneapolis', the existing docs/legacy-archive file is enough; otherwise archive the station's own records in the same {"menus": [...]} shape. promote-legacy-pages.py holds the promotion/restore/repoint tables keyed on Minneapolis legacy names; review them against the station before adding it to its STATIONS list.
	3. Care-setting merge: `python scripts/consolidate-care-settings.py --station <station> --survey` lists pages that still have pasted variants (PENDING/NEED SME REVIEW markers, ER blocks, INPATIENT:/OUTPATIENT: blocks). Then a dry run with `--dump FILE` (add `--archive FILE` for a station-specific archive) and read every generated page. `PROBLEM: <page>: page missing` only means the station lacks that page. Pages found by the survey but not in the script's tables (SEPSIS_ER, REBUILD, REBUILD_THERAPY, fix_mismerged, merge_copd) need a new table entry or rule, following the target shape: one narrative in Text; Therapy `## Inpatient` / `## Outpatient` / `## ER/UC` (identical sections merged under one slash-joined heading such as `## Inpatient/Outpatient`, sub-headings `###`, no References); SME-edited inpatient content kept, ER/UC rebuilt from the archived ORZID record rather than the lossy pasted copy. `--apply` also deletes DELETE_PAGES and removed pointer fields from cms-data and OMJSON, because compile-cms.py never deletes.
	4. Validation: compile-cms.py twice (second run byte-identical), audit-teststation.py (0 issues, warnings not increased), `node scripts/render-check.js --station <station>`, `node scripts/nav-snapshot.js` (`--write` after the new station's tree is reviewed), `python scripts/cleanup-legacy-records.py --station <station>` (legacy 0, dependent 0), browser smoke test.
- Order-dialog links: production ODJSONs lack the Non-VA (pshzid) order dialogs that the test station has; consolidate-care-settings.py drops generated "Non-VA order for above" lines whose dialog the station does not have.
- Commit data changes with a plain subject (invariant 12), recompile after committing and confirm `git status` is clean.

Repository hygiene
- Python bytecode (__pycache__/, *.pyc) is git-ignored; do not commit it. Node tooling lives in scripts/package.json; node_modules/ is git-ignored (commit package-lock.json).
- The repo lives under OneDrive; git's automatic gc can prompt about failing to delete .git/objects/XX folders. Answer n (or run git with `-c gc.auto=0`) and never leave a prompt waiting in an agent terminal.
- CI recompiles OMJSON on CMS edits ("chore: compile CMS edits into station OMJSON files" commits), so `git pull --rebase --autostash` before pushing.

Deprecated scripts (do not use in normal workflows)

The following scripts were one-off migration/cleanup utilities and should not be part of routine operations:
- scripts/restore-combined-links.py — reconstructed markdown links from LinkTargets metadata; use direct markdown editing in CMS instead.
- scripts/rewrite-links-to-combined.py — rewrote legacy link targets to combined equivalents; do not re-run without review.
- scripts/cleanup-combined-pageids.py — removed/consolidated combined page IDs; already applied to data.
- scripts/strip-order-links.py — removed VistA order-dialog links; use only if importing new legacy-format content.
- scripts/fix-broken-outpt-refs.py, scripts/fix-missing-nav-pages.py, scripts/fix-combined-link-headings.py — legacy one-off fixes; do not rely on these.
- scripts/migrate-pageids.py, scripts/review-skipped-variants.py — temporary migration helpers; not for routine use.
- scripts/fix-hardwrap-blank-lines.py, scripts/fix-extra-linebreaks.py — earlier line-break cleanups, superseded by scripts/convert-markdown.py; scripts/split-therapy.py — applied once to the test station.
- scripts/rebuild-combined-menus.py, scripts/report-legacy-without-combined.py — need the legacy records, which were removed on 2026-11-05.
- scripts/promote-legacy-pages.py — the 2026-11 legacy cleanup promotion; applied once to the four CMS stations. Kept as the record of what was promoted, restored and repointed. It reads legacy records from OMJSON, so it only runs for a station that still has them (wave 2, see above).
- scripts/restore-from-legacy.py — one-off repair of combined pages from their legacy text; now reads docs/legacy-archive/001-TestStation-legacy-records.json. Dry run before any use.

If a new cleanup pass is needed, implement a fresh script based on current markdown-only link rules and validate with audit-teststation.py.

Expected script behavior assumptions

- export-cms.py regenerates admin/config.yml and page-per-file JSON exports without LinkTargets.
- export-cms.py expects combined main menu at main-menu, with fallback inpt-main.
- export-cms.py classifies and emits combined CMS pages based on combined page markdown ancestry, not LinkTargets metadata.
- compile-cms.py compiles CMS page files back into OMJSON and preserves main-menu handling, including the optional Therapy field.
- compile-cms.py runs for all four CMS stations; stations whose cms-data did not change must come out byte-identical (check `git status` for unintended station changes).
- compile-cms.py only updates or adds records and fields; it never deletes a record and never removes Outpt/ERUC from a record (only Inpt and Therapy are dropped when the CMS page lacks them). Removing a record or a stale pointer is a direct OMJSON edit, and it stays removed because compile-cms.py has nothing to recreate it from.
- audit-teststation.py is the integrity gate and should be run after structural/data rewrites. It requires only main-menu, treats records with Inpt as combined pages, reports any remaining ORZ legacy record or Combined back-reference and any link to a removed legacy page as issues, and no longer checks Inpt/Outpt/ERUC as page references.
- scripts/cleanup-legacy-records.py (dry run by default) re-checks that no legacy record is left and that no link resolves through one (writes reports/legacy-cleanup-<station>.json); after the cleanup it should report legacy 0.
- scripts/consolidate-care-settings.py (dry run by default; `--survey`, `--station`, `--archive`, `--dump`, `--apply`) is idempotent: pages already in the target shape are skipped, so a re-run over the four CMS stations reports 0 pages changed.
- scripts/normalize-care-settings.py (dry run by default; `--station`, `--page`, `--archive`, `--dump`, `--apply`) applies the care-setting label rule to every Therapy panel with setting labels, and on every page's Text and Therapy removes "Refer to (the) Inpatient ... CDSS" lines (with the connector or heading they leave empty) and "Non-VA order for above" text. Sections are joined only when their words are identical (q8h vs TID is a deliberate difference). It never adds a setting the page has no section for, never rebuilds pages edited in Sveltia (on the station or on the test station), and a re-run reports 0 pages. Use it for wave 2 after local wording is applied.
- Order dialogs (VistA orders) are transitional and may be de-emphasized or removed entirely in non-VistA EHR contexts; do not build new features that depend on them.
- Tab-specific navigation (inpt/outpt/eruc) is transitional; all long-term development should assume combined-only model.

Change protocol for coding agents

Before edits
1. Identify whether the change affects runtime rendering, CMS schema, script pipelines, or more than one.
2. If more than one area is affected, plan cross-file updates up front.

During edits
1. Keep changes minimal and local.
2. Avoid changing function names or data field names used by scripts/runtime unless all call sites are updated.
3. Preserve backward compatibility paths unless intentionally deprecating with validation.

After edits (required checks)
1. Run targeted script checks for changed areas:
	 - python scripts/audit-teststation.py
	 - python scripts/export-cms.py if CMS grouping/config paths changed
	 - python scripts/compile-cms.py if CMS page schema/content mapping changed
2. Verify runtime behaviors manually in TestStation page:
	 - loads in combined tab by default
	 - combined main menu renders as intended
	 - structured navigation pages still render multi-column
	 - guidance pages remain single-column
	 - embedded links resolve and navigate correctly
	 - search shows no ORZ duplicates
	 - Abx links still render
3. If shared/cdss-app.js, shared/cdss-markdown.js or the css changed, also smoke-test one production station (e.g. stations/541-Cleveland/ClevelandCDSS.html): loads on the welcome page, navigates to a guidance page (banner, References list, Therapy panel), Abx links render, no console errors. Locally (python -m http.server from the repo root) unregister the service worker and clear caches first, or stale files are served. For the Minneapolis reference page (classic only), confirm nothing changed.
4. If service-worker behavior changed, verify HTML freshness after reload.

Regression checklist (must pass for merge)

- Combined is still default tab and starts on main-menu.
- No regression in cross-tab target remapping on the Minneapolis reference page (the CMS stations have no tabs).
- No regression in markdown link parsing with bracketed labels.
- No regression in multi-column navigation rendering.
- No regression in Sveltia collection visibility/editability.
- No schema drift in admin/config.yml collection-level keys.
- No orphaned internal markdown links created by ID rewrites.
- LinkTargets not reintroduced into export output or CMS schema.
- Stations without the Renderer/Layout flags (Minneapolis reference, obsolete stations) render identically after any shared/cdss-app.js, sidebar or markdown change.
- `node scripts/render-check.js` shows no hard errors outside the skipped pages, and `node scripts/nav-snapshot.js` matches the baseline.
- Therapy field survives an export-cms.py -> compile-cms.py round trip and no Therapy block contains References.
- audit-teststation.py reports no new issues.

Known acceptable risk profile

- Existing unresolved-link warnings may remain for legacy targets not present in TestStation data.
- Those warnings are non-blocking unless a change increases issue count or breaks active navigation paths.

Current site design summary to preserve

- Station-scoped architecture under stations/<station-id>/.
- Test station deployment path: stations/001-TestStation/TestStationCDSS.html
- Combined guidance model using stable slug PageIDs and Inpt linkage.
- CMS-managed page-per-file JSON model for disease-group collections.
- CMS-managed Abx links synced from cms-data/abx-links.cms.json to AbxLinks.json.

If uncertain

When requirements conflict (for example, link rewrite safety vs CMS schema constraints), prioritize non-breaking behavior and run the full validation checklist before finalizing changes.
