#!/usr/bin/env python3
# Fetch published papers from researchmap Web API and write academicpages-compatible
# Markdown files under _publications/. See https://api.researchmap.jp/ (public read).
# Profile: https://researchmap.jp/satoshi-nakano

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

API_ROOT = "https://api.researchmap.jp"

# Maps researchmap published_paper_type -> _config publication_category key
TYPE_TO_CATEGORY = {
    "scientific_journal": "manuscripts",
    "international_journal": "manuscripts",
    "national_journal": "manuscripts",
    "international_conference_proceedings": "conferences",
    "national_conference_proceedings": "conferences",
    "international_conference_paper": "conferences",
    "national_conference_paper": "conferences",
    "international_conference": "conferences",
    "national_conference": "conferences",
    "book": "books",
    "book_chapter": "books",
}


def yaml_single_quote(s: str) -> str:
    """Escape for YAML single-quoted scalars."""
    return str(s).replace("'", "''")


def html_escape_attr(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def paper_language(paper_title: dict | None) -> str:
    """Primary record language for display grouping (en if any English title exists)."""
    if not paper_title or not isinstance(paper_title, dict):
        return "en"
    if (paper_title.get("en") or "").strip():
        return "en"
    if (paper_title.get("ja") or "").strip():
        return "ja"
    return "en"


def pick_localized(obj: dict | None, prefer: tuple[str, ...] = ("en", "ja")) -> str:
    if not obj or not isinstance(obj, dict):
        return ""
    for lang in prefer:
        v = obj.get(lang)
        if v:
            return str(v).strip()
    for v in obj.values():
        if v:
            return str(v).strip()
    return ""


def format_authors(item: dict) -> str:
    authors = item.get("authors") or {}
    if not isinstance(authors, dict):
        return ""
    for lang in ("en", "ja"):
        lst = authors.get(lang)
        if isinstance(lst, list) and lst:
            names = [x.get("name", "").strip() for x in lst if isinstance(x, dict)]
            return ", ".join(n for n in names if n)
    return ""


def normalize_date(pub_date: str | None, fallback: str | None) -> str:
    if not pub_date:
        if fallback:
            return normalize_date(fallback[:10], None)
        return "1900-01-01"
    pub_date = str(pub_date).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub_date):
        return pub_date
    if re.fullmatch(r"\d{4}-\d{2}", pub_date):
        return f"{pub_date}-01"
    if re.fullmatch(r"\d{4}", pub_date):
        return f"{pub_date}-01-01"
    return pub_date[:10] if len(pub_date) >= 10 else "1900-01-01"


def paper_url_from_item(item: dict) -> str:
    see = item.get("see_also") or []
    if isinstance(see, list):
        for entry in see:
            if not isinstance(entry, dict):
                continue
            if entry.get("label") == "doi" and entry.get("@id"):
                return str(entry["@id"])
            if entry.get("label") == "url" and entry.get("@id"):
                return str(entry["@id"])
    ids = item.get("identifiers") or {}
    if isinstance(ids, dict):
        dois = ids.get("doi")
        if isinstance(dois, list) and dois:
            return f"https://doi.org/{dois[0]}"
    return ""


def venue_line(item: dict) -> str:
    pub_name = pick_localized(item.get("publication_name"))
    publisher = pick_localized(item.get("publisher"))
    vol = item.get("volume")
    sp, ep = item.get("starting_page"), item.get("ending_page")
    bits = []
    if pub_name:
        bits.append(pub_name)
    elif publisher:
        bits.append(publisher)
    if vol:
        bits.append(f"vol. {vol}")
    if sp and ep:
        bits.append(f"pp. {sp}–{ep}")
    elif sp:
        bits.append(f"p. {sp}")
    return ". ".join(bits) if bits else publisher or pub_name or "Unknown venue"


def build_citation(item: dict, title: str, authors: str, venue: str, year: str) -> str:
    tq = html_escape_attr(title)
    v = html_escape_attr(venue)
    cite = f'{html_escape_attr(authors)} ({year}). &quot;{tq}&quot; <i>{v}</i>.'
    return cite


def category_for(item: dict) -> str:
    t = item.get("published_paper_type") or ""
    if t in TYPE_TO_CATEGORY:
        return TYPE_TO_CATEGORY[t]
    if item.get("referee") and not item.get("publisher"):
        return "manuscripts"
    return "conferences"


def fetch_items(slug: str) -> list[dict]:
    url = f"{API_ROOT}/{slug}/published_papers?limit=200&start=1"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    items = data.get("items") or []
    if not isinstance(items, list):
        return []
    return items


def write_publication(repo_root: Path, item: dict, slug: str) -> None:
    rm_id = str(item.get("rm:id") or "").strip()
    if not rm_id:
        return

    title = pick_localized(item.get("paper_title"))
    if not title:
        return
    plang = paper_language(item.get("paper_title"))

    authors = format_authors(item)
    pub_raw = item.get("publication_date")
    fallback = item.get("rm:modified") or item.get("rm:created")
    date_iso = normalize_date(pub_raw, fallback)
    venue = venue_line(item)
    year = date_iso[:4]
    purl = paper_url_from_item(item)
    category = category_for(item)

    permalink = f"/publication/{date_iso}-rm-{rm_id}"
    cite = build_citation(item, title, authors or "Satoshi Nakano", venue, year)

    front = [
        "---",
        f"title: '{yaml_single_quote(title)}'",
        "collection: publications",
        f"category: {category}",
        f"lang: {plang}",
        f"permalink: {permalink}",
        f"date: {date_iso}",
    ]
    if venue:
        front.append(f"venue: '{yaml_single_quote(venue)}'")
    if purl:
        front.append(f"paperurl: '{yaml_single_quote(purl)}'")
    front.append(f"citation: '{yaml_single_quote(cite)}'")
    front.extend(["---", ""])

    body = (
        f"Metadata imported from [researchmap](https://researchmap.jp/{slug}) "
        f"(record `{rm_id}`)."
    )
    if purl:
        body += f" [DOI / link]({purl})."

    out = repo_root / "_publications" / f"{date_iso}-rm-{rm_id}.md"
    out.write_text("\n".join(front) + "\n" + body + "\n", encoding="utf-8")


def remove_generated(repo_root: Path) -> None:
    pub = repo_root / "_publications"
    for p in pub.glob("*-rm-*.md"):
        p.unlink()


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "satoshi-nakano"
    repo_root = Path(__file__).resolve().parent.parent
    items = fetch_items(slug)
    remove_generated(repo_root)
    for item in items:
        write_publication(repo_root, item, slug)
    print(f"Wrote {len(items)} publication(s) from researchmap/{slug}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
