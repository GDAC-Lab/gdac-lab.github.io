#!/usr/bin/env python3
"""Offline tests for the publication sync scripts.

Run: python3 scripts/test_pubsync.py

These cover the failure modes that actually broke the sync in production:
an empty/failed API response wiping the publication list, a truncated read,
a rate-limited preprint lookup dropping an entry, and dates leaking into
permalinks. Everything is driven from fixtures, so no network is required.
"""

from __future__ import annotations

import http.client
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_cv_bib as cv  # noqa: E402
import fetch_researchmap_publications as rm  # noqa: E402
import pubsync_common as common  # noqa: E402
import sync_preprints_from_sources as pp  # noqa: E402


# No test may reach the network or sleep. A test that needs a response installs
# its own urlopen; anything that slips through fails at once with a clear
# message instead of hanging in real retries (which is what happened when a
# lookup table bound the fetch functions at import time).
def _no_network(req, timeout=None):
    raise AssertionError(f"unexpected network call in tests: {req.full_url}")


common.urllib.request.urlopen = _no_network
common._sleep = lambda seconds: None
pp._arxiv_throttle = lambda: None


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

    def test_venue_parts_are_comma_separated(self):
        """Periods between venue parts read as sentence breaks in the rendered list."""
        item = paper("1")
        item.update({"volume": "12", "starting_page": "3", "ending_page": "9"})
        self.assertEqual(rm.venue_line(item), "J. Test, vol. 12, pp. 3–9")

    def test_japanese_author_list_uses_fullwidth_comma(self):
        item = {"authors": {"en": [], "ja": [{"name": "小島豪介"}, {"name": "仲野聡史"}]}}
        self.assertEqual(rm.format_authors(item), "小島豪介，仲野聡史")

    def test_english_author_list_uses_comma_space(self):
        item = {"authors": {"en": [{"name": "A. Author"}, {"name": "B. Author"}]}}
        self.assertEqual(rm.format_authors(item), "A. Author, B. Author")

    def test_venue_single_page(self):
        item = paper("1")
        item.update({"starting_page": "7"})
        self.assertEqual(rm.venue_line(item), "J. Test, p. 7")


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
            raise urllib.error.HTTPError(req.full_url, 404, "no such slug", None, None)

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

    def test_arxiv_request_sends_an_accept_header(self):
        """The API answers 406 without one; that broke the sync on 2026-09-14."""
        seen = {}

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def read(self_inner):
                return b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"

        def fake_urlopen(req, timeout=60):
            seen["headers"] = dict(req.headers)
            return _Resp()

        real_open, real_throttle = common.urllib.request.urlopen, pp._arxiv_throttle
        common.urllib.request.urlopen, pp._arxiv_throttle = fake_urlopen, lambda: None
        try:
            pp.arxiv_fetch("2503.16715")
        finally:
            common.urllib.request.urlopen, pp._arxiv_throttle = real_open, real_throttle

        # urllib title-cases header names on the Request object.
        accept = seen["headers"].get("Accept", "")
        self.assertIn("atom+xml", accept)
        self.assertIn("User-agent", seen["headers"])

    def _main_with_failing_lookup(self, arxiv_ids):
        """Run main() with every lookup failing, against a scratch sources file."""
        def boom(_value):
            raise urllib.error.HTTPError(
                "https://export.arxiv.org/", 406, "Not Acceptable", {}, None
            )

        src = Path(self._tmp.name) / "preprint_sources.json"
        src.write_text(json.dumps({"dois": [], "arxiv_ids": arxiv_ids}), encoding="utf-8")
        saved = (pp.DATA_PATH, pp.resolve_arxiv, pp.resolve_doi)
        pp.DATA_PATH, pp.resolve_arxiv, pp.resolve_doi = src, boom, boom
        try:
            return pp.main()
        finally:
            pp.DATA_PATH, pp.resolve_arxiv, pp.resolve_doi = saved

    def test_carried_forward_entry_does_not_fail_the_run(self):
        """An upstream outage that loses nothing must not fail CI every week."""
        self.seed("2025-03-20-pp-arxiv-2503-16715.md")
        rc = self._main_with_failing_lookup(["2503.16715"])
        self.assertEqual(rc, 0)
        self.assertIn("2025-03-20-pp-arxiv-2503-16715.md", self.names())

    # A DataCite record as arXiv actually registers one.
    DATACITE = {
        "titles": [{"title": "A Constrained\n   Attitude Result"}],
        "dates": [{"date": "2026-01-02", "dateType": "Created"},
                  {"date": "2025-03-20", "dateType": "Issued"}],
        "publicationYear": 2025,
        "creators": [
            {"name": "Nakano, Satoshi", "nameType": "Personal",
             "givenName": "Satoshi", "familyName": "Nakano"},
            {"name": "Sakamoto, Noboru", "nameType": "Personal"},
        ],
    }

    @staticmethod
    def _arxiv_406(_aid):
        raise urllib.error.HTTPError(
            "https://export.arxiv.org/", 406, "Not Acceptable", {}, None
        )

    def test_arxiv_failure_falls_back_to_datacite(self):
        """arXiv has answered 406 from CI since 2026-09-14; 10.48550 is a DataCite prefix."""
        seen = {}

        def fake_datacite(doi):
            seen["doi"] = doi
            return self.DATACITE

        saved = (pp.arxiv_fetch, pp.datacite_fetch)
        pp.arxiv_fetch, pp.datacite_fetch = self._arxiv_406, fake_datacite
        try:
            name, content = pp.resolve_arxiv("2503.16715")
        finally:
            pp.arxiv_fetch, pp.datacite_fetch = saved

        self.assertEqual(seen["doi"], "10.48550/arXiv.2503.16715")
        # The slug must stay in the arXiv form, or the published URL moves and
        # carry_forward stops finding the existing file.
        self.assertEqual(name, "2025-03-20-pp-arxiv-2503-16715.md")
        self.assertIn("permalink: /publication/pp-arxiv-2503-16715", content)
        self.assertIn("https://arxiv.org/abs/2503.16715", content)
        self.assertIn("Satoshi Nakano, Noboru Sakamoto", content)
        self.assertIn("A Constrained Attitude Result", content)

    def test_standby_source_never_moves_a_published_date(self):
        """The 2026-09-21 regression: publicationYear renamed three files to Jan 1."""
        self.seed("2025-03-20-pp-arxiv-2503-16715.md")
        # Overwrite the seeded stub with a realistic front matter block.
        (self.pub / "2025-03-20-pp-arxiv-2503-16715.md").write_text(
            "---\ntitle: 'T'\npermalink: /publication/pp-arxiv-2503-16715\n"
            "date: 2025-03-20\n---\n",
            encoding="utf-8",
        )
        saved = (pp.arxiv_fetch, pp.datacite_fetch)
        pp.arxiv_fetch = self._arxiv_406
        pp.datacite_fetch = lambda _doi: {          # year only, as the real record was
            "titles": [{"title": "T"}],
            "publicationYear": 2025,
            "creators": [{"name": "Nakano, Satoshi"}],
        }
        try:
            name, content = pp.resolve_arxiv("2503.16715")
        finally:
            pp.arxiv_fetch, pp.datacite_fetch = saved

        self.assertEqual(name, "2025-03-20-pp-arxiv-2503-16715.md")
        self.assertIn("date: 2025-03-20", content)
        self.assertIn("- /publication/2025-03-20-pp-arxiv-2503-16715", content)

    def test_datacite_date_reads_any_dated_entry(self):
        """Only fall back to the year when no dates[] entry carries a day."""
        self.assertEqual(
            pp.datacite_date({"dates": [{"date": "2025-03-20", "dateType": "Other"}],
                              "publicationYear": 2025}),
            "2025-03-20",
        )
        self.assertEqual(
            pp.datacite_date({"published": "2025-03-20", "publicationYear": 2025}),
            "2025-03-20",
        )
        self.assertEqual(pp.datacite_date({"dates": [], "publicationYear": 2025}), "2025-01-01")

    def test_crossref_is_tried_when_datacite_has_nothing(self):
        saved = (pp.arxiv_fetch, pp.datacite_fetch, pp.crossref_fetch)
        pp.arxiv_fetch = self._arxiv_406
        pp.datacite_fetch = lambda _doi: None
        pp.crossref_fetch = lambda _doi: {
            "title": ["Fallback Title"],
            "issued": {"date-parts": [[2025, 3, 20]]},
            "author": [{"given": "Satoshi", "family": "Nakano"}],
        }
        try:
            name, _ = pp.resolve_arxiv("2503.16715")
        finally:
            pp.arxiv_fetch, pp.datacite_fetch, pp.crossref_fetch = saved
        self.assertEqual(name, "2025-03-20-pp-arxiv-2503-16715.md")

    def test_datacite_field_extraction(self):
        self.assertEqual(pp.datacite_title(self.DATACITE), "A Constrained Attitude Result")
        # Issued wins over Created even though Created comes first in the list.
        self.assertEqual(pp.datacite_date(self.DATACITE), "2025-03-20")
        self.assertEqual(
            pp.datacite_authors(self.DATACITE), "Satoshi Nakano, Noboru Sakamoto"
        )
        self.assertEqual(pp.datacite_date({"publicationYear": 2024}), "2024-01-01")
        self.assertEqual(
            pp.datacite_authors({"creators": [{"name": "arXiv", "nameType": "Organizational"}]}),
            "arXiv",
        )

    def test_lookup_with_nothing_to_fall_back_on_fails_the_run(self):
        """No existing entry means the preprint is missing from the site."""
        rc = self._main_with_failing_lookup(["2604.04001"])
        self.assertEqual(rc, 1)

    def test_slug_matches_between_render_and_carry_forward(self):
        """carry_forward can only work if both sides derive the same slug."""
        name, _ = pp.render(
            date_iso="2025-03-20", slug_suffix="arxiv-2503-16715", title="T",
            venue="arXiv preprint", authors="A", paperurl="https://arxiv.org/abs/2503.16715",
        )
        self.assertEqual(name, f"2025-03-20-pp-{pp.slug_for_source('arxiv', '2503.16715')}.md")

    def test_arxiv_doi_is_resolved_as_its_arxiv_id(self):
        """A dois: entry of 10.48550/arXiv.* must get DataCite too, not just arXiv."""
        seen = {}
        saved = pp.resolve_arxiv
        pp.resolve_arxiv = lambda aid: seen.setdefault("aid", aid) and ("f", "c")
        try:
            out = pp.resolve_doi("https://doi.org/10.48550/arXiv.2503.16715")
        finally:
            pp.resolve_arxiv = saved
        self.assertEqual(seen["aid"], "2503.16715")
        self.assertEqual(out, ("f", "c"))

    def test_every_source_kind_shares_one_slug_rule(self):
        for kind, value in (
            ("arxiv", "2503.16715"),
            ("arxiv", "arxiv:2503.16715"),
            ("doi", "10.48550/arXiv.2503.16715"),
            ("doi", "https://doi.org/10.48550/arXiv.2503.16715"),
        ):
            self.assertEqual(pp.slug_for_source(kind, value), "arxiv-2503-16715", (kind, value))
        self.assertEqual(pp.slug_for_source("doi", "10.1000/A.B"), "doi-10-1000-a-b")

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


