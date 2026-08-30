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
                            "text": "Low demand",
                            "bbox_px": [200, 100, 400, 150],
                            "visible": True,
                            "hidden": False,
                            "offset_px": {"x": 0, "y": 0},
                            "font_size": 15,
                            "font_family": "sans-serif",
                            "override": {},
                        },
                        {
                            "id": "axis-00:x-tick-00",
                            "kind": "text",
                            "role": "X tick",
                            "label": "2025",
                            "text": "2025",
                            "bbox_px": [250, 400, 300, 430],
                            "visible": True,
                            "hidden": False,
                            "offset_px": {"x": 0, "y": 0},
                            "font_size": 12,
                            "font_family": "sans-serif",
                            "override": {},
                        },
                        {
                            "id": "axis-00:whisker-00",
                            "kind": "mark",
                            "role": "Capped whisker",
                            "label": "Capped whisker 1",
                            "bbox_px": [220, 180, 250, 330],
                            "visible": True,
                            "hidden": False,
                            "offset_px": {"x": 0, "y": 0},
                            "font_size": None,
                            "font_family": "",
                            "color": "#333333",
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
        self.assertTrue(catalog["elements"][0]["text_editable"])
        self.assertFalse(catalog["elements"][1]["text_editable"])
        update = prepare_layout_update(
            self.workspace,
            "figure-01",
            [
                {
                    "id": "axis-00:title",
                    "offset_px": {"x": 14, "y": -6},
                    "font_size": 16,
                    "font_family": "DejaVu Sans",
                    "font_weight": "bold",
                    "font_style": "italic",
                    "text": "Revised title",
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
        self.assertEqual(
            payload["elements"]["axis-00:title"]["font_weight"], "bold"
        )
        self.assertEqual(
            payload["elements"]["axis-00:title"]["font_style"], "italic"
        )
        self.assertEqual(
            payload["elements"]["axis-00:title"]["text"], "Revised title"
        )

    def test_unreviewed_font_is_rejected(self) -> None:
        with self.assertRaisesRegex(LayoutError, "font family"):
            prepare_layout_update(
                self.workspace,
                "figure-01",
                [{"id": "axis-00:title", "font_family": "Remote Web Font"}],
            )
        with self.assertRaisesRegex(LayoutError, "font weight"):
            prepare_layout_update(
                self.workspace,
                "figure-01",
                [{"id": "axis-00:title", "font_weight": "extra-black"}],
            )
        with self.assertRaisesRegex(LayoutError, "font style"):
            prepare_layout_update(
                self.workspace,
                "figure-01",
                [{"id": "axis-00:title", "font_style": "slanted"}],
            )
        with self.assertRaisesRegex(LayoutError, "cannot be empty"):
            prepare_layout_update(
                self.workspace,
                "figure-01",
                [{"id": "axis-00:title", "text": "   "}],
            )
        with self.assertRaisesRegex(LayoutError, "does not support"):
            prepare_layout_update(
                self.workspace,
                "figure-01",
                [{"id": "axis-00:x-tick-00", "text": "2030"}],
            )

    def test_mark_color_is_reviewable_and_position_is_locked(self) -> None:
        update = prepare_layout_update(
            self.workspace,
            "figure-01",
            [{"id": "axis-00:whisker-00", "color": "#b31b34"}],
            panel_id="a",
        )
        write_layout_update(update)
        payload = json.loads(update.path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["elements"]["axis-00:whisker-00"]["color"], "#b31b34"
        )
        with self.assertRaisesRegex(LayoutError, "does not support"):
            prepare_layout_update(
                self.workspace,
                "figure-01",
                [
                    {
                        "id": "axis-00:whisker-00",
                        "offset_px": {"x": 10, "y": 0},
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
