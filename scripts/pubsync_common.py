#!/usr/bin/env python3
"""Shared helpers for the publication sync scripts.

Both sync scripts regenerate a set of files under _publications/. The important
rule they share: **never delete the old set before the new set is known good.**
An empty or malformed API response must leave the site exactly as it was, not
wipe the publication list. `apply_generated()` enforces that.

Everything that talks to the network goes through `http_get()` here, so the
retry policy, the User-Agent and the timeout are decided in one place. The two
scripts used to carry their own copies, and the copies had drifted: the preprint
one did not retry a dropped connection at all, and its requests to researchmap
never carried the contact address.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUB_DIR = REPO_ROOT / "_publications"


# ------------------------------------------------------------------ logging


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def annotate(level: str, msg: str) -> None:
    """Log a warning or error, and surface it in the Actions run summary.

    GitHub picks `::warning::` / `::error::` lines up from stdout. Outside
    Actions only the log line is written.
    """
    log(f"{level.upper()}: {msg}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level}::{msg}", flush=True)


# --------------------------------------------------------------------- HTTP

RETRY_ATTEMPTS = 5
RETRY_DELAYS = (3.0, 6.0, 12.0, 24.0)   # pauses between attempts, seconds
RETRY_MAX_WAIT = 90.0                    # cap on a server's Retry-After
TRANSIENT_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
_sleep = time.sleep  # replaced in tests


def user_agent() -> str:
    """Identify the site to the APIs. A contact address, when configured, puts
    the requests in Crossref's and DataCite's polite pools."""
    mail = (os.environ.get("CROSSREF_CONTACT_EMAIL") or "").strip()
    base = "gdac-lab-site/1.0 (https://github.com/gdac-lab/gdac-lab.github.io)"
    return f"{base}; mailto:{mail}" if mail else base


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    raw = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def http_get(
    url: str,
    *,
    accept: str = "application/json",
    timeout: float = 60.0,
    tag: str = "http",
) -> bytes:
    """GET `url`, retrying the failures that are worth retrying.

    Retried, with a growing pause: a dropped or reset connection, a timeout, a
    DNS or connect failure, and HTTP 408/425/429/5xx (a Retry-After header is
    honoured, up to RETRY_MAX_WAIT). Any other HTTP status is raised at once as
    urllib.error.HTTPError, so a caller can read 404 as "not held here" and 406
    as "refused". When the retries are used up, SyncAbort is raised with the
    last problem in one line rather than a traceback.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": user_agent(), "Accept": accept}
    )
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        wait_hint: float | None = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in TRANSIENT_HTTP:
                raise
            problem = f"HTTP {exc.code}"
            wait_hint = _retry_after(exc)
        except urllib.error.URLError as exc:
            problem = f"unreachable ({exc.reason})"
        except (http.client.HTTPException, OSError) as exc:
            # RemoteDisconnected, IncompleteRead, a reset or a read timeout:
            # urllib lets these through without wrapping them in URLError.
            problem = type(exc).__name__ + (f": {exc}" if str(exc) else "")

        if attempt == RETRY_ATTEMPTS:
            raise SyncAbort(f"{url} failed {RETRY_ATTEMPTS} times; last: {problem}")
        wait = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)) - 1]
        if wait_hint is not None:
            wait = min(max(wait, wait_hint), RETRY_MAX_WAIT)
        log(f"[{tag}] {problem}; retry {attempt}/{RETRY_ATTEMPTS - 1} in {wait:.0f}s ({url})")
        _sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def http_get_json(url: str, *, timeout: float = 60.0, tag: str = "http") -> object:
    """`http_get` for a JSON API. A body that is not JSON is a SyncAbort."""
    body = http_get(url, accept="application/json", timeout=timeout, tag=tag)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SyncAbort(f"{url} returned a body that is not JSON: {exc}") from exc


# -------------------------------------------------------------------- text


def yaml_sq(s: object) -> str:
    """Escape a value for a YAML single-quoted scalar."""
    return str(s).replace("'", "''")


