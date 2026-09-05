#!/usr/bin/env python3
"""Regenerate _publications/*-rm-*.md from the researchmap Web API.

Usage:  python3 scripts/fetch_researchmap_publications.py [slug]

API: https://api.researchmap.jp/{slug}/published_papers  (public read)

Design notes
------------
* Everything is fetched and validated **before** any file is touched. A failed
  or empty response leaves the existing publication list untouched rather than
  deleting it (see pubsync_common.apply_generated).
* Results are paginated until the API stops returning new records, and the
  count is checked against the reported total. A short read is an error, not a
  silently truncated list.
* Permalinks are keyed on the researchmap record id alone. The publication date
  is metadata that researchmap does edit, and folding it into the URL meant a
  date correction silently moved the page. `redirect_from` keeps the previous
  date-based URL working.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pubsync_common import (  # noqa: E402
    SyncAbort,
    allow_shrink_from_env,
    apply_generated,
    build_citation,
    front_matter,
    log,
)

API_ROOT = "https://api.researchmap.jp"
PAGE_SIZE = 100
MAX_PAGES = 50
USER_AGENT = "gdac-lab-site/1.0 (https://github.com/gdac-lab/gdac-lab.github.io)"

# researchmap published_paper_type -> _config.yml publication_category key.
# Unknown types are reported rather than silently filed under "conferences".
TYPE_TO_CATEGORY = {
    "scientific_journal": "manuscripts",
    "international_journal": "manuscripts",
    "national_journal": "manuscripts",
    "joint_international_journal": "manuscripts",
    "joint_national_journal": "manuscripts",
    "in_book": "books",
    "book": "books",
    "book_chapter": "books",
    "international_conference_proceedings": "conferences",
    "national_conference_proceedings": "conferences",
    "international_conference_paper": "conferences",
    "national_conference_paper": "conferences",
    "international_conference": "conferences",
    "national_conference": "conferences",
    "symposium": "conferences",
    "summary_international_conference": "conferences",
    "summary_national_conference": "conferences",
    "research_institution": "manuscripts",
    "technical_report": "manuscripts",
    "doctoral_thesis": "manuscripts",
    "master_thesis": "manuscripts",
    "misc": "manuscripts",
}
DEFAULT_CATEGORY = "conferences"


def pick_localized(obj: object, prefer: tuple[str, ...] = ("en", "ja")) -> str:
    if not isinstance(obj, dict):
        return ""
    for lang in prefer:
        value = obj.get(lang)
        if value:
            return str(value).strip()
    for value in obj.values():
        if value:
            return str(value).strip()
    return ""


def record_language(paper_title: object) -> str:
    """Which language list this record belongs to.

    A record carrying an English title is shown on the English list; a
    Japanese-only record is shown on the Japanese list only.
    """
    if not isinstance(paper_title, dict):
        return "en"
    if (paper_title.get("en") or "").strip():
        return "en"
    if (paper_title.get("ja") or "").strip():
        return "ja"
    return "en"


def format_authors(item: dict) -> str:
    authors = item.get("authors")
    if not isinstance(authors, dict):
        return ""
    for lang in ("en", "ja"):
        entries = authors.get(lang)
        if isinstance(entries, list) and entries:
            names = [
                str(e.get("name", "")).strip()
                for e in entries
                if isinstance(e, dict) and str(e.get("name", "")).strip()
            ]
            if names:
                return ", ".join(names)
    return ""


def normalize_date(pub_date: object) -> str | None:
    """researchmap dates arrive as YYYY, YYYY-MM or YYYY-MM-DD. Anything else is unusable.

    Returns None when there is no usable date; callers report that rather than
    substituting a record's modification timestamp, which is not a publication
    date and silently mis-sorts the entry.
    """
    if not pub_date:
        return None
    text = str(pub_date).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return f"{text}-01"
    if re.fullmatch(r"\d{4}", text):
        return f"{text}-01-01"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    return m.group(0) if m else None


def paper_url(item: dict) -> str:
    """Prefer a DOI over a bare URL, wherever each appears in see_also."""
    see_also = item.get("see_also")
    if isinstance(see_also, list):
        for label in ("doi", "url"):
            for entry in see_also:
                if isinstance(entry, dict) and entry.get("label") == label and entry.get("@id"):
                    return str(entry["@id"]).strip()
    identifiers = item.get("identifiers")
    if isinstance(identifiers, dict):
        dois = identifiers.get("doi")
        if isinstance(dois, list) and dois:
            doi = str(dois[0]).strip()
            return doi if doi.startswith("http") else f"https://doi.org/{doi}"
    return ""


def venue_line(item: dict) -> str:
    name = pick_localized(item.get("publication_name")) or pick_localized(item.get("publisher"))
    bits = [name] if name else []
    volume = item.get("volume")
    if volume:
        bits.append(f"vol. {volume}")
    start, end = item.get("starting_page"), item.get("ending_page")
    if start and end:
        bits.append(f"pp. {start}–{end}")
    elif start:
        bits.append(f"p. {start}")
    # Comma-separated: periods here read as sentence breaks inside the venue.
    return ", ".join(bits) if bits else "Unknown venue"


def category_for(item: dict, unknown_types: set[str]) -> str:
    paper_type = str(item.get("published_paper_type") or "").strip()
    if paper_type in TYPE_TO_CATEGORY:
        return TYPE_TO_CATEGORY[paper_type]
    if paper_type:
        unknown_types.add(paper_type)
    return DEFAULT_CATEGORY


def fetch_items(slug: str) -> list[dict]:
    """Page through published_papers until every record has been retrieved."""
    collected: list[dict] = []
    seen_ids: set[str] = set()
    total_reported: int | None = None

    for page in range(MAX_PAGES):
        start = page * PAGE_SIZE + 1
        url = f"{API_ROOT}/{slug}/published_papers?limit={PAGE_SIZE}&start={start}"
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            raise SyncAbort(f"researchmap API returned HTTP {exc.code} for {url}") from exc
        except urllib.error.URLError as exc:
            raise SyncAbort(f"researchmap API unreachable ({exc.reason}) for {url}") from exc
        except json.JSONDecodeError as exc:
            raise SyncAbort(f"researchmap API returned non-JSON for {url}: {exc}") from exc

        if not isinstance(payload, dict):
            raise SyncAbort(f"researchmap API returned {type(payload).__name__}, expected object")

        if total_reported is None:
            for key in ("totalResults", "total_results", "rm:totalResults"):
                if isinstance(payload.get(key), int):
                    total_reported = payload[key]
                    break

        items = payload.get("items")
        if items is None:
            raise SyncAbort(f"researchmap response has no 'items' key (keys: {sorted(payload)})")
        if not isinstance(items, list):
            raise SyncAbort(f"researchmap 'items' is {type(items).__name__}, expected list")
        if not items:
            break

        new_on_page = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            rm_id = str(item.get("rm:id") or "").strip()
            if not rm_id or rm_id in seen_ids:
                continue
            seen_ids.add(rm_id)
            collected.append(item)
            new_on_page += 1

        if new_on_page == 0 or len(items) < PAGE_SIZE:
            break
    else:
        raise SyncAbort(f"pagination did not terminate after {MAX_PAGES} pages")

    if total_reported is not None and len(collected) < total_reported:
        raise SyncAbort(
            f"short read: got {len(collected)} record(s) but the API reports "
            f"{total_reported}. Refusing to publish a truncated list."
        )

    log(f"[researchmap] fetched {len(collected)} record(s)"
        + (f" (API total: {total_reported})" if total_reported is not None else ""))
    return collected


def render(item: dict, unknown_types: set[str], skipped: list[str]) -> tuple[str, str] | None:
    rm_id = str(item.get("rm:id") or "").strip()
    if not rm_id:
        skipped.append("record without rm:id")
        return None

    title = pick_localized(item.get("paper_title"))
    if not title:
        skipped.append(f"rm:{rm_id} has no title")
        return None

    date_iso = normalize_date(item.get("publication_date"))
    if date_iso is None:
        skipped.append(f"rm:{rm_id} ({title[:40]}) has no usable publication_date")
        return None

    authors = format_authors(item)
    venue = venue_line(item)
    year = date_iso[:4]
    citation = build_citation(authors or "Satoshi Nakano", year, title, venue)

    fields: list[tuple[str, object]] = [
        ("title", title),
        ("collection", "publications"),
        ("category", category_for(item, unknown_types)),
        ("lang", record_language(item.get("paper_title"))),
        ("permalink", f"/publication/rm-{rm_id}"),
        # Keeps the previous date-based URL working after the permalink change.
        ("redirect_from", [f"/publication/{date_iso}-rm-{rm_id}"]),
        ("date", date_iso),
        ("venue", venue),
        ("paperurl", paper_url(item)),
        ("authors", authors),
        ("citation", citation),
    ]
    return f"{date_iso}-rm-{rm_id}.md", front_matter(fields)


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "satoshi-nakano"
    try:
        items = fetch_items(slug)
    except SyncAbort as exc:
        log(f"[researchmap] ERROR: {exc}")
        return 1

    unknown_types: set[str] = set()
    skipped: list[str] = []
    generated: dict[str, str] = {}
    for item in items:
        rendered = render(item, unknown_types, skipped)
        if rendered:
            name, content = rendered
            generated[name] = content

    for note in skipped:
        log(f"[researchmap] skipped: {note}")
    if unknown_types:
        log(
            "[researchmap] WARNING: unmapped published_paper_type(s) filed under "
            f"'{DEFAULT_CATEGORY}': {', '.join(sorted(unknown_types))}. "
            "Add them to TYPE_TO_CATEGORY."
        )

    try:
        written, deleted, unchanged = apply_generated(
            pattern="*-rm-*.md",
            generated=generated,
            min_expected=1,
            allow_shrink=allow_shrink_from_env(),
        )
    except SyncAbort as exc:
        log(f"[researchmap] ERROR: {exc}")
        return 1

    log(
        f"[researchmap] {len(generated)} record(s) from researchmap/{slug}: "
        f"{written} written, {deleted} removed, {unchanged} unchanged"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
