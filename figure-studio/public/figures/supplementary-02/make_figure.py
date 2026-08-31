#!/usr/bin/env python3
"""Figure Studio entrypoint for Supplementary Figure 2."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import shutil
import sys


HERE = Path(__file__).resolve().parent
CANONICAL_OUTPUT = HERE / "supplementary-02.jpg"
sys.path.insert(0, str(HERE.parent / "helpers"))
from layout_runtime import install_entrypoint_layout


def main() -> None:
    install_entrypoint_layout(HERE, "supplementary-02")
    CANONICAL_OUTPUT.unlink(missing_ok=True)
    runpy.run_path(str(HERE / "make_figure_02.py"), run_name="__main__")
    if not CANONICAL_OUTPUT.is_file():
        raise RuntimeError("Supplementary Figure 2 did not create its JPG")
    output_dir = Path(os.environ["FIG_OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = os.environ.get("FIG_OUTPUT_STEM", "supplementary-02")
    target = output_dir / (stem + ".jpg")
    shutil.copy2(CANONICAL_OUTPUT, target)
    CANONICAL_OUTPUT.unlink()
    print(f"WROTE {target}")


if __name__ == "__main__":
    main()
