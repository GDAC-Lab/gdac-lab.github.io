#!/usr/bin/env python3
"""Regenerate _publications/*-pp-*.md from _data/preprint_sources.json.

Edit preprint_sources.json ("dois" / "arxiv_ids"), then run this script (or let
CI run it). A preprint that needs no external lookup can be added as an ordinary
.md in _publications with `category: preprints` and no "-pp-" in the filename;
this script only owns the "-pp-" files.

Where the records come from
---------------------------
* A DOI is read from Crossref.
* An arXiv id is read from arXiv's Atom API. When arXiv will not answer — it has
  returned 406 to every request from GitHub's runners since 2026-09-14 — the
  same record is read from DataCite, which is where arXiv registers its
  10.48550/arXiv.* DOIs, and Crossref is tried last. A DOI of that form is
  handled as the arXiv id it names, so it gets the same standby sources.

Two invariants keep the published URLs still whichever source answers:
* the file's slug comes from the id in preprint_sources.json, never from the
  record, so `/publication/pp-arxiv-2503-16715` does not move; and
* a standby source never changes the date of an entry already on disk. arXiv
  gives the submission day; DataCite may only know the year, and letting that
  through renamed three files to January 1 on 2026-09-21.

Failure handling
----------------
Nothing is deleted until every entry has been resolved. When a lookup fails on
every source, the previously generated file for that entry is carried forward.
That is reported as a warning and the script still exits 0, because nothing was
lost. It exits non-zero only when a source fails and there is no existing entry
to fall back on, which does leave a preprint off the site.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pubsync_common import (  # noqa: E402
    PUB_DIR,
    REPO_ROOT,
    SyncAbort,
    allow_shrink_from_env,
    annotate,
    apply_generated,
    build_citation,
    front_matter,
    http_get,
    http_get_json,
    iso_day,
    log,
    title_language,
)

DATA_PATH = REPO_ROOT / "_data" / "preprint_sources.json"

CROSSREF_API = "https://api.crossref.org/works/"
DATACITE_API = "https://api.datacite.org/dois/"
ARXIV_API = "https://export.arxiv.org/api/query?id_list="
ARXIV_ACCEPT = "application/atom+xml, text/xml;q=0.9, */*;q=0.8"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
UNKNOWN_DATE = "1900-01-01"

# arXiv asks for no more than one request every few seconds.
_ARXIV_MIN_INTERVAL_SEC = float(os.environ.get("ARXIV_MIN_INTERVAL_SEC", "3.5"))
_ARXIV_NEXT_MONO = 0.0


def _arxiv_throttle() -> None:
    global _ARXIV_NEXT_MONO
    wait = _ARXIV_NEXT_MONO - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _ARXIV_NEXT_MONO = time.monotonic() + _ARXIV_MIN_INTERVAL_SEC


# ------------------------------------------------------------------- ids and slugs


def strip_doi(doi: str) -> str:
    doi = doi.strip()
    prefix = "https://doi.org/"
    return doi[len(prefix):] if doi.lower().startswith(prefix) else doi


def arxiv_id_from_doi(doi: str) -> str | None:
    m = re.search(r"10\.48550/\s*arXiv\.(\d{4}\.\d{4,5})", doi, re.I)
    return m.group(1) if m else None


def clean_arxiv_id(aid: str) -> str:
    return aid.strip().replace("arxiv:", "")


def slug_for_source(kind: str, value: str) -> str:
    """The one place a slug is derived. render() and carry_forward() both key
    on it, so a file written by one run is found by the next."""
    if kind == "arxiv":
        return f"arxiv-{clean_arxiv_id(value).replace('.', '-')}"
    doi = strip_doi(value)
    aid = arxiv_id_from_doi(doi)
    if aid:
        return f"arxiv-{aid.replace('.', '-')}"
    return f"doi-{re.sub(r'[^a-z0-9]+', '-', doi.lower()).strip('-')[:72]}"


# ------------------------------------------------------------------------ Crossref


def crossref_fetch(doi: str) -> dict | None:
    """The Crossref work record, or None when Crossref does not hold the DOI."""
    url = CROSSREF_API + urllib.parse.quote(doi.strip(), safe="")
    try:
        payload = http_get_json(url, tag="crossref")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    return payload.get("message") or {}


def crossref_date(msg: dict) -> str:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (msg.get(key) or {}).get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            dp = parts[0]
            year = int(dp[0])
            month = int(dp[1]) if len(dp) > 1 else 1
            day = int(dp[2]) if len(dp) > 2 else 1
            return f"{year:04d}-{month:02d}-{day:02d}"
    return UNKNOWN_DATE


def crossref_title(msg: dict) -> str:
    titles = msg.get("title")
    return str(titles[0]).strip() if isinstance(titles, list) and titles else ""


def crossref_authors(msg: dict) -> str:
    names: list[str] = []
    for author in msg.get("author") or []:
        if not isinstance(author, dict):
            continue
        family = (author.get("family") or "").strip()
        given = (author.get("given") or "").strip()
        if family and given:
            names.append(f"{given} {family}")
        elif family:
            names.append(family)
        elif author.get("name"):
            names.append(str(author["name"]).strip())
    return ", ".join(names)


def crossref_venue(msg: dict) -> str:
    container = msg.get("container-title")
    if isinstance(container, list) and container:
        return str(container[0]).strip()
    publisher = msg.get("publisher")
    if isinstance(publisher, str) and publisher.strip():
        return publisher.strip()
    return "Preprint"


def crossref_url(msg: dict, doi: str) -> str:
    if msg.get("URL"):
        return str(msg["URL"])
    doi = doi.strip()
    return doi if doi.lower().startswith("http") else f"https://doi.org/{doi}"


# ------------------------------------------------------------------------ DataCite


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
        title = str(t.get("title") or "").strip()
        if title:
            return " ".join(title.split())
    return ""


def datacite_date(attrs: dict) -> str:
    """The submission day if the record carries one anywhere, else the year."""
    entries = attrs.get("dates") or []
    for want in ("Issued", "Submitted", "Available", "Accepted", "Created"):
        for d in entries:
            if str(d.get("dateType") or "") == want:
                day = iso_day(d.get("date"))
                if day:
                    return day
    for d in entries:  # any type, rather than invent a date
        day = iso_day(d.get("date"))
        if day:
            return day
    for key in ("published", "created", "registered", "updated"):
        day = iso_day(attrs.get(key))
        if day:
            return day
    year = attrs.get("publicationYear")
    return f"{int(year):04d}-01-01" if str(year or "").isdigit() else UNKNOWN_DATE


def datacite_authors(attrs: dict) -> str:
    names: list[str] = []
    for c in attrs.get("creators") or []:
        given = str(c.get("givenName") or "").strip()
        family = str(c.get("familyName") or "").strip()
        if given and family:
            names.append(f"{given} {family}")
            continue
        raw = str(c.get("name") or "").strip()
        if not raw:
            continue
        # DataCite stores personal names as "Family, Given".
        if c.get("nameType") != "Organizational" and raw.count(",") == 1:
            fam, _, giv = raw.partition(",")
            raw = f"{giv.strip()} {fam.strip()}".strip()
        names.append(raw)
    return ", ".join(n for n in names if n)


# --------------------------------------------------------------------------- arXiv


def arxiv_fetch(arxiv_id: str) -> dict | None:
    """The arXiv Atom record, or None when arXiv has no such id."""
    _arxiv_throttle()
    aid = clean_arxiv_id(arxiv_id)
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

    names = [
        name_el.text.strip()
        for author in entry.findall("atom:author", ATOM_NS)
        for name_el in [author.find("atom:name", ATOM_NS)]
        if name_el is not None and name_el.text
    ]
    href = f"https://arxiv.org/abs/{aid}"
    for link in entry.findall("atom:link", ATOM_NS):
        if link.get("rel") == "alternate" and link.get("type") == "text/html" and link.get("href"):
            href = link.get("href")
            break
    return {
        "title": text("title"),
        "date": iso_day(text("published")) or UNKNOWN_DATE,
        "authors": ", ".join(names),
        "url": href,
        "arxiv_id": aid,
    }


# -------------------------------------------------------------------------- render


def render(
    *,
    date_iso: str,
    slug_suffix: str,
    title: str,
    venue: str,
    authors: str,
    paperurl: str,
) -> tuple[str, str]:
    """Return (filename, content). Permalinks are keyed on the source id, not the
    date, so a metadata correction cannot silently move the page."""
    fields: list[tuple[str, object]] = [
        ("title", title),
        ("collection", "publications"),
        ("category", "preprints"),
        ("lang", title_language(title)),
        ("permalink", f"/publication/pp-{slug_suffix}"),
        ("redirect_from", [f"/publication/{date_iso}-pp-{slug_suffix}"]),
        ("date", date_iso),
        ("venue", venue),
        ("paperurl", paperurl),
        ("authors", authors or "—"),
        ("citation", build_citation(authors or "—", date_iso[:4], title, venue)),
    ]
    return f"{date_iso}-pp-{slug_suffix}.md", front_matter(fields)


def carry_forward(slug_suffix: str) -> tuple[str, str] | None:
    """The previously generated file for a slug, as (name, content), if any."""
    for path in sorted(PUB_DIR.glob(f"*-pp-{slug_suffix}.md")):
        return path.name, path.read_text(encoding="utf-8")
    return None


def published_date(slug_suffix: str) -> str | None:
    """The date already published for this slug, if there is a file on disk."""
    existing = carry_forward(slug_suffix)
    if not existing:
        return None
    m = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})\s*$", existing[1], re.M)
    return m.group(1) if m else None


_Standby = tuple[str, Callable[[str], dict | None], Callable[[dict], str],
                 Callable[[dict], str], Callable[[dict], str]]


def arxiv_standby_sources() -> tuple[_Standby, ...]:
    """Where an arXiv record is read when arXiv itself will not answer: how to
    fetch its 10.48550 DOI record and read the title, date and authors out of
    it, in the order tried. Looked up at call time, not bound at import, so
    the tests can stand in for any one of them."""
    return (
        ("DataCite", datacite_fetch, datacite_title, datacite_date, datacite_authors),
        ("Crossref", crossref_fetch, crossref_title, crossref_date, crossref_authors),
    )


def resolve_arxiv(arxiv_id: str) -> tuple[str, str] | None:
    """Render an arXiv preprint from arXiv, or from a standby source."""
    aid = clean_arxiv_id(arxiv_id)
    slug = slug_for_source("arxiv", aid)

    try:
        meta = arxiv_fetch(aid)
    except Exception as exc:  # 406, a rate limit past its retries, a parse error
        log(f"[preprint] arxiv {aid}: {type(exc).__name__}: {exc}; trying a standby source")
        meta = None
    if meta:
        return render(
            date_iso=meta["date"],
            slug_suffix=slug,
            title=meta["title"],
            venue="arXiv preprint",
            authors=meta["authors"],
            paperurl=meta["url"],
        )

    doi = f"10.48550/arXiv.{aid}"
    for source, fetch, get_title, get_date, get_authors in arxiv_standby_sources():
        try:
            rec = fetch(doi)
        except Exception as exc:
            log(f"[preprint] arxiv {aid}: {source}: {type(exc).__name__}: {exc}")
            continue
        title = get_title(rec) if rec else ""
        if not title:
            continue
        # arXiv gave the submission day; a standby source may only know the year.
        # Keeping the published date keeps the file name, the redirect from the
        # old date-based URL and the ordering on the page where they are.
        date_iso = published_date(slug) or get_date(rec)
        log(f"[preprint] arxiv {aid}: resolved via {source} ({doi}), date {date_iso}")
        return render(
            date_iso=date_iso,
            slug_suffix=slug,
            title=title,
            venue="arXiv preprint",
            authors=get_authors(rec),
            paperurl=f"https://arxiv.org/abs/{aid}",
        )
    return None


def resolve_doi(doi: str) -> tuple[str, str] | None:
    """Render a DOI preprint from Crossref. An arXiv DOI is the arXiv id it
    names, and goes through resolve_arxiv so it gets the same standby sources."""
    doi = strip_doi(doi)
    aid = arxiv_id_from_doi(doi)
    if aid:
        return resolve_arxiv(aid)

    msg = crossref_fetch(doi)
    title = crossref_title(msg) if msg else ""
    if not title:
        return None
    return render(
        date_iso=crossref_date(msg),
        slug_suffix=slug_for_source("doi", doi),
        title=title,
        venue=crossref_venue(msg),
        authors=crossref_authors(msg),
        paperurl=crossref_url(msg, doi),
    )


# ---------------------------------------------------------------------------- main


def read_sources() -> list[tuple[str, str]] | None:
    """(kind, value) pairs from preprint_sources.json; None when the file is bad."""
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        annotate("error", f"[preprint] {DATA_PATH.name} is not valid JSON: {exc}")
        return None
    if not isinstance(raw, dict):
        annotate("error", f"[preprint] {DATA_PATH.name} must hold an object")
        return None

    def listed(key: str) -> list[str]:
        values = raw.get(key)
        return [str(v) for v in values] if isinstance(values, list) else []

    sources = [("doi", d) for d in listed("dois")] + [("arxiv", a) for a in listed("arxiv_ids")]
    return [(k, v.strip()) for k, v in sources if v.strip() and not v.strip().startswith("#")]


def main() -> int:
    if not DATA_PATH.is_file():
        log(f"[preprint] no {DATA_PATH.relative_to(REPO_ROOT)}; nothing to do")
        return 0
    sources = read_sources()
    if sources is None:
        return 1

    generated: dict[str, str] = {}
    kept: list[str] = []   # lookup failed, the existing entry still stands
    lost: list[str] = []   # lookup failed and nothing is left to show

    for kind, value in sources:
        try:
            result = resolve_doi(value) if kind == "doi" else resolve_arxiv(value)
            reason = "no record found"
        except Exception as exc:  # network, rate limit, malformed response
            result, reason = None, f"{type(exc).__name__}: {exc}"

        if result is not None:
            generated[result[0]] = result[1]
            continue
        fallback = carry_forward(slug_for_source(kind, value))
        if fallback:
            generated[fallback[0]] = fallback[1]
            kept.append(f"{kind} {value}: {reason} — kept the existing entry")
        else:
            lost.append(f"{kind} {value}: {reason} — no existing entry to keep")

    for note in kept:
        annotate("warning", f"[preprint] {note}")
    for note in lost:
        annotate("error", f"[preprint] {note}")

    # An empty sources list legitimately means "no preprints"; allow the clear-out.
    try:
        written, deleted, unchanged = apply_generated(
            pattern="*-pp-*.md",
            generated=generated,
            min_expected=0 if not sources else 1,
            allow_shrink=allow_shrink_from_env() or not sources,
        )
    except SyncAbort as exc:
        annotate("error", f"[preprint] {exc}")
        return 1

    log(
        f"[preprint] {len(generated)} entr(ies) from {len(sources)} source(s): "
        f"{written} written, {deleted} removed, {unchanged} unchanged"
    )
    # A lookup that failed while the published entry still stands loses nothing.
    # A source with nothing to fall back on means the site is missing a preprint.
    return 1 if lost else 0


if __name__ == "__main__":
    raise SystemExit(main())
