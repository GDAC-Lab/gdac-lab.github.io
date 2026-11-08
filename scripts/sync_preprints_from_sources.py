#!/usr/bin/env python3
"""Regenerate _publications/*-pp-*.md: the list of preprints.

Usage:  python3 scripts/sync_preprints_from_sources.py [researchmap-slug]

The researchmap account defaults to the one `researchmap_url` in _config.yml
names.

Which preprints
---------------
* Every researchmap MISC record that links to arXiv (an arxiv.org/abs URL or
  the 10.48550/arXiv.* DOI). Registering a preprint there is all it takes.
* Any id in _data/preprint_sources.json ("dois" / "arxiv_ids"), for a preprint
  that is not on researchmap.
A preprint leaves the list once researchmap's papers hold its published
version: a paper that links to the same arXiv id, or one with the same title.

Where the details come from
---------------------------
* An arXiv id is read from arXiv's Atom API. When arXiv will not answer -- it
  has returned 406 to every request from GitHub's runners since 2026-09-14 --
  the same record is read from DataCite, which is where arXiv registers its
  10.48550/arXiv.* DOIs, and then from Crossref.
* Any other DOI is read from Crossref.

Invariants
----------
* The file's slug comes from the id, never from the record, so
  /publication/pp-arxiv-2503-16715 does not move.
* A standby source never changes the date of an entry already on disk. arXiv
  gives the submission day; DataCite may only know the year, and letting that
  through renamed three files to January 1 on 2026-09-21.
* No day is made up: when no source gives one, a new arXiv entry is dated by
  the month its id encodes.
* The link is the version-less abs URL whichever source answered, so a file
  does not flip between ".../2604.04001v1" and ".../2604.04001" week by week.

Failure handling
----------------
Nothing is deleted until every entry has been resolved. When a lookup fails on
every source, the file already published for it is carried forward; that is a
warning and the exit status stays 0, because nothing was lost. The script exits
1 only when a preprint has neither a record nor a file to fall back on, which
does leave it off the site. If researchmap cannot be read, the preprints
already on the site stay as they are.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_researchmap_publications as rm  # noqa: E402
from pubsync_common import (  # noqa: E402
    PUB_DIR,
    REPO_ROOT,
    SyncAbort,
    allow_shrink_from_env,
    annotate,
    apply_generated,
    arxiv_ids_in_text,
    build_citation,
    clean_text,
    crossref_authors,
    crossref_date,
    crossref_fetch,
    crossref_first,
    front_matter,
    http_get,
    http_get_json,
    iso_day,
    log,
    normalize_arxiv_id,
    normalize_doi,
    page_urls,
    researchmap_slug,
    title_language,
)

DATA_PATH = REPO_ROOT / "_data" / "preprint_sources.json"

DATACITE_API = "https://api.datacite.org/dois/"
ARXIV_API = "https://export.arxiv.org/api/query?id_list="
ARXIV_ACCEPT = "application/atom+xml, text/xml;q=0.9, */*;q=0.8"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_VENUE = "arXiv preprint"

# What a lookup can run into that is not a fault in this script: trouble that
# outlasted the retries, a refusal, a body that does not parse. Anything else
# is a bug, and is left to fail the step rather than be carried forward quietly.
LOOKUP_ERRORS = (SyncAbort, urllib.error.URLError, http.client.HTTPException,
                 OSError, ET.ParseError, ValueError)

# arXiv asks for no more than one request every few seconds.
_ARXIV_MIN_INTERVAL_SEC = float(os.environ.get("ARXIV_MIN_INTERVAL_SEC", "3.5"))
_ARXIV_NEXT_MONO = 0.0


def _arxiv_throttle() -> None:
    global _ARXIV_NEXT_MONO
    wait = _ARXIV_NEXT_MONO - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _ARXIV_NEXT_MONO = time.monotonic() + _ARXIV_MIN_INTERVAL_SEC


# ------------------------------------------------------------------- sources


@dataclass(frozen=True)
class Source:
    """One preprint to list: an arXiv id or a DOI, already normalised."""

    kind: str     # "arxiv" or "doi"
    id: str       # "2503.16715", or "10.xxxx/..."
    origin: str   # where it was listed, for the log

    @property
    def slug(self) -> str:
        """The one place a file's slug is derived: the file name, the permalink
        and carry_forward() all key on it, so a run finds the last one's file."""
        if self.kind == "arxiv":
            return f"arxiv-{self.id.replace('.', '-')}"
        return f"doi-{re.sub(r'[^a-z0-9]+', '-', self.id.lower()).strip('-')[:72]}"

    def __str__(self) -> str:
        return f"{self.kind} {self.id}"


