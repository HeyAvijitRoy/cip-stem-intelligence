# =========================================
# backfill_nces_missing.py
# =========================================
# Summary:
# - Reads overlay records marked missingInNcesSnapshot == true
# - NORMALIZES existing NCES dataset CIP codes to canonical 4-decimal format:
#     "14" -> "14.0000"
#     "14.09" -> "14.0900"
#     "14.0903" -> "14.0903"
# - Uses NCES searchresults.aspx to locate the cipdetail link for the EXACT CIP row
#   (supports 2-digit/4-digit rollups like "14" or "14.09")
# - Fetches + parses those detail pages (best-effort)
# - Appends truly missing records into data/processed/nces_cip2020.json
#
# Key Fix:
# - Canonical CIP normalization applied to BOTH:
#   (1) existing NCES dataset records (in-place normalization)
#   (2) matching logic (search-results row matching + detail-page CIP matching)
# =========================================

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


BASE = "https://nces.ed.gov/ipeds/cipcode/"
SEARCHRESULTS_URL = (
    "https://nces.ed.gov/ipeds/cipcode/searchresults.aspx"
    "?y=56&aw={cip}&sw=1,2,3&ct=1,2,3&ca=1,2,5,3,4"
)

# Matches detail header like: "Detail for CIP Code 14.0903"
CIP_CAPTURE_RE = re.compile(r"Detail for CIP Code\s+(\d{2}(?:\.\d{1,4})?)")


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def canonical_cip(cip: str) -> str:
    """
    Convert NCES/DHS CIP variants into a canonical format:
    - 2-digit: "14"      -> "14.0000"
    - 4-digit: "14.09"   -> "14.0900"
    - 6-digit: "14.0903" -> "14.0903"
    Also strips brackets/parentheses sometimes used for moved/deleted codes.
    """
    s = (cip or "").strip()
    if not s:
        return ""

    s = s.strip("[]()")
    s = s.replace(" ", "")

    # 2-digit family
    if "." not in s:
        if len(s) == 2 and s.isdigit():
            return f"{s}.0000"
        return s

    left, right = s.split(".", 1)
    left = left.strip()
    right = right.strip()

    if not (len(left) == 2 and left.isdigit()):
        return s

    # rollup like 14.09
    if len(right) == 2 and right.isdigit():
        return f"{left}.{right}00"

    # program code like 14.0903
    if len(right) == 4 and right.isdigit():
        return f"{left}.{right}"

    # any other numeric right side: pad to 4
    if right.isdigit() and 1 <= len(right) <= 4:
        return f"{left}.{right.zfill(4)}"

    return s


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def extract_section_text(page_text: str, label: str) -> str:
    labels = ["Title:", "Definition:", "Action:", "Illustrative Examples", "Crosswalk", "Browse", "Print"]

    start = page_text.find(label)
    if start < 0:
        return ""

    start += len(label)

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
    candidates: List[str] = []

    for selector in ["h1", "h2", "div.cipdetail h1", "div.cipdetail h2", "#cipHeader"]:
        el = soup.select_one(selector)
        if el:
            candidates.append(el.get_text(" ", strip=True))

    candidates.append(page_text)

    for cand in candidates:
        m = CIP_CAPTURE_RE.search(cand)
        if m:
            return m.group(1).strip().rstrip(").,;:")

    return ""


def parse_illustrative_examples(page_text: str) -> List[str]:
    if "Illustrative Examples" not in page_text:
        return []

    ex_idx = page_text.find("Illustrative Examples")
    window = page_text[ex_idx : ex_idx + 3000]

    lines = [normalize_spaces(ln) for ln in window.split("\n") if normalize_spaces(ln)]

    cleaned: List[str] = []
    for ln in lines:
        if ln in ("Illustrative Examples", "Help"):
            continue
        if ln.startswith("Browse") or ln.startswith("Crosswalk") or ln.startswith("Print"):
            break
        cleaned.append(ln)

    if any("None available" in ln for ln in cleaned):
        return []

    cleaned = [ln for ln in cleaned if len(ln) > 2 and ln not in ("Print",)]
    return cleaned


