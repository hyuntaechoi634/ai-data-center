from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from studio.layout import LayoutError, load_layout_catalog, prepare_layout_update, write_layout_update


class LayoutContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        (self.workspace / "layout").mkdir(parents=True)
        figure = self.workspace / "figures/figure-01"
        figure.mkdir(parents=True)
        (self.workspace / "layout/elements.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "figure_id": "figure-01",
                    "canvas_px": [2652, 2006],
                    "elements": [
                        {
                            "id": "axis-00:title",
                            "kind": "text",
                            "role": "Title",
                            "label": "Low demand",
                            "bbox_px": [200, 100, 400, 150],
                            "visible": True,
                            "hidden": False,
                            "offset_px": {"x": 0, "y": 0},
                            "font_size": 15,
                            "font_family": "sans-serif",
                            "override": {},
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (figure / "layout-overrides.json").write_text(
            '{"schema_version": 1, "figure_id": "figure-01", "elements": {}}\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_reviewable_layout_update(self) -> None:
        catalog = load_layout_catalog(self.workspace, "figure-01")
        self.assertEqual(catalog["elements"][0]["panel_id"], "a")
        update = prepare_layout_update(
            self.workspace,
            "figure-01",
            [
                {
                    "id": "axis-00:title",
                    "offset_px": {"x": 14, "y": -6},
                    "font_size": 16,
                    "font_family": "DejaVu Sans",
                }
            ],
            panel_id="a",
        )
        write_layout_update(update)
        payload = json.loads(update.path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["elements"]["axis-00:title"]["offset_px"],
            {"x": 14.0, "y": -6.0},
        )

    def test_unreviewed_font_is_rejected(self) -> None:
        with self.assertRaisesRegex(LayoutError, "font family"):
            prepare_layout_update(
                self.workspace,
                "figure-01",
                [{"id": "axis-00:title", "font_family": "Remote Web Font"}],
            )


if __name__ == "__main__":
    unittest.main()
