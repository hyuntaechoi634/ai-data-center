from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any

from .panels import figure_canvas_px, panel_catalog


SCHEMA_VERSION = 1
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_OVERRIDE_BYTES = 1024 * 1024
MAX_ELEMENTS = 2000
MAX_CHANGES = 120
ELEMENT_ID = re.compile(r"^[A-Za-z0-9:_-]{1,120}$")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
FONT_FAMILIES = (
    ("DejaVu Sans", "DejaVu Sans"),
    ("Liberation Sans", "Liberation Sans"),
    ("sans-serif", "System sans serif"),
    ("DejaVu Serif", "DejaVu Serif"),
    ("Liberation Serif", "Liberation Serif"),
    ("serif", "System serif"),
    ("DejaVu Sans Mono", "DejaVu Sans Mono"),
    ("monospace", "System monospace"),
)
ALLOWED_FONT_FAMILIES = {value for value, _label in FONT_FAMILIES}
FONT_WEIGHTS = {"normal", "bold"}
FONT_STYLES = {"normal", "italic"}


class LayoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class LayoutUpdate:
    path: Path
    before: dict[str, Any]
    after: dict[str, Any]
    changed_elements: int

    @property
    def changed(self) -> bool:
        return self.before != self.after


def _number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise LayoutError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LayoutError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise LayoutError(f"{label} must be a finite number")
    return number


def _font_weight(value: object) -> str:
    normalized = str(value or "normal").lower()
    try:
        return "bold" if float(normalized) >= 600 else "normal"
    except ValueError:
        return (
            "bold"
            if normalized in {"bold", "semibold", "demibold", "heavy", "black"}
            else "normal"
        )


def _font_style(value: object) -> str:
    return "italic" if str(value or "normal").lower() in {"italic", "oblique"} else "normal"


