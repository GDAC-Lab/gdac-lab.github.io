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

`.github/workflows/researchmap-sync.yml` runs both weekly (Mondays 00:00 UTC) and on demand,
committing any changes to `master`.

`publication_list_last_n_years:` in `_config.yml` limits the index to the last N years (0 = all).

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
