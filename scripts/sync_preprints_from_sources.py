#!/usr/bin/env python3
# Generate _publications/*-pp-*.md from _data/preprint_sources.json using:
# - Crossref API for DOIs (https://api.crossref.org/works/{doi})
# - arXiv Atom API for bare arXiv ids or when Crossref has no record for 10.48550/arXiv.* DOIs
#
# Edit preprint_sources.json ("dois" / "arxiv_ids"), then run this script (or rely on CI).
# Manual preprints: add normal .md in _publications with category: preprints (no "-pp-" in filename).

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "_data" / "preprint_sources.json"
PUB_DIR = REPO_ROOT / "_publications"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def user_agent() -> str:
    import os

    m = (os.environ.get("CROSSREF_CONTACT_EMAIL") or "").strip()
    base = "gdac-lab-site/1.0 (https://github.com/gdac-lab/gdac-lab.github.io)"
    return f"{base}; mailto:{m}" if m else base


def yaml_sq(s: str) -> str:
    return str(s).replace("'", "''")


def html_esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def remove_generated() -> None:
    for p in PUB_DIR.glob("*-pp-*.md"):
        p.unlink()


def crossref_fetch(doi: str) -> dict | None:
    enc = urllib.parse.quote(doi.strip(), safe="")
    url = f"https://api.crossref.org/works/{enc}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent(), "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if payload.get("status") != "ok":
        return None
    return payload.get("message") or {}


def crossref_date(msg: dict) -> str:
    for key in ("published-print", "published-online", "issued", "created"):
        block = msg.get(key) or {}
        parts = block.get("date-parts")
        if isinstance(parts, list) and parts:
            dp = parts[0]
            if isinstance(dp, list) and dp:
                y = int(dp[0])
                m = int(dp[1]) if len(dp) > 1 else 1
                d = int(dp[2]) if len(dp) > 2 else 1
                return f"{y:04d}-{m:02d}-{d:02d}"
    return "1900-01-01"


def crossref_title(msg: dict) -> str:
    t = msg.get("title")
    if isinstance(t, list) and t:
        return str(t[0]).strip()
    return ""


def crossref_authors(msg: dict) -> str:
    authors = msg.get("author") or []
    if not isinstance(authors, list):
        return ""
    names: list[str] = []
    for a in authors:
        if not isinstance(a, dict):
            continue
        fam = (a.get("family") or "").strip()
        giv = (a.get("given") or "").strip()
        if fam and giv:
            names.append(f"{giv} {fam}")
        elif fam:
            names.append(fam)
        elif a.get("name"):
            names.append(str(a["name"]).strip())
    return ", ".join(names)


def crossref_venue(msg: dict) -> str:
    ct = msg.get("container-title")
    if isinstance(ct, list) and ct:
        return str(ct[0]).strip()
    pub = msg.get("publisher")
    if isinstance(pub, str) and pub.strip():
        return pub.strip()
    typ = msg.get("type") or ""
    if "posted" in typ or typ == "report":
        return "Preprint"
    return "Preprint"


def crossref_url(msg: dict, doi: str) -> str:
    if msg.get("URL"):
        return str(msg["URL"])
    d = doi.strip()
    if d.lower().startswith("http"):
        return d
    return f"https://doi.org/{d}"


def arxiv_id_from_doi(doi: str) -> str | None:
    m = re.search(r"10\.48550/\s*arXiv\.(\d{4}\.\d{4,5})", doi, re.I)
    if m:
        return m.group(1)
    return None


def arxiv_fetch(arxiv_id: str) -> dict | None:
    aid = arxiv_id.strip().replace("arxiv:", "")
    url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(aid)}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=45) as resp:
        xml = resp.read()
    root = ET.fromstring(xml)
    entry = root.find("atom:entry", ATOM_NS)
    if entry is None:
        return None
    title_el = entry.find("atom:title", ATOM_NS)
    title = title_el.text.strip() if title_el is not None and title_el.text else ""
    published_el = entry.find("atom:published", ATOM_NS)
    pub = "1900-01-01"
    if published_el is not None and published_el.text:
        pub = published_el.text.strip()[:10]
    names = []
    for a in entry.findall("atom:author", ATOM_NS):
        ne = a.find("atom:name", ATOM_NS)
        if ne is not None and ne.text:
            names.append(ne.text.strip())
    link_el = None
    for link in entry.findall("atom:link", ATOM_NS):
        if link.get("rel") == "alternate" and link.get("type") == "text/html":
            link_el = link
            break
    if link_el is None:
        for link in entry.findall("atom:link", ATOM_NS):
            if link.get("href"):
                link_el = link
                break
    href = link_el.get("href") if link_el is not None else f"https://arxiv.org/abs/{aid}"
    return {
        "title": title,
        "date": pub,
        "authors": ", ".join(names),
        "url": href,
        "arxiv_id": aid,
    }


