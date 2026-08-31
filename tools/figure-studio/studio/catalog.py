from __future__ import annotations

from copy import deepcopy


DEFAULT_FIGURE_ID = "figure-01"

MAIN_FIGURE_IDS = tuple(f"figure-{number:02d}" for number in range(1, 7))
SUPPLEMENTARY_FIGURE_IDS = tuple(
    f"supplementary-{number:02d}" for number in range(1, 7)
)
FIGURE_IDS = MAIN_FIGURE_IDS + SUPPLEMENTARY_FIGURE_IDS

FIGURE_PROJECTS: dict[str, dict[str, str]] = {
    "figure-01": {
        "label": "Figure 01",
        "title": "Compute-service growth and data center electricity consumption",
        "project_id": "figure-01-compute-and-electricity",
        "entrypoint": "figures/figure-01/make_figure.py",
        "output_stem": "figure-01",
        "default_image": "figure-01.jpg",
        "baseline_description": "GCAM 9.1 final calibrated Figure 1 compute-service and electricity-demand results",
    },
    "figure-02": {
        "label": "Figure 02",
        "title": "Power-system response to data center growth",
        "project_id": "figure-02-power-system-response",
        "entrypoint": "figures/figure-02/make_figure.py",
        "output_stem": "figure-02",
        "default_image": "figure-02.jpg",
        "baseline_description": "GCAM 9.1 final calibrated Figure 2 clean-capacity and generation results",
    },
    "figure-03": {
        "label": "Figure 03",
        "title": "Data center carbon dioxide emissions and remaining carbon budgets",
        "project_id": "figure-03-emissions",
        "entrypoint": "figures/figure-03/make_figure.py",
        "output_stem": "figure-03",
        "default_image": "figure-03.jpg",
        "baseline_description": "GCAM 9.1 final calibrated Figure 3 operational-emissions results and manufacturing sensitivity",
    },
    "figure-04": {
        "label": "Figure 04",
        "title": "Global data center water use",
        "project_id": "figure-04-water",
        "entrypoint": "figures/figure-04/make_figure.py",
        "output_stem": "figure-04",
        "default_image": "figure-04.jpg",
        "baseline_description": "GCAM 9.1 final calibrated Figure 4 water-consumption and withdrawal results",
    },
    "figure-05": {
        "label": "Figure 05",
        "title": "Price consequences of data center growth",
        "project_id": "figure-05-prices",
        "entrypoint": "figures/figure-05/make_figure.py",
        "output_stem": "figure-05",
        "default_image": "figure-05.jpg",
        "baseline_description": "GCAM 9.1 final calibrated Figure 5 carbon-price and electricity-price results",
    },
    "figure-06": {
        "label": "Figure 06",
        "title": "Regional data center shares of electricity and water",
        "project_id": "figure-06-regional",
        "entrypoint": "figures/figure-06/make_figure.py",
        "output_stem": "figure-06",
        "default_image": "figure-06.jpg",
        "baseline_description": "GCAM 9.1 final calibrated Figure 6 with 32 model-region maps and 12-region comparison rails",
    },
    "supplementary-01": {
        "label": "Supplementary Figure 01",
        "title": "Computing-service demand calibration and pathways",
        "project_id": "supplementary-01-computing-demand-paths",
        "entrypoint": "figures/supplementary-01/make_figure.py",
        "output_stem": "supplementary-01",
        "default_image": "supplementary-01.jpg",
        "baseline_description": "Supplementary computing-demand calibration and scenario pathways",
    },
    "supplementary-02": {
        "label": "Supplementary Figure 02",
        "title": "Computing-efficiency calibration and pathways",
        "project_id": "supplementary-02-computing-efficiency-paths",
        "entrypoint": "figures/supplementary-02/make_figure.py",
        "output_stem": "supplementary-02",
        "default_image": "supplementary-02.jpg",
        "baseline_description": "Supplementary computing-efficiency calibration and scenario pathways",
    },
    "supplementary-03": {
        "label": "Supplementary Figure 03",
        "title": "Climate-policy emissions pathways",
        "project_id": "supplementary-03-climate-policy-paths",
        "entrypoint": "figures/supplementary-03/make_figure.py",
        "output_stem": "supplementary-03",
        "default_image": "supplementary-03.jpg",
        "baseline_description": "Supplementary Reference and global net-zero carbon dioxide pathways",
    },
    "supplementary-04": {
        "label": "Supplementary Figure 04",
        "title": "Historical global electricity generation and capacity additions",
        "project_id": "supplementary-04-historical-electricity",
        "entrypoint": "figures/supplementary-04/make_figure.py",
        "output_stem": "supplementary-04",
        "default_image": "supplementary-04.jpg",
        "baseline_description": "Supplementary historical global generation mix, clean shares, and tracked capacity additions",
    },
    "supplementary-05": {
        "label": "Supplementary Figure 05",
        "title": "Regional industrial electricity-price effects",
        "project_id": "supplementary-05-regional-electricity-prices",
        "entrypoint": "figures/supplementary-05/make_figure.py",
        "output_stem": "supplementary-05",
        "default_image": "supplementary-05.jpg",
        "baseline_description": "Supplementary full-resolution industrial electricity-price effects for 32 GCAM regions",
    },
    "supplementary-06": {
        "label": "Supplementary Figure 06",
        "title": "Regional data center electricity and water shares",
        "project_id": "supplementary-06-regional-electricity-water",
        "entrypoint": "figures/supplementary-06/make_figure.py",
        "output_stem": "supplementary-06",
        "default_image": "supplementary-06.jpg",
        "baseline_description": "Supplementary full-resolution electricity and water shares for 32 GCAM regions",
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
