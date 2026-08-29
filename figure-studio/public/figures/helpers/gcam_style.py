"""Shared GCAM-ROK figure style for the NCC main-text diagnostic charts.
Palette + stack order + sector taxonomy mirror gcam-v7.1-rok/gcam-core/analysis
(power_v11.ipynb custom_colors/stack_order; emiss_by_sec CO2_tech_map categories).
Use: `from gcam_style import POWER_COLORS, GEN_ORDER, SECTOR_COLORS, SECTOR_ORDER, sector_cat, apply_rc, F`
"""
import matplotlib as _mpl

# --- electricity generation by technology (GCAM-ROK power_v11 custom_colors, rgb->hex) ---
POWER_COLORS = {
    "Coal": "#222A2A", "Coal w/ CCS": "#750D86", "Oil": "#7D1215",
    "Gas": "#FFA15A", "Gas w/ CCS": "#DEA0FD", "Nuclear": "#AB63FA",
    "Biomass": "#73AF48", "Biomass w/ CCS": "#2E7D5B", "Geothermal": "#8C564B",
    "Hydro": "#5F4690", "Hydrogen": "#727DCD", "Wind": "#88CCEE",
    "Solar": "#FECB52", "Other": "#D9D9D9",
}
# stacked-area order, bottom -> top (fossils low, renewables high), per ROK stack_order reversed
GEN_ORDER = ["Coal", "Coal w/ CCS", "Oil", "Gas", "Gas w/ CCS", "Nuclear",
             "Biomass", "Biomass w/ CCS", "Geothermal", "Hydro", "Hydrogen",
             "Wind", "Solar", "Other"]
CCS_TECHS = {"Coal w/ CCS", "Gas w/ CCS", "Biomass w/ CCS"}  # hatch these

# --- CO2 emissions by sector (GCAM-ROK emiss_by_sec taxonomy) ---
SECTOR_COLORS = {
    "Power": "#636EFA", "Industry": "#EF553B", "Transport": "#00CC96",
    "Buildings": "#AB63FA", "Energy supply": "#FFA15A", "Agriculture": "#B6E880",
    "Hydrogen": "#19D3F3", "DAC": "#FF97FF", "LULUCF": "#1CA71C", "Other": "#BAB0AC",
}
SECTOR_ORDER = ["Power", "Industry", "Transport", "Buildings", "Energy supply",
                "Agriculture", "Hydrogen", "DAC", "LULUCF", "Other"]


def sector_cat(raw):
    """raw GCAM sector name -> GCAM-ROK sector category."""
    t = str(raw).lower()
    if t.startswith("elec"):
        return "Power"
    if t.startswith("trn") or "transport" in t or "shipping" in t or "aviation" in t:
        return "Transport"
    if any(k in t for k in ["resid", "comm", "building", "district heat"]):
        return "Buildings"
    if any(k in t for k in ["iron", "steel", "cement", "chemical", "alumina", "aluminum",
                            "ammonia", "industr", "process heat", "mining", "construction",
                            "paper", "food processing", "fertilizer", "feedstock"]):
        return "Industry"
    if "hydrogen" in t or t.startswith("h2"):
        return "Hydrogen"
    if "co2 removal" in t or "dac" in t:
        return "DAC"
    if "agricultur" in t:
        return "Agriculture"
    if any(k in t for k in ["land", "lulucf", "uncharacterized", "deforest"]):
        return "LULUCF"
    if any(k in t for k in ["refining", "gas processing", "pipeline", "regional ", "oil",
                            "coal", "gas", "delivered", "backup", "csp_backup", "nuclearFuel"]):
        return "Energy supply"
    return "Other"


# --- fonts / spines (GCAM-ROK: DejaVu Sans, large, white bg, lightgray grid) ---
F = {"axis": 16, "tick": 14, "legend": 13, "panel": 18, "title": 16}


def apply_rc():
    _mpl.rcParams.update({
        "font.size": 14, "font.family": "DejaVu Sans", "axes.linewidth": 1.3,
        "axes.facecolor": "white", "figure.facecolor": "white",
        "axes.edgecolor": "0.2", "axes.grid": False,
        "xtick.labelsize": F["tick"], "ytick.labelsize": F["tick"],
        "legend.fontsize": F["legend"], "axes.labelsize": F["axis"],
        "savefig.facecolor": "white",
    })


def open_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def panel_letter(ax, s):
    ax.text(-0.02, 1.04, s, transform=ax.transAxes, fontsize=F["panel"],
            fontweight="bold", va="bottom", ha="right")
