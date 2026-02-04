# =========================================
# validate_overlay.py
# =========================================
# Summary:
# - Validates:
#   - overlay file exists and has records
#   - CIP format is valid (2/4/6-digit)
#   - DHS STEM count is reasonable
#   - Reports DHS STEM codes missing in NCES snapshot
# =========================================

from __future__ import annotations

import json
import re
from pathlib import Path


CIP_RE = re.compile(r"^\d{2}(?:\.\d{2}(?:\d{2})?)?$")


def main() -> None:
    p = Path("data/processed/cip_stem_overlay_latest.json")
    if not p.exists():
        raise FileNotFoundError("Run build_overlay.py first.")

    data = json.loads(p.read_text(encoding="utf-8"))
    records = data.get("records", [])
    meta = data.get("meta", {})

    if not records:
        raise ValueError("Overlay contains zero records.")

    bad = 0
    stem_count = 0
    missing_stem = 0

    for r in records:
        cip = (r.get("cip") or "").strip()
        if not CIP_RE.match(cip):
            bad += 1

        if r.get("stemEligible") is True:
            stem_count += 1

        if r.get("missingInNcesSnapshot") is True:
            missing_stem += 1

    print("Overlay validation summary")
    print(f"- Total records: {len(records)}")
    print(f"- STEM-eligible (true): {stem_count}")
    print(f"- Bad CIP format: {bad}")
    print(f"- STEM codes missing in NCES snapshot: {missing_stem}")

    if bad > 0:
        raise ValueError("Overlay has invalid CIP formats.")

    # DHS list should be non-trivial
    if stem_count < 100:
        raise ValueError("STEM count is suspiciously low. Something is wrong with DHS parsing or merge.")

    # For now, allow missing STEM codes but surface them loudly
    # Later we’ll expand NCES ingestion to eliminate these.
    if missing_stem > 0:
        print("⚠️  Some DHS STEM codes are missing from the current NCES snapshot.")
        print("   Possibly browse extraction didn’t include all detail pages.")
        print("   Will fix this by expanding NCES ingestion in a later step.")

    print("✅ Overlay validation passed")


if __name__ == "__main__":
    main()