def make_source(kind: str, value: str, origin: str) -> Source | None:
    """A Source for a listed value, or None if it names neither an arXiv id nor
    a DOI. An arXiv DOI becomes the arXiv id it names, so it gets the same
    standby sources and the same slug as the id itself."""
    aid = normalize_arxiv_id(value)
    if aid:
        return Source("arxiv", aid, origin)
    doi = normalize_doi(value) if kind == "doi" else None
    return Source("doi", doi, origin) if doi else None


def listed_sources() -> list[Source] | None:
    """The preprints in preprint_sources.json; None when the file is unusable."""
    if not DATA_PATH.is_file():
        return []
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        annotate("error", f"[preprint] {DATA_PATH.name} is not valid JSON: {exc}")
        return None
    if not isinstance(raw, dict):
        annotate("error", f"[preprint] {DATA_PATH.name} must hold an object")
        return None
    sources = []
    for kind, key in (("doi", "dois"), ("arxiv", "arxiv_ids")):
        values = raw.get(key)
        for value in values if isinstance(values, list) else []:
            text = str(value).strip()
            if not text or text.startswith("#"):
                continue
            source = make_source(kind, text, DATA_PATH.name)
            if source:
                sources.append(source)
            else:
                annotate("warning", f"[preprint] {DATA_PATH.name}: {text!r} is neither an arXiv id nor a DOI; skipped")
    return sources


def arxiv_ids_in(item: dict) -> list[str]:
    """arXiv ids a researchmap record links to, in order, without versions."""
    fields = {k: item.get(k) for k in ("see_also", "identifiers", "paper_title", "publication_name")}
    return arxiv_ids_in_text(json.dumps(fields, ensure_ascii=False))


def researchmap_sources(slug: str) -> list[Source] | None:
    """The preprints researchmap's MISC list links to; None if it cannot be read."""
    try:
        items = rm.fetch_items(slug, "misc")
    except SyncAbort as exc:
        annotate("warning", f"[preprint] researchmap MISC unreadable ({exc}); the preprints already listed stay")
        return None
    ids = list(dict.fromkeys(aid for item in items for aid in arxiv_ids_in(item)))
    log(f"[preprint] researchmap MISC: {len(ids)} arXiv id(s)")
    return [Source("arxiv", aid, "researchmap MISC") for aid in ids]


def sources_on_disk() -> list[Source]:
    """A Source for every arXiv preprint already published."""
    sources = []
    for path in sorted(PUB_DIR.glob("*-pp-arxiv-*.md")):
        m = re.search(r"-pp-arxiv-(\d{4})-(\d{4,5})\.md$", path.name)
        if m:
            sources.append(Source("arxiv", f"{m.group(1)}.{m.group(2)}", "already published"))
    return sources


def collect_sources(slug: str) -> list[Source] | None:
    """Every preprint to list, each once; None when the list file is unusable."""
    listed = listed_sources()
    if listed is None:
        return None
    found = researchmap_sources(slug)
    if found is None:
        found = sources_on_disk()
    elif not found and not allow_shrink_from_env():
        # A record that stops matching (a renamed field, say) reads the same as
        # an empty MISC list, so an empty list keeps what is published.
        listed_slugs = {s.slug for s in listed}
        found = [s for s in sources_on_disk() if s.slug not in listed_slugs]
        if found:
            annotate("warning",
                     f"[preprint] researchmap MISC links to no arXiv id, but {len(found)} preprint(s) "
                     "from it are on the site; kept them. If they were removed from researchmap on "
                     "purpose, run the sync once with SYNC_ALLOW_SHRINK=1.")
    unique: dict[str, Source] = {}
    for source in listed + found:
        unique.setdefault(source.slug, source)
    return list(unique.values())


# ---------------------------------------------------------- published versions


