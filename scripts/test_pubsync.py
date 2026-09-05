#!/usr/bin/env python3
"""Offline tests for the publication sync scripts.

Run: python3 scripts/test_pubsync.py

These cover the failure modes that actually broke the sync in production:
an empty/failed API response wiping the publication list, a truncated read,
a rate-limited preprint lookup dropping an entry, and dates leaking into
permalinks. Everything is driven from fixtures, so no network is required.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_researchmap_publications as rm  # noqa: E402
import pubsync_common as common  # noqa: E402
import sync_preprints_from_sources as pp  # noqa: E402


def paper(rm_id: str, *, title_en="A Paper", title_ja=None, date="2024-05-06",
          ptype="scientific_journal", see_also=None, name="J. Test") -> dict:
    titles: dict[str, str] = {}
    if title_en:
        titles["en"] = title_en
    if title_ja:
        titles["ja"] = title_ja
    return {
        "rm:id": rm_id,
        "paper_title": titles,
        "publication_date": date,
        "published_paper_type": ptype,
        "publication_name": {"en": name},
        "authors": {"en": [{"name": "A. Author"}, {"name": "B. Author"}]},
        "see_also": see_also if see_also is not None else [
            {"label": "doi", "@id": "https://doi.org/10.1000/xyz"}
        ],
    }


class TempPubDir(unittest.TestCase):
    """Point both modules at a scratch _publications directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.pub = Path(self._tmp.name) / "_publications"
        self.pub.mkdir(parents=True)
        self._saved = (common.PUB_DIR, pp.PUB_DIR)
        common.PUB_DIR = self.pub
        pp.PUB_DIR = self.pub

    def tearDown(self) -> None:
        common.PUB_DIR, pp.PUB_DIR = self._saved
        self._tmp.cleanup()

    def seed(self, *names: str) -> None:
        for n in names:
            (self.pub / n).write_text(f"---\ntitle: '{n}'\n---\n", encoding="utf-8")

    def names(self) -> set[str]:
        return {p.name for p in self.pub.glob("*.md")}


class TestApplyGenerated(TempPubDir):
    def test_empty_result_does_not_wipe_existing(self):
        """The bug that could have deleted every publication."""
        self.seed("a-rm-1.md", "b-rm-2.md")
        with self.assertRaises(common.SyncAbort):
            common.apply_generated(pattern="*-rm-*.md", generated={}, min_expected=1)
        self.assertEqual(self.names(), {"a-rm-1.md", "b-rm-2.md"})

    def test_large_shrink_is_refused(self):
        self.seed(*[f"p{i}-rm-{i}.md" for i in range(10)])
        with self.assertRaises(common.SyncAbort):
            common.apply_generated(
                pattern="*-rm-*.md", generated={"p0-rm-0.md": "x"}, min_expected=1
            )
        self.assertEqual(len(self.names()), 10)

    def test_shrink_allowed_with_override(self):
        self.seed(*[f"p{i}-rm-{i}.md" for i in range(10)])
        common.apply_generated(
            pattern="*-rm-*.md",
            generated={"p0-rm-0.md": "x"},
            min_expected=1,
            allow_shrink=True,
        )
        self.assertEqual(self.names(), {"p0-rm-0.md"})

    def test_renamed_record_leaves_no_duplicate(self):
        """A date correction renames the file; the old one must go."""
        self.seed("2024-01-01-rm-7.md")
        common.apply_generated(
            pattern="*-rm-*.md", generated={"2024-06-01-rm-7.md": "new"}, min_expected=1
        )
        self.assertEqual(self.names(), {"2024-06-01-rm-7.md"})

    def test_unrelated_files_untouched(self):
        self.seed("2024-01-01-rm-1.md", "2024-01-01-pp-arxiv-1.md", "hand-written.md")
        common.apply_generated(
            pattern="*-rm-*.md", generated={"2024-01-01-rm-1.md": "x"}, min_expected=1
        )
        self.assertIn("2024-01-01-pp-arxiv-1.md", self.names())
        self.assertIn("hand-written.md", self.names())


