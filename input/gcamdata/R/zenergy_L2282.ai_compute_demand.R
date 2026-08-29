# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_L2282.ai_compute_demand
#'
#' DEMAND layer (GCAM v7.0 PORT, chi-deepening structure): TWO per-capita final demands on the regional
#' Armington goods "regional training compute" and "regional inference compute".
#'   D = D_base (GDP/GDP0)^1 (p/p0)^beta chi(t).
#'   income.elasticity = 1 (GDP-proportional; replaces the old satiating alpha 1.0/1.4).
#'   price.elasticity  = beta (from A280.demand; -0.8 main).
#'   aeei              = dimensionless autonomous-demand shifter from
#'                       analysis/demand-axes. Scenarios diverge in 2030.
#'   BaseService       = service-specific 2021 consumption from LB1281.
#' @return L2282.* tibbles.
#' @importFrom assertthat assert_that
#' @importFrom dplyr filter if_else left_join mutate rename select distinct
#' @importFrom tidyr replace_na
#' @author gcamdata-ai 2026 (v7.0 port)
module_energy_L2282.ai_compute_demand <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(FILE = "common/GCAM_region_names",
             FILE = "energy/A280.demand",                # perCapitaBased + price.elasticity (beta); service names
             FILE = "energy/aeei_chi_compute_ref",       # chi-deepening aeei (med/reference), by service x year
             FILE = "energy/aeei_calib_2025_R",          # REGION-specific aeei(2025) = 2025 soft-calibration
             "LB1281.Tradebalance_aicompute_R_Y"))       # consumption_reval -> base.service
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c("L2282.PerCapitaBased_aicompute",
             "L2282.BaseService_aicompute",
             "L2282.IncomeElasticity_aicompute",   # = 1 (GDP-proportional)
             "L2282.PriceElasticity_aicompute",    # = beta
             "L2282.aeei_aicompute"))              # = chi deepening (NEW)
  } else if(command == driver.MAKE) {

    year <- value <- region <- GCAM_region <- GCAM_region_ID <- metric <- energy.final.demand <-
      perCapitaBased <- income.elasticity <- price.elasticity <- base.service <-
      consumption_reval <- service <- scenario <- aeei <- aeei_calib <- NULL

    all_data <- list(...)[[1]]
    GCAM_region_names <- get_data(all_data, "common/GCAM_region_names", strip_attributes = TRUE)
    A280.demand <- get_data(all_data, "energy/A280.demand", strip_attributes = TRUE)
    aeei_chi_ref <- get_data(all_data, "energy/aeei_chi_compute_ref", strip_attributes = TRUE)
    aeei_calib_2025_R <- get_data(all_data, "energy/aeei_calib_2025_R", strip_attributes = TRUE)
    LB1281.Tradebalance_aicompute_R_Y <- get_data(all_data, "LB1281.Tradebalance_aicompute_R_Y", strip_attributes = TRUE)

    # 1. PerCapitaBased flag (both services)
    A280.demand %>%
      mutate(perCapitaBased = 1) %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["PerCapitaBased"]], GCAM_region_names) ->
      L2282.PerCapitaBased_aicompute

    # 2. BaseService uses the service key carried by the separate trade accounts.
    LB1281.Tradebalance_aicompute_R_Y %>%
      filter(metric == "consumption_reval", year %in% MODEL_BASE_YEARS) %>%
      rename(region = GCAM_region, consumption_reval = value) %>%
      select(service, region, year, consumption_reval) ->
      consumption_R_Y
    A280.demand %>%
      select(energy.final.demand) %>%
      distinct() %>%
      mutate(service = if_else(
        grepl("inference", energy.final.demand), "inference", "training")) %>%
      left_join(consumption_R_Y, by = "service") %>%
      mutate(base.service = round(
        consumption_reval, energy.DIGITS_CALOUTPUT)) %>%
      select(LEVEL2_DATA_NAMES[["BaseService"]]) ->
      L2282.BaseService_aicompute

    # 3. Income elasticity = 1 (GDP-proportional). Deepening is carried by aeei (chi), NOT income-elasticity.
    A280.demand %>%
      select(energy.final.demand) %>% distinct() %>%
      repeat_add_columns(GCAM_region_names["region"]) %>%
      repeat_add_columns(tibble::tibble(year = MODEL_FUTURE_YEARS)) %>%
      mutate(income.elasticity = 1) %>%
      select(LEVEL2_DATA_NAMES[["IncomeElasticity"]]) ->
      L2282.IncomeElasticity_aicompute

    # 4. Price elasticity = beta (from A280.demand), over future years.
    A280.demand %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["PriceElasticity"]][LEVEL2_DATA_NAMES[["PriceElasticity"]] != "year"],
                           GCAM_region_names) %>%
      repeat_add_columns(tibble::tibble(year = MODEL_FUTURE_YEARS)) %>%
      select(LEVEL2_DATA_NAMES[["PriceElasticity"]]) ->
      L2282.PriceElasticity_aicompute

    # 5. aeei = chi DEEPENING (med/reference). Map service -> energy.final.demand; region-common; future years.
    #    "training"/"inference" service rows -> the matching demand name (grepl). Scenario XMLs override low/high.
    A280.demand %>% select(energy.final.demand) %>% distinct() %>%
      mutate(service = if_else(grepl("inference", energy.final.demand), "inference", "training")) ->
      demand_map
    aeei_chi_ref %>%
      filter(service %in% c("training", "inference"), year %in% MODEL_FUTURE_YEARS) %>%
      select(service, year, aeei) %>%
      left_join_error_no_match(demand_map, by = "service") %>%
      repeat_add_columns(GCAM_region_names["region"]) %>%
      # 2025 soft calibration (plan 2026-07-06): the year-2025 aeei is REGION-SPECIFIC, from
      # energy/aeei_calib_2025_R (seeded region-common by chi_to_aeei.py; refined per region by
      # scripts/recal/step5_softcal_2025.py so the SOLVED 2025 hits the BNEF/IEA targets). 2030+ stays
      # region-common (the scenario grid), so scenarios pass through the calibrated 2025 point.
      left_join(aeei_calib_2025_R %>% rename(aeei_calib = aeei), by = c("service", "region")) %>%
      mutate(aeei = if_else(year == 2025 & !is.na(aeei_calib), aeei_calib, aeei)) %>%
      select(region, energy.final.demand, year, aeei) ->
      L2282.aeei_aicompute

    # ---- metadata ----
    L2282.PerCapitaBased_aicompute %>%
      add_title("Per-capita-based flag for AI-compute final demands") %>% add_units("NA") %>%
      add_comments("Both regional compute services are per-capita based") %>%
      add_precursors("energy/A280.demand", "common/GCAM_region_names") -> L2282.PerCapitaBased_aicompute
    L2282.BaseService_aicompute %>%
      add_title("Base-year (2021) service for AI-compute final demands") %>% add_units("TSU or ISU") %>%
      add_comments("Service-specific consumption from independently balanced training and inference accounts") %>%
      add_precursors("energy/A280.demand", "LB1281.Tradebalance_aicompute_R_Y",
                     "common/GCAM_region_names") -> L2282.BaseService_aicompute
    L2282.IncomeElasticity_aicompute %>%
      add_title("Income elasticity (=1) for AI-compute final demands") %>% add_units("Unitless") %>%
      add_comments("GDP-proportional; deepening carried by aeei (chi), not income elasticity") %>%
      add_precursors("energy/A280.demand", "common/GCAM_region_names") -> L2282.IncomeElasticity_aicompute
    L2282.PriceElasticity_aicompute %>%
      add_title("Price elasticity (beta) for AI-compute final demands") %>% add_units("Unitless") %>%
      add_comments("From A280.demand (beta); expanded over future years") %>%
      add_precursors("energy/A280.demand", "common/GCAM_region_names") -> L2282.PriceElasticity_aicompute
    L2282.aeei_aicompute %>%
      add_title("Deepening aeei (chi) for AI-compute final demands") %>% add_units("/yr") %>%
      add_comments("chi deepening: 2025 region-specific (soft calibration, aeei_calib_2025_R); 2030+ common (scenario grid); negative=growth") %>%
      add_precursors("energy/aeei_chi_compute_ref", "energy/aeei_calib_2025_R", "energy/A280.demand", "common/GCAM_region_names") ->
      L2282.aeei_aicompute

    return_data(L2282.PerCapitaBased_aicompute, L2282.BaseService_aicompute,
                L2282.IncomeElasticity_aicompute, L2282.PriceElasticity_aicompute, L2282.aeei_aicompute)
  } else {
    stop("Unknown command")
  }
}
