# =========================================
# build_overlay.py
# =========================================
# Summary:
# - Loads:
#   - data/processed/nces_cip2020.json
#   - data/processed/stem_dhs_latest.json
#   - data/raw/dhs/stem-list-latest.manifest.json
# - Merges to produce:
#   - data/processed/cip_stem_overlay_latest.json
#
# - Canonical CIP normalization to 4 decimals everywhere:
#     "14"      -> "14.0000"
#     "14.09"   -> "14.0900"
#     "14.0903" -> "14.0903"
# - Indexing + matching uses canonical CIP keys (NCES + DHS).
# - Output records always store canonical CIP.
#
# Enhancements:
# - If a DHS STEM CIP code is missing from the current NCES snapshot,
#   we still include it and fall back to DHS "title_from_pdf" for title.
# =========================================

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_cip(cip: str) -> str:
    """
    Convert CIP variants into canonical XX.XXXX format:
    - 2-digit: "14"      -> "14.0000"
    - 4-digit: "14.09"   -> "14.0900"
    - 6-digit: "14.0903" -> "14.0903"
    Also removes bracket/paren wrappers sometimes used by NCES for moved/deleted codes.
    """
    s = (cip or "").strip()
    if not s:
        return ""

    # Remove wrappers like [14.0901] or (14.0901)
    s = s.strip("[]()").strip()

    if "." not in s:
        # 2-digit family
        if len(s) == 2 and s.isdigit():
            return f"{s}.0000"
        return s

    left, right = s.split(".", 1)
    left = left.strip()
    right = right.strip()

    # If right has 2 digits => 4-digit rollup (e.g., 14.09 -> 14.0900)
    if len(left) == 2 and left.isdigit() and len(right) == 2 and right.isdigit():
        return f"{left}.{right}00"

    # If right has 4 digits => already 6-digit program code (e.g., 14.0903)
    if len(left) == 2 and left.isdigit() and len(right) == 4 and right.isdigit():
        return f"{left}.{right}"

    # If right is 1-4 digits, pad to 4 to be safe
    if len(left) == 2 and left.isdigit() and right.isdigit() and 1 <= len(right) <= 4:
        return f"{left}.{right.zfill(4)}"

    return s


def pick_first_nonempty(*vals: str) -> str:
    for v in vals:
        if v and v.strip():
            return v.strip()
    return ""


