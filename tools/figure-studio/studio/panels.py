from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile


class PanelError(RuntimeError):
    pass


FIGURE_PANELS: dict[str, dict] = {
    "figure-01": {
        "canvas_px": (2652, 2006),
        "dpi": 170,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 2652, 612)},
            {"id": "b", "label": "B", "bbox_px": (0, 612, 2652, 1298)},
            {"id": "c", "label": "C", "bbox_px": (0, 1298, 926, 2006)},
            {"id": "d", "label": "D", "bbox_px": (926, 1298, 1795, 2006)},
            {"id": "e", "label": "E", "bbox_px": (1795, 1298, 2652, 2006)},
        ),
    },
    "figure-02": {
        "canvas_px": (2340, 2340),
        "dpi": 150,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 1144, 699)},
            {"id": "b", "label": "B", "bbox_px": (1144, 0, 2340, 699)},
            {"id": "c", "label": "C", "bbox_px": (0, 699, 2340, 1414)},
            {"id": "d", "label": "D", "bbox_px": (0, 1414, 1165, 2340)},
            {"id": "e", "label": "E", "bbox_px": (1165, 1414, 2340, 2340)},
        ),
    },
    "figure-03": {
        "canvas_px": (2910, 990),
        "dpi": 150,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 936, 990)},
            {"id": "b", "label": "B", "bbox_px": (936, 0, 1967, 990)},
            {"id": "c", "label": "C", "bbox_px": (1967, 0, 2910, 990)},
        ),
    },
    "figure-04": {
        "canvas_px": (3150, 1020),
        "dpi": 150,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 1256, 1020)},
            {"id": "b", "label": "B", "bbox_px": (1256, 0, 2176, 1020)},
            {"id": "c", "label": "C", "bbox_px": (2176, 0, 3150, 1020)},
        ),
    },
    "figure-05": {
        "canvas_px": (3400, 2448),
        "dpi": 170,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 1602, 1168)},
            {"id": "b", "label": "B", "bbox_px": (1602, 0, 3400, 1168)},
            {"id": "c", "label": "C", "bbox_px": (0, 1168, 1469, 2448)},
            {"id": "d", "label": "D", "bbox_px": (1453, 1168, 3400, 2448)},
        ),
    },
    "figure-06": {
        "canvas_px": (3640, 3360),
        "dpi": 200,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (90, 173, 1251, 948)},
            {"id": "b", "label": "B", "bbox_px": (1316, 159, 2432, 948)},
            {"id": "c", "label": "C", "bbox_px": (2494, 173, 3613, 948)},
            {"id": "d", "label": "D", "bbox_px": (125, 1047, 1396, 3110)},
            {"id": "e", "label": "E", "bbox_px": (1306, 1060, 2491, 3117)},
            {"id": "f", "label": "F", "bbox_px": (2485, 1046, 3640, 3117)},
        ),
    },
    "supplementary-01": {
        "canvas_px": (2720, 919),
        "dpi": 200,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 1035, 919)},
            {"id": "b", "label": "B", "bbox_px": (1035, 0, 1875, 919)},
            {"id": "c", "label": "C", "bbox_px": (1875, 0, 2720, 919)},
        ),
    },
    "supplementary-02": {
        "canvas_px": (4080, 1380),
        "dpi": 300,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 1532, 1380)},
            {"id": "b", "label": "B", "bbox_px": (1532, 0, 2818, 1380)},
            {"id": "c", "label": "C", "bbox_px": (2818, 0, 4080, 1380)},
        ),
    },
    "supplementary-04": {
        "canvas_px": (6840, 1770),
        "dpi": 300,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 2010, 1770)},
            {"id": "b", "label": "B", "bbox_px": (2010, 0, 3892, 1770)},
            {"id": "c", "label": "C", "bbox_px": (3892, 0, 6840, 1770)},
        ),
    },
    "supplementary-06": {
        "canvas_px": (5460, 4140),
        "dpi": 300,
        "panels": (
            {"id": "a", "label": "A", "bbox_px": (0, 0, 2109, 4140)},
            {"id": "b", "label": "B", "bbox_px": (2109, 0, 3868, 4140)},
            {"id": "c", "label": "C", "bbox_px": (3868, 0, 5460, 4140)},
        ),
    },
}


