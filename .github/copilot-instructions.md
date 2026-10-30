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
- Completed (2026-10-30): the opt-in sidebar redesign (left menu tree + right therapy panel) is rolled out to the test station and the three production stations (506/539/541). Clean pages were overwritten from the test station; SME-edited pages were held back and split by hand in Sveltia. See invariant 11. Known follow-ups: (a) osteom-empirical-therapy is redundant (its therapy now lives in the osteomyelitis page) and still exists, linked from `index`, in all four stations; (b) the production welcome page is still the test-station placeholder until each station's SME supplies text; (c) a few Therapy fields break the Therapy rules (References inside Therapy: otitis-externa, orolabial-herpes; Therapy starting with `# `: empirical-therapy, doxypep, post-exposure-prophylaxis-non-occupational, hepatitis-b, influenza-chemoprophylaxis; empirical-therapy also has an empty Text). These exist in the test station too.
- This status note should be revisited/updated as the increment progresses or a new increment begins — ask the user before assuming it is still current if there is a large time gap since the note was last updated (last updated 2026-10-30).

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
- createRichTextTable remains the baseline single-column guidance renderer.
- Column delimiter compatibility must preserve both modern and legacy markers:
	- <!-- COLUMN 2 -->, <!-- COLUMN 3 -->, ...
	- <!-- RIGHT COLUMN --> (backward compatibility)

6) Abx links behavior
- Drug links are injected in two paths:
	- legacy row-based path for older tab displays
	- combined markdown text path via appendTextWithAbxLinks
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
- .js and .css are network-first along with HTML so a page and its shared scripts/styles stay in sync. New shared assets (e.g. cdss-sidebar.js/.css) must be added to the precache list in service-worker.js together with a VERSION bump (currently 1.273).

11) Sidebar layout (opt-in per station page; live on the test station and the three production stations)
- Opt-in mechanism: a station page enables the layout by setting `var Layout = 'sidebar'` (and optionally `var WelcomePage = '<pageid>'`) in its configuration block and loading /shared/cdss-sidebar.css and /shared/cdss-sidebar.js before /shared/cdss-app.js. The test station and the 506/539/541 production station pages do this; the Minneapolis reference page and obsolete stations stay classic. `?layout=classic` on the URL restores the original layout for that visit.
- shared/cdss-sidebar.js sets `window.CDSSSidebar.enabled`; shared/cdss-app.js reads it into `SIDEBAR_LAYOUT`. All sidebar behavior in cdss-app.js (hooks such as beforeRender, afterRender, syncUrl, onDataReady) is behind `SIDEBAR_LAYOUT`; stations without the flag must behave exactly as before, so never remove that gating or let sidebar code run unconditionally.
- Production rollout (done 2026-10-30) used scripts/rollout-diff.py, a one-time three-way classification against the fork commit b9498ed8 (the commit that copied the test station into the production stations). Pages unchanged by SMEs since the fork were overwritten from the test station (`--apply-a`); SME-edited pages were held and split by hand. The script's FORK_COMMIT is fixed, so re-running it now only reports test-vs-production drift. Before any future bulk copy from the test station to a production station, classify first and never overwrite SME-edited pages. Onboarding a new station: copy a production station's cms-data, add its HTML (Layout/WelcomePage variables and the sidebar css/js tags), add its collection (including the Therapy field) to admin/config.yml, and add it to the STATIONS lists in compile-cms.py and audit-teststation.py. split-therapy.py and export-cms.py remain hard-wired to 001-TestStation; export-cms.py regenerates admin/config.yml, so check that the production collections still have their Therapy field before committing if it is ever run.
- The menu tree is derived at runtime from main-menu plus nav-like pages (no separate menu data). Nav pages are detected by link-line ratio; bold-only lines act as sub-headings.
- Optional per-page `Therapy` field (markdown, CMS label "Therapy Panel", present in all four station collections in admin/config.yml) renders in the right-hand therapy panel; the panel is absent when the field is empty. Data flow: cms-data page JSON `Therapy` -> compile-cms.py writes it to the OMJSON record -> runtime renders it in the panel. export-cms.py writes it back out only when present and emits the field definition into admin/config.yml (edit the generator, not just config.yml, or the next export loses it); audit-teststation.py checks markdown links in both Text and Therapy.
- Therapy markdown must not start with a level-1 heading (`# ` becomes a page banner); therapy headings start at `##`. Keep Therapy free of References; References always stay in Text.
- Classic layout fallback: when `!SIDEBAR_LAYOUT` and Therapy is non-empty, cdss-app.js (`withTherapyInText`) merges Therapy back into the page text before the trailing separator/References block, so the content is never hidden.
- scripts/split-therapy.py (dry run by default; `--apply` to write; `--show <PageID>`, `--page <PageID>`, `--include-empty`; then compile-cms.py and audit-teststation.py) bulk-moves therapy sections from Text into Therapy for 001-TestStation pages. It skips pages that already have Therapy (hand-edited splits are safe), skips pages whose Text would be left with only a title, verifies each split is lossless, refuses any split that would put a References line in Therapy, and writes reports/therapy-split-report.json. The heuristics are noisy (see the report's stragglers); review the report and rendered pages after applying. To undo a bulk split: `git checkout -- cms-data/001-TestStation/pages`, but first back up any hand-split pages that are uncommitted.
- The welcome page (PageID `welcome`) is a standalone page kept by export-cms.py (STANDALONE_PAGES). Production stations carry the placeholder welcome page until their SMEs supply text.

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

Therapy split flow (test station, sidebar layout)
1. python scripts/split-therapy.py (dry run; review reports/therapy-split-report.json)
2. python scripts/split-therapy.py --apply
3. python scripts/compile-cms.py
4. python scripts/audit-teststation.py
5. Verify in the browser: sidebar layout and `?layout=classic` on several split pages

Repository hygiene
- Python bytecode (__pycache__/, *.pyc) is git-ignored; do not commit it.
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
3. If shared/cdss-app.js changed, also smoke-test one production station (e.g. stations/541-Cleveland/ClevelandCDSS.html): sidebar layout and `?layout=classic`, loads on the welcome page, navigates to a guidance page, Abx links render, no console errors. Test the test station in both sidebar and `?layout=classic`. For the Minneapolis reference page (classic only), confirm nothing changed.
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
- Stations without the Layout flag (Minneapolis reference, obsolete stations) and any station viewed with `?layout=classic` render identically after any shared/cdss-app.js or sidebar change.
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
