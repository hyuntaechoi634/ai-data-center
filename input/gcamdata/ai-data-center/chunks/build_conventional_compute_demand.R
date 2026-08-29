# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_L2286.conv_compute_demand
#'
#' DEMAND layer for conventional compute (GCAM v7.0 PORT, chi-deepening structure): ONE per-capita final
#' demand on the regional "conventional compute" good (non-traded).
#'   income.elasticity = 1 (GDP-proportional; replaces the old satiating 0.8->0.2).
#'   price.elasticity  = beta (from A281.demand).
#'   aeei              = dimensionless benchmark-equivalent demand shifter from analysis/demand-axes.
#'                       Conventional demand follows one common post-2025 path across the AI scenarios.
#'   BaseService       = the L1280 conventional carve in CSU, base year 2021.
#' @return L2286.* tibbles.
#' @importFrom assertthat assert_that
#' @importFrom dplyr filter if_else left_join mutate rename select distinct
#' @author gcamdata-ai 2026 (v7.0 port)
module_energy_L2286.conv_compute_demand <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(FILE = "common/GCAM_region_names",
             FILE = "energy/A281.demand",
             FILE = "energy/aeei_chi_compute_ref",      # chi_conv deepening (med/reference)
             FILE = "energy/aeei_calib_2025_R",         # REGION-specific aeei(2025) = 2025 soft-calibration
             "L1280.out_R_convcompute_Yh"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c("L2286.PerCapitaBased_convcompute",
             "L2286.BaseService_convcompute",
             "L2286.IncomeElasticity_convcompute",   # = 1
             "L2286.PriceElasticity_convcompute",    # = beta
             "L2286.aeei_convcompute"))              # = chi_conv deepening
  } else if(command == driver.MAKE) {

    year <- value <- GCAM_region_ID <- region <- energy.final.demand <- perCapitaBased <-
      income.elasticity <- price.elasticity <- base.service <- service <- scenario <- aeei <- aeei_calib <- NULL

    all_data <- list(...)[[1]]
    GCAM_region_names <- get_data(all_data, "common/GCAM_region_names", strip_attributes = TRUE)
    A281.demand <- get_data(all_data, "energy/A281.demand", strip_attributes = TRUE)
    aeei_chi_ref <- get_data(all_data, "energy/aeei_chi_compute_ref", strip_attributes = TRUE)
    aeei_calib_2025_R <- get_data(all_data, "energy/aeei_calib_2025_R", strip_attributes = TRUE)
    L1280.out_R_convcompute_Yh <- get_data(all_data, "L1280.out_R_convcompute_Yh", strip_attributes = TRUE)

    conv_demand_name <- A281.demand[["energy.final.demand"]][1]

    # 1. PerCapitaBased flag
    A281.demand %>%
      mutate(perCapitaBased = 1) %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["PerCapitaBased"]], GCAM_region_names) ->
      L2286.PerCapitaBased_convcompute

    # 2. BaseService = the conventional CSU carve. Non-traded: consumption = production.
    L1280.out_R_convcompute_Yh %>%
      filter(year %in% MODEL_BASE_YEARS) %>%
      mutate(energy.final.demand = conv_demand_name,
             base.service = round(value, energy.DIGITS_CALOUTPUT)) %>%
      select(LEVEL2_DATA_NAMES[["BaseService"]]) ->
      L2286.BaseService_convcompute

    # 3. Income elasticity = 1 (GDP-proportional); deepening carried by aeei.
    tibble::tibble(energy.final.demand = conv_demand_name) %>%
      repeat_add_columns(GCAM_region_names["region"]) %>%
      repeat_add_columns(tibble::tibble(year = MODEL_FUTURE_YEARS)) %>%
      mutate(income.elasticity = 1) %>%
      select(LEVEL2_DATA_NAMES[["IncomeElasticity"]]) ->
      L2286.IncomeElasticity_convcompute

    # 4. Price elasticity = beta (constant from A281.demand).
    A281.demand %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["PriceElasticity"]][LEVEL2_DATA_NAMES[["PriceElasticity"]] != "year"],
                           GCAM_region_names) %>%
      repeat_add_columns(tibble::tibble(year = MODEL_FUTURE_YEARS)) %>%
      select(LEVEL2_DATA_NAMES[["PriceElasticity"]]) ->
      L2286.PriceElasticity_convcompute

    # 5. aeei = chi_conv deepening (med/reference), from the SAME chi generator as AI. Region-common; future yrs.
    aeei_chi_ref %>%
      filter(service == "conv", year %in% MODEL_FUTURE_YEARS) %>%
      select(year, aeei) %>%
      repeat_add_columns(GCAM_region_names["region"]) %>%
      # 2025 soft calibration: region-specific aeei(2025) from energy/aeei_calib_2025_R (service "conv");
      # 2030+ stays region-common. Refined by scripts/recal/step5_softcal_2025.py to hit the BNEF/IEA
      # regional conventional-DC targets (conv is non-traded, so this pins conv geography AND level).
      left_join(aeei_calib_2025_R %>% filter(service == "conv") %>%
                  select(region, aeei_calib = aeei), by = "region") %>%
      mutate(aeei = if_else(year == 2025 & !is.na(aeei_calib), aeei_calib, aeei)) %>%
      mutate(energy.final.demand = conv_demand_name) %>%
      select(region, energy.final.demand, year, aeei) ->
      L2286.aeei_convcompute

    # ---- metadata ----
    L2286.PerCapitaBased_convcompute %>%
      add_title("Per-capita flag for conventional compute") %>% add_units("NA") %>%
      add_comments("Single mature digital-service final demand") %>%
      add_precursors("energy/A281.demand", "common/GCAM_region_names") -> L2286.PerCapitaBased_convcompute
    L2286.BaseService_convcompute %>%
      add_title("Base-year (2021) service for conventional compute") %>% add_units("CSU") %>%
      add_comments("2021-normalized conventional benchmark-equivalent service unit") %>%
      add_precursors("L1280.out_R_convcompute_Yh", "energy/A281.demand") -> L2286.BaseService_convcompute
    L2286.IncomeElasticity_convcompute %>%
      add_title("Income elasticity (=1) for conventional compute") %>% add_units("Unitless") %>%
      add_comments("GDP-proportional; deepening carried by aeei (chi_conv)") %>%
      add_precursors("energy/A281.demand", "common/GCAM_region_names") -> L2286.IncomeElasticity_convcompute
    L2286.PriceElasticity_convcompute %>%
      add_title("Price elasticity (beta) for conventional compute") %>% add_units("Unitless") %>%
      add_comments("From A281.demand (beta), constant over future years") %>%
      add_precursors("energy/A281.demand", "common/GCAM_region_names") -> L2286.PriceElasticity_convcompute
    L2286.aeei_convcompute %>%
      add_title("Deepening aeei (chi_conv) for conventional compute") %>% add_units("/yr") %>%
      add_comments("chi_conv from the chi generator; 2025 region-specific (soft calibration, aeei_calib_2025_R); negative=growth") %>%
      add_precursors("energy/aeei_chi_compute_ref", "energy/aeei_calib_2025_R", "energy/A281.demand", "common/GCAM_region_names") ->
      L2286.aeei_convcompute

    return_data(L2286.PerCapitaBased_convcompute, L2286.BaseService_convcompute,
                L2286.IncomeElasticity_convcompute, L2286.PriceElasticity_convcompute,
                L2286.aeei_convcompute)
  } else {
    stop("Unknown command")
  }
}
