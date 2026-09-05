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

### How the sync protects the list

* Nothing is deleted until a complete, validated result is in hand. An empty or malformed API
  response aborts with a non-zero exit and leaves `_publications/` untouched — previously it
  deleted every entry. A result that would shrink the list by more than half is also refused;
  set `SYNC_ALLOW_SHRINK=1` when a large removal is genuinely intended.
* researchmap is paged through to the end and the count is checked against the API's reported
  total, so a truncated read cannot quietly publish a partial list.
* A failed preprint lookup (arXiv rate limiting is the usual cause) keeps the previously
  generated entry rather than dropping it, and does not discard the researchmap results.
* Permalinks are keyed on the record id (`/publication/rm-<id>`, `/publication/pp-<id>`), not on
  the publication date, because researchmap does edit dates. `redirect_from` keeps the old
  date-based URLs working.
* An unmapped researchmap `published_paper_type` is reported in the log instead of being filed
  silently under Conference Papers. Add new types to `TYPE_TO_CATEGORY`.

### If publications stop updating

Check **Actions → Researchmap publication sync** first. GitHub disables a scheduled workflow
after 60 days without repository activity, with no failure notice — this is what stopped the sync
between 2026-07-06 and 2026-09-05. If the workflow shows as disabled, press **Enable workflow**.
The heartbeat step in the workflow now commits a timestamp whenever the repository has been quiet
for a month, so the 60-day timer should not run out again.

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

Repo-only files (`scripts/`, `README.md`, `CONTRIBUTING.md`, Docker files, `.devcontainer`) are
listed under `exclude:` in `_config.yml`. Anything not excluded is copied verbatim into the
published site, so add new tooling directories there too.

Images are committed at their delivery size — the group photo is 1600 px wide. Resize before
committing rather than checking in camera originals; a 24-megapixel JPEG is loaded by the sidebar
on *every* page.
