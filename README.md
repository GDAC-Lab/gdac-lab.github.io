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
| Home page news items | `_data/news.yml` — newest first; the home page lists the latest five and folds the rest under "Earlier news" |
| Collaborators shown on People | `_data/collaborators.yml` |
| Site/author settings, publication categories | `_config.yml` |
| Images | `images/` (group photo: `images/lab/group-photo.jpg`) |

Home page composition is `_pages/about.md` (EN) / `_pages/ja/index.md` (JA), which pull in
`_includes/home-photo.html`, `home-extra.html` and `home-news.html`.

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

Two things about that are easy to break:

* **The parent is not a link.** It opens the menu, so the page it would have
  pointed at has to be the first child. The children are ordinary `<a>`
  elements present in the markup of every page whether the menu is open or not,
  so they are links a crawler follows, not something JavaScript conjures up.
* **The same markup renders in two places.** In the header bar the menu is a
  panel floating under its parent; once the item has moved into the ☰ menu
  (see below) it is an indented list in the flow. Both are styled at the end of
  `_sass/layout/_navigation.scss`; `assets/js/site.js` decides when it is open,
  and is the single source of truth for that, hover included.

Header items are dropped from the end when the window is too narrow, so what
goes last is what disappears first on a small laptop. One page stays out of the
header on purpose: `/terms/`, which is in the footer where a reader looks for
it.

## Publications are generated — do not hand-edit

`_publications/*.md` is written by the sync scripts and is overwritten on every run:

- `scripts/fetch_researchmap_publications.py` — pulls from researchmap
  (account set by `researchmap_url:` in `_config.yml`); writes `*-rm-*.md`.
- `scripts/sync_preprints_from_sources.py` — lists preprints; writes `*-pp-*.md`.

To add a preprint, register it in researchmap under MISC with its arXiv URL
(`https://arxiv.org/abs/…`) or the `10.48550/arXiv.…` DOI. The sync picks up every MISC record
that links to arXiv and reads the title, authors and date from arXiv (DataCite and Crossref
standing in when arXiv will not answer). When researchmap lists a published paper with the same
title, the preprint drops off the list. If researchmap cannot be read, the preprints already on
the site stay. A preprint that is not on researchmap can instead be listed by its ID in
`_data/preprint_sources.json` — not as a file in `_publications/`.
A one-off preprint that needs no lookup can be a normal `.md` with `category: preprints`, as long
as its filename contains no `-pp-`; the scripts only own the `-rm-` and `-pp-` files.

`.github/workflows/researchmap-sync.yml` runs both weekly (Mondays 00:00 UTC) and on demand,
commits any changes to `master`, and then dispatches `deploy.yml` so the new files go out.
`scripts/test_pubsync.py` runs first and covers the sync logic offline — run it locally after
touching either script. Everything the scripts share — the retry policy, the User-Agent, the
Actions annotations, date normalisation, the swap-in of generated files — lives in
`scripts/pubsync_common.py`.

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
* A dropped connection, a timeout or an HTTP 408/429/5xx from any of the APIs is retried (five
  attempts, pauses of 3–24 s, a `Retry-After` header honoured up to 90 s) before the run is
  called failed. `deploy.yml` never fetches: it builds the committed list, so a deploy cannot
  fail because researchmap, arXiv or DataCite is down.
* An arXiv id is read from arXiv's Atom API; when arXiv will not answer (it has returned 406 to
  every request from GitHub's runners since 2026-09-14) the same record is read from DataCite,
  which is where arXiv registers its `10.48550/arXiv.*` DOIs, and Crossref is tried last. A
  standby source never changes the date of an entry already on disk, so the file name, the
  redirect from the old date-based URL and the ordering stay put even when the standby only
  knows the year.
* A preprint that no source can resolve keeps its previously generated entry rather than
  being dropped; that is a warning on the run. The run fails only when a preprint cannot be
  resolved *and* has no existing entry, because then it really is missing from the site.
  Either way the researchmap result is still committed and deployed.
