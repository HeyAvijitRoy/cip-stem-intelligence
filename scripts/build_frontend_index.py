# =========================================
# build_frontend_index.py
# =========================================
# Summary:
# - Reads:  data/processed/cip_stem_overlay_latest.json
# - Writes: data/processed/cip_stem_index.json
#          data/processed/cip_stem_index.manifest.json
#
# Purpose:
# - Produce a compact, frontend-friendly index that is safe to load fully in-browser
#   (GitHub Pages), enabling fast search + filters later.
#
# Key guarantees:
# - Canonical CIP format enforced: "XX.XXXX" (e.g., "14.0900")
# - Deterministic sorting for stable diffs
# - STEM records must have a stemSource
# =========================================

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


CANON_CIP_RE = re.compile(r"^\d{2}\.\d{4}$")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_cip(cip: str) -> str:
    """
    Convert CIP variants into canonical format: "XX.XXXX"
    - "14"      -> "14.0000"
    - "14.09"   -> "14.0900"
    - "14.0903" -> "14.0903"
    """
    s = (cip or "").strip()
    if not s:
        return ""

    s = s.strip("[]()")  # safety for moved/deleted notations sometimes present in NCES outputs

    if "." not in s:
        if len(s) == 2 and s.isdigit():
            return f"{s}.0000"
        return s

    left, right = s.split(".", 1)
    left = left.strip()
    right = right.strip()

    if len(left) == 2 and left.isdigit() and right.isdigit():
        # 4-digit rollup: "14.09"
        if len(right) == 2:
            return f"{left}.{right}00"
        # 6-digit already: "14.0903"
        if len(right) == 4:
            return f"{left}.{right}"
        # pad anything else up to 4
        if 1 <= len(right) <= 4:
            return f"{left}.{right.zfill(4)}"

    return s


def cip_family(cip_canon: str) -> str:
    # "14.0900" -> "14"
    return cip_canon.split(".", 1)[0] if cip_canon else ""


def main() -> None:
    overlay_path = Path("data/processed/cip_stem_overlay_latest.json")
    if not overlay_path.exists():
        raise FileNotFoundError("Missing overlay. Run build_overlay.py first.")

    overlay = load_json(overlay_path)
    records: List[Dict[str, Any]] = overlay.get("records", [])

    out_records: List[Dict[str, Any]] = []

    bad_cip: List[str] = []
    bad_stem_source: List[str] = []

    for r in records:
        cip_raw = (r.get("cip") or "").strip()
        cip = canonical_cip(cip_raw)

        if not cip or not CANON_CIP_RE.match(cip):
            bad_cip.append(cip_raw)
            continue

        title = (r.get("title") or "").strip()
        title_source = (r.get("titleSource") or "").strip()

        stem_eligible = bool(r.get("stemEligible") is True)

        # Determine stem source (future-proofed):
        # - Today: if stemEligible true, it comes from DHS (because the stem list is DHS)
        # - Later: you may introduce other authorities; this field is intentionally explicit.
        stem_source = "DHS" if stem_eligible else ""

        if stem_eligible and not stem_source:
            bad_stem_source.append(cip)

        definition = (r.get("definition") or "").strip()
        examples = r.get("illustrative_examples") or []

        out_records.append(
            {
                "cip": cip,
                "cipFamily": cip_family(cip),
                "cipYear": int(r.get("cipYear") or 2020),
                "title": title,
                "titleSource": title_source or ("NCES" if definition else "Unknown"),
                "stemEligible": stem_eligible,
                "stemSource": stem_source,
                "hasDefinition": bool(definition),
                "hasIllustrativeExamples": bool(isinstance(examples, list) and len(examples) > 0),
            }
        )

    if bad_cip:
        # show a few examples to make debugging fast
        sample = bad_cip[:20]
        raise ValueError(
            f"Invalid CIP format encountered while building index. "
            f"Count={len(bad_cip)} Sample={sample}"
        )

    if bad_stem_source:
        sample = bad_stem_source[:20]
        raise ValueError(
            f"Some STEM-eligible records are missing stemSource. "
            f"Count={len(bad_stem_source)} Sample={sample}"
        )

    # Deterministic ordering
    out_records.sort(key=lambda x: x["cip"])

    generated_utc = datetime.now(timezone.utc).isoformat()

    output = {
        "meta": {
            "name": "CIP STEM Intelligence - Frontend Index",
            "generated_utc": generated_utc,
            "source_overlay_file": str(overlay_path).replace("\\", "/"),
            "record_count": len(out_records),
            "stem_true_count": sum(1 for x in out_records if x.get("stemEligible") is True),
            "cip_version": overlay.get("meta", {}).get("cip_version", "2020"),
        },
        "records": out_records,
    }

    out_path = Path("data/processed/cip_stem_index.json")
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    digest = sha256_bytes(out_path.read_bytes())
    manifest = {
        "file": str(out_path).replace("\\", "/"),
        "sha256": digest,
        "bytes": out_path.stat().st_size,
        "generated_utc": generated_utc,
        "record_count": output["meta"]["record_count"],
        "stem_true_count": output["meta"]["stem_true_count"],
        "source_overlay_sha256": sha256_bytes(overlay_path.read_bytes()),
    }

    manifest_path = Path("data/processed/cip_stem_index.manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote: {out_path} ({output['meta']['record_count']} records)")
    print(f"SHA256: {digest}")
    print(f"Wrote: {manifest_path}")


if __name__ == "__main__":
    main()
