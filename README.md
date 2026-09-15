# GDAC Lab website

Source for the website of the **Geometric Dynamics, Autonomy, and Control Laboratory
(GDAC Lab / 仲野研究室)** at Nagoya Institute of Technology.

- Live site: <https://gdaclab.web.nitech.ac.jp> (host is set in `CNAME` and `url:` in `_config.yml`)
- Built with [Jekyll](https://jekyllrb.com); forked from
  [Academic Pages](https://github.com/academicpages/academicpages.github.io), itself a fork of the
  [Minimal Mistakes](https://mmistakes.github.io/minimal-mistakes/) theme (© 2016 Michael Rose, MIT — see `LICENSE`).

The site is bilingual: English pages live at the site root, Japanese pages under `/ja/`.

## Where the content lives

| What | Where |
| --- | --- |
| Pages (EN) | `_pages/*.md`, `_pages/*.html` |
| Pages (JA) | `_pages/ja/` |
| Publications | `_publications/` — **generated, see below** |
| Header navigation | `_data/navigation.yml` |
| Home page news items | `_data/news.yml` |
| Collaborators shown on People | `_data/collaborators.yml` |
| Site/author settings, publication categories | `_config.yml` |
| UI strings | `_data/ui-text.yml` |
| Images | `images/` (group photo: `images/lab/group-photo.jpg`) |

Home page composition is `_pages/about.md` (EN) / `_pages/ja/index.md` (JA), which pull in
`_includes/home-slideshow.html`, `home-extra.html` and `home-news.html`.

## Publications are generated — do not hand-edit

`_publications/*.md` is written by the sync scripts and is overwritten on every run:

- `scripts/fetch_researchmap_publications.py` — pulls from researchmap
  (account set by `researchmap_url:` in `_config.yml`); writes `*-rm-*.md`.
- `scripts/sync_preprints_from_sources.py` — resolves the DOI/arXiv IDs listed in
  `_data/preprint_sources.json`; writes `*-pp-*.md`.

To add a preprint, add its ID to `_data/preprint_sources.json` — not a file in `_publications/`.
A one-off preprint that needs no lookup can be a normal `.md` with `category: preprints`, as long
as its filename contains no `-pp-`; the scripts only own the `-rm-` and `-pp-` files.

`.github/workflows/researchmap-sync.yml` runs both weekly (Mondays 00:00 UTC) and on demand,
committing any changes to `master`. `scripts/test_pubsync.py` runs first and covers the sync
logic offline — run it locally after touching either script.

`publication_list_last_n_years:` in `_config.yml` limits the index to the last N years (0 = all).

### How the two publication indexes are built

`_pages/publications.html` (English works only) and `_pages/ja/publications.html` (both
languages, under one heading per category) share their logic through four includes, so the year
window and the "is this category empty?" test cannot drift apart between the two pages:

| Include | Does what |
| --- | --- |
| `publication-window.html` | Derives `pub_years`, `current_y`, `min_pub_y` from `publication_list_last_n_years`. Safe to include more than once. |
| `publication-recent-count.html` | `docs=` a list of records → how many fall inside the window, in `recent_count`. |
| `publication-list.html` | `docs=` a list of records → the `<ol>` of those inside the window, newest first, numbering continued in `pub_counter`. |
| `publication-entry.html` | One `<li>`; `publication-author-names.html` works out its author line. |

Each page picks the records it wants with `where`/`where_exp` and hands them to those; the
category jump buttons (`publications-category-jump.html`) count with the same include, so a
button never points at a heading that was not rendered.

### How the sync protects the list

* Nothing is deleted until a complete, validated result is in hand. An empty or malformed API
  response aborts with a non-zero exit and leaves `_publications/` untouched — previously it
  deleted every entry. A result that would shrink the list by more than half is also refused;
  set `SYNC_ALLOW_SHRINK=1` when a large removal is genuinely intended.
* researchmap is paged through to the end and the count is checked against the API's reported
  total, so a truncated read cannot quietly publish a partial list.
* A dropped connection, a timeout or an HTTP 429/5xx from researchmap is retried (five attempts,
  pauses of 3–24 s) before the run is called failed. In `deploy.yml` a failed fetch is a warning on
  the run, not a failed deploy: the site is built from the committed list, which the weekly sync
  keeps current, and the warning names which fetch failed.
* A failed preprint lookup (arXiv rate limiting is the usual cause) keeps the previously
  generated entry rather than dropping it, and does not discard the researchmap results.
* Permalinks are keyed on the record id (`/publication/rm-<id>`, `/publication/pp-<id>`), not on
  the publication date, because researchmap does edit dates. `redirect_from` keeps the old
  date-based URLs working.
* An unmapped researchmap `published_paper_type` is reported in the log instead of being filed
  silently under Conference papers. Add new types to `TYPE_TO_CATEGORY`.

### If publications stop updating

Check **Actions → Researchmap publication sync** first. GitHub disables a scheduled workflow
after 60 days without repository activity, with no failure notice — this is what stopped the sync
between 2026-07-06 and 2026-09-05. If the workflow shows as disabled, press **Enable workflow**.
The heartbeat step in the workflow now commits a timestamp whenever the repository has been quiet
for a month, so the 60-day timer should not run out again.

## The two browser demos

Both live under `assets/`, are served entirely from this site, and are reached from their
own pages. Neither is documented anywhere else, and neither is something you would guess
from the tree.

| | `/simulator/` | `/sun-safe-slew/` |
| --- | --- | --- |
| What it does | solves MuJoCo physics live in the browser | plays back a run computed offline |
| Page | `_pages/simulator.md`, `_pages/ja/simulator.md` | `_pages/sun-safe-slew.md`, `_pages/ja/sun-safe-slew.md` |
| Include | `_includes/simulator-demo.html` | `_includes/slew-demo.html` |
| Styles | `_sass/layout/_simulator.scss` | `_sass/layout/_slew-demo.scss` |
| Code | `assets/js/simulator/`, `assets/models/` | `assets/demos/sun-safe-slew/` |
| Weight | ~3.5-12 MB, behind a load gate | ~126 kB, no gate |

`assets/vendor/three/` is shared by both. `assets/vendor/fonts/` is used only by the slew
viewer, which needs its two faces; the rest of the site uses system fonts.

### The slew viewer is vendored, with local changes

`assets/demos/sun-safe-slew/index.html` was written as a standalone page in the research
repository that produced `data/trajectory.json`, and is adapted here. If it is ever
refreshed from upstream, these are the changes to re-apply — all of them are commented in
place, so diffing against the upstream file will show them:

1. `loadThree()` imports `../../vendor/three/three.module.min.js` instead of reaching for
   cdnjs and jsdelivr.
2. `@font-face` rules for the two self-hosted faces, in place of a Google Fonts
   stylesheet link, and `--font-body` pointing at this site's font stack.
3. An `STR`/`TR()` string table selected by a `lang` query parameter. The file is a static
   asset, so Liquid never runs in it; `_includes/slew-demo.html` passes `?lang=ja`.
4. A `FRAMED` check that relaxes the wheel-zoom and `touch-action` so an iframe does not
   swallow the page's scroll.
5. A doctype, charset, viewport and `noscript` fallback.

It is the viewer and the run, not the method: nothing that computes the control law is in
this repository. `satellite.obj` is generated from primitives upstream and is CC0-1.0
(`assets/LICENSE.txt` beside it); the `.stl` of the same mesh is deliberately not copied,
since the viewer does not load it.

The still on the Research pages (`images/research/sun-safe-slew*.jpg`) is rendered from
the viewer with `#shell` hidden, one per language because the labels drawn into the scene
are localized.

## Deployment

Pushing to `master` triggers `.github/workflows/deploy.yml`, which re-runs the publication sync,
builds with Jekyll, and publishes `_site` to the `plesk-deploy` branch, from which the NITech
Plesk host serves the site. There is no GitHub Pages deployment.

## Running locally

Requires Ruby (with `ruby-dev`) and Bundler.

```bash
bundle install
bundle exec jekyll serve -l -H localhost   # http://localhost:4000
```

If `bundle install` hits permission errors, install gems into the project instead:

```bash
bundle config set --local path 'vendor/bundle'
```

Changes to Markdown/HTML rebuild automatically; changes to `_config.yml` need a restart.

Note: build the site under a UTF-8 locale (`LANG=C.UTF-8`). Some SCSS partials contain Japanese
comments, and Jekyll's SCSS converter aborts under a US-ASCII locale.

### Docker

```bash
docker compose up   # http://localhost:4000
```

VS Code users can instead use the bundled dev container
(**F1 → Dev Containers: Reopen in Container**).

## Notes on this fork

Upstream Academic Pages ships demo content (sample blog posts, talks, teaching entries, a
portfolio, a "GitHub University" CV, a talk map, and TSV/notebook publication generators). None
of it applied to this site and all of it was published as live pages, so it has been removed. The
theme machinery behind those features is still in place, so a feature can be brought back by
adding content again:

- `_talks/`, `_teaching/`, `_portfolio/` are still declared as collections in `_config.yml` and
  their layouts/includes are intact — add documents plus an index page under `_pages/` to re-enable.
- The JSON-CV feature (`_includes/cv-template.html`, `_layouts/cv-layout.html`,
  `_sass/layout/_json_cv.scss`) was removed entirely; restore those three files from upstream if wanted.

Web fonts are served as `woff2` only (plus a `woff` fallback for Academicons). Legacy `eot`,
`svg` and `ttf` faces were dropped — they were dead weight for any browser released since ~2016.

MathJax, Plotly and Mermaid used to load from CDNs on *every* page, several megabytes of
JavaScript for features no page used. They are now loaded per page in
`_includes/footer/custom.html`:

- **MathJax** — opt in with `mathjax: true` in a page's front matter.
- **Plotly** and **Mermaid** — detected automatically from a <code>```plotly</code> or
  <code>```mermaid</code> code block in the page.

`assets/js/theme.js` — 14 kB of Plotly light/dark layout templates — is imported the same way.
It used to be a static `import` in `assets/js/_main.js`, which made every page fetch it on top of
the bundle; it is now an `import('./theme.js')` inside the branch that runs only when a
<code>```plotly</code> block is present.

`assets/js/main.min.js` is generated, not written: it is jQuery + fitvids + jquery-smooth-scroll
+ `assets/js/plugins/jquery.greedy-navigation.js` + `assets/js/_main.js` run through uglify-js.
After editing `_main.js`, rebuild it and commit both files:

```bash
npm install          # once
npm run build:js     # rewrites assets/js/main.min.js
```

Repo-only files (`scripts/`, `README.md`, `CONTRIBUTING.md`, Docker files, `.devcontainer`) are
listed under `exclude:` in `_config.yml`. Anything not excluded is copied verbatim into the
published site, so add new tooling directories there too.

Images are committed at their delivery size — the group photo is 1600 px wide. Resize before
committing rather than checking in camera originals; a 24-megapixel JPEG is loaded by the sidebar
on *every* page.
