"""
parse_dhs.py
- Extracts CIP codes + titles from the DHS STEM PDF into JSON
- Outputs:
  data/processed/stem_dhs_latest.json

Notes:
- DHS PDFs can vary in layout. This parser is built to be resilient:
  1) Extract all text
  2) Detect CIP patterns like NN.NNNN
  3) Capture a reasonable title on the same line (or nearby)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pdfplumber


CIP_RE = re.compile(r"\b(\d{2}\.\d{4})\b")


@dataclass(frozen=True)
class StemCipRow:
    cip: str
    title: str


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_lines(pdf_path: Path) -> List[str]:
    lines: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = normalize_spaces(line)
                if line:
                    lines.append(line)
    return lines


def parse_cip_lines(lines: Iterable[str]) -> List[StemCipRow]:
    """
    Heuristic:
    - Find CIP code on a line
    - Title = remainder of the line after the CIP code
    - If remainder is too short, try the next line as title continuation
    """
    rows: List[StemCipRow] = []
    lines_list = list(lines)

    for i, line in enumerate(lines_list):
        m = CIP_RE.search(line)
        if not m:
            continue

        cip = m.group(1)

        # Try to get title from the same line after the CIP
        after = normalize_spaces(line[m.end() :])
        title = after

        # If title is empty or suspiciously tiny, look at next line
        if len(title) < 3 and i + 1 < len(lines_list):
            title = normalize_spaces(lines_list[i + 1])

        # Guardrails: avoid headers/footers/noise
        if not title or title.lower().startswith(("page ", "department of homeland", "stem designated")):
            title = ""

        rows.append(StemCipRow(cip=cip, title=title))

    # Deduplicate by CIP (keep first non-empty title if possible)
    by_cip: dict[str, StemCipRow] = {}
    for row in rows:
        if row.cip not in by_cip:
            by_cip[row.cip] = row
        else:
            existing = by_cip[row.cip]
            if (not existing.title) and row.title:
                by_cip[row.cip] = row

    # Sort for stable diffs
    return sorted(by_cip.values(), key=lambda x: x.cip)


def main() -> None:
    pdf_path = Path("data/raw/dhs/stem-list-latest.pdf")
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing {pdf_path}. Run fetch_dhs.py first.")

    lines = extract_lines(pdf_path)
    rows = parse_cip_lines(lines)

    out = {
        "source": {
            "publisher": "DHS/ICE",
            "type": "stem_designated_degree_program_list",
            "pdf_file": str(pdf_path).replace("\\", "/"),
        },
        "records": [{"cip": r.cip, "title_from_pdf": r.title} for r in rows],
        "record_count": len(rows),
    }

    out_path = Path("data/processed/stem_dhs_latest.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"Wrote: {out_path} ({len(rows)} records)")


if __name__ == "__main__":
    main()
