#!/usr/bin/env python3
"""Shared helpers for the publication sync scripts.

Both sync scripts regenerate a set of files under _publications/. The important
rule they share: **never delete the old set before the new set is known good.**
An empty or malformed API response must leave the site exactly as it was, not
wipe the publication list. `apply_generated()` enforces that.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUB_DIR = REPO_ROOT / "_publications"


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


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


class SyncAbort(RuntimeError):
    """Raised when a sync result is too suspect to apply."""


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
