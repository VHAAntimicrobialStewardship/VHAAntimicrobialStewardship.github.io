Project purpose

This repository powers a VA Antimicrobial Stewardship static site with station-specific guidance, originally derived from Minneapolis VistA menu/order data and now evolving toward scalable multi-station and CMS-managed content.

Primary references:
- Minneapolis source site: https://antimicrobialcdss.github.io/MinneapolisCDSS.html
- Current site: https://vhaantimicrobialstewardship.github.io/

Stability-first operating rule

When making any change, preserve behavior across three coupled systems:
1. Runtime navigation and rendering in stations/001-TestStation/TestStationCDSS.html
2. CMS schema and content files (admin/config.yml and cms-data/)
3. OMJSON compile/export pipelines in scripts/

If a change fixes one area but regresses another, the change is incomplete.

Critical files and ownership

- Runtime UI behavior: stations/001-TestStation/TestStationCDSS.html
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
- compile-cms.py compiles CMS page files back into OMJSON and preserves main-menu handling.
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
3. If service-worker behavior changed, verify HTML freshness after reload.

Regression checklist (must pass for merge)

- Combined is still default tab and starts on main-menu.
- No regression in cross-tab target remapping (combined/inpt/outpt/eruc).
- No regression in markdown link parsing with bracketed labels.
- No regression in multi-column navigation rendering.
- No regression in Sveltia collection visibility/editability.
- No schema drift in admin/config.yml collection-level keys.
- No orphaned internal markdown links created by ID rewrites.
- LinkTargets not reintroduced into export output or CMS schema.
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
