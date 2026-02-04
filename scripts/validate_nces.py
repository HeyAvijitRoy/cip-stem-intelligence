"""
validate_nces.py
- Validates NCES CIP 2020 dataset:
  - CIP format NN.NNNN
  - title/definition present for most rows
  - reports parse warnings
"""

from __future__ import annotations

import json
import re
from pathlib import Path


CIP_RE = re.compile(r"^\d{2}(?:\.\d{2}(?:\d{2})?)?$")


def main() -> None:
    p = Path("data/processed/nces_cip2020.json")
    if not p.exists():
        raise FileNotFoundError("Run build_nces_cip2020.py first.")

    data = json.loads(p.read_text(encoding="utf-8"))
    records = data.get("records", [])
    if not records:
        raise ValueError("No records found.")

    total = len(records)
    bad_cip = 0
    missing_core = 0
    warnings = 0

    for r in records:
        cip = (r.get("cip") or "").strip()
        if not CIP_RE.match(cip):
            bad_cip += 1

        if not (r.get("title") and r.get("definition")):
            missing_core += 1

        if r.get("parse_warning"):
            warnings += 1

    print("NCES dataset validation summary")
    print(f"- Total records: {total}")
    print(f"- Bad CIP format: {bad_cip}")
    print(f"- Missing title/definition: {missing_core}")
    print(f"- Parse warnings flagged: {warnings}")

    # Set a reasonable bar: should be overwhelmingly successful
    if bad_cip > 0:
        raise ValueError("Some records have invalid CIP format. Parser needs adjustment.")
    if missing_core > 50:
        raise ValueError("Too many missing title/definition entries. Parser likely broke.")

    print("✅ NCES CIP 2020 validation passed")


if __name__ == "__main__":
    main()
