# =========================================
# publish_site_data.py
# =========================================
# Summary:
# - Copies processed public artifacts into /docs so GitHub Pages can serve them
# - Keeps UI paths stable: "data/processed/..." from site root (docs/)
# - Currently publishes the frontend index + its manifest
# =========================================

from __future__ import annotations

import shutil
from pathlib import Path


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Missing source file: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    repo_root = Path(".")
    src_dir = repo_root / "data" / "processed"
    dst_dir = repo_root / "docs" / "data" / "processed"

    files = [
        "cip_stem_index.json",
        "cip_stem_index.manifest.json",
    ]

    for name in files:
        copy_file(src_dir / name, dst_dir / name)

    print("✅ Published site data to docs/data/processed:")
    for name in files:
        print(f" - {dst_dir / name}")


if __name__ == "__main__":
    main()