def main() -> None:
    nces_path = Path("data/processed/nces_cip2020.json")
    dhs_path = Path("data/processed/stem_dhs_latest.json")
    dhs_manifest_path = Path("data/raw/dhs/stem-list-latest.manifest.json")

    if not nces_path.exists():
        raise FileNotFoundError("Missing NCES dataset. Run build_nces_cip2020.py first.")
    if not dhs_path.exists():
        raise FileNotFoundError("Missing DHS dataset. Run parse_dhs.py first.")
    if not dhs_manifest_path.exists():
        raise FileNotFoundError("Missing DHS manifest. Run fetch_dhs.py first.")

    nces = load_json(nces_path)
    dhs = load_json(dhs_path)
    dhs_manifest = load_json(dhs_manifest_path)

    nces_records: List[Dict[str, Any]] = nces.get("records", [])
    dhs_records: List[Dict[str, Any]] = dhs.get("records", [])

    # -----------------------------
    # Index NCES by canonical CIP
    # -----------------------------
    nces_by_cip: Dict[str, Dict[str, Any]] = {}
    for r in nces_records:
        raw = (r.get("cip") or "").strip()
        cip = canonical_cip(raw)
        if not cip:
            continue

        # Normalize the record CIP in-memory so overlay output is consistent
        r_canon = dict(r)
        r_canon["cip"] = cip

        # If duplicates exist, prefer the one with a definition/title (more complete)
        existing = nces_by_cip.get(cip)
        if not existing:
            nces_by_cip[cip] = r_canon
        else:
            existing_score = int(bool(existing.get("title"))) + int(bool(existing.get("definition")))
            new_score = int(bool(r_canon.get("title"))) + int(bool(r_canon.get("definition")))
            if new_score > existing_score:
                nces_by_cip[cip] = r_canon

    # -----------------------------
    # DHS STEM set (canonical) + title fallback map
    # -----------------------------
    stem_set = set()
    dhs_title_by_cip: Dict[str, str] = {}

    for r in dhs_records:
        raw = (r.get("cip") or "").strip()
        cip = canonical_cip(raw)
        title = (r.get("title_from_pdf") or "").strip()

        if cip:
            stem_set.add(cip)

        # Keep first non-empty title encountered for that CIP
        if cip and title and cip not in dhs_title_by_cip:
            dhs_title_by_cip[cip] = title

    # -----------------------------
    # Build overlay (NCES as the base)
    # -----------------------------
    overlay_records: List[Dict[str, Any]] = []

    for cip, r in nces_by_cip.items():
        overlay_records.append(
            {
                "cip": cip,
                "cipYear": 2020,
                "title": pick_first_nonempty(r.get("title", ""), dhs_title_by_cip.get(cip, "")),
                "definition": r.get("definition", "") or "",
                "action": r.get("action", "") or "",
                "illustrative_examples": r.get("illustrative_examples", []) or [],
                "stemEligible": cip in stem_set,
                "ncesSourceUrl": r.get("source_url", "") or "",
                "titleSource": "NCES" if (r.get("title") or "").strip() else "DHS PDF (fallback)",
            }
        )

    # Add “orphan STEM codes” if any DHS CIP is missing in NCES snapshot
    missing_stem = sorted([c for c in stem_set if c not in nces_by_cip])

    for cip in missing_stem:
        overlay_records.append(
            {
                "cip": cip,
                "cipYear": 2020,
                "title": dhs_title_by_cip.get(cip, ""),
                "definition": "",
                "action": "",
                "illustrative_examples": [],
                "stemEligible": True,
                "ncesSourceUrl": "",
                "missingInNcesSnapshot": True,
                "titleSource": "DHS PDF (fallback)",
            }
        )

    # Stable ordering for diffs
    overlay_records = sorted(overlay_records, key=lambda x: x.get("cip", ""))

    output = {
        "meta": {
            "name": "CIP STEM Intelligence Overlay",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "cip_version": "2020",
            "nces_record_count": len(nces_by_cip),
            "dhs_stem_record_count": len(stem_set),
            "overlay_record_count": len(overlay_records),
            "missing_stem_in_nces_snapshot": len(missing_stem),
        },
        "sources": {
            "nces": nces.get("source", {}),
            "dhs": {
                "publisher": "DHS/ICE",
                "final_url": dhs_manifest.get("final_url", ""),
                "requested_url": dhs_manifest.get("requested_url", ""),
                "sha256": dhs_manifest.get("sha256", ""),
                "fetched_utc": dhs_manifest.get("fetched_utc", ""),
                "note": "DHS STEM Designated Degree Program List (latest pinned PDF)",
            },
        },
        "records": overlay_records,
    }

    out_path = Path("data/processed/cip_stem_overlay_latest.json")
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    digest = sha256_bytes(out_path.read_bytes())
    manifest = {
        "file": str(out_path).replace("\\", "/"),
        "sha256": digest,
        "bytes": out_path.stat().st_size,
        "generated_utc": output["meta"]["generated_utc"],
        "missing_stem_in_nces_snapshot": output["meta"]["missing_stem_in_nces_snapshot"],
    }

    (Path("data/processed/cip_stem_overlay_latest.manifest.json")).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"Wrote: {out_path} ({len(overlay_records)} records)")
    print(f"SHA256: {digest}")
    print(f"Missing STEM codes in NCES snapshot: {len(missing_stem)}")


if __name__ == "__main__":
    main()