class TestRetry(unittest.TestCase):
    """A researchmap blip is retried; a permanent error or a real outage aborts cleanly."""

    class _Resp:
        def __init__(self, body: dict):
            self._body = json.dumps(body).encode()
        def read(self):
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fetch(self, urlopen):
        """Run fetch_items with `urlopen` in place and sleeps recorded, not slept."""
        sleeps: list[float] = []
        orig_open, orig_sleep = common.urllib.request.urlopen, common._sleep
        common.urllib.request.urlopen, common._sleep = urlopen, sleeps.append
        try:
            return rm.fetch_items("slug"), sleeps
        finally:
            common.urllib.request.urlopen, common._sleep = orig_open, orig_sleep

    def test_dropped_connection_is_retried(self):
        calls = {"n": 0}

        def flaky(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise http.client.RemoteDisconnected(
                    "Remote end closed connection without response")
            return self._Resp({"items": [paper("1")], "totalResults": 1})

        items, sleeps = self._fetch(flaky)
        self.assertEqual([i["rm:id"] for i in items], ["1"])
        self.assertEqual(calls["n"], 2)
        self.assertEqual(sleeps, [common.RETRY_DELAYS[0]])

    def test_server_error_is_retried(self):
        calls = {"n": 0}

        def busy_once(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(req.full_url, 503, "busy", None, None)
            return self._Resp({"items": [paper("1")]})

        items, sleeps = self._fetch(busy_once)
        self.assertEqual(len(items), 1)
        self.assertEqual(len(sleeps), 1)

    def test_persistent_disconnect_aborts_without_traceback(self):
        calls = {"n": 0}

        def dead(req, timeout=None):
            calls["n"] += 1
            raise http.client.RemoteDisconnected(
                "Remote end closed connection without response")

        with self.assertRaises(common.SyncAbort) as ctx:
            self._fetch(dead)
        self.assertEqual(calls["n"], common.RETRY_ATTEMPTS)
        self.assertIn("RemoteDisconnected", str(ctx.exception))

    def test_pauses_grow_between_attempts(self):
        def dead(req, timeout=None):
            raise TimeoutError("timed out")

        sleeps: list[float] = []
        orig_open, orig_sleep = common.urllib.request.urlopen, common._sleep
        common.urllib.request.urlopen, common._sleep = dead, sleeps.append
        try:
            with self.assertRaises(common.SyncAbort):
                rm.fetch_items("slug")
        finally:
            common.urllib.request.urlopen, common._sleep = orig_open, orig_sleep
        self.assertEqual(sleeps, list(common.RETRY_DELAYS[:common.RETRY_ATTEMPTS - 1]))

    def test_retry_after_is_honoured_up_to_the_cap(self):
        calls = {"n": 0}

        def throttled(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                hdrs = {"Retry-After": "600"}
                raise urllib.error.HTTPError(req.full_url, 429, "slow down", hdrs, None)
            return self._Resp({"items": [paper("1")]})

        _, sleeps = self._fetch(throttled)
        self.assertEqual(sleeps, [common.RETRY_MAX_WAIT])

    def test_preprint_lookups_share_the_retry(self):
        """The preprint script used to give up on the first dropped connection."""
        calls = {"n": 0}

        class _Json:
            def read(self_inner):
                return json.dumps({"status": "ok", "message": {"title": ["T"]}}).encode()
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False

        def flaky(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise http.client.RemoteDisconnected("gone")
            return _Json()

        sleeps: list[float] = []
        orig_open, orig_sleep = common.urllib.request.urlopen, common._sleep
        common.urllib.request.urlopen, common._sleep = flaky, sleeps.append
        try:
            msg = pp.crossref_fetch("10.1000/x")
        finally:
            common.urllib.request.urlopen, common._sleep = orig_open, orig_sleep
        self.assertEqual(msg, {"title": ["T"]})
        self.assertEqual(calls["n"], 2)

    def test_not_found_is_not_retried(self):
        calls = {"n": 0}

        def missing(req, timeout=None):
            calls["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 404, "no such slug", None, None)

        with self.assertRaises(common.SyncAbort):
            self._fetch(missing)
        self.assertEqual(calls["n"], 1)


def crossref(title, container, authors, *, year=2022, page=None, number=None,
             volume=None, issue=None, event=None, publisher="IEEE"):
    """A Crossref work message shaped like the real ones."""
    msg = {
        "title": [title],
        "container-title": [container],
        "author": [{"given": g, "family": f} for g, f in authors],
        "issued": {"date-parts": [[year, 10]]},
        "publisher": publisher,
    }
    for key, value in (("page", page), ("article-number", number), ("volume", volume),
                       ("issue", issue), ("event", event)):
        if value is not None:
            msg[key] = value
    return msg


class TestCvBib(unittest.TestCase):
    """The English CV's .bib files: the list from researchmap, details from Crossref."""

    ME = ("Satoshi", "Nakano")

    def _build(self, items, answers, previous=None):
        """Run cv.build with Crossref answering from `answers` (doi -> msg or exception)."""
        def fake(doi):
            answer = answers.get(doi)
            if isinstance(answer, Exception):
                raise answer
            return answer

        saved = cv.crossref_fetch
        cv.crossref_fetch = fake
        try:
            return cv.build(items, previous or {})
        finally:
            cv.crossref_fetch = saved

    @staticmethod
    def _item(rm_id, *, doi="10.1000/x", date="2022-08-01", ptype="scientific_journal",
              title_en="A Paper", title_ja=None):
        item = paper(rm_id, title_en=title_en, title_ja=title_ja, date=date, ptype=ptype,
                     see_also=[{"label": "doi", "@id": f"https://doi.org/{doi}"}] if doi else [])
        return item

    def test_journal_entry_matches_the_hand_made_file(self):
        msg = crossref(
            "Design Method of Tuned Mass Damper by Linear-Matrix-Inequality-Based Robust "
            "Control Theory for Seismic Excitation", "Journal of Vibration and Acoustics",
            [("Kou", "Miyamoto"), self.ME, ("Qing-Long", "Han")],
            number="041008", volume="144", issue="4", publisher="ASME International")
        sections, notes = self._build([self._item("36586866", doi="10.1115/1.4053544")],
                                      {"10.1115/1.4053544": msg})
        self.assertEqual(notes, [])
        self.assertEqual(sections["proceedings"], [])
        self.assertEqual(sections["journals"][0], (
            "@article{rm36586866,\n"
            "  title = {Design Method of Tuned Mass Damper by Linear-Matrix-Inequality-Based "
            "Robust Control Theory for Seismic Excitation},\n"
            "  author = {Miyamoto, Kou and {\\textbf{Nakano}}, {\\textbf{Satoshi}} and Han, Qing-Long},\n"
            "  year = {2022},\n"
            "  journal = {Journal of Vibration and Acoustics},\n"
            "  volume = {144},\n"
            "  number = {4},\n"
            "  pages = {041008},\n"
            "  doi = {10.1115/1.4053544}\n"
            "}\n"))

    def test_proceedings_entry_has_publisher_and_address(self):
        msg = crossref(
            "Attitude Constrained Control on SO(3): An Explicit Reference Governor Approach",
            "2018 IEEE Conference on Decision and Control (CDC)",
            [self.ME, ("Tam W.", "Nguyen")], year=2018, page="1833-1838",
            event={"name": "CDC", "location": "Miami Beach, FL"})
        sections, _ = self._build(
            [self._item("19751130", doi="10.1109/CDC.2018.8618908", ptype="international_conference_proceedings")],
            {"10.1109/CDC.2018.8618908": msg})
        text = sections["proceedings"][0]
        self.assertTrue(text.startswith("@inproceedings{rm19751130,\n"))
        self.assertIn("  title = {Attitude Constrained Control on ${SO(3)}$: An Explicit Reference Governor Approach},", text)
        self.assertIn("  booktitle = {2018 IEEE Conference on Decision and Control (CDC)},", text)
        self.assertIn("  pages = {1833--1838},", text)
        self.assertIn("  publisher = {IEEE},", text)
        self.assertIn("  address = {Miami Beach, FL},", text)
        self.assertNotIn("journal", text)

    def test_titles_keep_acronyms_through_unsrt(self):
        self.assertEqual(cv.title_tex("A Distributed Reference Governor for High-Order LTI Swarm Systems"),
                         "A Distributed Reference Governor for High-Order {LTI} Swarm Systems")
        self.assertEqual(cv.title_tex("Wind-Load Estimation with Equivalent-Input-Disturbance Approach"),
                         "Wind-Load Estimation with Equivalent-Input-Disturbance Approach")
        self.assertEqual(cv.title_tex("CBF-Based iLQR for 3D and H2 & more_stuff"),
                         "{CBF}-Based {iLQR} for {3D} and {H2} \\& more\\_stuff")
        self.assertEqual(cv.title_tex("Control on <mml:math><mml:mi>SO</mml:mi><mml:mo>(</mml:mo>"
                                      "<mml:mn>3</mml:mn><mml:mo>)</mml:mo></mml:math> &amp; beyond"),
                         "Control on ${SO(3)}$ \\& beyond")
        # Each symbol in an element of its own, as in Crossref's record of the
        # Automatica paper, with namespace attributes and line breaks.
        self.assertEqual(cv.title_tex(
            'Explicit reference governor on <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML">'
            '\n<mml:mrow><mml:mi mathvariant="normal">S</mml:mi><mml:mi mathvariant="normal">O</mml:mi>'
            '\n<mml:mo stretchy="false">(</mml:mo><mml:mn>3</mml:mn><mml:mo stretchy="false">)</mml:mo>'
            '</mml:mrow></mml:math> for torque and pointing constraint management'),
            "Explicit reference governor on ${SO(3)}$ for torque and pointing constraint management")
        # Spaces inside the math's text stay; only the layout between elements goes.
        self.assertEqual(cv._clean("<math>\n<mtext>for all </mtext>\n<mi>x</mi>\n</math> holds"),
                         "for all x holds")

    def test_capitalised_names_are_printed_as_names(self):
        self.assertEqual(cv.name_tex("NAKANO", "SATOSHI"), "{\\textbf{Nakano}}, {\\textbf{Satoshi}}")
        self.assertEqual(cv.name_tex("SHE", "JINHUA"), "She, Jinhua")
        self.assertEqual(cv.name_tex("Nakano", "S."), "{\\textbf{Nakano}}, {\\textbf{S.}}")
        self.assertEqual(cv.name_tex("Nakano", "Kenji"), "Nakano, Kenji")
        self.assertEqual(cv.name_tex(None, None, "The Consortium"), "{The Consortium}")

    def test_selection_and_order(self):
        items = [
            self._item("1", date="2021-10-01", ptype="international_conference_proceedings", doi="10.1000/a"),
            self._item("2", date="2025-06-01", doi="10.1000/b"),
            self._item("3", date="2024-10-01", doi="10.1000/c"),
            self._item("4", title_en=None, title_ja="和文の論文", doi="10.1000/d"),   # Japanese only
            self._item("5", ptype="misc", doi="10.1000/e"),                          # not an article
            self._item("6", ptype="totally_new_type", doi="10.1000/f"),              # unknown type
        ]
        answers = {d: crossref(f"T{d}", "J", [self.ME]) for d in ("10.1000/a", "10.1000/b", "10.1000/c")}
        sections, notes = self._build(items, answers)
        self.assertEqual(notes, [])
        self.assertIn("doi = {10.1000/b}", sections["journals"][0])
        keys = {k: [e.split(",", 1)[0] for e in v] for k, v in sections.items()}
        self.assertEqual(keys, {"journals": ["@article{rm2", "@article{rm3"],
                                "proceedings": ["@inproceedings{rm1"]})

    def test_doi_is_found_wherever_researchmap_keeps_it(self):
        item = self._item("1", doi=None)
        item["see_also"] = [{"label": "url", "@id": "https://example.org/page"}]
        item["identifiers"] = {"doi": ["10.1115/1.4053544"]}
        self.assertEqual(cv.doi_of(item), "10.1115/1.4053544")
        self.assertIsNone(cv.doi_of(self._item("2", doi=None)))

    def test_record_without_doi_is_written_from_researchmap(self):
        item = self._item("39916160", doi=None, date="2022-05-01", ptype="international_conference_proceedings",
                          title_en="Linearization-Based Position Tracking Control")
        item.update(starting_page="1419", ending_page="1420",
                    publication_name={"en": "The 13th Asian Control Conference"},
                    authors={"en": [{"name": "Satoshi Nakano"}, {"name": "Yuya Hada"}]})
        sections, notes = self._build([item], {})
        self.assertEqual(notes, [])
        text = sections["proceedings"][0]
        self.assertIn("author = {{\\textbf{Nakano}}, {\\textbf{Satoshi}} and Hada, Yuya}", text)
        self.assertIn("booktitle = {The 13th Asian Control Conference}", text)
        self.assertIn("pages = {1419--1420}", text)
        self.assertIn("year = {2022}", text)

    def test_unreachable_crossref_keeps_the_previous_entry(self):
        previous = cv.read_entries(cv.render_file("journals", [
            "@article{rm7,\n  title = {Old but good},\n  year = {2020}\n}\n"]))
        sections, notes = self._build([self._item("7", doi="10.1000/g")],
                                      {"10.1000/g": common.SyncAbort("gone")}, previous)
        self.assertEqual(sections["journals"], ["@article{rm7,\n  title = {Old but good},\n  year = {2020}\n}\n"])
        self.assertIn("kept the previous entry", notes[0])

    def test_output_is_deterministic_and_has_no_stray_at_sign(self):
        items = [self._item("2", doi="10.1000/b"), self._item("3", doi="10.1000/c", date="2021-01-01")]
        answers = {d: crossref(f"T{d}", "J", [self.ME]) for d in ("10.1000/b", "10.1000/c")}
        first = {k: cv.render_file(k, v) for k, v in self._build(items, answers)[0].items()}
        second = {k: cv.render_file(k, v) for k, v in self._build(list(reversed(items)), answers)[0].items()}
        self.assertEqual(first, second)
        header = cv.HEADER.format(title="X")
        self.assertNotIn("@", header)
        self.assertIn("\\nocite{*}", header)

    def test_round_trip_reads_back_every_entry(self):
        items = [self._item(str(i), doi=f"10.1000/{i}") for i in range(5)]
        answers = {f"10.1000/{i}": crossref(f"T{i}", "J", [self.ME]) for i in range(5)}
        text = cv.render_file("journals", self._build(items, answers)[0]["journals"])
        self.assertEqual(sorted(cv.read_entries(text)), [f"rm{i}" for i in range(5)])


class TestIsoDay(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(common.iso_day("2024-07-09"), "2024-07-09")
        self.assertEqual(common.iso_day("2024-07-09T12:00:00Z"), "2024-07-09")
        self.assertEqual(common.iso_day("2024-07"), "2024-07-01")
        self.assertIsNone(common.iso_day("2024"))
        self.assertEqual(common.iso_day("2024", allow_year=True), "2024-01-01")
        self.assertIsNone(common.iso_day(""))
        self.assertIsNone(common.iso_day(None))
        self.assertIsNone(common.iso_day("July 2024"))


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
