"""
extract_nces_detail_urls.py
- Parses NCES browse HTML and extracts all cipdetail URLs for CIP 2020 (y=56)
- Handles:
  - href values containing HTML-encoded ampersands (&amp;)
  - parameter order (y=56&cipid=XXXX or cipid=XXXX&y=56)
- Outputs:
  data/raw/nces/nces_cip2020_detail_urls.json
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup


BASE = "https://nces.ed.gov/ipeds/cipcode/"


def normalize_detail_url(href: str) -> str | None:
    """
    Normalize href into a canonical absolute URL:
      https://nces.ed.gov/ipeds/cipcode/cipdetail.aspx?y=56&cipid=XXXX
    Returns None if href is not a cipdetail link for y=56 with a cipid.
    """
    if not href:
        return None

    if "cipdetail.aspx" not in href.lower():
        return None

    abs_url = urljoin(BASE, href)

    u = urlparse(abs_url)
    qs = parse_qs(u.query)

    # Must be CIP 2020 for this milestone
    if qs.get("y", [""])[0] != "56":
        return None

    cipid = qs.get("cipid", [""])[0]
    if not cipid.isdigit():
        return None

    # Canonicalize ordering (y then cipid)
    canonical_qs = urlencode({"y": "56", "cipid": cipid})
    canonical = urlunparse((u.scheme, u.netloc, u.path, "", canonical_qs, ""))

    return canonical


def main() -> None:
    raw_dir = Path("data/raw/nces")
    html_path = raw_dir / "nces_cip2020_browse.html"
    if not html_path.exists():
        raise FileNotFoundError("Missing browse HTML. Run fetch_nces_index.py first.")

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    urls = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href")
        norm = normalize_detail_url(href)
        if norm:
            urls.add(norm)

    urls_list = sorted(urls)

    out_path = raw_dir / "nces_cip2020_detail_urls.json"
    out_path.write_text(
        json.dumps({"count": len(urls_list), "urls": urls_list}, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote: {out_path} ({len(urls_list)} URLs)")


if __name__ == "__main__":
    main()