PANEL_DATA_SOURCES: dict[str, dict[str, tuple[str, ...]]] = {
    "figure-01": {
        "a": ("results/derived/figure-data/v7_service.csv",),
        "b": (
            "results/derived/figure-data/scenario_electricity_timeseries.csv",
            "results/derived/figure-data/v7_master.csv",
        ),
        "c": (
            "results/derived/figure-data/scenario_electricity_timeseries.csv",
            "figures/figure-01/outlooks_literature.csv",
            "figures/figure-01/outlooks_literature_2050.csv",
        ),
        "d": (
            "results/derived/figure-data/scenario_electricity_timeseries.csv",
            "figures/figure-01/outlooks_literature.csv",
        ),
        "e": ("results/derived/figure-data/scenario_electricity_timeseries.csv",),
    },
    "figure-02": {
        "a": (
            "results/derived/figure-data/fig_capacity_additions_historical.csv",
            "results/derived/figure-data/fig_capacity_additions_model.csv",
            "results/derived/figure-data/v7_capacity.csv",
            "figures/source-data/fig_clean_capacity_history.csv",
            "figures/source-data/fig_clean_capacity_alignment.csv",
            "figures/source-data/fig_clean_capacity_alignment_by_technology.csv",
        ),
        "b": (
            "results/derived/figure-data/fig_capacity_additions_historical.csv",
            "results/derived/figure-data/fig_capacity_additions_model.csv",
            "results/derived/figure-data/v7_capacity.csv",
            "figures/source-data/fig_clean_capacity_history.csv",
            "figures/source-data/fig_clean_capacity_alignment.csv",
            "figures/source-data/fig_clean_capacity_alignment_by_technology.csv",
        ),
        "c": (
            "results/derived/figure-data/v7_capacity.csv",
            "figures/source-data/fig_clean_capacity_history.csv",
            "figures/source-data/fig_clean_capacity_alignment.csv",
            "figures/source-data/fig_clean_capacity_alignment_by_technology.csv",
        ),
        "d": ("results/derived/figure-data/v7_genmix.csv",),
        "e": ("results/derived/figure-data/v7_elec_enduse.csv",),
    },
    "figure-03": {
        "a": ("results/derived/figure-data/fig3_dc_co2_regional.csv",),
        "b": ("results/derived/figure-data/fig3_dc_co2_regional.csv",),
        "c": (
            "results/derived/figure-data/fig3_gridEF_net.csv",
            "figures/source-data/ar6_selected_rows.csv.gz",
        ),
    },
    "figure-04": {
        panel_id: ("results/derived/figure-data/fig_water_footprint.csv",)
        for panel_id in ("a", "b", "c")
    },
    "figure-05": {
        "a": ("results/derived/figure-data/carbon_price_v91.csv",),
        "b": ("results/derived/figure-data/carbon_price_v91.csv",),
        "c": ("results/derived/figure-data/solved_regional_prices_all.csv",),
        "d": ("results/derived/figure-data/solved_regional_prices_all.csv",),
    },
    "figure-06": {
        "a": (
            "results/derived/figure-data/v7_regional.csv",
            "results/derived/figure-data/fig_region_elec_dc_v3.csv",
            "figures/source-data/ne_110m_admin_0_countries.zip",
            "figures/source-data/iso_GCAM_regID.csv",
            "figures/source-data/GCAM_region_names.csv",
        ),
        "b": (
            "results/derived/figure-data/fig_water_footprint.csv",
            "results/derived/figure-data/v7_region_total_water.csv",
            "figures/source-data/ne_110m_admin_0_countries.zip",
            "figures/source-data/iso_GCAM_regID.csv",
            "figures/source-data/GCAM_region_names.csv",
        ),
        "c": (
            "results/derived/figure-data/fig_water_footprint.csv",
            "results/derived/figure-data/v7_region_total_water.csv",
            "figures/source-data/ne_110m_admin_0_countries.zip",
            "figures/source-data/iso_GCAM_regID.csv",
            "figures/source-data/GCAM_region_names.csv",
        ),
        "d": (
            "results/derived/figure-data/v7_regional.csv",
            "results/derived/figure-data/fig_region_elec_dc_v3.csv",
        ),
        "e": (
            "results/derived/figure-data/fig_water_footprint.csv",
            "results/derived/figure-data/v7_region_total_water.csv",
        ),
        "f": (
            "results/derived/figure-data/fig_water_footprint.csv",
            "results/derived/figure-data/v7_region_total_water.csv",
        ),
    },
    "supplementary-01": {
        panel_id: (
            "figures/source-data/supplementary-01/demand_calibration_annual.csv",
            "figures/source-data/supplementary-01/demand_calibration_summary.csv",
            "figures/source-data/supplementary-01/scenario_design.csv",
            "figures/source-data/supplementary-01/scenario_common_parameters.csv",
        )
        for panel_id in ("a", "b", "c")
    },
    "supplementary-02": {
        panel_id: (
            "figures/source-data/supplementary-02/fleet_efficiency_index_2021_2025.csv",
            "figures/source-data/supplementary-02/efficiency_scenario_parameters.csv",
        )
        for panel_id in ("a", "b", "c")
    },
    "supplementary-04": {
        "a": (
            "figures/source-data/supplementary-04/global-electricity-generation-by-source-2000-2025.csv",
        ),
        "b": (
            "figures/source-data/supplementary-04/global-electricity-generation-summary-2000-2025.csv",
        ),
        "c": (
            "figures/source-data/supplementary-04/global-tracked-gross-capacity-additions-2000-2024.csv",
        ),
    },
    "supplementary-06": {
        panel_id: (
            "results/derived/figure-data/v7_regional.csv",
            "results/derived/figure-data/fig_region_elec_dc_v3.csv",
            "results/derived/figure-data/fig_water_footprint.csv",
            "results/derived/figure-data/v7_region_total_water.csv",
        )
        for panel_id in ("a", "b", "c")
    },
}


