from __future__ import annotations

from copy import deepcopy


DEFAULT_FIGURE_ID = "figure-01"

FIGURE_PROJECTS: dict[str, dict[str, str]] = {
    "figure-01": {
        "label": "Figure 01",
        "title": "Compute-service growth and data center electricity consumption",
        "project_id": "figure-01-compute-and-electricity",
        "entrypoint": "figures/figure-01/make_figure.py",
        "output_stem": "figure-01",
        "default_image": "figure-01.jpg",
        "baseline_description": "Selected template Figure 1 compute-service and electricity-demand results",
    },
    "figure-02": {
        "label": "Figure 02",
        "title": "Power-system response to data center growth",
        "project_id": "figure-02-power-system-response",
        "entrypoint": "figures/figure-02/make_figure.py",
        "output_stem": "figure-02",
        "default_image": "figure-02.jpg",
        "baseline_description": "Selected template Figure 2 clean-capacity and generation results",
    },
    "figure-03": {
        "label": "Figure 03",
        "title": "Data center carbon dioxide emissions and remaining carbon budgets",
        "project_id": "figure-03-emissions",
        "entrypoint": "figures/figure-03/make_figure.py",
        "output_stem": "figure-03",
        "default_image": "figure-03.jpg",
        "baseline_description": "Selected template Figure 3 operational-emissions results and manufacturing sensitivity",
    },
    "figure-04": {
        "label": "Figure 04",
        "title": "Global data center water use",
        "project_id": "figure-04-water",
        "entrypoint": "figures/figure-04/make_figure.py",
        "output_stem": "figure-04",
        "default_image": "figure-04.jpg",
        "baseline_description": "Selected template Figure 4 water-consumption and withdrawal results",
    },
    "figure-05": {
        "label": "Figure 05",
        "title": "Price consequences of data center growth",
        "project_id": "figure-05-prices",
        "entrypoint": "figures/figure-05/make_figure.py",
        "output_stem": "figure-05",
        "default_image": "figure-05.jpg",
        "baseline_description": "Selected template Figure 5 carbon-price and electricity-price results",
    },
    "figure-06": {
        "label": "Figure 06",
        "title": "Regional data center shares of electricity and water",
        "project_id": "figure-06-regional",
        "entrypoint": "figures/figure-06/make_figure.py",
        "output_stem": "figure-06-r12",
        "default_image": "figure-06-r12.jpg",
        "baseline_description": "Selected template Figure 6 with GCAM-32 maps and regional comparison rails",
    },
}


def figure_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": figure_id,
            "label": project["label"],
            "title": project["title"],
        }
        for figure_id, project in FIGURE_PROJECTS.items()
    ]


def project_manifest(figure_id: str) -> dict:
    if figure_id not in FIGURE_PROJECTS:
        raise ValueError("Unknown figure")
    selected = deepcopy(FIGURE_PROJECTS[figure_id])
    selected.pop("label")
    selected.pop("default_image")
    selected.update(
        {
            "figure_id": figure_id,
            "default_formats": ["jpg"],
            "preview_priority": ["jpg", "jpeg", "png", "webp"],
            "data_contract": (
                "Files under results/derived/figure-data, figures/source-data and uploads "
                "are immutable source material. Derived data belongs under data/derived."
            ),
            "output_contract": (
                "The generated JPG must be written under outputs/current. The entrypoint "
                "reads FIG_OUTPUT_DIR, FIG_OUTPUT_FORMATS and FIG_OUTPUT_STEM."
            ),
        }
    )
    return selected
