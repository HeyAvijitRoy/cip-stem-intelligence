"""
fetch_nces_index.py
- Downloads NCES CIP 2020 "Browse all CIP codes" HTML
- Saves to data/raw/nces/
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


NCES_BROWSE_URL = "https://nces.ed.gov/ipeds/cipcode/browse.aspx?y=56"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    out_dir = Path("data/raw/nces")
    out_dir.mkdir(parents=True, exist_ok=True)

    r = requests.get(NCES_BROWSE_URL, timeout=60)
    r.raise_for_status()

    content = r.content
    digest = sha256_bytes(content)

    html_path = out_dir / "nces_cip2020_browse.html"
    html_path.write_bytes(content)

    manifest = {
        "requested_url": NCES_BROWSE_URL,
        "final_url": r.url,
        "sha256": digest,
        "bytes": len(content),
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "note": "NCES CIP 2020 browse listing (y=56)",
    }

    (out_dir / "nces_cip2020_browse.manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(f"Saved: {html_path}")
    print(f"SHA256: {digest}")
    print(f"Final URL: {r.url}")


if __name__ == "__main__":
    main()
