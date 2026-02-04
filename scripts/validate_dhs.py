"""
validate_dhs.py
- Validates the parsed DHS STEM JSON:
  - CIP format NN.NNNN
  - No duplicates
  - Count > 0
"""

from __future__ import annotations

import json
import re
from pathlib import Path


CIP_RE = re.compile(r"^\d{2}\.\d{4}$")


def main() -> None:
    p = Path("data/processed/stem_dhs_latest.json")
    if not p.exists():
        raise FileNotFoundError("Run parse_dhs.py first.")

    data = json.loads(p.read_text(encoding="utf-8"))
    records = data.get("records", [])

    if not records:
        raise ValueError("No records found. Parsing likely failed.")

    seen = set()
    bad = []
    dupes = 0

    for r in records:
        cip = (r.get("cip") or "").strip()
        if not CIP_RE.match(cip):
            bad.append(cip)
        if cip in seen:
            dupes += 1
        seen.add(cip)

    if bad:
        raise ValueError(f"Invalid CIP formats: {bad[:20]} (showing up to 20)")

    if dupes:
        raise ValueError(f"Duplicate CIP codes found: {dupes}")

    print("✅ DHS STEM JSON validation passed")
    print(f"Records: {len(records)}")


if __name__ == "__main__":
    main()
