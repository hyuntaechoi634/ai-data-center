"""Single source of truth for the service-specific scenario topology."""

DEMANDS = ("Low", "Medium", "High")
EFFS = ("Low", "Medium", "High")
POLICIES = ("ref", "nz2050co2")
# Scenario-name policy tokens used by the final 24-scenario matrix.
POLNAME = {"ref": "Reference", "nz2050co2": "NetZero2050"}
COUNTERFACTUALS = ("Constant",)
EXTRA_DEMAND_XMLS = COUNTERFACTUALS


def cell(demand, efficiency):
    """Return an unambiguous demand-by-efficiency cell name."""
    return f"D{demand}_E{efficiency}"


def tag(cell_name, policy):
    return f"{cell_name}_{policy}"


def fq(cell_name, policy):
    return f"AI_{cell_name}_{POLNAME[policy]}"


CELLS = tuple(
    cell(demand, efficiency)
    for efficiency in EFFS
    for demand in DEMANDS
)
CF_CELLS = tuple(
    cell(demand, efficiency)
    for efficiency in EFFS
    for demand in COUNTERFACTUALS
)
TAGS = tuple(tag(value, policy) for policy in POLICIES for value in CELLS)
FQNAMES = tuple(fq(value, policy) for policy in POLICIES for value in CELLS)
CF_TAGS = tuple(
    tag(value, policy) for policy in POLICIES for value in CF_CELLS
)
CF_FQNAMES = tuple(
    fq(value, policy) for policy in POLICIES for value in CF_CELLS
)

# New databases keep the service-unit architecture separate from all legacy
# base/loweff results. Runs sharing a policy append distinct scenario names.
# Final matrix layout: two databases, one per policy.
# Constant counterfactuals live inside the policy databases.
DB = {
    "ref": "database_ai_data_center_reference_basexdb",
    "nz2050co2": "database_ai_data_center_net_zero_2050_basexdb",
}
CONSTANT_DB = None

def database_for(demand, policy):
    """Return the result database for a scenario (policy decides; Constant included)."""
    return DB[policy]


def db_short(policy):
    return DB[policy].removeprefix("database_").removesuffix("_basexdb")


INTERMEDIATE = cell("Medium", "Medium")
# Compatibility alias for calibration utilities written before the scenario
# terminology was tightened. "Medium" is an intermediate-persistence pathway,
# not a central estimate or probabilistic expectation.
CENTRAL = INTERMEDIATE
LOWER_BOUND = cell("Low", "High")
UPPER_BOUND = cell("High", "Low")