* Permalinks are keyed on the record id (`/publication/rm-<id>/`, `/publication/pp-<id>/`), not
  on the publication date, because researchmap does edit dates. They end in a slash, so any
  static server serves them as `index.html`. `redirect_from` keeps both earlier forms working:
  the extensionless `/publication/rm-<id>` and the date-based one (`pubsync_common.page_urls`).
* An unmapped researchmap `published_paper_type` is reported in the log instead of being filed
  silently under Conference papers. Add new types to `TYPE_TO_CATEGORY`.

### The CV's publication lists

The weekly sync also writes `_cv/journals.bib` and `_cv/proceedings.bib`
(`scripts/build_cv_bib.py`): the English CV's journal articles and conference papers,
newest first. researchmap decides which papers appear — every English-titled journal
article and conference paper, preprints aside — and Crossref, looked up by DOI, supplies
the details, because researchmap's own fields are rougher (an author split in two at a
comma, venue names written several ways, article numbers missing). A record without a DOI
is written from researchmap. The owner's name is bold, acronyms are braced so `unsrt`'s
sentence case leaves them alone, and the output is byte-for-byte stable, so a week with no
change commits nothing.

The CV itself is not in this repository; it lives in an Overleaf project. When the
Actions secrets `OVERLEAF_GIT_TOKEN` (an Overleaf Git authentication token) and
`OVERLEAF_CV_PROJECT_ID` (the ID in the project's URL) are set, the sync copies the two
files into that project as `generated/journals.bib` and `generated/proceedings.bib`
through Overleaf's Git integration. Only those two paths are written, and nothing is
pushed when they are unchanged. The CV reads them with `\nocite{*}` and the `unsrt`
style, which keeps the file order. Do not edit them, here or in Overleaf: correct the
record in researchmap and the next sync brings it through. `_cv/` starts with an
underscore, so Jekyll does not publish it.

The token opens every project on the Overleaf account, so it is kept only in the
repository's Actions secrets. If the sync reports that the copy into Overleaf failed
with an authentication error, the token was revoked or has expired: create a new one in
Overleaf's account settings and replace the secret.

### The CV PDF

`.github/workflows/cv-pdf.yml` compiles the CV from the same Overleaf project and
commits the PDF as `files/satoshi-nakano-cv.pdf`, which both People pages link to.
Overleaf does not announce changes, so the workflow clones the project every night
(03:17 JST) and compares its commit with `_data/cv.yml`, the commit the committed PDF
was built from. Only a change is compiled, committed and deployed. The publication sync
also starts it as soon as it has written new lists into the project. To publish an edit
at once, run **Actions → CV PDF → Run workflow**; tick *force* to rebuild when nothing
has changed. The CV source stays in Overleaf: it is cloned into the runner's temporary
directory, and only the PDF is copied out.

`scripts/build_cv_pdf.sh` compiles the way Overleaf does: XeLaTeX, BibTeX for every
bibliography (one per multibib list), then XeLaTeX twice. Like Overleaf it carries on
past LaTeX errors, and reports them as warnings on the run. It stops instead, leaving
the PDF on the site as it was, when no PDF comes out or a font cannot be found. A new
PDF reaches the live site with the usual pull on Plesk.

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
6. A "Guided" view (`view=3`, the default): the camera starts 30° to one side of the
   Sun line and, while the spacecraft passes under the keep-out cone, orbits to 15° on the
   other side, so the detour and the climb to target B both read clearly. It follows run
   time, so scrubbing moves it too; dragging or zooming hands the camera back.

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

`.github/workflows/deploy.yml` builds the committed tree with Jekyll and publishes `_site` to
the `plesk-deploy` branch, from which the NITech Plesk host serves the site. There is no GitHub
Pages deployment. The pull from `plesk-deploy` into `httpdocs` is done by hand in Plesk, so
nothing here reaches the live site until someone does that.

It runs on every push to `master` and on demand (Actions → *Build and Deploy to Plesk* → *Run
workflow*). The weekly `researchmap-sync.yml` cannot trigger it by pushing — GitHub does not
start a workflow from a push made with the default `GITHUB_TOKEN` — so, when it has committed
something, it dispatches `deploy.yml` explicitly; `workflow_dispatch` is the documented exception
to that rule. A week with no publication changes therefore does not rebuild the site. Builds
run one at a time in commit order (`concurrency: deploy`).

`.github/workflows/ci.yml` runs the sync scripts' tests and the same build on every push and
pull request, on any branch, and publishes nothing: a branch shows there whether it would
deploy before it is merged.

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

Needs the Ruby in `.ruby-version` (3.3) with Bundler; `Gemfile.lock` pins every gem, the same
versions the deploy uses.

```bash
bundle install
LANG=C.UTF-8 bundle exec jekyll serve -l -H localhost   # http://localhost:4000
```

If `bundle install` hits permission errors, install gems into the project instead:

```bash
bundle config set --local path 'vendor/bundle'
```

Changes to Markdown/HTML rebuild automatically; changes to `_config.yml` need a restart.
Build under a UTF-8 locale (`LANG=C.UTF-8`): some SCSS partials contain Japanese comments, and
Jekyll's SCSS converter aborts under a US-ASCII locale.

The sync scripts' tests run offline: `python3 scripts/test_pubsync.py`.

## How the theme is put together

**Styles.** `assets/css/main.scss` is the one stylesheet; it imports, in order:

| | |
| --- | --- |
| `_sass/_variables.scss` | type, breakpoints (`$small` 600px, `$medium` 768px, `$large` 925px, `$x-large` 1280px), layout widths, the base palette |
| `_sass/_colors.scss` | every colour the pages use, as custom properties: the light theme on `:root`, the dark one on `html[data-theme="dark"]` |
| `_sass/include/` | the `breakpoint` mixin (px in, em out), utility classes, the icon rules |
| `_sass/layout/` | one partial per component or page: reset and base elements, masthead and navigation, sidebar, footer, the prose scale, the publication lists, People, the galleries, the two demos |

Later partials win ties, so the page-specific ones come after the shared ones they adjust. A
colour belongs in `_colors.scss` with a value for each theme, not hard-coded in a partial: a
fixed `#fff` is what left white panels in the dark theme.

**Icons.** Font Awesome and Academicons are served as `woff2` only and cut down to the dozen
icons the site shows, about 6 kB in all. `scripts/build_icon_fonts.sh` rebuilds them; to use
another icon, add its code point there and its rule to `_sass/include/_icons.scss`.

**Scripts.** All the pages' behaviour is in `assets/js/site.js`, plain JavaScript with no build
step: the theme toggle, the header's ☰ menu (items that do not fit move into it, from the right)
and its submenus, the sidebar's Links button, and the footer that sits at the bottom of a short
page. The theme itself is set by a few lines in `_includes/head.html`, before the page paints, so
a dark page never flashes white. The simulator and the sun-safe slew demo have their own scripts.

MathJax is the one third-party script a page can load: opt in with `mathjax: true` in its front
matter (`_includes/footer/custom.html`).

## Notes on this fork

Upstream Academic Pages ships demo content (sample posts, talks, teaching, a portfolio, a JSON
CV, a talk map, publication generators) and the theme machinery behind it: comments, analytics,
breadcrumbs, pagination, tags, a table of contents, hero images, an Atom feed, jQuery and its
plugins. None of it applied to this site, so all of it has been removed; restore a feature from
upstream if it is ever wanted, rather than expecting a switch in `_config.yml` to bring it back.

Repo-only files (`scripts/`, `README.md`, `Gemfile*`, `LICENSE`) are listed under `exclude:` in
`_config.yml`. Anything not excluded is copied verbatim into the published site, so add new
tooling directories there too.

Images are committed at their delivery size — the group photo is 1600 px wide. Resize before
committing rather than checking in camera originals; a 24-megapixel JPEG is loaded by the sidebar
on *every* page.
