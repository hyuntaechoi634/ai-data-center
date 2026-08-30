"""Apply reviewed Figure Studio layout overrides to Matplotlib figures.

The plotting scripts remain the scientific source of truth.  This module adds
only a small presentation layer at save time and records selectable artist
bounds for the browser editor.  Offsets are expressed in pixels on the final
saved canvas, while font sizes remain Matplotlib points.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from matplotlib.figure import Figure
from matplotlib.text import Text
from matplotlib.transforms import Bbox, ScaledTranslation


SCHEMA_VERSION = 1
MAX_ELEMENTS = 2000
_INSTALLED = False
_ORIGINAL_SAVEFIG = Figure.savefig


def _finite_number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _load_overrides(path: Path, figure_id: str) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        return {}
    if raw.get("figure_id") != figure_id or not isinstance(raw.get("elements"), dict):
        return {}
    return {
        str(element_id): record
        for element_id, record in raw["elements"].items()
        if isinstance(element_id, str) and isinstance(record, dict)
    }


def _nonempty(text: Text) -> bool:
    try:
        return bool(str(text.get_text()).strip())
    except Exception:
        return False


def _text_inventory(fig: Figure) -> list[tuple[str, str, Text, int | None]]:
    """Return deterministic IDs, roles, artists and parent-axis indices."""
    records: list[tuple[str, str, Text, int | None]] = []
    seen: set[int] = set()

    def add(element_id: str, role: str, artist: Text, axis_index: int | None) -> None:
        if id(artist) in seen or not _nonempty(artist):
            return
        seen.add(id(artist))
        records.append((element_id, role, artist, axis_index))

    for axis_index, axis in enumerate(fig.axes):
        prefix = f"axis-{axis_index:02d}"
        add(f"{prefix}:title", "Title", axis.title, axis_index)
        left_title = getattr(axis, "_left_title", None)
        right_title = getattr(axis, "_right_title", None)
        if isinstance(left_title, Text):
            add(f"{prefix}:title-left", "Title", left_title, axis_index)
        if isinstance(right_title, Text):
            add(f"{prefix}:title-right", "Title", right_title, axis_index)
        add(f"{prefix}:x-label", "X-axis label", axis.xaxis.label, axis_index)
        add(f"{prefix}:y-label", "Y-axis label", axis.yaxis.label, axis_index)

        for tick_index, artist in enumerate(axis.get_xticklabels(minor=False)):
            add(f"{prefix}:x-tick-{tick_index:02d}", "X tick", artist, axis_index)
        for tick_index, artist in enumerate(axis.get_xticklabels(minor=True)):
            add(f"{prefix}:x-minor-tick-{tick_index:02d}", "X minor tick", artist, axis_index)
        for tick_index, artist in enumerate(axis.get_yticklabels(minor=False)):
            add(f"{prefix}:y-tick-{tick_index:02d}", "Y tick", artist, axis_index)
        for tick_index, artist in enumerate(axis.get_yticklabels(minor=True)):
            add(f"{prefix}:y-minor-tick-{tick_index:02d}", "Y minor tick", artist, axis_index)

        legends = []
        primary_legend = axis.get_legend()
        if primary_legend is not None:
            legends.append(primary_legend)
        legends.extend(
            artist
            for artist in axis.artists
            if artist.__class__.__name__ == "Legend" and artist not in legends
        )
        for legend_index, legend in enumerate(legends):
            legend_prefix = f"{prefix}:legend-{legend_index:02d}"
            title = legend.get_title()
            if isinstance(title, Text):
                add(f"{legend_prefix}:title", "Legend title", title, axis_index)
            for text_index, artist in enumerate(legend.get_texts()):
                add(
                    f"{legend_prefix}:text-{text_index:02d}",
                    "Legend label",
                    artist,
                    axis_index,
                )

        for text_index, artist in enumerate(axis.texts):
            add(f"{prefix}:text-{text_index:02d}", "Annotation", artist, axis_index)

        for text_index, artist in enumerate(axis.findobj(match=Text)):
            add(f"{prefix}:other-text-{text_index:02d}", "Text", artist, axis_index)

    for text_index, artist in enumerate(fig.texts):
        add(f"figure:text-{text_index:02d}", "Figure text", artist, None)

    for text_index, artist in enumerate(fig.findobj(match=Text)):
        add(f"figure:other-text-{text_index:02d}", "Text", artist, None)

    return records[:MAX_ELEMENTS]


def _axis_label(axis: Any, index: int) -> str:
    for candidate in (axis.get_title(), axis.get_ylabel(), axis.get_xlabel()):
        text = str(candidate).strip()
        if text:
            return text
    return f"Plot {index + 1}"


def _offset(record: dict[str, Any]) -> tuple[float, float]:
    raw = record.get("offset_px")
    if not isinstance(raw, dict):
        return 0.0, 0.0
    return _finite_number(raw.get("x")), _finite_number(raw.get("y"))


def _apply_axis_override(
    fig: Figure,
    axis: Any,
    record: dict[str, Any],
    canvas_width: float,
    canvas_height: float,
) -> None:
    dx, dy = _offset(record)
    if dx or dy:
        position = axis.get_position(original=False)
        axis.set_position(
            Bbox.from_bounds(
                position.x0 + dx / canvas_width,
                position.y0 - dy / canvas_height,
                position.width,
                position.height,
            )
        )
    if record.get("hidden") is True:
        axis.set_visible(False)
    font_size = record.get("font_size")
    font_family = record.get("font_family")
    if font_size is not None or font_family:
        for artist in axis.findobj(match=Text):
            if font_size is not None:
                artist.set_fontsize(float(font_size))
            if font_family:
                artist.set_fontfamily(str(font_family))


def _apply_text_override(
    fig: Figure,
    artist: Text,
    record: dict[str, Any],
    save_dpi: float,
) -> None:
    dx, dy = _offset(record)
    if dx or dy:
        artist.set_transform(
            artist.get_transform()
            + ScaledTranslation(dx / save_dpi, -dy / save_dpi, fig.dpi_scale_trans)
        )
    if record.get("hidden") is True:
        artist.set_visible(False)
    if record.get("font_size") is not None:
        artist.set_fontsize(float(record["font_size"]))
    if record.get("font_family"):
        artist.set_fontfamily(str(record["font_family"]))


def _bbox_px(artist: Any, renderer: Any, height: float) -> list[float] | None:
    try:
        bbox = artist.get_window_extent(renderer)
        values = (bbox.x0, height - bbox.y1, bbox.x1, height - bbox.y0)
    except Exception:
        return None
    if not all(math.isfinite(float(value)) for value in values):
        return None
    return [round(float(value), 2) for value in values]


def _font_family(artist: Text) -> str:
    try:
        families = artist.get_fontfamily()
    except Exception:
        return ""
    return str(families[0]) if families else ""


def _write_catalog(
    path: Path,
    fig: Figure,
    figure_id: str,
    save_dpi: float,
    axes: list[tuple[str, Any]],
    texts: list[tuple[str, str, Text, int | None]],
    overrides: dict[str, dict[str, Any]],
) -> None:
    original_dpi = float(fig.dpi)
    try:
        fig.set_dpi(save_dpi)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        width = float(fig.get_figwidth() * save_dpi)
        height = float(fig.get_figheight() * save_dpi)
        elements: list[dict[str, Any]] = []
        for element_id, axis in axes:
            bbox = _bbox_px(axis, renderer, height)
            if bbox is None:
                continue
            record = overrides.get(element_id, {})
            elements.append(
                {
                    "id": element_id,
                    "kind": "axis",
                    "role": "Plot",
                    "label": _axis_label(axis, int(element_id.split("-")[1])),
                    "bbox_px": bbox,
                    "visible": bool(axis.get_visible()),
                    "offset_px": {
                        "x": _offset(record)[0],
                        "y": _offset(record)[1],
                    },
                    "font_size": record.get("font_size"),
                    "font_family": record.get("font_family", ""),
                    "hidden": record.get("hidden") is True,
                    "override": record,
                }
            )
        for element_id, role, artist, axis_index in texts:
            bbox = _bbox_px(artist, renderer, height)
            if bbox is None:
                continue
            record = overrides.get(element_id, {})
            label = " ".join(str(artist.get_text()).split())
            elements.append(
                {
                    "id": element_id,
                    "kind": "text",
                    "role": role,
                    "label": label[:240],
                    "axis_index": axis_index,
                    "bbox_px": bbox,
                    "visible": bool(artist.get_visible()),
                    "offset_px": {
                        "x": _offset(record)[0],
                        "y": _offset(record)[1],
                    },
                    "font_size": round(float(artist.get_fontsize()), 3),
                    "font_family": _font_family(artist),
                    "hidden": record.get("hidden") is True,
                    "override": record,
                }
            )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "figure_id": figure_id,
            "canvas_px": [round(width), round(height)],
            "dpi": save_dpi,
            "elements": elements,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        fig.set_dpi(original_dpi)


def install_layout_runtime(
    figure_id: str,
    override_path: Path,
    catalog_path: Path,
) -> None:
    """Install one save hook for the active Figure Studio render process."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    overrides = _load_overrides(override_path, figure_id)

    def savefig_with_layout(fig: Figure, *args: Any, **kwargs: Any) -> Any:
        save_dpi = _finite_number(kwargs.get("dpi"), float(fig.dpi))
        if save_dpi <= 0:
            save_dpi = float(fig.dpi)
        fig.canvas.draw()
        texts = _text_inventory(fig)
        axes = [(f"axis-{index:02d}", axis) for index, axis in enumerate(fig.axes)]
        width = float(fig.get_figwidth() * save_dpi)
        height = float(fig.get_figheight() * save_dpi)
        for element_id, axis in axes:
            _apply_axis_override(
                fig,
                axis,
                overrides.get(element_id, {}),
                width,
                height,
            )
        for element_id, _role, artist, _axis_index in texts:
            _apply_text_override(
                fig,
                artist,
                overrides.get(element_id, {}),
                save_dpi,
            )
        result = _ORIGINAL_SAVEFIG(fig, *args, **kwargs)
        _write_catalog(
            catalog_path,
            fig,
            figure_id,
            save_dpi,
            axes,
            texts,
            overrides,
        )
        return result

    Figure.savefig = savefig_with_layout


def install_entrypoint_layout(figure_dir: Path, figure_id: str) -> None:
    """Install layout support when a public figure entrypoint runs directly."""
    project_root = (
        figure_dir.parents[1]
        if figure_dir.parent.name == "figures"
        else figure_dir
    )
    catalog_path = Path(
        os.environ.get(
            "FIG_LAYOUT_CATALOG",
            str(project_root / "layout" / "elements.json"),
        )
    )
    install_layout_runtime(
        figure_id,
        figure_dir / "layout-overrides.json",
        catalog_path,
    )
