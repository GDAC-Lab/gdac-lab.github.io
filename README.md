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
| Header navigation | `_data/navigation.yml` — see "The header menu" below |
| Home page news items | `_data/news.yml` |
| Collaborators shown on People | `_data/collaborators.yml` |
| Site/author settings, publication categories | `_config.yml` |
| UI strings | `_data/ui-text.yml` |
| Images | `images/` (group photo: `images/lab/group-photo.jpg`) |

Home page composition is `_pages/about.md` (EN) / `_pages/ja/index.md` (JA), which pull in
`_includes/home-slideshow.html`, `home-extra.html` and `home-news.html`.

## The header menu

`_data/navigation.yml` drives the header. Each entry carries `title` and
`title_ja`, and one path in `url:` that serves both languages — Japanese pages
live under `/ja/`, and `_includes/nav-url.html` works the prefix out.

An entry with `children:` becomes a drop-down instead of a link:

```yaml
- title: "Research"
  title_ja: "研究内容"
  children:
    - title: "Overview"
      title_ja: "研究の概要"
      url: /research/
```

Three things about that are easy to break:

* **The parent is not a link.** It opens the menu, so the page it would have
  pointed at has to be the first child. The children are ordinary `<a>`
  elements present in the markup of every page whether the menu is open or not,
  so they are links a crawler follows, not something JavaScript conjures up.
* **The toggle is an `<a role="button">`, not a `<button>`.** greedy-nav — the
  script that moves overflowing items into the ☰ menu — claims every `<button>`
  inside `#site-nav` as its own overflow control, so a real button here breaks
  the header.
* **The same markup renders in two places.** In the header bar the menu is a
  panel floating under its parent; once greedy-nav has moved the item into the
  ☰ list it is an indented list in the flow. Both are styled at the end of
  `_sass/layout/_navigation.scss`; `assets/js/nav-submenu.js` decides when it
  is open, and is the single source of truth for that, hover included.

Header items are dropped from the end when the window is too narrow, so what
goes last is what disappears first on a small laptop. Two pages stay out of the
header on purpose: `/policy/`, still in preparation, and `/terms/`, which is in
the footer where a reader looks for it.

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

`publication_list_last_n_years:` in `_config.yml` limits the index to the last N years (0 = all,
which is the current setting). The counts on the category jump buttons follow it without being
edited, and so does the lead paragraph, which says a window is in force only when there is one.

### How the two publication indexes are built

`_pages/publications.html` (English works only) and `_pages/ja/publications.html` (both
languages, under one heading per category) share their logic through four includes, so the year
window and the "is this category empty?" test cannot drift apart between the two pages:

| Include | Does what |
| --- | --- |
| `publication-window.html` | Derives `pub_years`, `current_y`, `min_pub_y` from `publication_list_last_n_years`. Safe to include more than once. |
| `publication-recent-count.html` | `docs=` a list of records → how many fall inside the window, in `recent_count`. |
| `publication-list.html` | `docs=` a list of records → the `<ol>` of those inside the window, newest first, with the year in the left gutter (printed where it changes, blank below). |
| `publication-entry.html` | One `<li>`; `publication-author-names.html` works out its author line. Fills the gutter from `rail`/`rail_year`, or from `pub_index` for a numbered list — which is what `/sitemap/` uses. |

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

## What search engines are told

The site has to answer 「名工大 仲野」, and until now it did not say so anywhere a
search engine reads. Four things carry that, and all four are easy to undo by
accident:

| Where | What it must say |
| --- | --- |
| `<title>` | `_includes/seo.html` composes `<page title> - <site title>`, taking the Japanese suffix from `title_ja` in `_config.yml`, so every Japanese page says 仲野研究室. A page may set `seo_title` in its front matter to state the whole thing itself; both home pages do, because the composed form would repeat the name. |
| `description` | Every content page carries its own, in its own language, front-loaded for the ~90 Japanese or ~155 Latin characters a result shows. Publication records have no prose, so seo.html composes one from their authors, venue and year. `site.description` is a fallback that should never be reached. |
| `hreflang` | `_includes/head/alternate-languages.html`, from the same `_includes/lang-urls.html` the language switcher uses — the switcher and hreflang must not contradict each other. Only emitted where a counterpart exists. |
| structured data | `_includes/head/structured-data.html`: the lab as a research organization inside the university, 仲野 聡史 as a person, the site, cross-referenced by `@id`. `sameAs` is what ties the person here to the same person on researchmap, Pure and the university's own pages, so keep those URLs live — `nitech_faculty_url` in `_config.yml` is one of them. |

The theme's own structured data used to declare `{"@type":"Person","name":"GDAC
Lab"}` — a person named after the laboratory — and switching `og_image` on added
a second, anonymous `Organization` for the same URL. Both are gone from
`seo.html`; do not restore them from upstream.

Names: Japanese pages say 仲野研究室（GDAC Lab）, English ones GDAC Lab. The
masthead uses `title_ja_short` (仲野研究室) because the full form breaks over two
lines on a laptop and three on a phone.

What the repository cannot do: register the site in Google Search Console and
submit `sitemap.xml`, and get the older 機械制御研究室 site to link here. Those
matter more than anything above and have to be done outside it.

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
the viewer itself by `scripts/render_slew_figure.mjs`, one per language:

```bash
python3 -m http.server 8000                                   # serve the site root
NODE_PATH=<global node_modules> \
  node scripts/render_slew_figure.mjs http://127.0.0.1:8000 images/research
```

The viewer's `?figure=1` mode strips the overlay and the text baked into the scene as
sprites, leaving geometry, and takes `&view=`, `&t=` and `&earth=` so a URL fixes the
frame. Figure mode also lights the spacecraft from the camera side: on screen it is
backlit and reads as a silhouette in motion, which is honest, but a still has no motion
to carry it and the solar cells are near black on a near-black sky. The annotation is
placed by hand in the script, in pixel coordinates of the 1280x720 frame, so it holds
only for the view and time set there. The frame is the "from the Sun" view at the end of
the run, where the keep-out cone projects to a circle and inside the ring is a breach
with no depth to argue about. Downscale the 2x screenshot to 1280x720 before committing.

## Deployment

Pushing to `master` triggers `.github/workflows/deploy.yml`, which re-runs the publication sync,
builds with Jekyll, and publishes `_site` to the `plesk-deploy` branch, from which the NITech
Plesk host serves the site. There is no GitHub Pages deployment. The pull from `plesk-deploy`
into `httpdocs` is done by hand in Plesk, so a push here does not reach the live site until
someone does that.

### The WordPress site at /nakano/

`https://gdaclab.web.nitech.ac.jp/nakano/` is the PI's own page. It is a WordPress install
living in `httpdocs/nakano/` on the server, it is **not** built from this repository, and
nothing here should ever write to that path.

The two coexist because Plesk's git deploy only adds and updates the files the repository
carries — it leaves anything else in `httpdocs` alone (verified by experiment). So the
WordPress directory survives every deploy.

What would break it is this repository producing a page there. Apache serves `index.html`
ahead of `index.php`, so a single `permalink: /nakano/` anywhere in `_pages/` would put a
blank Jekyll page in front of that site, with no error and nothing in the deploy log to say
so. **Never give a page, collection, or redirect the permalink `/nakano/` or anything below
it.** The deploy workflow fails the build if `_site/nakano` appears, which is the backstop,
not the rule.

`site.author.uri` in `_config.yml` points at that site; the sidebar link, the People page and
the `url` of the Person in the structured data all follow from it.

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
