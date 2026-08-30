"""Apply reviewed Figure Studio layout overrides to Matplotlib figures.

The plotting scripts remain the scientific source of truth.  This module adds
only a small presentation layer at save time and records selectable artist
bounds for the browser editor.  Offsets are expressed in pixels on the final
saved canvas, while font sizes remain Matplotlib points.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Any

from matplotlib.colors import to_hex
from matplotlib.container import BarContainer, ErrorbarContainer
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.text import Text
from matplotlib.transforms import Bbox, ScaledTranslation


SCHEMA_VERSION = 1
MAX_ELEMENTS = 2000
_INSTALLED = False
_ORIGINAL_SAVEFIG = Figure.savefig


@dataclass(frozen=True)
class MarkRecord:
    element_id: str
    role: str
    label: str
    artists: tuple[Any, ...]
    bbox_artists: tuple[Any, ...]
    axis_index: int
    color_mode: str


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


def _public_artist_label(artist: Any) -> str:
    try:
        label = " ".join(str(artist.get_label()).split())
    except Exception:
        return ""
    return "" if not label or label.startswith("_") else label[:160]


def _errorbar_artists(container: ErrorbarContainer) -> tuple[Any, ...]:
    artists: list[Any] = []
    try:
        data_line, cap_lines, bar_lines = container.lines
    except (AttributeError, TypeError, ValueError):
        return ()
    artists.extend(bar_lines or ())
    artists.extend(cap_lines or ())
    if data_line is not None:
        artists.append(data_line)
    return tuple(artist for artist in artists if artist is not None)


def _legend_handles(axis: Any) -> list[tuple[Any, str]]:
    legend = axis.get_legend()
    if legend is None:
        return []
    handles = getattr(legend, "legend_handles", None)
    if handles is None:
        handles = getattr(legend, "legendHandles", ())
    texts = legend.get_texts()
    return [
        (handle, " ".join(str(text.get_text()).split())[:160])
        for handle, text in zip(handles or (), texts)
    ]


def _line_segments(artist: Any) -> list[list[list[float]]]:
    getter = getattr(artist, "get_segments", None)
    if getter is None:
        return []
    try:
        raw_segments = getter()
    except Exception:
        return []
    segments: list[list[list[float]]] = []
    for raw_segment in raw_segments:
        if hasattr(raw_segment, "tolist"):
            raw_segment = raw_segment.tolist()
        try:
            segment = [
                [float(point[0]), float(point[1])]
                for point in raw_segment
            ]
        except (TypeError, ValueError, IndexError):
            continue
        if len(segment) >= 2:
            segments.append(segment)
    return segments


def _is_capped_whisker_pair(vertical: Any, caps: Any) -> bool:
    vertical_segments = _line_segments(vertical)
    cap_segments = _line_segments(caps)
    if len(vertical_segments) != 1 or len(cap_segments) != 2:
        return False
    v0, v1 = vertical_segments[0][0], vertical_segments[0][-1]
    scale = max(abs(value) for value in (*v0, *v1, 1.0))
    tolerance = scale * 1e-7
    if abs(v0[0] - v1[0]) > tolerance:
        return False
    endpoint_y = sorted((v0[1], v1[1]))
    cap_y: list[float] = []
    for segment in cap_segments:
        start, end = segment[0], segment[-1]
        if abs(start[1] - end[1]) > tolerance:
            return False
        if not min(start[0], end[0]) - tolerance <= v0[0] <= max(
            start[0], end[0]
        ) + tolerance:
            return False
        cap_y.append((start[1] + end[1]) / 2)
    return all(
        abs(actual - expected) <= tolerance
        for actual, expected in zip(sorted(cap_y), endpoint_y)
    )


def _mark_inventory(fig: Figure) -> list[MarkRecord]:
    """Collect deterministic bar, whisker, line and shape groups."""
    records: list[MarkRecord] = []
    seen: set[int] = set()

    for axis_index, axis in enumerate(fig.axes):
        prefix = f"axis-{axis_index:02d}"
        legend_entries = _legend_handles(axis)
        counters = {"bar": 0, "whisker": 0, "line": 0, "shape": 0, "legend": 0}

        def add(
            category: str,
            role: str,
            label: str,
            artists: tuple[Any, ...],
            color_mode: str,
        ) -> None:
            base_artists = tuple(
                artist
                for artist in artists
                if artist is not None and id(artist) not in seen
            )
            if not base_artists:
                return
            for artist in base_artists:
                seen.add(id(artist))
            public_label = label or f"{role} {counters[category] + 1}"
            linked = tuple(
                handle
                for handle, legend_label in legend_entries
                if label and legend_label == label and id(handle) not in seen
            )
            for artist in linked:
                seen.add(id(artist))
            element_id = f"{prefix}:{category}-{counters[category]:02d}"
            counters[category] += 1
            records.append(
                MarkRecord(
                    element_id=element_id,
                    role=role,
                    label=public_label,
                    artists=base_artists + linked,
                    bbox_artists=base_artists,
                    axis_index=axis_index,
                    color_mode=color_mode,
                )
            )

        for container in axis.containers:
            if isinstance(container, BarContainer):
                add(
                    "bar",
                    "Bars",
                    _public_artist_label(container),
                    tuple(container.patches),
                    "face",
                )
            elif isinstance(container, ErrorbarContainer):
                add(
                    "whisker",
                    "Capped whisker",
                    _public_artist_label(container),
                    _errorbar_artists(container),
                    "stroke",
                )

        collections = list(axis.collections)
        for collection_index in range(len(collections) - 1):
            vertical = collections[collection_index]
            caps = collections[collection_index + 1]
            if id(vertical) in seen or id(caps) in seen:
                continue
            if _is_capped_whisker_pair(vertical, caps):
                add(
                    "whisker",
                    "Capped whisker",
                    "",
                    (vertical, caps),
                    "stroke",
                )

        for collection in axis.collections:
            if id(collection) in seen:
                continue
            class_name = collection.__class__.__name__
            if "LineCollection" in class_name:
                role, category, color_mode = "Range line", "line", "stroke"
            elif "PathCollection" in class_name:
                role, category, color_mode = "Markers", "shape", "face"
            else:
                role, category, color_mode = "Area", "shape", "face"
            add(
                category,
                role,
                _public_artist_label(collection),
                (collection,),
                color_mode,
            )

        for line in axis.lines:
            if id(line) in seen or not isinstance(line, Line2D):
                continue
            add(
                "line",
                "Line",
                _public_artist_label(line),
                (line,),
                "stroke",
            )

        for patch in axis.patches:
            if id(patch) in seen or not isinstance(patch, Patch):
                continue
            add(
                "shape",
                "Shape",
                _public_artist_label(patch),
                (patch,),
                "face",
            )

        for handle, label in legend_entries:
            if id(handle) in seen:
                continue
            add(
                "legend",
                "Legend color",
                label,
                (handle,),
                "face" if isinstance(handle, Patch) else "stroke",
            )

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


def _apply_mark_override(mark: MarkRecord, record: dict[str, Any]) -> None:
    hidden = record.get("hidden") is True
    color = str(record.get("color", ""))
    for artist in mark.artists:
        if hidden:
            artist.set_visible(False)
        if not color:
            continue
        try:
            if mark.color_mode == "face" and hasattr(artist, "set_facecolor"):
                artist.set_facecolor(color)
            elif hasattr(artist, "set_color"):
                artist.set_color(color)
            elif hasattr(artist, "set_edgecolor"):
                artist.set_edgecolor(color)
        except (AttributeError, TypeError, ValueError):
            continue


def _bbox_px(artist: Any, renderer: Any, height: float) -> list[float] | None:
    try:
        bbox = artist.get_window_extent(renderer)
        values = (bbox.x0, height - bbox.y1, bbox.x1, height - bbox.y0)
    except Exception:
        return None
    if not all(math.isfinite(float(value)) for value in values):
        return None
    return [round(float(value), 2) for value in values]


def _group_bbox_px(
    artists: tuple[Any, ...],
    renderer: Any,
    height: float,
) -> list[float] | None:
    boxes: list[Bbox] = []
    for artist in artists:
        bbox: Bbox | None = None
        try:
            candidate = artist.get_window_extent(renderer)
            candidate_values = (
                candidate.x0,
                candidate.y0,
                candidate.x1,
                candidate.y1,
            )
            if all(math.isfinite(float(value)) for value in candidate_values):
                bbox = candidate
        except Exception:
            pass
        if bbox is None:
            segments = _line_segments(artist)
            points = [point for segment in segments for point in segment]
            if points:
                try:
                    transformed = artist.get_transform().transform(points)
                    if hasattr(transformed, "tolist"):
                        transformed = transformed.tolist()
                    xs = [float(point[0]) for point in transformed]
                    ys = [float(point[1]) for point in transformed]
                    values = (*xs, *ys)
                    if values and all(math.isfinite(value) for value in values):
                        bbox = Bbox.from_extents(min(xs), min(ys), max(xs), max(ys))
                except Exception:
                    pass
        if bbox is None:
            continue
        try:
            values = (bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        except Exception:
            continue
        if all(math.isfinite(float(value)) for value in values):
            boxes.append(bbox)
    if not boxes:
        return None
    combined = Bbox.union(boxes)
    return [
        round(float(combined.x0), 2),
        round(float(height - combined.y1), 2),
        round(float(combined.x1), 2),
        round(float(height - combined.y0), 2),
    ]


def _simple_color(value: Any) -> str:
    if hasattr(value, "tolist"):
        value = value.tolist()
    while isinstance(value, (list, tuple)) and value and isinstance(
        value[0], (list, tuple)
    ):
        value = value[0]
    try:
        return to_hex(value, keep_alpha=False).lower()
    except (TypeError, ValueError):
        return ""


def _mark_color(mark: MarkRecord) -> str:
    for artist in mark.bbox_artists:
        getters = (
            ("get_facecolor", "get_color", "get_edgecolor")
            if mark.color_mode == "face"
            else ("get_color", "get_edgecolor", "get_facecolor")
        )
        for getter_name in getters:
            getter = getattr(artist, getter_name, None)
            if getter is None:
                continue
            try:
                color = _simple_color(getter())
            except Exception:
                continue
            if color:
                return color
    return ""


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
    marks: list[MarkRecord],
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
        for mark in marks:
            bbox = _group_bbox_px(mark.bbox_artists, renderer, height)
            if bbox is None:
                continue
            record = overrides.get(mark.element_id, {})
            elements.append(
                {
                    "id": mark.element_id,
                    "kind": "mark",
                    "role": mark.role,
                    "label": mark.label,
                    "axis_index": mark.axis_index,
                    "bbox_px": bbox,
                    "visible": any(
                        bool(artist.get_visible()) for artist in mark.bbox_artists
                    ),
                    "offset_px": {"x": 0.0, "y": 0.0},
                    "font_size": None,
                    "font_family": "",
                    "color": record.get("color") or _mark_color(mark),
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
            "elements": elements[:MAX_ELEMENTS],
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
        marks = _mark_inventory(fig)
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
        for mark in marks:
            _apply_mark_override(mark, overrides.get(mark.element_id, {}))
        result = _ORIGINAL_SAVEFIG(fig, *args, **kwargs)
        _write_catalog(
            catalog_path,
            fig,
            figure_id,
            save_dpi,
            axes,
            texts,
            marks,
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
