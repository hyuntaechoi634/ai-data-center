#!/usr/bin/env python3
"""Figure Studio entrypoint for the authors' Figure 3."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import shutil
import sys


HERE = Path(__file__).resolve().parent
LEGACY_OUTPUT = HERE / "figure-03.jpg"
sys.path.insert(0, str(HERE.parent / "helpers"))
from layout_runtime import install_entrypoint_layout


def main() -> None:
    install_entrypoint_layout(HERE, "figure-03")
    LEGACY_OUTPUT.unlink(missing_ok=True)
    runpy.run_path(str(HERE / "make_figure_03.py"), run_name="__main__")
    if not LEGACY_OUTPUT.is_file():
        raise RuntimeError("Figure 3 did not create its JPG")
    output_dir = Path(os.environ["FIG_OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{os.environ.get('FIG_OUTPUT_STEM', 'figure-03')}.jpg"
    shutil.copy2(LEGACY_OUTPUT, target)
    LEGACY_OUTPUT.unlink()
    print(f"WROTE {target}")


if __name__ == "__main__":
    main()