def _read_json(path: Path, maximum: int, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise LayoutError(f"The {label} is unavailable")
    if path.stat().st_size > maximum:
        raise LayoutError(f"The {label} is too large")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LayoutError(f"The {label} is invalid") from exc
    if not isinstance(payload, dict):
        raise LayoutError(f"The {label} is invalid")
    return payload


def _panel_for_bbox(
    figure_id: str,
    bbox: list[float],
    canvas: tuple[float, float],
) -> str | None:
    panels = panel_catalog(figure_id)
    if not panels:
        return None
    canonical = figure_canvas_px(figure_id)
    if canonical is None:
        return None
    max_x, max_y = [float(value) for value in canonical]
    width, height = canvas
    x0, y0, x1, y1 = bbox
    best_id: str | None = None
    best_area = 0.0
    for panel in panels:
        px0, py0, px1, py1 = [float(value) for value in panel["bbox_px"]]
        px0, px1 = px0 * width / max_x, px1 * width / max_x
        py0, py1 = py0 * height / max_y, py1 * height / max_y
        overlap_width = max(0.0, min(x1, px1) - max(x0, px0))
        overlap_height = max(0.0, min(y1, py1) - max(y0, py0))
        area = overlap_width * overlap_height
        if area > best_area:
            best_area = area
            best_id = str(panel["id"])
    return best_id


def load_layout_catalog(root: Path, figure_id: str) -> dict[str, Any]:
    payload = _read_json(
        root / "layout" / "elements.json",
        MAX_CATALOG_BYTES,
        "layout catalog",
    )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise LayoutError("The layout catalog version is unsupported")
    if payload.get("figure_id") != figure_id:
        raise LayoutError("The layout catalog belongs to another figure")
    raw_canvas = payload.get("canvas_px")
    if not isinstance(raw_canvas, list) or len(raw_canvas) != 2:
        raise LayoutError("The layout canvas is invalid")
    width = _number(raw_canvas[0], "Canvas width")
    height = _number(raw_canvas[1], "Canvas height")
    if not 100 <= width <= 20000 or not 100 <= height <= 20000:
        raise LayoutError("The layout canvas is invalid")
    raw_elements = payload.get("elements")
    if not isinstance(raw_elements, list) or len(raw_elements) > MAX_ELEMENTS:
        raise LayoutError("The layout element list is invalid")

    elements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_elements:
        if not isinstance(raw, dict):
            raise LayoutError("The layout element list is invalid")
        element_id = str(raw.get("id", ""))
        if not ELEMENT_ID.fullmatch(element_id) or element_id in seen:
            raise LayoutError("The layout element identifiers are invalid")
        seen.add(element_id)
        kind = str(raw.get("kind", ""))
        if kind not in {"axis", "text", "mark"}:
            raise LayoutError("The layout element type is invalid")
        raw_bbox = raw.get("bbox_px")
        if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
            raise LayoutError("A layout element boundary is invalid")
        bbox = [_number(value, "Element boundary") for value in raw_bbox]
        if bbox[2] < bbox[0] or bbox[3] < bbox[1]:
            raise LayoutError("A layout element boundary is invalid")
        if any(abs(value) > max(width, height) * 4 for value in bbox):
            raise LayoutError("A layout element boundary is outside the safe canvas")
        label = " ".join(str(raw.get("label", "")).replace(chr(0xB7), ",").split())
        role = " ".join(str(raw.get("role", "")).split())
        font_size = raw.get("font_size")
        if font_size is not None:
            font_size = _number(font_size, "Font size")
        font_family = str(raw.get("font_family", ""))[:100]
        font_weight = _font_weight(raw.get("font_weight"))
        font_style = _font_style(raw.get("font_style"))
        color = str(raw.get("color", ""))
        if color and not HEX_COLOR.fullmatch(color):
            raise LayoutError("A layout element color is invalid")
        raw_offset = raw.get("offset_px")
        offset = {"x": 0.0, "y": 0.0}
        if isinstance(raw_offset, dict):
            offset = {
                "x": _number(raw_offset.get("x", 0), "Horizontal offset"),
                "y": _number(raw_offset.get("y", 0), "Vertical offset"),
            }
        override = raw.get("override")
        if not isinstance(override, dict):
            override = {}
        elements.append(
            {
                "id": element_id,
                "kind": kind,
                "role": role[:80] or (
                    "Plot" if kind == "axis" else "Mark" if kind == "mark" else "Text"
                ),
                "label": label[:240] or (
                    "Plot" if kind == "axis" else "Mark" if kind == "mark" else "Text"
                ),
                "bbox_px": [round(value, 2) for value in bbox],
                "panel_id": _panel_for_bbox(figure_id, bbox, (width, height)),
                "visible": bool(raw.get("visible", True)),
                "hidden": bool(raw.get("hidden", False)),
                "offset_px": {
                    "x": round(offset["x"], 2),
                    "y": round(offset["y"], 2),
                },
                "font_size": None if font_size is None else round(font_size, 3),
                "font_family": font_family,
                "font_weight": font_weight,
                "font_style": font_style,
                "color": color.lower(),
                "override": override,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "figure_id": figure_id,
        "canvas_px": [round(width), round(height)],
        "elements": elements,
        "font_families": [
            {"id": value, "label": label} for value, label in FONT_FAMILIES
        ],
    }


def _load_overrides(path: Path, figure_id: str) -> dict[str, Any]:
    payload = _read_json(path, MAX_OVERRIDE_BYTES, "layout override file")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("figure_id") != figure_id
        or not isinstance(payload.get("elements"), dict)
    ):
        raise LayoutError("The layout override file is invalid")
    return payload


def prepare_layout_update(
    workspace: Path,
    figure_id: str,
    raw_changes: object,
    panel_id: str | None = None,
) -> LayoutUpdate:
    if not isinstance(raw_changes, list) or not raw_changes:
        raise LayoutError("Choose at least one layout change")
    if len(raw_changes) > MAX_CHANGES:
        raise LayoutError("Too many layout elements were changed at once")
    catalog = load_layout_catalog(workspace, figure_id)
    catalog_by_id = {element["id"]: element for element in catalog["elements"]}
    path = workspace / "figures" / figure_id / "layout-overrides.json"
    before = _load_overrides(path, figure_id)
    after = json.loads(json.dumps(before))
    records = after["elements"]
    changed_ids: set[str] = set()
    maximum_offset = max(catalog["canvas_px"])

    for raw_change in raw_changes:
        if not isinstance(raw_change, dict):
            raise LayoutError("A layout change is invalid")
        element_id = str(raw_change.get("id", ""))
        element = catalog_by_id.get(element_id)
        if element is None:
            raise LayoutError("A selected layout element is no longer available")
        if panel_id and element.get("panel_id") != panel_id:
            raise LayoutError(
                f"The selected element is outside panel {panel_id.upper()}"
            )
        if raw_change.get("reset") is True:
            records.pop(element_id, None)
            changed_ids.add(element_id)
            continue

        allowed_fields = {"id", "reset", "hidden"}
        if element["kind"] == "mark":
            allowed_fields.add("color")
        else:
            allowed_fields.update(
                {"offset_px", "font_size", "font_family", "font_weight", "font_style"}
            )
        if set(raw_change) - allowed_fields:
            raise LayoutError("The selected element does not support that setting")

        record = records.setdefault(element_id, {})
        if not isinstance(record, dict):
            record = {}
            records[element_id] = record
        if "offset_px" in raw_change:
            raw_offset = raw_change["offset_px"]
            if not isinstance(raw_offset, dict):
                raise LayoutError("The element offset is invalid")
            x = _number(raw_offset.get("x", 0), "Horizontal offset")
            y = _number(raw_offset.get("y", 0), "Vertical offset")
            if abs(x) > maximum_offset or abs(y) > maximum_offset:
                raise LayoutError("The element offset is outside the safe canvas")
            if abs(x) < 0.005 and abs(y) < 0.005:
                record.pop("offset_px", None)
            else:
                record["offset_px"] = {"x": round(x, 2), "y": round(y, 2)}
        if "hidden" in raw_change:
            if not isinstance(raw_change["hidden"], bool):
                raise LayoutError("The visibility setting is invalid")
            if raw_change["hidden"]:
                record["hidden"] = True
            else:
                record.pop("hidden", None)
        if "font_size" in raw_change:
            font_size = raw_change["font_size"]
            if font_size in {None, ""}:
                record.pop("font_size", None)
            else:
                parsed_size = _number(font_size, "Font size")
                if not 5 <= parsed_size <= 72:
                    raise LayoutError("Font size must be between 5 and 72 points")
                record["font_size"] = round(parsed_size, 2)
        if "font_family" in raw_change:
            font_family = str(raw_change["font_family"] or "")
            if not font_family:
                record.pop("font_family", None)
            elif font_family not in ALLOWED_FONT_FAMILIES:
                raise LayoutError("The selected font family is unavailable")
            else:
                record["font_family"] = font_family
        if "font_weight" in raw_change:
            font_weight = str(raw_change["font_weight"] or "")
            if not font_weight:
                record.pop("font_weight", None)
            elif font_weight not in FONT_WEIGHTS:
                raise LayoutError("The selected font weight is unavailable")
            else:
                record["font_weight"] = font_weight
        if "font_style" in raw_change:
            font_style = str(raw_change["font_style"] or "")
            if not font_style:
                record.pop("font_style", None)
            elif font_style not in FONT_STYLES:
                raise LayoutError("The selected font style is unavailable")
            else:
                record["font_style"] = font_style
        if "color" in raw_change:
            color = str(raw_change["color"] or "")
            if not color:
                record.pop("color", None)
            elif not HEX_COLOR.fullmatch(color):
                raise LayoutError("Choose a six-digit hexadecimal color")
            else:
                record["color"] = color.lower()
        if not record:
            records.pop(element_id, None)
        changed_ids.add(element_id)

    after["elements"] = dict(sorted(records.items()))
    return LayoutUpdate(path, before, after, len(changed_ids))


def write_layout_update(update: LayoutUpdate) -> None:
    update.path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=update.path.parent,
        delete=False,
    ) as handle:
        json.dump(update.after, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(update.path)
