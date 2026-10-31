# VA Antimicrobial CDSS

Static web app (GitHub Pages + installable PWA) that gives clinicians station-specific
antimicrobial stewardship guidance.

- Live site: https://vhaantimicrobialstewardship.github.io/
- Content editor (CMS): https://vhaantimicrobialstewardship.github.io/admin
- Usage tracking: Google Analytics (https://analytics.google.com)

Detailed design rules, invariants and the regression checklist for code changes are in
[`.github/copilot-instructions.md`](.github/copilot-instructions.md). Read it before
changing runtime code, the CMS schema or the scripts.

## Stations

| Group | Folders | Notes |
|---|---|---|
| Production | `506-AnnArbor`, `539-Cincinnati`, `541-Cleveland` | Live; content edited by station SMEs in the CMS. |
| Test | `001-TestStation` | Try runtime/CMS/pipeline changes here first. |
| Reference | `618-Minneapolis` | Original source site. Do not change. |
| Obsolete | `437-Fargo`, `438-SiouxFalls`, `442-Cheyenne`, `568-BlackHills`, `636-Omaha`, `636A6-DesMoines`, `656-StCloud` | Not maintained. |

## Repository layout

| Path | Purpose |
|---|---|
| `index.html` | Landing page with station buttons. |
| `stations/<id>/<Name>CDSS.html` | Station entry page. Holds only a configuration block (`Layout`, `WelcomePage`, file names); loads the shared app. |
| `stations/<id>/<Name>OMJSON.json` | Menus and guidance pages. **Generated** from `cms-data/` for CMS stations; do not hand-edit. |
| `stations/<id>/<Name>ODJSON.json` | VistA order dialogs (legacy). |
| `shared/cdss-app.js` | Runtime that renders every station. A change here reaches production on push to `main`. |
| `shared/cdss-sidebar.js`, `.css` | Opt-in sidebar layout (menu tree + Therapy panel). `?layout=classic` shows the original layout. |
| `cms-data/<id>/pages/<group>/<page-id>.json` | One file per guidance page; the source of truth edited in the CMS. |
| `cms-data/<id>/documents/*.json` | CMS document entries (uploaded PDFs, spreadsheets, images). |
| `cms-data/abx-links.cms.json` | Drug-name link registry; synced to `AbxLinks.json`. |
| `assets/uploads/<id>/` | Files uploaded through the CMS. |
| `admin/` | Sveltia CMS (`config.yml` defines the collections). |
| `Cloudflare/sveltia-cms-auth/` | Cloudflare Worker that handles GitHub login for the CMS. |
| `scripts/` | Python pipeline and one-off migration scripts (see below). |
| `service-worker.js`, `manifest.webmanifest` | Offline support and app install. |
| `Resources/`, `Resources.html` | Shared reference documents. |
| `docs/` | Non-site design documents (kept out of the CMS's view). |
| `reports/` | Output of audit/migration scripts. |
| `Repository/` | Old experiments; not part of the site. |

## Editing content (SMEs)

1. Open https://vhaantimicrobialstewardship.github.io/admin and sign in with GitHub.
2. Pick your station's collection and edit a page.
   - Put internal links in the page text as markdown: `[label](page-id)`.
   - **Therapy Panel** content appears in the right-hand panel. Start its headings at
     `##` (never `#`) and keep References in the main text, not in Therapy.
3. Upload documents through the station's documents collection; the absolute URL and a
   ready-to-paste markdown link are filled in automatically after you publish.
4. Publish. Changes are live within a few minutes (see below). Ask the team to test on
   `001-TestStation` first for anything structural.

## What happens on push to `main`

GitHub Actions (`.github/workflows/`) run automatically and commit their results as
`github-actions[bot]`:

| Workflow | Trigger | Does |
|---|---|---|
| `compile-cms.yml` | `cms-data/**` | Runs `scripts/compile-cms.py` and commits the regenerated station OMJSON files. |
| `sync-abx-links.yml` | `cms-data/abx-links.cms.json` | Copies the entries into `AbxLinks.json`. |
| `sync-document-links.yml` | `cms-data/*/documents/*.json` | Runs `scripts/sync-document-links.py` to fill in absolute URLs and markdown links. |

Because the bot pushes to `main`, run `git pull --rebase --autostash` before pushing
local changes.

## Developer workflows

Requires Python 3.12. Run from the repository root.

```bash
# After editing cms-data/ locally: rebuild OMJSON, then run the integrity check
python scripts/compile-cms.py
python scripts/audit-teststation.py   # must report 0 issues; existing warnings are known noise
git status                            # stations you did not touch must be unchanged
```

Other flows (spreadsheet-driven combined rebuild, CMS export, Therapy split) are
documented step by step in `.github/copilot-instructions.md`. Most other files in
`scripts/` are one-off migrations; check that file before re-running any of them.

Preview locally with any static server, for example `python -m http.server 8000`, then
open http://localhost:8000/stations/001-TestStation/TestStationCDSS.html (absolute
paths like `/shared/cdss-app.js` require serving from the repository root).

## Service worker and caching

- HTML, `.js`, `.css`, `.json` and `.txml` are fetched network-first, so page and
  content edits reach users without any extra step.
- Everything else (PDFs, images, fonts, uploaded documents) is cache-first. If you
  **replace a file under the same name**, bump `VERSION` in `service-worker.js` so
  installed apps pick up the new copy.
- Also bump `VERSION` whenever the precache list (`URLS`) or a caching rule changes.

## Onboarding a new station

1. Copy a production station's `cms-data/<id>/` folder to the new station ID.
2. Add `stations/<id>/<Name>CDSS.html` (copy a production station page; set
   `CDSSlocation`, `Title`, `MainMenuButton` and the `OMjson`/`ODjson` paths) and its
   OMJSON/ODJSON files.
3. Add the station's page and documents collections (including the Therapy field) to
   `admin/config.yml`.
4. Add the station to the `STATIONS` lists in `scripts/compile-cms.py`,
   `scripts/audit-teststation.py` and `scripts/sync-document-links.py`, and to the
   `git add` lines in `.github/workflows/compile-cms.yml`.
5. Add a button to `index.html`.
6. Run `compile-cms.py` and `audit-teststation.py`, then smoke-test the page in sidebar
   and `?layout=classic` modes.

## Legacy: VistA export (Minneapolis-derived data)

Original OMJSON/ODJSON files were exported from VistA FileMan (Order Dialog file
101.41) with the "MenuManager" Excel workbook and the "VistA-MenuMan" Reflections
session:

1. Put the workbook and session/ini files in one non-cloud-synced folder with a `JSON`
   subfolder. Automation fails from cloud-synced locations.
2. Log in to VistA-MenuMan, press **OrderExport**, enter the version name (row 1 of the
   workbook's `SystemConfig` sheet). This writes `<Version>ODJSON.json`.
3. Press **MenuExport** to write `<Version>OMJSON.json`.
4. If export errors occur, close all VistA/Excel windows (or restart) and re-run.
   Validate JSON with a formatter such as https://jsonformatter.curiousconcept.com/.

`.txml` link files can be updated by hand or with the CPRS Template export. This path
is not used for CMS-managed stations.