def write_md(
    *,
    date_iso: str,
    slug_suffix: str,
    title: str,
    venue: str,
    authors: str,
    paperurl: str,
    citation: str,
    extra_body: str,
) -> None:
    front = [
        "---",
        f"title: '{yaml_sq(title)}'",
        "collection: publications",
        "category: preprints",
        f"permalink: /publication/{date_iso}-pp-{slug_suffix}",
        f"date: {date_iso}",
        f"venue: '{yaml_sq(venue)}'",
    ]
    if paperurl:
        front.append(f"paperurl: '{yaml_sq(paperurl)}'")
    front.append(f"citation: '{yaml_sq(citation)}'")
    front.extend(["---", "", extra_body.strip(), ""])
    path = PUB_DIR / f"{date_iso}-pp-{slug_suffix}.md"
    path.write_text("\n".join(front), encoding="utf-8")


def build_citation(authors: str, year: str, title: str, venue: str) -> str:
    tq = html_esc(title)
    v = html_esc(venue)
    return f'{html_esc(authors)} ({year}). &quot;{tq}&quot; <i>{v}</i>.'


def sync_doi(doi: str) -> None:
    doi = doi.strip()
    if not doi or doi.startswith("#"):
        return
    if doi.lower().startswith("https://doi.org/"):
        doi = doi[16:]

    msg = crossref_fetch(doi)
    if msg is None:
        aid = arxiv_id_from_doi(doi)
        if aid:
            meta = arxiv_fetch(aid)
            if meta:
                slug = f"arxiv-{meta['arxiv_id'].replace('.', '-')}"
                year = meta["date"][:4]
                cite = build_citation(
                    meta["authors"],
                    year,
                    meta["title"],
                    "arXiv preprint",
                )
                url = meta["url"]
                if not url.startswith("http"):
                    url = f"https://arxiv.org/abs/{meta['arxiv_id']}"
                write_md(
                    date_iso=meta["date"],
                    slug_suffix=slug,
                    title=meta["title"],
                    venue="arXiv preprint",
                    authors=meta["authors"] or "—",
                    paperurl=f"https://doi.org/{doi}" if doi else url,
                    citation=cite,
                    extra_body=f"Synced from arXiv (DOI [{doi}](https://doi.org/{doi})).",
                )
                return
        print(f"[preprint] skip DOI (not in Crossref / arXiv): {doi}", file=sys.stderr)
        return

    title = crossref_title(msg)
    if not title:
        print(f"[preprint] skip DOI (no title): {doi}", file=sys.stderr)
        return
    date_iso = crossref_date(msg)
    venue = crossref_venue(msg)
    authors = crossref_authors(msg) or "—"
    year = date_iso[:4]
    purl = crossref_url(msg, doi)
    cite = build_citation(authors, year, title, venue)
    slug = re.sub(r"[^a-z0-9]+", "-", doi.lower()).strip("-")[:72]
    write_md(
        date_iso=date_iso,
        slug_suffix=f"doi-{slug}",
        title=title,
        venue=venue,
        authors=authors,
        paperurl=purl,
        citation=cite,
        extra_body=f"Metadata from [Crossref](https://doi.org/{doi}) (auto-generated).",
    )


def sync_arxiv_id(aid: str) -> None:
    aid = aid.strip()
    if not aid or aid.startswith("#"):
        return
    meta = arxiv_fetch(aid)
    if not meta:
        print(f"[preprint] skip arXiv id: {aid}", file=sys.stderr)
        return
    slug = f"arxiv-{meta['arxiv_id'].replace('.', '-')}"
    year = meta["date"][:4]
    cite = build_citation(
        meta["authors"],
        year,
        meta["title"],
        "arXiv preprint",
    )
    write_md(
        date_iso=meta["date"],
        slug_suffix=slug,
        title=meta["title"],
        venue="arXiv preprint",
        authors=meta["authors"] or "—",
        paperurl=meta["url"],
        citation=cite,
        extra_body=f"Metadata from [arXiv](https://arxiv.org/abs/{meta['arxiv_id']}) (auto-generated).",
    )


def main() -> int:
    if not DATA_PATH.is_file():
        remove_generated()
        print("[preprint] no _data/preprint_sources.json; removed stale *-pp-*.md", file=sys.stderr)
        return 0
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    dois = raw.get("dois") or []
    arxiv_ids = raw.get("arxiv_ids") or []
    if not isinstance(dois, list):
        dois = []
    if not isinstance(arxiv_ids, list):
        arxiv_ids = []

    remove_generated()
    for d in dois:
        sync_doi(str(d))
    for a in arxiv_ids:
        sync_arxiv_id(str(a))

    print(
        f"[preprint] wrote {len(list(PUB_DIR.glob('*-pp-*.md')))} file(s) from sources",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