@dataclass(frozen=True)
class PanelSnapshot:
    figure_id: str
    canvas_px: tuple[int, int]
    hashes: dict[str, str]
    outside_hashes: dict[str, str]


def panel_catalog(figure_id: str) -> list[dict]:
    configuration = FIGURE_PANELS.get(figure_id)
    if configuration is None:
        return []
    return [
        {
            "id": panel["id"],
            "label": panel["label"],
            "bbox_px": list(panel["bbox_px"]),
            "size_px": [
                panel["bbox_px"][2] - panel["bbox_px"][0],
                panel["bbox_px"][3] - panel["bbox_px"][1],
            ],
        }
        for panel in configuration["panels"]
    ]


def figure_canvas_px(figure_id: str) -> tuple[int, int] | None:
    configuration = FIGURE_PANELS.get(figure_id)
    if configuration is None:
        return None
    return tuple(configuration["canvas_px"])


def panel_data_sources(figure_id: str, panel_id: str) -> tuple[Path, ...]:
    validate_panel_id(figure_id, panel_id)
    return tuple(
        Path(relative)
        for relative in PANEL_DATA_SOURCES.get(figure_id, {}).get(panel_id, ())
    )


def validate_panel_id(figure_id: str, value: object | None) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise PanelError("The selected panel is invalid")
    panel_id = value.strip().lower()
    allowed = {panel["id"] for panel in panel_catalog(figure_id)}
    if panel_id not in allowed:
        if figure_id not in FIGURE_PANELS:
            raise PanelError("Panel editing is not available for this figure")
        raise PanelError("The selected panel is invalid")
    return panel_id


def panel_filename(figure_id: str, panel_id: str) -> str:
    validate_panel_id(figure_id, panel_id)
    return f"{figure_id}-{panel_id}.jpg"


def _safe_rgb(path: Path) -> Image.Image:
    from PIL import Image

    if not path.is_file() or path.is_symlink():
        raise PanelError("The full figure preview is unavailable")
    if path.stat().st_size > 50 * 1024 * 1024:
        raise PanelError("The full figure preview is too large for panel editing")
    Image.MAX_IMAGE_PIXELS = 100_000_000
    try:
        with Image.open(path) as source:
            source.load()
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > 100_000_000:
                raise PanelError("The full figure canvas is invalid")
            return source.convert("RGB")
    except PanelError:
        raise
    except Exception as exc:
        raise PanelError("The full figure preview could not be read") from exc


def _scaled_bbox(
    bbox: tuple[int, int, int, int],
    canonical: tuple[int, int],
    actual: tuple[int, int],
) -> tuple[int, int, int, int]:
    canonical_width, canonical_height = canonical
    width, height = actual
    x0, y0, x1, y1 = bbox
    return (
        round(x0 * width / canonical_width),
        round(y0 * height / canonical_height),
        round(x1 * width / canonical_width),
        round(y1 * height / canonical_height),
    )


def _panel_crops(image: Image.Image, figure_id: str):
    configuration = FIGURE_PANELS.get(figure_id)
    if configuration is None:
        raise PanelError("Panel editing is not available for this figure")
    canonical = configuration["canvas_px"]
    for panel in configuration["panels"]:
        bbox = _scaled_bbox(panel["bbox_px"], canonical, image.size)
        yield panel, image.crop(bbox)