class TestResearchmapParsing(unittest.TestCase):
    def test_permalink_is_date_independent(self):
        a = rm.render(paper("42", date="2024-05-06"), set(), [])
        b = rm.render(paper("42", date="2024-11-30"), set(), [])
        self.assertIn("permalink: /publication/rm-42", a[1])
        self.assertIn("permalink: /publication/rm-42", b[1])

    def test_old_date_url_is_redirected(self):
        _, content = rm.render(paper("42", date="2024-05-06"), set(), [])
        self.assertIn("- /publication/2024-05-06-rm-42", content)

    def test_doi_preferred_over_url_regardless_of_order(self):
        item = paper("1", see_also=[
            {"label": "url", "@id": "https://example.org/page"},
            {"label": "doi", "@id": "https://doi.org/10.1000/real"},
        ])
        self.assertEqual(rm.paper_url(item), "https://doi.org/10.1000/real")

    def test_bare_doi_identifier_is_expanded(self):
        item = paper("1", see_also=[])
        item["identifiers"] = {"doi": ["10.1000/bare"]}
        self.assertEqual(rm.paper_url(item), "https://doi.org/10.1000/bare")

    def test_partial_dates_normalise(self):
        self.assertEqual(rm.normalize_date("2024"), "2024-01-01")
        self.assertEqual(rm.normalize_date("2024-07"), "2024-07-01")
        self.assertEqual(rm.normalize_date("2024-07-09"), "2024-07-09")

    def test_missing_date_is_reported_not_invented(self):
        self.assertIsNone(rm.normalize_date(None))
        self.assertIsNone(rm.normalize_date(""))
        skipped: list[str] = []
        self.assertIsNone(rm.render(paper("9", date=None), set(), skipped))
        self.assertTrue(any("publication_date" in s for s in skipped))

    def test_unknown_paper_type_is_flagged(self):
        unknown: set[str] = set()
        rm.render(paper("1", ptype="totally_new_type"), unknown, [])
        self.assertIn("totally_new_type", unknown)

    def test_known_types_map_correctly(self):
        for ptype, expected in [
            ("scientific_journal", "manuscripts"),
            ("international_conference_proceedings", "conferences"),
            ("book", "books"),
        ]:
            self.assertEqual(rm.category_for({"published_paper_type": ptype}, set()), expected)

    def test_language_follows_available_titles(self):
        self.assertEqual(rm.record_language({"en": "T", "ja": "題"}), "en")
        self.assertEqual(rm.record_language({"ja": "題"}), "ja")

    def test_japanese_only_record_renders_as_ja(self):
        _, content = rm.render(paper("5", title_en=None, title_ja="日本語の題"), set(), [])
        self.assertIn("lang: ja", content)

    def test_apostrophe_in_title_is_escaped(self):
        _, content = rm.render(paper("6", title_en="Bell's Theorem"), set(), [])
        self.assertIn("title: 'Bell''s Theorem'", content)

    def test_venue_includes_volume_and_pages(self):
        item = paper("1")
        item.update({"volume": "12", "starting_page": "3", "ending_page": "9"})
        self.assertEqual(rm.venue_line(item), "J. Test. vol. 12. pp. 3–9")