def html_esc(s: object) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# Hiragana / Katakana / CJK ideographs
_JA_RE = re.compile(r"[぀-ヿ一-鿿]")


def title_language(title: str) -> str:
    """Rough language tag used to decide which publication list an entry joins."""
    return "ja" if title and _JA_RE.search(title) else "en"


def iso_day(raw: object, *, allow_year: bool = False) -> str | None:
    """Normalise a date to YYYY-MM-DD.

    Accepts YYYY-MM-DD (a longer timestamp is cut to its day), YYYY-MM (day 1)
    and, when `allow_year` is set, a bare YYYY (January 1). Anything else is
    None: the caller decides whether that means "report and skip" or "fall
    back", rather than a made-up date going into a file name.
    """
    text = str(raw or "").strip()
    m = re.match(r"\d{4}-\d{2}-\d{2}", text)
    if m:
        return m.group(0)
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return f"{text}-01"
    if allow_year and re.fullmatch(r"\d{4}", text):
        return f"{text}-01-01"
    return None


def build_citation(authors: str, year: str, title: str, venue: str) -> str:
    return (
        f"{html_esc(authors)} ({year}). "
        f"&quot;{html_esc(title)}&quot; <i>{html_esc(venue)}</i>."
    )


def front_matter(fields: list[tuple[str, object]]) -> str:
    """Render front matter. Values of None/'' are dropped; lists become YAML lists."""
    lines = ["---"]
    for key, value in fields:
        if value is None or value == "":
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {yaml_sq(v)}" for v in value)
        elif isinstance(value, str) and key in ("collection", "category", "lang", "permalink", "date"):
            lines.append(f"{key}: {value}")  # simple scalars, no quoting needed
        else:
            lines.append(f"{key}: '{yaml_sq(value)}'")
    lines.append("---")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------- files


class SyncAbort(RuntimeError):
    """Raised when a sync result is too suspect to apply, or a fetch gave up."""


def apply_generated(
    *,
    pattern: str,
    generated: dict[str, str],
    min_expected: int = 1,
    shrink_floor: float = 0.5,
    allow_shrink: bool = False,
) -> tuple[int, int, int]:
    """Replace every PUB_DIR file matching `pattern` with `generated`.

    `generated` maps filename -> file content. Files matching `pattern` that are
    absent from `generated` are deleted; everything else is left alone.

    Refuses to apply (raises SyncAbort) when the new set looks like a failed
    fetch rather than a real change:
      * fewer than `min_expected` records, or
      * a drop to below `shrink_floor` of the previous count.
    `allow_shrink` (SYNC_ALLOW_SHRINK=1) overrides the shrink guard for the
    legitimate case of genuinely removing records.

    Returns (written, deleted, unchanged).
    """
    existing = {p.name: p for p in PUB_DIR.glob(pattern)}

    if len(generated) < min_expected:
        raise SyncAbort(
            f"refusing to apply: got {len(generated)} record(s), expected at least "
            f"{min_expected}. Leaving {len(existing)} existing file(s) untouched."
        )

    if existing and not allow_shrink:
        ratio = len(generated) / len(existing)
        if ratio < shrink_floor:
            raise SyncAbort(
                f"refusing to apply: record count would fall from {len(existing)} to "
                f"{len(generated)} ({ratio:.0%}). Re-run with SYNC_ALLOW_SHRINK=1 if this "
                f"is intentional."
            )

    PUB_DIR.mkdir(parents=True, exist_ok=True)
    written = unchanged = 0
    for name, content in sorted(generated.items()):
        path = PUB_DIR / name
        if path.exists() and path.read_text(encoding="utf-8") == content:
            unchanged += 1
            continue
        path.write_text(content, encoding="utf-8")
        written += 1

    deleted = 0
    for name, path in sorted(existing.items()):
        if name not in generated:
            path.unlink()
            deleted += 1

    return written, deleted, unchanged


def allow_shrink_from_env() -> bool:
    return (os.environ.get("SYNC_ALLOW_SHRINK") or "").strip().lower() in ("1", "true", "yes")
