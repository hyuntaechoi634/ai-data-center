from __future__ import annotations

from pathlib import Path
import sys
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from studio.catalog import FIGURE_IDS, FIGURE_PROJECTS, figure_catalog, project_manifest
from studio.panels import panel_catalog


class FigureCatalogTests(unittest.TestCase):
    def test_main_and_supplementary_catalogs_are_complete(self) -> None:
        expected = tuple(f"figure-{number:02d}" for number in range(1, 7)) + tuple(
            f"supplementary-{number:02d}" for number in range(1, 7)
        )
        self.assertEqual(FIGURE_IDS, expected)
        self.assertEqual(tuple(FIGURE_PROJECTS), expected)
        self.assertEqual([item["id"] for item in figure_catalog()], list(expected))

    def test_each_project_is_scoped_to_its_own_directory(self) -> None:
        for figure_id in FIGURE_IDS:
            with self.subTest(figure_id=figure_id):
                manifest = project_manifest(figure_id)
                self.assertEqual(manifest["figure_id"], figure_id)
                self.assertEqual(
                    Path(manifest["entrypoint"]).parent,
                    Path("figures") / figure_id,
                )

    def test_supplementary_panel_catalogs_match_the_manuscript_layout(self) -> None:
        self.assertEqual(
            [item["id"] for item in panel_catalog("supplementary-01")],
            ["a", "b", "c"],
        )
        self.assertEqual(panel_catalog("supplementary-03"), [])
        self.assertEqual(
            [item["id"] for item in panel_catalog("supplementary-06")],
            ["a", "b", "c"],
        )


if __name__ == "__main__":
    unittest.main()