def parse_detail_html(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text("\n", strip=True)

    cip_raw = parse_cip_code(soup, page_text)
    title = extract_section_text(page_text, "Title:")
    definition = extract_section_text(page_text, "Definition:")
    action = extract_section_text(page_text, "Action:")
    examples = parse_illustrative_examples(page_text)

    rec: Dict[str, Any] = {
        "cip": cip_raw,
        "title": title,
        "definition": definition,
        "action": action,
        "illustrative_examples": examples,
        "source_url": url,
    }

    if not cip_raw or not title or not definition:
        rec["parse_warning"] = True

    return rec


def find_detail_url_for_target_cip(searchresults_html: str, target_cip: str) -> Optional[str]:
    """
    Parse searchresults.aspx and find the cipdetail link for the row whose CIP Code column matches target_cip.
    Matching uses canonical 4-decimal normalization.
    """
    soup = BeautifulSoup(searchresults_html, "html.parser")
    target_canon = canonical_cip(target_cip)

    grid = soup.find("table", {"id": re.compile(r"GridView_searchresults")})
    if not grid:
        return None

    rows = grid.find_all("tr")
    if len(rows) < 2:
        return None

    for tr in rows[1:]:
        cip_td = tr.find("td", {"class": "cipcode"})
        title_a = tr.select_one("span.CIPTitle a[href]")

        if not cip_td or not title_a:
            continue

        row_cip_raw = normalize_spaces(cip_td.get_text(" ", strip=True))
        row_canon = canonical_cip(row_cip_raw)

        if row_canon == target_canon:
            href = title_a["href"]
            abs_url = urljoin(BASE, href)
            qs = parse_qs(urlparse(abs_url).query)
            if qs.get("y", [""])[0] == "56" and qs.get("cipid", [""])[0].isdigit():
                return abs_url

    return None


def normalize_existing_nces_dataset(nces_doc: Dict[str, Any]) -> int:
    """
    Normalize ALL existing NCES records to canonical CIP format.
    Returns count of records changed.
    """
    records: List[Dict[str, Any]] = nces_doc.get("records", [])
    changed = 0

    for r in records:
        raw = (r.get("cip") or "").strip()
        if not raw:
            continue

        canon = canonical_cip(raw)
        if canon and canon != raw:
            # preserve original display value for debugging
            if "nces_display_cip" not in r:
                r["nces_display_cip"] = raw
            r["cip"] = canon
            changed += 1

    # de-dup by canonical cip (keep first)
    dedup: Dict[str, Dict[str, Any]] = {}
    for r in records:
        c = canonical_cip(r.get("cip", ""))
        if not c:
            continue
        if c not in dedup:
            dedup[c] = r

    nces_doc["records"] = sorted(dedup.values(), key=lambda x: (x.get("cip") or ""))
    nces_doc["record_count"] = len(nces_doc["records"])
    return changed


def main() -> None:
    overlay_path = Path("data/processed/cip_stem_overlay_latest.json")
    nces_path = Path("data/processed/nces_cip2020.json")

    if not overlay_path.exists():
        raise FileNotFoundError("Missing overlay. Run build_overlay.py first.")
    if not nces_path.exists():
        raise FileNotFoundError("Missing NCES dataset. Run build_nces_cip2020.py first.")

    overlay = load_json(overlay_path)
    nces = load_json(nces_path)

    # ✅ First: normalize what you already have (this fixes "14" / "14.09" etc.)
    changed = normalize_existing_nces_dataset(nces)
    if changed:
        write_json(nces_path, nces)
        print(f"✅ Normalized existing NCES records to canonical CIP: {changed} updated")
    else:
        print("ℹ️  NCES records already canonical. No normalization changes needed.")

    overlay_records: List[Dict[str, Any]] = overlay.get("records", [])
    nces_records: List[Dict[str, Any]] = nces.get("records", [])

    nces_by_canon = {canonical_cip(r.get("cip", "")): r for r in nces_records if r.get("cip")}
    missing_cips = sorted([r["cip"] for r in overlay_records if r.get("missingInNcesSnapshot") is True])

    if not missing_cips:
        print("No missing NCES records found. Nothing to backfill.")
        return

    print(f"Missing NCES records to backfill: {len(missing_cips)}")

    session = requests.Session()
    session.headers.update({"User-Agent": "CIP-STEM-INTELLIGENCE (open-source) - educational use"})

    raw_dir = Path("data/raw/nces")
    search_cache = raw_dir / "searchresults_cache"
    detail_cache = raw_dir / "detail_cache_backfill"
    search_cache.mkdir(parents=True, exist_ok=True)
    detail_cache.mkdir(parents=True, exist_ok=True)

    added = 0
    skipped = 0
    failed: List[str] = []

    for i, cip in enumerate(missing_cips, start=1):
        cip_canon = canonical_cip(cip)

        if cip_canon in nces_by_canon:
            skipped += 1
            continue

        # fetch/cache searchresults
        search_path = search_cache / f"searchresults_{cip}.html"
        if search_path.exists():
            search_html = search_path.read_text(encoding="utf-8", errors="ignore")
        else:
            url = SEARCHRESULTS_URL.format(cip=cip)
            r = session.get(url, timeout=60)
            r.raise_for_status()
            search_html = r.text
            search_path.write_text(search_html, encoding="utf-8")
            time.sleep(0.10)

        detail_url = find_detail_url_for_target_cip(search_html, cip)
        if not detail_url:
            failed.append(cip)
            continue

        qs = parse_qs(urlparse(detail_url).query)
        cipid = qs.get("cipid", [""])[0]
        detail_path = detail_cache / f"cipdetail_{cipid}.html"

        if detail_path.exists():
            detail_html = detail_path.read_text(encoding="utf-8", errors="ignore")
        else:
            r2 = session.get(detail_url, timeout=60)
            r2.raise_for_status()
            detail_html = r2.text
            detail_path.write_text(detail_html, encoding="utf-8")
            time.sleep(0.10)

        rec = parse_detail_html(detail_html, detail_url)

        parsed_cip_raw = (rec.get("cip") or "").strip()
        parsed_canon = canonical_cip(parsed_cip_raw)

        if parsed_canon != cip_canon or not rec.get("title") or not rec.get("definition"):
            failed.append(cip)
            continue

        rec["cip"] = cip_canon
        rec["nces_display_cip"] = parsed_cip_raw

        nces_records.append(rec)
        nces_by_canon[cip_canon] = rec
        added += 1

        if i % 10 == 0:
            print(f"Backfill progress: {i}/{len(missing_cips)}")

    # write updated NCES dataset
    nces["records"] = sorted(nces_records, key=lambda x: (x.get("cip") or ""))
    nces["record_count"] = len(nces["records"])
    write_json(nces_path, nces)

    print(f"✅ Backfilled: {added}")
    print(f"⏭️  Skipped (already existed in NCES by canonical CIP): {skipped}")
    print(f"❌ Failed: {len(failed)}")
    if failed:
        print("Failed CIP codes (first 25):", failed[:25])


if __name__ == "__main__":
    main()
