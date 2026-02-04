"""
build_nces_cip2020.py
- Reads NCES CIP 2020 detail-page URLs (y=56) extracted from the NCES browse page
- Fetches each cipdetail page (with caching + polite throttling)
- Extracts:
  - CIP code (supports 2-digit, 4-digit, and 6-digit formats)
  - Title
  - Definition
  - Action
  - Illustrative Examples (best-effort)
- Writes:
  - data/processed/nces_cip2020.json
  - data/processed/nces_cip2020.manifest.json (sha256 + size)

Notes:
- The CIP detail page is the authoritative definition source for each code. Example structure:
  "Detail for CIP Code 01.0000", "Title:", "Definition:", "Action:" etc.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup


BASE = "https://nces.ed.gov/ipeds/cipcode/"
CIP2020_BROWSE_URL = "https://nces.ed.gov/ipeds/cipcode/browse.aspx?y=56"


# CIP formats we support:
# - 2-digit:  01
# - 4-digit:  01.00
# - 6-digit:  01.0000
CIP_CAPTURE_RE = re.compile(r"Detail for CIP Code\s+(\d{2}(?:\.\d{2}(?:\d{2})?)?)")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_section_text(page_text: str, label: str) -> str:
    """
    Extracts the text after 'Label:' up to the next known section label.
    Works against the page's rendered text output.

    Labels observed on NCES cipdetail pages:
      - Title:
      - Definition:
      - Action:
      - Illustrative Examples
    """
    # Order matters: these become our "stop markers"
    labels = ["Title:", "Definition:", "Action:", "Illustrative Examples", "Crosswalk", "Browse", "Print"]

    start = page_text.find(label)
    if start < 0:
        return ""

    start += len(label)

    # Find the nearest next marker after this label
    candidates: List[int] = []
    for nxt in labels:
        if nxt == label:
            continue
        pos = page_text.find(nxt, start)
        if pos >= 0:
            candidates.append(pos)

    end = min(candidates) if candidates else len(page_text)
    return page_text[start:end].strip()


def parse_cip_code(soup: BeautifulSoup, page_text: str) -> str:
    """
    Robust CIP extraction:
    - Prefer structured header area if present
    - Fallback to page_text search
    - Supports 2/4/6 digit formats
    """
    cip = ""

    # Try common header containers first
    # (NCES markup can change, so we keep this flexible)
    header_candidates = []

    # Common: a header element that includes "Detail for CIP Code ..."
    for selector in [
        "h1",
        "h2",
        "div.cipdetail h1",
        "div.cipdetail h2",
        "#cipHeader",
    ]:
        el = soup.select_one(selector)
        if el:
            header_candidates.append(el.get_text(" ", strip=True))

    # Add a fallback candidate: entire page text
    header_candidates.append(page_text)

    for candidate in header_candidates:
        m = CIP_CAPTURE_RE.search(candidate)
        if m:
            cip = m.group(1).strip()
            break

    # Safety cleanup for trailing punctuation
    return cip.rstrip(").,;:")


def parse_illustrative_examples(page_text: str) -> List[str]:
    """
    Best-effort extraction of illustrative examples.
    NCES pages vary; sometimes examples are absent or show "None available".
    """
    if "Illustrative Examples" not in page_text:
        return []

    # Grab a window after the section header
    ex_idx = page_text.find("Illustrative Examples")
    window = page_text[ex_idx : ex_idx + 3000]

    lines = [normalize_spaces(ln) for ln in window.split("\n") if normalize_spaces(ln)]

    cleaned: List[str] = []
    for ln in lines:
        if ln in ("Illustrative Examples", "Help"):
            continue
        # Stop if we hit a nav section
        if ln.startswith("Browse") or ln.startswith("Crosswalk") or ln.startswith("Print"):
            break
        cleaned.append(ln)

    # If the page says none are available, return empty list
    if any("None available" in ln for ln in cleaned):
        return []

    # Remove obvious non-example noise
    cleaned = [ln for ln in cleaned if len(ln) > 2 and ln not in ("Print",)]
    return cleaned


def parse_detail_html(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    # Rendered text for section extraction
    page_text = soup.get_text("\n", strip=True)

    cip = parse_cip_code(soup, page_text)

    title = extract_section_text(page_text, "Title:")
    definition = extract_section_text(page_text, "Definition:")
    action = extract_section_text(page_text, "Action:")

    examples = parse_illustrative_examples(page_text)

    rec: Dict[str, Any] = {
        "cip": cip,
        "title": title,
        "definition": definition,
        "action": action,
        "illustrative_examples": examples,
        "source_url": url,
    }

    # Flag for debugging if parsing looks incomplete
    if not cip or not title or not definition:
        rec["parse_warning"] = True

    return rec


def get_cipid_from_url(url: str) -> str:
    """
    Robust query parsing regardless of param order.
    """
    qs = parse_qs(urlparse(url).query)
    return qs.get("cipid", [""])[0]


def main() -> None:
    raw_dir = Path("data/raw/nces")
    urls_path = raw_dir / "nces_cip2020_detail_urls.json"
    if not urls_path.exists():
        raise FileNotFoundError("Missing detail URLs. Run extract_nces_detail_urls.py first.")

    urls_doc = json.loads(urls_path.read_text(encoding="utf-8"))
    urls: List[str] = urls_doc.get("urls", [])
    if not urls:
        raise ValueError("No NCES detail URLs found. Step 3 extraction likely failed.")

    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "CIP-STEM-INTELLIGENCE (open-source) - educational use",
        }
    )

    # Cache raw HTML for reproducibility / debugging
    cache_dir = raw_dir / "detail_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []

    for i, url in enumerate(urls, start=1):
        cipid = get_cipid_from_url(url)
        if not cipid.isdigit():
            # If URL is malformed, skip but record the issue
            records.append(
                {
                    "cip": "",
                    "title": "",
                    "definition": "",
                    "action": "",
                    "illustrative_examples": [],
                    "source_url": url,
                    "parse_warning": True,
                    "error": "invalid_cipid_in_url",
                }
            )
            continue

        cache_path = cache_dir / f"cipdetail_{cipid}.html"

        if cache_path.exists():
            html = cache_path.read_text(encoding="utf-8", errors="ignore")
        else:
            r = session.get(url, timeout=60)
            r.raise_for_status()
            html = r.text
            cache_path.write_text(html, encoding="utf-8")

            # Polite throttling
            time.sleep(0.10)

        rec = parse_detail_html(html, url)
        records.append(rec)

        if i % 250 == 0:
            print(f"Processed {i}/{len(urls)}")

    dataset = {
        "source": {
            "publisher": "NCES (IPEDS CIP site)",
            "cip_version": "2020",
            "browse_url": CIP2020_BROWSE_URL,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "note": "Scraped cipdetail pages referenced from the NCES CIP 2020 browse page (y=56).",
        },
        "record_count": len(records),
        "records": records,
    }

    out_path = out_dir / "nces_cip2020.json"
    out_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")

    digest = sha256_bytes(out_path.read_bytes())
    (out_dir / "nces_cip2020.manifest.json").write_text(
        json.dumps(
            {
                "file": str(out_path).replace("\\", "/"),
                "sha256": digest,
                "bytes": out_path.stat().st_size,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote: {out_path} ({len(records)} records)")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
