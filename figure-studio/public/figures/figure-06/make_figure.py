#!/usr/bin/env python3
"""Figure Studio entrypoint for the authors' Figure 6."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import shutil
import sys


HERE = Path(__file__).resolve().parent
CANONICAL_OUTPUT = HERE / "figure-06.jpg"
sys.path.insert(0, str(HERE.parent / "helpers"))
from layout_runtime import install_entrypoint_layout


def main() -> None:
    install_entrypoint_layout(HERE, "figure-06")
    CANONICAL_OUTPUT.unlink(missing_ok=True)
    runpy.run_path(str(HERE / "make_figure_06.py"), run_name="__main__")
    if not CANONICAL_OUTPUT.is_file():
        raise RuntimeError("Figure 6 did not create its JPG")
    output_dir = Path(os.environ["FIG_OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{os.environ.get('FIG_OUTPUT_STEM', 'figure-06')}.jpg"
    shutil.copy2(CANONICAL_OUTPUT, target)
    CANONICAL_OUTPUT.unlink()
    print(f"WROTE {target}")


if __name__ == "__main__":
    main()