def title_key(title: str) -> str:
    """A title reduced for comparison: NFKC, case-folded, letters and digits
    only. Empty when too short to identify one paper, so that an empty or
    one-word title never matches anything."""
    folded = unicodedata.normalize("NFKC", clean_text(title)).casefold()
    key = "".join(ch for ch in folded if ch.isalnum())
    return key if len(key) >= 16 else ""


@dataclass
class Published:
    """researchmap's papers, indexed to recognise a preprint's published version."""

    by_arxiv: dict[str, str]   # arXiv id -> rm:id of a paper that links to it
    by_title: dict[str, str]   # title_key -> rm:id

    def match(self, source: Source, title: str) -> str | None:
        if source.kind == "arxiv" and source.id in self.by_arxiv:
            return self.by_arxiv[source.id]
        key = title_key(title)
        return self.by_title.get(key) if key else None


def published_index(slug: str) -> Published | None:
    """researchmap's papers as a Published index; None if they cannot be read."""
    try:
        items = rm.fetch_items(slug)
    except SyncAbort as exc:
        annotate("warning", f"[preprint] researchmap papers unreadable ({exc}); the preprint list was left as it is")
        return None
    by_arxiv: dict[str, str] = {}
    by_title: dict[str, str] = {}
    for item in items:
        rm_id = str(item.get("rm:id") or "")
        for aid in arxiv_ids_in(item):
            by_arxiv.setdefault(aid, rm_id)
        titles = item.get("paper_title")
        for title in titles.values() if isinstance(titles, dict) else [titles]:
            key = title_key(str(title or ""))
            if key:
                by_title.setdefault(key, rm_id)
    return Published(by_arxiv, by_title)


# -------------------------------------------------------------------- records


@dataclass
class Preprint:
    source: Source
    title: str
    date: str      # YYYY-MM-DD
    authors: str
    venue: str
    url: str

    def render(self) -> tuple[str, str]:
        """(file name, content). The permalink is keyed on the id, not the date,
        so a metadata correction cannot silently move the page."""
        slug, authors = self.source.slug, self.authors or "—"
        fields: list[tuple[str, object]] = [
            ("title", self.title),
            ("collection", "publications"),
            ("category", "preprints"),
            ("lang", title_language(self.title)),
            *page_urls(f"pp-{slug}", self.date),
            ("date", self.date),
            ("venue", self.venue),
            ("paperurl", self.url),
            ("authors", authors),
            ("citation", build_citation(authors, self.date[:4], self.title, self.venue)),
        ]
        return f"{self.date}-pp-{slug}.md", front_matter(fields)


def carry_forward(slug: str) -> tuple[str, str] | None:
    """The file already published for a slug, as (name, content), if any."""
    for path in sorted(PUB_DIR.glob(f"*-pp-{slug}.md")):
        return path.name, path.read_text(encoding="utf-8")
    return None


def published_date(slug: str) -> str | None:
    """The date of the file already published for this slug, if there is one."""
    existing = carry_forward(slug)
    m = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})\s*$", existing[1], re.M) if existing else None
    return m.group(1) if m else None


def front_title(content: str) -> str:
    """The title written in a generated file's front matter."""
    m = re.search(r"^title: '(.*)'$", content, re.M)
    return m.group(1).replace("''", "'") if m else ""


def arxiv_abs_url(aid: str) -> str:
    return f"https://arxiv.org/abs/{aid}"


def arxiv_month(aid: str) -> str:
    """The first of the month an arXiv id encodes: 2610.40502 -> 2026-10-01."""
    return f"20{aid[:2]}-{aid[2:4]}-01"


# ---------------------------------------------------------------------- arXiv


def arxiv_fetch(aid: str) -> dict | None:
    """{title, date, authors} from arXiv's Atom API; None when arXiv has no such
    id. arXiv answers an unknown or malformed id with HTTP 200 and an entry
    titled "Error", not with a 404."""
    _arxiv_throttle()
    try:
        xml = http_get(ARXIV_API + urllib.parse.quote(aid), accept=ARXIV_ACCEPT, tag="arxiv")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    entry = ET.fromstring(xml).find("atom:entry", ATOM_NS)
    if entry is None:
        return None

    def text(tag: str) -> str:
        el = entry.find(f"atom:{tag}", ATOM_NS)
        return " ".join(el.text.split()) if el is not None and el.text else ""

    if "/api/errors" in text("id") or text("title") == "Error":
        return None
    names = [
        name_el.text.strip()
        for author in entry.findall("atom:author", ATOM_NS)
        for name_el in [author.find("atom:name", ATOM_NS)]
        if name_el is not None and name_el.text
    ]
    return {"title": text("title"), "date": iso_day(text("published")), "authors": ", ".join(names)}


