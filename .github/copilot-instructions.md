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
- This status note should be revisited/updated as the increment progresses or a new increment begins — ask the user before assuming it is still current if there is a large time gap since the note was last updated (last updated 2026-11-05).

Station roles (do not conflate these)

- Production stations — stations/506-AnnArbor/, stations/539-Cincinnati/, stations/541-Cleveland/: live stations where real SME-driven content changes are expected and should be made freely per station request.
- Test station — stations/001-TestStation/: for testing runtime/CMS/pipeline changes before they reach production stations. Safe to modify experimentally.
- Minneapolis (reference only) — stations/618-Minneapolis/: the original source-of-truth reference kept only to check new work against. Do not make changes here (including incidental/cosmetic ones like footer buttons) unless the user explicitly asks for a Minneapolis-specific change.
- All other station folders (437-Fargo, 438-SiouxFalls, 442-Cheyenne, 568-BlackHills, 636-Omaha, 636A6-DesMoines, 656-StCloud) are obsolete: do not touch, build features for, or treat as in-scope for changes unless the user explicitly says otherwise.

When a request says "all stations" or is otherwise ambiguous about scope, ask which of the above groups it applies to rather than assuming Minneapolis or the obsolete stations are included.

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

3) Combined crosswalk navigation (transitional)
- Combined pages are identified by the presence of Inpt (inpatient source pointer).
- Combined pages may include Outpt and ERUC crossrefs for backward-compatible tab navigation during transition.
- handleRowClick must resolve requested Item through resolveTargetForCurrentVersion before OM/OD lookup.
- In combined mode, link and click targets should prefer combined equivalents when crosswalk exists.
- Strategic direction: combined pages are the long-term primary navigation surface; avoid introducing new dependencies on legacy inpt/outpt/eruc menus.

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
- Combined main menu ID is main-menu.
- Some scripts support legacy fallback inpt-main for compatibility; do not remove fallback unless all dependent data is migrated and validated.

9) LinkTargets deprecated: markdown-only link management
- LinkTargets field is removed from active CMS workflows (export-cms.py does not write LinkTargets to exported page JSON).
- LinkTargets may still exist in historical OMJSON records but are not authoritative for future edits.
- For active workflows, treat markdown targets in Text as canonical.
- Do not add new LinkTargets dependencies in runtime, CMS schema, or export pipeline logic.
- When updating links or pages, always use markdown format in Text field, never rely on LinkTargets metadata.

10) Service worker and cache behavior
- Service worker strategy is network-first for HTML.
- Any caching rule changes must include explicit version bump and regression check for content freshness.
- .js and .css are network-first along with HTML so a page and its shared scripts/styles stay in sync. New shared assets (e.g. cdss-sidebar.js/.css) must be added to the precache list in service-worker.js together with a VERSION bump (currently 1.275).

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

Combined guidance rebuild flow (spreadsheet-driven)
1. python scripts/rebuild-combined-menus.py
2. python scripts/audit-teststation.py

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

If a new cleanup pass is needed, implement a fresh script based on current markdown-only link rules and validate with audit-teststation.py.

Expected script behavior assumptions

- export-cms.py regenerates admin/config.yml and page-per-file JSON exports without LinkTargets.
- export-cms.py expects combined main menu at main-menu, with fallback inpt-main.
- export-cms.py classifies and emits combined CMS pages based on combined page markdown ancestry, not LinkTargets metadata.
- compile-cms.py compiles CMS page files back into OMJSON and preserves main-menu handling, including the optional Therapy field.
- compile-cms.py runs for all four CMS stations; stations whose cms-data did not change must come out byte-identical (check `git status` for unintended station changes).
- audit-teststation.py is the integrity gate and should be run after structural/data rewrites.
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
	 - tab switches preserve expected crosswalk behavior
	 - Abx links still render in combined and legacy row paths
3. If shared/cdss-app.js, shared/cdss-markdown.js or the css changed, also smoke-test one production station (e.g. stations/541-Cleveland/ClevelandCDSS.html): loads on the welcome page, navigates to a guidance page (banner, References list, Therapy panel), Abx links render, no console errors. Locally (python -m http.server from the repo root) unregister the service worker and clear caches first, or stale files are served. For the Minneapolis reference page (classic only), confirm nothing changed.
4. If service-worker behavior changed, verify HTML freshness after reload.

Regression checklist (must pass for merge)

- Combined is still default tab and starts on main-menu.
- No regression in cross-tab target remapping (combined/inpt/outpt/eruc).
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
