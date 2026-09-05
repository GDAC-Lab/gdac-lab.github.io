#!/usr/bin/env python3
"""Regenerate _publications/*-pp-*.md from _data/preprint_sources.json.

Sources: Crossref for DOIs (https://api.crossref.org/works/{doi}); the arXiv Atom
API for bare arXiv ids and for 10.48550/arXiv.* DOIs Crossref does not hold.

Edit preprint_sources.json ("dois" / "arxiv_ids"), then run this script (or let CI
run it). A preprint that needs no external lookup can be added as an ordinary .md
in _publications with `category: preprints` and no "-pp-" in the filename; this
script only owns the "-pp-" files.

Failure handling
----------------
Nothing is deleted until every entry has been resolved. When a single lookup
fails — arXiv rate limiting is the common case, and it is what broke the sync on
2026-06-22 and 06-29 — the previously generated file for that entry is carried
forward instead of being dropped, and the script exits non-zero so CI reports it.

arXiv rate limits: at most one request per ARXIV_MIN_INTERVAL_SEC (default 3.5s);
429/503 are retried with backoff.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pubsync_common import (  # noqa: E402
    PUB_DIR,
    REPO_ROOT,
    SyncAbort,
    allow_shrink_from_env,
    apply_generated,
    build_citation,
    front_matter,
    log,
    title_language,
)

_ARXIV_MIN_INTERVAL_SEC = float(os.environ.get("ARXIV_MIN_INTERVAL_SEC", "3.5"))
_ARXIV_NEXT_MONO = 0.0

DATA_PATH = REPO_ROOT / "_data" / "preprint_sources.json"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def user_agent() -> str:
    mail = (os.environ.get("CROSSREF_CONTACT_EMAIL") or "").strip()
    base = "gdac-lab-site/1.0 (https://github.com/gdac-lab/gdac-lab.github.io)"
    return f"{base}; mailto:{mail}" if mail else base


def _arxiv_throttle() -> None:
    global _ARXIV_NEXT_MONO
    wait = _ARXIV_NEXT_MONO - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _ARXIV_NEXT_MONO = time.monotonic() + _ARXIV_MIN_INTERVAL_SEC


def urlopen_with_retry(req: urllib.request.Request, timeout: float = 60):
    """Retry on 429 / 503 (arXiv and Crossref rate limits)."""
    backoff = 5.0
    last_err: Exception | None = None
    for attempt in range(6):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code not in (429, 503) or attempt >= 5:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                wait = float(retry_after)
            except (TypeError, ValueError):
                wait = backoff
            wait = max(3.0, wait)
            log(f"[preprint] HTTP {exc.code} ({req.full_url}), sleep {wait:.1f}s "
                f"retry {attempt + 1}/5")
            time.sleep(wait)
            backoff = min(backoff * 1.5, 90.0)
    raise last_err  # pragma: no cover


# --------------------------------------------------------------------------- Crossref


def crossref_fetch(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi.strip(), safe='')}"
    req = urllib.request.Request(
        url, headers={"User-Agent": user_agent(), "Accept": "application/json"}
    )
    try:
        with urlopen_with_retry(req) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if payload.get("status") != "ok":
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
    return "1900-01-01"


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


def arxiv_id_from_doi(doi: str) -> str | None:
    m = re.search(r"10\.48550/\s*arXiv\.(\d{4}\.\d{4,5})", doi, re.I)
    return m.group(1) if m else None


# ------------------------------------------------------------------------------ arXiv


def arxiv_fetch(arxiv_id: str) -> dict | None:
    _arxiv_throttle()
    aid = arxiv_id.strip().replace("arxiv:", "")
    url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(aid)}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    try:
        with urlopen_with_retry(req) as resp:
            xml = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    entry = ET.fromstring(xml).find("atom:entry", ATOM_NS)
    if entry is None:
        return None

    title_el = entry.find("atom:title", ATOM_NS)
    title = " ".join(title_el.text.split()) if title_el is not None and title_el.text else ""

    published_el = entry.find("atom:published", ATOM_NS)
    published = (
        published_el.text.strip()[:10]
        if published_el is not None and published_el.text
        else "1900-01-01"
    )

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
        "title": title,
        "date": published,
        "authors": ", ".join(names),
        "url": href,
        "arxiv_id": aid,
    }


# ----------------------------------------------------------------------------- render


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
        ("authors", authors),
        ("citation", build_citation(authors, date_iso[:4], title, venue)),
    ]
    return f"{date_iso}-pp-{slug_suffix}.md", front_matter(fields)


def carry_forward(slug_suffix: str) -> tuple[str, str] | None:
    """Reuse the previously generated file for an entry whose lookup just failed."""
    for path in sorted(PUB_DIR.glob(f"*-pp-{slug_suffix}.md")):
        return path.name, path.read_text(encoding="utf-8")
    return None


def resolve_arxiv(aid: str) -> tuple[str, str] | None:
    meta = arxiv_fetch(aid)
    if not meta:
        return None
    return render(
        date_iso=meta["date"],
        slug_suffix=f"arxiv-{meta['arxiv_id'].replace('.', '-')}",
        title=meta["title"],
        venue="arXiv preprint",
        authors=meta["authors"] or "—",
        paperurl=meta["url"],
    )


def resolve_doi(doi: str) -> tuple[str, str] | None:
    doi = doi.strip()
    if doi.lower().startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    msg = crossref_fetch(doi)
    if msg is None:
        aid = arxiv_id_from_doi(doi)
        if not aid:
            return None
        meta = arxiv_fetch(aid)
        if not meta:
            return None
        return render(
            date_iso=meta["date"],
            slug_suffix=f"arxiv-{meta['arxiv_id'].replace('.', '-')}",
            title=meta["title"],
            venue="arXiv preprint",
            authors=meta["authors"] or "—",
            paperurl=f"https://doi.org/{doi}",
        )

    title = crossref_title(msg)
    if not title:
        return None
    return render(
        date_iso=crossref_date(msg),
        slug_suffix=f"doi-{re.sub(r'[^a-z0-9]+', '-', doi.lower()).strip('-')[:72]}",
        title=title,
        venue=crossref_venue(msg),
        authors=crossref_authors(msg) or "—",
        paperurl=crossref_url(msg, doi),
    )


def slug_for_source(kind: str, value: str) -> str:
    if kind == "arxiv":
        return f"arxiv-{value.strip().replace('arxiv:', '').replace('.', '-')}"
    doi = value.strip()
    if doi.lower().startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]
    aid = arxiv_id_from_doi(doi)
    if aid:
        return f"arxiv-{aid.replace('.', '-')}"
    return f"doi-{re.sub(r'[^a-z0-9]+', '-', doi.lower()).strip('-')[:72]}"


def main() -> int:
    if not DATA_PATH.is_file():
        log(f"[preprint] no {DATA_PATH.relative_to(REPO_ROOT)}; nothing to do")
        return 0

    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log(f"[preprint] ERROR: {DATA_PATH.name} is not valid JSON: {exc}")
        return 1

    dois = [str(d) for d in (raw.get("dois") or []) if isinstance(raw.get("dois"), list)]
    arxiv_ids = [
        str(a) for a in (raw.get("arxiv_ids") or []) if isinstance(raw.get("arxiv_ids"), list)
    ]

    sources = [("doi", d) for d in dois] + [("arxiv", a) for a in arxiv_ids]
    sources = [(k, v) for k, v in sources if v.strip() and not v.strip().startswith("#")]

    generated: dict[str, str] = {}
    failures: list[str] = []

    for kind, value in sources:
        try:
            result = resolve_doi(value) if kind == "doi" else resolve_arxiv(value)
        except Exception as exc:  # network / rate limit / malformed response
            result = None
            reason = f"{type(exc).__name__}: {exc}"
        else:
            reason = "no record found"

        if result is None:
            fallback = carry_forward(slug_for_source(kind, value))
            if fallback:
                generated[fallback[0]] = fallback[1]
                failures.append(f"{kind} {value}: {reason} — kept the existing entry")
            else:
                failures.append(f"{kind} {value}: {reason} — no existing entry to keep")
            continue

        generated[result[0]] = result[1]

    for note in failures:
        log(f"[preprint] WARNING: {note}")

    # An empty sources list legitimately means "no preprints"; allow the clear-out.
    try:
        written, deleted, unchanged = apply_generated(
            pattern="*-pp-*.md",
            generated=generated,
            min_expected=0 if not sources else 1,
            allow_shrink=allow_shrink_from_env() or not sources,
        )
    except SyncAbort as exc:
        log(f"[preprint] ERROR: {exc}")
        return 1

    log(
        f"[preprint] {len(generated)} entr(ies) from {len(sources)} source(s): "
        f"{written} written, {deleted} removed, {unchanged} unchanged"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