# ------------------------------------------------------------------- DataCite


def datacite_fetch(doi: str) -> dict | None:
    """The DataCite attributes for a DOI, or None when DataCite does not hold it."""
    url = DATACITE_API + urllib.parse.quote(doi.strip(), safe="")
    try:
        payload = http_get_json(url, tag="datacite")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if not isinstance(payload, dict):
        return None
    return (payload.get("data") or {}).get("attributes") or None


def datacite_title(attrs: dict) -> str:
    for t in attrs.get("titles") or []:
        title = clean_text(t.get("title") if isinstance(t, dict) else "")
        if title:
            return title
    return ""


def datacite_date(attrs: dict) -> str | None:
    """The submission day, if the record carries a whole date anywhere."""
    entries = [d for d in attrs.get("dates") or [] if isinstance(d, dict)]
    for want in ("Issued", "Submitted", "Available", "Accepted", "Created"):
        for d in entries:
            if str(d.get("dateType") or "") == want and iso_day(d.get("date")):
                return iso_day(d.get("date"))
    for d in entries:  # any type, rather than settle for the year
        if iso_day(d.get("date")):
            return iso_day(d.get("date"))
    for key in ("published", "created", "registered", "updated"):
        if iso_day(attrs.get(key)):
            return iso_day(attrs.get(key))
    return None


def datacite_authors(attrs: dict) -> str:
    names: list[str] = []
    for c in attrs.get("creators") or []:
        if not isinstance(c, dict):
            continue
        given, family = clean_text(c.get("givenName")), clean_text(c.get("familyName"))
        if given and family:
            names.append(f"{given} {family}")
            continue
        raw = clean_text(c.get("name"))
        # DataCite stores personal names as "Family, Given".
        if raw and c.get("nameType") != "Organizational" and raw.count(",") == 1:
            fam, _, giv = raw.partition(",")
            raw = f"{giv.strip()} {fam.strip()}".strip()
        if raw:
            names.append(raw)
    return ", ".join(names)


# ------------------------------------------------------------------- Crossref


def crossref_day(msg: dict, *, whole_day: bool = True) -> str | None:
    """The record's date as YYYY-MM-DD; with `whole_day`, only if Crossref
    gives the day, otherwise the missing parts count as the first."""
    ymd = crossref_date(msg)
    if not ymd:
        return None
    year, month, day = ymd
    if whole_day and not (month and day):
        return None
    return iso_day(f"{year:04d}-{month or 1:02d}-{day or 1:02d}")


def crossref_names(msg: dict) -> str:
    names = []
    for given, family, literal in crossref_authors(msg):
        names.append(f"{given} {family}".strip() if family else literal)
    return ", ".join(n for n in names if n)


def crossref_venue(msg: dict) -> str:
    return crossref_first(msg, "container-title") or clean_text(msg.get("publisher")) or "Preprint"


def crossref_url(msg: dict, doi: str) -> str:
    return str(msg.get("URL") or f"https://doi.org/{doi}")


# -------------------------------------------------------------------- resolve

# (name, fetch, title, whole day or None, authors)
Standby = tuple[str, Callable[[str], "dict | None"], Callable[[dict], str],
                Callable[[dict], "str | None"], Callable[[dict], str]]


def arxiv_standby_sources() -> tuple[Standby, ...]:
    """Where an arXiv record is read when arXiv itself will not answer, in the
    order tried. Looked up at call time, not bound at import, so the tests can
    stand in for any one of them."""
    return (
        ("DataCite", datacite_fetch, datacite_title, datacite_date, datacite_authors),
        ("Crossref", crossref_fetch, lambda m: crossref_first(m, "title"), crossref_day, crossref_names),
    )


