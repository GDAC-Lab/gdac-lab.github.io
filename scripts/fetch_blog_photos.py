#!/usr/bin/env python3
"""Pull every photo from the lab's Blogger album into a folder, with a manifest.

Usage:  python3 scripts/fetch_blog_photos.py --out blog-photos [--size 1200]

Reads the public JSON feed of https://gdaclab.blogspot.com/, walks each post's
HTML for <img> tags, requests each image at the given longest-side size
(Blogger honours an =sNNNN / /sNNNN/ size token), and writes

    <out>/pNN-MM.jpg          post NN (oldest = 01), image MM within the post
    <out>/manifest.json       date, title, post URL, caption, source URL, size
    <out>/posts.json          each post's text with the images marked in place

The lab wrote the blog, so this is its own material coming home; the script
only exists because the editing sandbox cannot reach blogspot.com.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

FEED = "https://gdaclab.blogspot.com/feeds/posts/default?alt=json&max-results=500"
UA = "gdac-lab-site/1.0 (+https://github.com/gdac-lab/gdac-lab.github.io)"


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sized(url: str, size: int) -> str:
    """Rewrite a Blogger image URL to request the longest side = size px."""
    url = html.unescape(url)
    if re.search(r"=s\d+(-[a-z0-9-]+)?$", url):
        return re.sub(r"=s\d+(-[a-z0-9-]+)?$", f"=s{size}", url)
    if re.search(r"=w\d+-h\d+(-[a-z0-9-]+)?$", url):
        return re.sub(r"=w\d+-h\d+(-[a-z0-9-]+)?$", f"=s{size}", url)
    if re.search(r"/s\d+(-[a-z0-9-]+)?/", url):
        return re.sub(r"/s\d+(-[a-z0-9-]+)?/", f"/s{size}/", url)
    if re.search(r"/w\d+-h\d+(-[a-z0-9-]+)?/", url):
        return re.sub(r"/w\d+-h\d+(-[a-z0-9-]+)?/", f"/s{size}/", url)
    if "googleusercontent.com" in url and "=" not in url.rsplit("/", 1)[-1]:
        # lh3-style URLs may carry ?width=NNN; the =sNNN form replaces it
        return url.split("?", 1)[0] + f"=s{size}"
    return url


def captions_by_image(content: str) -> dict[str, str]:
    """Blogger puts captions in a table: the <img> cell is followed by a
    td.tr-caption cell. Map image src -> caption text where that holds."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r'<img[^>]+src="([^"]+)"[^>]*>.*?<td[^>]*class="tr-caption"[^>]*>(.*?)</td>',
        content, flags=re.S | re.I,
    ):
        text = re.sub(r"<[^>]+>", "", m.group(2))
        out[html.unescape(m.group(1))] = html.unescape(text).strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="blog-photos")
    ap.add_argument("--size", type=int, default=1200)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    feed = json.loads(get(FEED).decode("utf-8"))["feed"]
    entries = feed.get("entry", [])
    total = feed.get("openSearch$totalResults", {}).get("$t")
    print(f"feed: {len(entries)} post(s), reported total {total}", file=sys.stderr)
    entries.sort(key=lambda e: e["published"]["$t"])  # oldest first, stable numbering

    try:
        from PIL import Image  # type: ignore
    except Exception:  # pragma: no cover
        Image = None

    manifest = []
    posts = []
    for pi, e in enumerate(entries, 1):
        title = html.unescape(e.get("title", {}).get("$t", "")).strip()
        date = e["published"]["$t"][:10]
        url = next((l["href"] for l in e.get("link", []) if l.get("rel") == "alternate"), "")
        content = e.get("content", {}).get("$t", "") or e.get("summary", {}).get("$t", "")
        caps = captions_by_image(content)
        # The post text, in reading order with the images marked, so a photo can
        # be matched to the sentence that introduces it.
        marked = re.sub(r'<img[^>]+src="([^"]+)"[^>]*>', lambda m: f" [IMG {html.unescape(m.group(1))[-24:]}] ", content, flags=re.I)
        marked = re.sub(r"<(br|/p|/div|/tr|/li|/h\d)[^>]*>", "\n", marked, flags=re.I)
        text = html.unescape(re.sub(r"<[^>]+>", "", marked))
        text = re.sub(r"[ \t\u3000]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text).strip()
        posts.append({"post": pi, "date": date, "title": title, "post_url": url, "text": text})
        srcs = []
        for m in re.finditer(r'<img[^>]+src="([^"]+)"', content, flags=re.I):
            s = html.unescape(m.group(1))
            # Blogger serves images from several Google hosts (blogger.googleusercontent.com,
            # lh3.googleusercontent.com, N.bp.blogspot.com); take any of them.
            if ("googleusercontent.com" in s or "blogspot.com" in s) and s not in srcs:
                srcs.append(s)
        for ii, s in enumerate(srcs, 1):
            name = f"p{pi:02d}-{ii:02d}.jpg"
            try:
                data = get(sized(s, args.size))
            except Exception as exc:
                print(f"skip {name}: {exc}", file=sys.stderr)
                continue
            w = h = None
            if Image is not None:
                try:
                    im = Image.open(BytesIO(data))
                    im = im.convert("RGB")
                    w, h = im.size
                    buf = BytesIO()
                    im.save(buf, "JPEG", quality=88, optimize=True)
                    data = buf.getvalue()
                except Exception as exc:
                    print(f"{name}: not decodable ({exc}); keeping bytes", file=sys.stderr)
            (out / name).write_bytes(data)
            manifest.append({
                "file": name, "post": pi, "date": date, "title": title, "post_url": url,
                "caption": caps.get(s, ""), "source": s, "width": w, "height": h, "bytes": len(data),
            })
            print(f"{name}  {date}  {w}x{h}  {len(data)//1024} KB  {title[:40]}", file=sys.stderr)

    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(manifest)} image(s) to {out}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
