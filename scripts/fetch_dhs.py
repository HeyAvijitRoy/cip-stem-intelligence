"""
fetch_dhs.py
- Downloads the DHS/ICE STEM designated degree list PDF
- Records provenance (final URL, sha256, bytes, timestamp)
- Saves to data/raw/dhs/
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


# DEFAULT_DHS_PDF_URL = "https://www.ice.gov/sites/default/files/documents/stem-list.pdf"
DEFAULT_DHS_PDF_URL = "https://www.ice.gov/doclib/sevis/pdf/stemList2024.pdf"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    out_dir = Path("data/raw/dhs")
    out_dir.mkdir(parents=True, exist_ok=True)

    url = DEFAULT_DHS_PDF_URL
    r = requests.get(url, allow_redirects=True, timeout=60)
    r.raise_for_status()

    content = r.content
    final_url = r.url
    digest = sha256_bytes(content)

    # Save PDF with a stable name
    pdf_path = out_dir / "stem-list-latest.pdf"
    pdf_path.write_bytes(content)

    manifest = {
        "requested_url": url,
        "final_url": final_url,
        "sha256": digest,
        "bytes": len(content),
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
    }

    (out_dir / "stem-list-latest.manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(f"Saved: {pdf_path}")
    print(f"SHA256: {digest}")
    print(f"Final URL: {final_url}")


if __name__ == "__main__":
    main()