def resolve_arxiv(source: Source) -> Preprint | None:
    """The preprint as arXiv describes it, or as a standby source does."""
    aid = source.id
    try:
        meta = arxiv_fetch(aid)
    except LOOKUP_ERRORS as exc:
        log(f"[preprint] arxiv {aid}: {type(exc).__name__}: {exc}; trying a standby source")
        meta = None
    if meta and meta["title"] and meta["date"]:
        return Preprint(source, meta["title"], meta["date"], meta["authors"], ARXIV_VENUE, arxiv_abs_url(aid))

    doi = f"10.48550/arXiv.{aid}"
    for name, fetch, title_of, day_of, authors_of in arxiv_standby_sources():
        try:
            record = fetch(doi)
        except LOOKUP_ERRORS as exc:
            log(f"[preprint] arxiv {aid}: {name}: {type(exc).__name__}: {exc}")
            continue
        title = title_of(record) if record else ""
        if not title:
            continue
        # Keeping the published date keeps the file name, the redirect from the
        # old date-based URL and the place in the list where they are.
        date = published_date(source.slug) or day_of(record) or arxiv_month(aid)
        log(f"[preprint] arxiv {aid}: resolved via {name} ({doi}), date {date}")
        return Preprint(source, title, date, authors_of(record), ARXIV_VENUE, arxiv_abs_url(aid))
    return None


def resolve_doi(source: Source) -> Preprint | None:
    """The preprint as Crossref describes it."""
    msg = crossref_fetch(source.id)
    title = crossref_first(msg, "title") if msg else ""
    date = crossref_day(msg, whole_day=False) if msg else None
    if not (title and date):
        return None
    return Preprint(source, title, date, crossref_names(msg), crossref_venue(msg), crossref_url(msg, source.id))


def resolve(source: Source) -> Preprint | None:
    return resolve_arxiv(source) if source.kind == "arxiv" else resolve_doi(source)


# ----------------------------------------------------------------------- main


def main() -> int:
    try:
        slug = researchmap_slug()
    except SyncAbort as exc:
        annotate("error", f"[preprint] {exc}")
        return 1
    sources = collect_sources(slug)
    if sources is None:
        return 1
    published = published_index(slug)
    if published is None:
        # Without the papers there is no telling which preprints were published
        # since; putting those back for a week is worse than waiting a week.
        return 0

    generated: dict[str, str] = {}
    kept: list[str] = []   # lookup failed, the published file still stands
    lost: list[str] = []   # lookup failed and there is nothing to show
    dropped = 0            # files removed because the paper is out

    for source in sources:
        try:
            record = resolve(source)
            reason = "no record found"
        except LOOKUP_ERRORS as exc:
            record, reason = None, f"{type(exc).__name__}: {exc}"
        existing = carry_forward(source.slug)
        title = record.title if record else front_title(existing[1]) if existing else ""
        rm_id = published.match(source, title)
        if rm_id:
            log(f"[preprint] {source}: published as rm:{rm_id}; the preprint is no longer listed")
            dropped += 1 if existing else 0
            continue
        if record:
            name, content = record.render()
            generated[name] = content
        elif existing:
            generated[existing[0]] = existing[1]
            kept.append(f"{source}: {reason} — kept the existing entry")
        else:
            lost.append(f"{source}: {reason} — no existing entry to keep")

    for note in kept:
        annotate("warning", f"[preprint] {note}")
    for note in lost:
        annotate("error", f"[preprint] {note}")

    try:
        written, deleted, unchanged = apply_generated(
            pattern="*-pp-*.md",
            generated=generated,
            # No sources at all is a real "no preprints"; the guard is for runs
            # that had sources and still produced nothing.
            min_expected=1 if generated or lost or kept else 0,
            allow_shrink=allow_shrink_from_env() or not sources,
            removed_on_purpose=dropped,
        )
    except SyncAbort as exc:
        annotate("error", f"[preprint] {exc}")
        return 1

    log(
        f"[preprint] {len(generated)} entr(ies) from {len(sources)} source(s): "
        f"{written} written, {deleted} removed, {unchanged} unchanged"
    )
    return 1 if lost else 0


if __name__ == "__main__":
    raise SystemExit(main())
