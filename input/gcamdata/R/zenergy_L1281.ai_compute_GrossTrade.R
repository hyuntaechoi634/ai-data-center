# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_L1281.ai_compute_GrossTrade
#'
#' Validate and reshape the constructed 2021 trade accounts separately for
#' training (TSU) and inference (ISU). No cross-service quantity sum is used.
#' @importFrom assertthat assert_that
#' @importFrom dplyr group_by mutate rename select summarise ungroup
#' @importFrom tidyr gather
#' @author gcamdata-ai 2026
module_energy_L1281.ai_compute_GrossTrade <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(FILE = "common/GCAM_region_names",
             FILE = "energy/datacenter_tradebalance_R_Y",
             "L1280.out_R_aicompute_Yh"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c("LB1281.Tradebalance_aicompute_R_Y"))
  } else if(command == driver.MAKE) {

    region <- service <- year <- metric <- value <- production <-
      consumption <- exports <- imports <- domestic <- generated_production <-
      relative_error <- GCAM_region <- NULL

    all_data <- list(...)[[1]]
    GCAM_region_names <- get_data(
      all_data, "common/GCAM_region_names", strip_attributes = TRUE)
    datacenter_tradebalance_R_Y <- get_data(
      all_data, "energy/datacenter_tradebalance_R_Y",
      strip_attributes = TRUE)
    L1280.out_R_aicompute_Yh <- get_data(
      all_data, "L1280.out_R_aicompute_Yh", strip_attributes = TRUE)

    expected_regions <- sort(GCAM_region_names$region)
    region_counts <- datacenter_tradebalance_R_Y %>%
      group_by(service) %>%
      summarise(
        complete = identical(sort(region), expected_regions),
        .groups = "drop")
    assert_that(
      all(region_counts$complete),
      msg = "L1281: each service must contain the complete GCAM region set")

    L1280.out_R_aicompute_Yh %>%
      filter(year == max(MODEL_BASE_YEARS)) %>%
      select(service, region, generated_production = value) %>%
      left_join_error_no_match(
        datacenter_tradebalance_R_Y %>%
          select(service, region, production),
        by = c("service", "region")) %>%
      mutate(
        relative_error = abs(production - generated_production) /
          pmax(abs(generated_production), 1e-12)) ->
      production_check
    assert_that(
      max(production_check$relative_error) <= 0.005,
      msg = paste0(
        "L1281: trade production differs from generated service output; ",
        "maximum relative error = ",
        signif(max(production_check$relative_error), 4)))

    regional_error <- max(
      abs(
        datacenter_tradebalance_R_Y$production -
          datacenter_tradebalance_R_Y$domestic -
          datacenter_tradebalance_R_Y$exports),
      abs(
        datacenter_tradebalance_R_Y$consumption -
          datacenter_tradebalance_R_Y$domestic -
          datacenter_tradebalance_R_Y$imports))
    assert_that(
      regional_error <= 1e-6,
      msg = paste0(
        "L1281: service trade identities fail; max error = ",
        signif(regional_error, 4)))

    world_balance <- datacenter_tradebalance_R_Y %>%
      group_by(service) %>%
      summarise(
        error = abs(sum(exports) - sum(imports)),
        production = sum(production),
        consumption = sum(consumption),
        .groups = "drop")
    assert_that(
      all(world_balance$error <= 1e-6),
      all(abs(world_balance$production - world_balance$consumption) <= 1e-6),
      msg = "L1281: world trade must clear separately in TSU and ISU")

    datacenter_tradebalance_R_Y %>%
      rename(
        exports_reval = exports,
        imports_reval = imports,
        consumption_reval = consumption,
        domestic_supply = domestic,
        GCAM_region = region) %>%
      mutate(year = max(MODEL_BASE_YEARS)) %>%
      gather(
        key = "metric", value = "value",
        production, exports_reval, imports_reval,
        consumption_reval, domestic_supply) %>%
      mutate(value = round(value, energy.DIGITS_CALOUTPUT)) %>%
      select(service, GCAM_region, year, metric, value) ->
      LB1281.Tradebalance_aicompute_R_Y

    LB1281.Tradebalance_aicompute_R_Y %>%
      add_title("Base-year service-specific gross trade of AI compute") %>%
      add_units("TSU for training; ISU for inference") %>%
      add_comments("Constructed accounting initialization; each service clears separately") %>%
      add_precursors(
        "common/GCAM_region_names",
        "energy/datacenter_tradebalance_R_Y",
        "L1280.out_R_aicompute_Yh") ->
      LB1281.Tradebalance_aicompute_R_Y

    return_data(LB1281.Tradebalance_aicompute_R_Y)
  } else {
    stop("Unknown command")
  }
}