class TestPagination(unittest.TestCase):
    """fetch_items must not publish a truncated list."""

    def _patch(self, pages, total=None):
        calls = {"n": 0}

        class FakeResp:
            def __init__(self, body):
                self._body = body
            def read(self):
                return self._body
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            idx = calls["n"]
            calls["n"] += 1
            body = {"items": pages[idx] if idx < len(pages) else []}
            if total is not None:
                body["totalResults"] = total
            return FakeResp(json.dumps(body).encode())

        return fake_urlopen, calls

    def test_multiple_pages_are_combined(self):
        page1 = [paper(str(i)) for i in range(rm.PAGE_SIZE)]
        page2 = [paper("x1"), paper("x2")]
        fake, _ = self._patch([page1, page2])
        orig = rm.urllib.request.urlopen
        rm.urllib.request.urlopen = fake
        try:
            items = rm.fetch_items("slug")
        finally:
            rm.urllib.request.urlopen = orig
        self.assertEqual(len(items), rm.PAGE_SIZE + 2)

    def test_short_read_against_reported_total_aborts(self):
        fake, _ = self._patch([[paper("1"), paper("2")]], total=99)
        orig = rm.urllib.request.urlopen
        rm.urllib.request.urlopen = fake
        try:
            with self.assertRaises(common.SyncAbort) as ctx:
                rm.fetch_items("slug")
        finally:
            rm.urllib.request.urlopen = orig
        self.assertIn("short read", str(ctx.exception))

    def test_http_error_aborts_cleanly(self):
        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 503, "busy", None, None)

        orig = rm.urllib.request.urlopen
        rm.urllib.request.urlopen = boom
        try:
            with self.assertRaises(common.SyncAbort):
                rm.fetch_items("slug")
        finally:
            rm.urllib.request.urlopen = orig

    def test_missing_items_key_aborts(self):
        class FakeResp:
            def read(self):
                return b'{"unexpected": true}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        orig = rm.urllib.request.urlopen
        rm.urllib.request.urlopen = lambda req, timeout=None: FakeResp()
        try:
            with self.assertRaises(common.SyncAbort):
                rm.fetch_items("slug")
        finally:
            rm.urllib.request.urlopen = orig


class TestPreprints(TempPubDir):
    def test_failed_lookup_keeps_existing_entry(self):
        """A rate-limited arXiv call must not drop the preprint."""
        existing = "2025-03-20-pp-arxiv-2503-16715.md"
        self.seed(existing)
        self.assertIsNotNone(pp.carry_forward("arxiv-2503-16715"))
        name, _ = pp.carry_forward("arxiv-2503-16715")
        self.assertEqual(name, existing)

    def test_slug_matches_between_render_and_carry_forward(self):
        """carry_forward can only work if both sides derive the same slug."""
        name, _ = pp.render(
            date_iso="2025-03-20", slug_suffix="arxiv-2503-16715", title="T",
            venue="arXiv preprint", authors="A", paperurl="https://arxiv.org/abs/2503.16715",
        )
        self.assertEqual(name, f"2025-03-20-pp-{pp.slug_for_source('arxiv', '2503.16715')}.md")

    def test_doi_slug_routes_arxiv_dois_to_arxiv_slug(self):
        self.assertEqual(
            pp.slug_for_source("doi", "10.48550/arXiv.2503.16715"), "arxiv-2503-16715"
        )

    def test_preprint_permalink_is_date_independent(self):
        _, content = pp.render(
            date_iso="2025-03-20", slug_suffix="arxiv-1", title="T",
            venue="arXiv preprint", authors="A", paperurl="u",
        )
        self.assertIn("permalink: /publication/pp-arxiv-1", content)
        self.assertIn("- /publication/2025-03-20-pp-arxiv-1", content)

    def test_crossref_date_parts(self):
        self.assertEqual(
            pp.crossref_date({"issued": {"date-parts": [[2024, 3]]}}), "2024-03-01"
        )
        self.assertEqual(pp.crossref_date({"issued": {"date-parts": [[2024]]}}), "2024-01-01")

    def test_crossref_authors_formatting(self):
        msg = {"author": [{"given": "Ada", "family": "Lovelace"}, {"family": "Turing"}]}
        self.assertEqual(pp.crossref_authors(msg), "Ada Lovelace, Turing")


class TestFrontMatter(unittest.TestCase):
    def test_empty_values_are_dropped(self):
        out = common.front_matter([("title", "T"), ("paperurl", ""), ("authors", None)])
        self.assertIn("title: 'T'", out)
        self.assertNotIn("paperurl", out)
        self.assertNotIn("authors", out)

    def test_list_renders_as_yaml_list(self):
        out = common.front_matter([("redirect_from", ["/a", "/b"])])
        self.assertIn("redirect_from:\n  - /a\n  - /b", out)

    def test_citation_escapes_html(self):
        cite = common.build_citation("A & B", "2024", 'He said "hi"', "V<x>")
        self.assertIn("A &amp; B", cite)
        self.assertIn("&quot;hi&quot;", cite)
        self.assertIn("V&lt;x&gt;", cite)


if __name__ == "__main__":
    unittest.main(verbosity=2)