def capture_panel_snapshot(path: Path, figure_id: str) -> PanelSnapshot:
    image = _safe_rgb(path)
    hashes: dict[str, str] = {}
    outside_hashes: dict[str, str] = {}
    raw = image.tobytes()
    raw_view = memoryview(raw)
    row_bytes = image.width * 3
    configuration = FIGURE_PANELS.get(figure_id)
    if configuration is None:
        raise PanelError("Panel editing is not available for this figure")
    for panel, crop in _panel_crops(image, figure_id):
        digest = hashlib.sha256()
        digest.update(f"{crop.width}x{crop.height}:RGB\0".encode("ascii"))
        digest.update(crop.tobytes())
        hashes[panel["id"]] = digest.hexdigest()

        x0, y0, x1, y1 = _scaled_bbox(
            panel["bbox_px"], configuration["canvas_px"], image.size
        )
        outside_digest = hashlib.sha256()
        outside_digest.update(
            f"{image.width}x{image.height}:outside:{x0},{y0},{x1},{y1}:RGB\0".encode(
                "ascii"
            )
        )
        outside_digest.update(raw_view[: y0 * row_bytes])
        left_bytes = x0 * 3
        right_bytes = x1 * 3
        for row in range(y0, y1):
            start = row * row_bytes
            outside_digest.update(raw_view[start : start + left_bytes])
            outside_digest.update(raw_view[start + right_bytes : start + row_bytes])
        outside_digest.update(raw_view[y1 * row_bytes :])
        outside_hashes[panel["id"]] = outside_digest.hexdigest()
    return PanelSnapshot(
        figure_id=figure_id,
        canvas_px=image.size,
        hashes=hashes,
        outside_hashes=outside_hashes,
    )


def validate_panel_revision(
    before: PanelSnapshot,
    after_path: Path,
    selected_panel: str,
) -> bool:
    panel_id = validate_panel_id(before.figure_id, selected_panel)
    if panel_id is None:
        raise PanelError("A panel must be selected for panel validation")
    after = capture_panel_snapshot(after_path, before.figure_id)
    if after.canvas_px != before.canvas_px:
        raise PanelError("A panel-only edit must preserve the full figure canvas size")
    changed = [
        candidate
        for candidate, digest in before.hashes.items()
        if after.hashes.get(candidate) != digest
    ]
    if after.outside_hashes.get(panel_id) != before.outside_hashes.get(panel_id):
        outside = [candidate.upper() for candidate in changed if candidate != panel_id]
        detail = (
            " It also changed panel(s) " + ", ".join(outside) + "."
            if outside
            else ""
        )
        raise PanelError(
            f"The panel-only edit changed pixels outside panel {panel_id.upper()}."
            + detail
            + " The attempted revision was restored"
        )
    return panel_id in changed


def ensure_panel_previews(
    source: Path,
    destination: Path,
    figure_id: str,
) -> dict[str, Path]:
    configuration = FIGURE_PANELS.get(figure_id)
    if configuration is None:
        return {}
    if not source.is_file() or source.is_symlink():
        raise PanelError("The full figure preview is unavailable")
    if source.stat().st_size > 50 * 1024 * 1024:
        raise PanelError("The full figure preview is too large for panel editing")
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    source_hash = digest.hexdigest()
    metadata_path = destination / "preview-manifest.json"
    expected = {
        panel["id"]: destination / panel_filename(figure_id, panel["id"])
        for panel in configuration["panels"]
    }
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
        metadata = {}
    if metadata.get("source_sha256") == source_hash and all(
        path.is_file() and not path.is_symlink() for path in expected.values()
    ):
        return expected

    image = _safe_rgb(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=".panel-previews-", dir=destination.parent)
    )
    try:
        for panel, crop in _panel_crops(image, figure_id):
            target = temporary / panel_filename(figure_id, panel["id"])
            crop.save(
                target,
                format="JPEG",
                quality=95,
                subsampling=0,
                dpi=(configuration["dpi"], configuration["dpi"]),
            )
        (temporary / "preview-manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "figure_id": figure_id,
                    "source_sha256": source_hash,
                    "canvas_px": list(image.size),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        panel["id"]: destination / panel_filename(figure_id, panel["id"])
        for panel in configuration["panels"]
    }
