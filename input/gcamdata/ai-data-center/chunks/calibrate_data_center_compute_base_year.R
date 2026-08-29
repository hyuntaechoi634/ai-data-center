# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_L1280.ai_compute_prod
#'
#' Recover 2021 service-specific compute output and carve data-center
#' electricity and scope-1 water from the inherited industrial residual.
#' Training, inference, and conventional output use TSU, ISU, and CSU,
#' respectively; world output of each service is normalized to one in 2021.
#' @importFrom assertthat assert_that
#' @importFrom dplyr bind_rows distinct filter group_by if_else left_join mutate
#'   rename select summarise ungroup
#' @importFrom tidyr gather replace_na
#' @author gcamdata-ai 2026
module_energy_L1280.ai_compute_prod <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(FILE = "common/GCAM_region_names",
             FILE = "energy/datacenter_elec_EJ_R_Yh",
             FILE = "energy/datacenter_convshare_R",
             FILE = "energy/ai_share_fAI_R_Y",
             FILE = "energy/ai_service_electricity_share_Y",
             FILE = "energy/A_aicomp_services",
             FILE = "energy/A280.globaltech_eff",
             FILE = "energy/A281.globaltech_eff",
             FILE = "water/A280.globaltech_water_coef",
             FILE = "energy/pue_R",
             "L144.in_EJ_R_bld_serv_F_Yh",
             "L144.base_service_EJ_serv_fuel",
             "L1441.in_EJ_R_bld_serv_F_tech_Yh_USA",
             "L1441.base_service_EJ_serv_fuel_tech_USA"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c("L1280.out_R_aicompute_Yh",
             "L1280.in_EJ_R_aicompute_F_Y",
             "L1280.out_R_convcompute_Yh",
             "L1280.in_EJ_R_convcompute_F_Y",
             "L1280.in_EJ_R_bld_serv_F_Yh",
             "L1280.base_service_EJ_serv",
             "L1280.base_service_EJ_serv_fuel",
             "L1280.in_EJ_R_bld_serv_F_tech_Yh_USA",
             "L1280.base_service_EJ_serv_fuel_tech_USA",
             "L1280.gamma_R",
             "L1280.omega_R",
             "L1280.water_km3_R"))
  } else if(command == driver.MAKE) {

    year <- value <- GCAM_region_ID <- region <- fuel <- service <-
      supplysector <- production.good <- minicam.energy.input <-
      minicam.water.input <- coefficient <- iota <- M <- gamma <-
      electricity.share <- elec_total <- f_AI <- convshare <- elec_AI <-
      elec_conv <- raw <- scale <- water_type <- wcoef <- elec <-
      water_km3 <- `2021` <- NULL

    all_data <- list(...)[[1]]
    GCAM_region_names <- get_data(
      all_data, "common/GCAM_region_names", strip_attributes = TRUE)
    datacenter_elec_EJ_R_Yh <- get_data(
      all_data, "energy/datacenter_elec_EJ_R_Yh", strip_attributes = TRUE)
    datacenter_convshare_R <- get_data(
      all_data, "energy/datacenter_convshare_R", strip_attributes = TRUE)
    ai_share_fAI_R_Y <- get_data(
      all_data, "energy/ai_share_fAI_R_Y", strip_attributes = TRUE)
    ai_service_electricity_share_Y <- get_data(
      all_data, "energy/ai_service_electricity_share_Y",
      strip_attributes = TRUE)
    A_aicomp_services <- get_data(
      all_data, "energy/A_aicomp_services", strip_attributes = TRUE)
    A280.globaltech_eff <- get_data(
      all_data, "energy/A280.globaltech_eff", strip_attributes = TRUE)
    A281.globaltech_eff <- get_data(
      all_data, "energy/A281.globaltech_eff", strip_attributes = TRUE)
    A280.globaltech_water_coef <- get_data(
      all_data, "water/A280.globaltech_water_coef",
      strip_attributes = TRUE)
    pue_R <- get_data(all_data, "energy/pue_R", strip_attributes = TRUE)
    L144.in_EJ_R_bld_serv_F_Yh <- get_data(
      all_data, "L144.in_EJ_R_bld_serv_F_Yh", strip_attributes = TRUE)
    L144.base_service_EJ_serv_fuel <- get_data(
      all_data, "L144.base_service_EJ_serv_fuel", strip_attributes = TRUE)
    L1441.in_EJ_R_bld_serv_F_tech_Yh_USA <- get_data(
      all_data, "L1441.in_EJ_R_bld_serv_F_tech_Yh_USA", strip_attributes = TRUE)
    L1441.base_service_EJ_serv_fuel_tech_USA <- get_data(
      all_data, "L1441.base_service_EJ_serv_fuel_tech_USA", strip_attributes = TRUE)


    calibration_year <- max(MODEL_BASE_YEARS)

    # Headroom for the carve: the commercial residual service. Outside the
    # United States that is "comm others" in the aggregate buildings data;
    # inside it, L244 replaces the aggregate rows with the Scout-based
    # detailed services, whose residual is "comm other".
    BLD_COMM_RESIDUAL <- "comm others"
    USA_COMM_RESIDUAL <- "comm other"
    L144.in_EJ_R_bld_serv_F_Yh %>%
      filter(sector == "bld_comm", service == BLD_COMM_RESIDUAL,
             fuel == "electricity", year == calibration_year) %>%
      group_by(GCAM_region_ID) %>%
      summarise(raw = sum(value), .groups = "drop") ->
      L1280.bld_headroom_row
    L1441.in_EJ_R_bld_serv_F_tech_Yh_USA %>%
      filter(supplysector == USA_COMM_RESIDUAL, subsector == "electricity",
             year == calibration_year) %>%
      group_by(GCAM_region_ID) %>%
      summarise(raw_usa = sum(calibrated.value), .groups = "drop") ->
      L1280.bld_headroom_usa
    L1280.bld_headroom_row %>%
      left_join(L1280.bld_headroom_usa, by = "GCAM_region_ID") %>%
      mutate(raw = if_else(is.na(raw_usa), raw, raw_usa), raw_usa = NULL) ->
      L1280.bld_headroom

    datacenter_elec_EJ_R_Yh %>%
      left_join_error_no_match(GCAM_region_names, by = "region") %>%
      rename(elec_total = `2021`) %>%
      select(GCAM_region_ID, region, fuel, elec_total) %>%
      left_join_error_no_match(
        ai_share_fAI_R_Y %>%
          select(region, f_AI = `2021`),
        by = "region") %>%
      left_join_error_no_match(datacenter_convshare_R, by = "region") %>%
      mutate(
        elec_AI = elec_total * f_AI,
        elec_conv = sum(elec_total * (1 - f_AI)) * convshare) ->
      L1280.electricity

    # Preserve the inherited residual with a proportional regional clamp. The
    # same scale applies to both AI services and conventional compute.
    L1280.bld_headroom %>%
      select(GCAM_region_ID, raw) ->
      L1280.residual
    L1280.electricity %>%
      left_join_error_no_match(L1280.residual, by = "GCAM_region_ID") %>%
      mutate(
        scale = if_else(
          elec_AI + elec_conv > raw & elec_AI + elec_conv > 0,
          pmax(raw, 0) / (elec_AI + elec_conv), 1),
        elec_AI = elec_AI * scale,
        elec_conv = elec_conv * scale) ->
      L1280.electricity
    if(any(L1280.electricity$scale < 1)) {
      warning("L1280: data-center carve scaled in ",
              sum(L1280.electricity$scale < 1), " region(s).")
    }

    # A280 stores IT electricity per service unit. Regional facility
    # electricity per unit is gamma_s,r = iota_s * M_r.
    A280.globaltech_eff %>%
      gather_years() %>%
      filter(year == calibration_year) %>%
      select(production.good = supplysector, iota = value) %>%
      left_join_error_no_match(
        A_aicomp_services %>% select(service, production.good),
        by = "production.good") %>%
      select(service, iota) ->
      L1280.ai_iota
    pue_R %>%
      filter(year == calibration_year) %>%
      select(region, M) ->
      L1280.M
    ai_service_electricity_share_Y %>%
      filter(year == calibration_year) %>%
      select(service, electricity.share) ->
      L1280.service_share

    L1280.electricity %>%
      select(GCAM_region_ID, region, elec_AI) %>%
      repeat_add_columns(L1280.service_share) %>%
      left_join_error_no_match(L1280.ai_iota, by = "service") %>%
      left_join_error_no_match(L1280.M, by = "region") %>%
      mutate(
        elec = elec_AI * electricity.share,
        gamma = iota * M,
        year = calibration_year,
        value = round(elec / gamma, energy.DIGITS_CALOUTPUT)) ->
      L1280.ai_service

    assert_that(
      all(sort(unique(L1280.ai_service$service)) ==
            sort(c("training", "inference"))),
      msg = "L1280: both AI services must be present")

    L1280.ai_service %>%
      select(GCAM_region_ID, region, year, service, value) ->
      L1280.out_R_aicompute_Yh

    L1280.ai_service %>%
      mutate(gamma = round(gamma, energy.DIGITS_COEFFICIENT)) %>%
      select(GCAM_region_ID, region, service, gamma) ->
      L1280.gamma_R

    A280.globaltech_water_coef %>%
      select(supplysector, minicam.water.input, omega = coefficient) %>%
      left_join_error_no_match(
        A_aicomp_services %>% select(service, production.good),
        by = c("supplysector" = "production.good")) %>%
      select(service, minicam.water.input, omega) ->
      L1280.water_coef
    L1280.gamma_R %>%
      left_join(L1280.water_coef, by = "service") %>%
      mutate(omega = round(omega * gamma, energy.DIGITS_COEFFICIENT)) %>%
      select(GCAM_region_ID, region, service, minicam.water.input, omega) ->
      L1280.omega_R

    L1280.electricity %>%
      mutate(year = calibration_year, fuel = "electricity",
             value = round(elec_AI, energy.DIGITS_CALOUTPUT)) %>%
      select(GCAM_region_ID, year, fuel, value) ->
      L1280.in_EJ_R_aicompute_F_Y

    A281.globaltech_eff %>%
      gather_years() %>%
      filter(year == calibration_year) %>%
      pull(value) ->
      L1280.conv_iota
    L1280.conv_iota <- L1280.conv_iota[1]

    L1280.electricity %>%
      left_join_error_no_match(L1280.M, by = "region") %>%
      mutate(
        year = calibration_year,
        value = round(
          elec_conv / (L1280.conv_iota * M),
          energy.DIGITS_CALOUTPUT)) %>%
      select(GCAM_region_ID, region, year, value) ->
      L1280.out_R_convcompute_Yh

    L1280.electricity %>%
      mutate(year = calibration_year, fuel = "electricity",
             value = round(elec_conv, energy.DIGITS_CALOUTPUT)) %>%
      select(GCAM_region_ID, year, fuel, value) ->
      L1280.in_EJ_R_convcompute_F_Y

    # Total data center electricity to remove, by region and year
    bind_rows(
      L1280.in_EJ_R_aicompute_F_Y,
      L1280.in_EJ_R_convcompute_F_Y) %>%
      filter(fuel == "electricity") %>%
      group_by(GCAM_region_ID, year) %>%
      summarise(carve = sum(value), .groups = "drop") ->
      L1280.bld_carve

    # (a) aggregate buildings energy, all regions, commercial residual only
    L144.in_EJ_R_bld_serv_F_Yh %>%
      left_join(L1280.bld_carve, by = c("GCAM_region_ID", "year")) %>%
      mutate(carve = replace_na(carve, 0),
             target = sector == "bld_comm" & service == BLD_COMM_RESIDUAL &
                      fuel == "electricity",
             keep = if_else(target, pmax(value - carve, 0), value),
             ratio = if_else(target & value > 0, keep / value, 1),
             value = keep, carve = NULL, target = NULL, keep = NULL) ->
      L1280.bld_energy_ratio
    L1280.bld_energy_ratio %>%
      select(-ratio) ->
      L1280.in_EJ_R_bld_serv_F_Yh

    # (b) base service by fuel scales with the same ratio, so that the
    #     identity base service = energy x efficiency is preserved
    L144.base_service_EJ_serv_fuel %>%
      left_join(L1280.bld_energy_ratio %>%
                  select(GCAM_region_ID, sector, fuel, service, year, ratio),
                by = c("GCAM_region_ID", "sector", "fuel", "service", "year")) %>%
      mutate(ratio = replace_na(ratio, 1), value = value * ratio, ratio = NULL) ->
      L1280.base_service_EJ_serv_fuel

    # (c) the aggregate base service is the sum over fuels, as in L144
    L1280.base_service_EJ_serv_fuel %>%
      group_by(GCAM_region_ID, sector, service, year) %>%
      summarise(value = sum(value), .groups = "drop") ->
      L1280.base_service_EJ_serv

    # (d) the United States, whose detailed services replace the aggregate
    L1441.in_EJ_R_bld_serv_F_tech_Yh_USA %>%
      left_join(L1280.bld_carve, by = c("GCAM_region_ID", "year")) %>%
      mutate(carve = replace_na(carve, 0),
             target = supplysector == USA_COMM_RESIDUAL &
                      subsector == "electricity") %>%
      group_by(GCAM_region_ID, year) %>%
      mutate(pool = sum(if_else(target, calibrated.value, 0)),
             share = if_else(target & pool > 0, calibrated.value / pool, 0),
             new_value = if_else(target,
                                 pmax(calibrated.value - carve * share, 0),
                                 calibrated.value),
             usa_ratio = if_else(target & calibrated.value > 0,
                                 new_value / calibrated.value, 1)) %>%
      ungroup() %>%
      mutate(calibrated.value = new_value) %>%
      select(-carve, -target, -pool, -share, -new_value) ->
      L1280.usa_energy_ratio
    L1280.usa_energy_ratio %>%
      select(-usa_ratio) ->
      L1280.in_EJ_R_bld_serv_F_tech_Yh_USA

    L1441.base_service_EJ_serv_fuel_tech_USA %>%
      left_join(L1280.usa_energy_ratio %>%
                  select(GCAM_region_ID, supplysector, subsector, technology,
                         year, usa_ratio),
                by = c("GCAM_region_ID", "supplysector", "subsector",
                       "technology", "year")) %>%
      mutate(usa_ratio = replace_na(usa_ratio, 1),
             calibrated.value = calibrated.value * usa_ratio,
             base.service = base.service * usa_ratio,
             usa_ratio = NULL) ->
      L1280.base_service_EJ_serv_fuel_tech_USA

    water_type_map <- tibble::tibble(
      minicam.water.input = c("water_td_ind_W", "water_td_ind_C"),
      water_type = c("water withdrawals", "water consumption"))
    bind_rows(
      L1280.in_EJ_R_aicompute_F_Y,
      L1280.in_EJ_R_convcompute_F_Y) %>%
      filter(fuel == "electricity") %>%
      group_by(GCAM_region_ID, year) %>%
      summarise(elec = sum(value), .groups = "drop") %>%
      repeat_add_columns(
        A280.globaltech_water_coef %>%
          select(minicam.water.input, wcoef = coefficient) %>%
          distinct(minicam.water.input, .keep_all = TRUE)) %>%
      left_join_error_no_match(water_type_map, by = "minicam.water.input") %>%
      mutate(water_km3 = round(elec * wcoef, energy.DIGITS_CALOUTPUT)) %>%
      select(GCAM_region_ID, year, water_type, water_km3) ->
      L1280.water_km3_R

    L1280.out_R_aicompute_Yh %>%
      add_title("Base-year regional AI compute output by service") %>%
      add_units("TSU for training; ISU for inference") %>%
      add_comments("Recovered independently from allocated IT electricity and the matching service benchmark") %>%
      add_precursors(
        "common/GCAM_region_names", "energy/datacenter_elec_EJ_R_Yh",
        "energy/ai_share_fAI_R_Y",
        "energy/ai_service_electricity_share_Y",
        "energy/A_aicomp_services", "energy/A280.globaltech_eff",
        "energy/pue_R", "L144.in_EJ_R_bld_serv_F_Yh") ->
      L1280.out_R_aicompute_Yh

    L1280.in_EJ_R_aicompute_F_Y %>%
      add_title("Base-year AI-compute facility electricity") %>%
      add_units("EJ") %>%
      add_comments("Total training plus inference electricity carved from the industrial residual") %>%
      same_precursors_as(L1280.out_R_aicompute_Yh) ->
      L1280.in_EJ_R_aicompute_F_Y

    L1280.out_R_convcompute_Yh %>%
      add_title("Base-year regional conventional compute output") %>%
      add_units("CSU") %>%
      add_comments("Recovered from conventional IT electricity and its matching SPECpower benchmark") %>%
      add_precursors(
        "common/GCAM_region_names", "energy/datacenter_elec_EJ_R_Yh",
        "energy/datacenter_convshare_R", "energy/A281.globaltech_eff",
        "energy/pue_R") ->
      L1280.out_R_convcompute_Yh

    L1280.in_EJ_R_convcompute_F_Y %>%
      add_title("Base-year conventional-compute facility electricity") %>%
      add_units("EJ") %>%
      same_precursors_as(L1280.out_R_convcompute_Yh) ->
      L1280.in_EJ_R_convcompute_F_Y

    L1280.in_EJ_R_bld_serv_F_Yh %>%
      add_title("Building energy after the data-center carve") %>%
      add_units("EJ") %>%
      add_comments("Commercial residual electricity minus data-center electricity") %>%
      add_precursors("L144.in_EJ_R_bld_serv_F_Yh") ->
      L1280.in_EJ_R_bld_serv_F_Yh

    L1280.base_service_EJ_serv %>%
      add_title("Building base service after the data-center carve") %>%
      add_units("EJ") %>%
      add_comments("Sum over fuels of the rebased base service") %>%
      add_precursors("L144.base_service_EJ_serv_fuel", "L144.in_EJ_R_bld_serv_F_Yh") ->
      L1280.base_service_EJ_serv

    L1280.base_service_EJ_serv_fuel %>%
      add_title("Building base service by fuel after the data-center carve") %>%
      add_units("EJ") %>%
      add_comments("Scaled by the same ratio as the rebased energy") %>%
      add_precursors("L144.base_service_EJ_serv_fuel", "L144.in_EJ_R_bld_serv_F_Yh") ->
      L1280.base_service_EJ_serv_fuel

    L1280.in_EJ_R_bld_serv_F_tech_Yh_USA %>%
      add_title("United States detailed building energy after the carve") %>%
      add_units("EJ") %>%
      add_comments("Carve applied to the comm other electricity technologies") %>%
      add_precursors("L1441.in_EJ_R_bld_serv_F_tech_Yh_USA") ->
      L1280.in_EJ_R_bld_serv_F_tech_Yh_USA

    L1280.base_service_EJ_serv_fuel_tech_USA %>%
      add_title("United States detailed base service after the carve") %>%
      add_units("EJ") %>%
      add_comments("Scaled by the same ratio as the rebased energy") %>%
      add_precursors("L1441.base_service_EJ_serv_fuel_tech_USA",
                     "L1441.in_EJ_R_bld_serv_F_tech_Yh_USA") ->
      L1280.base_service_EJ_serv_fuel_tech_USA

    L1280.gamma_R %>%
      add_title("Base-year regional AI facility-electricity coefficients") %>%
      add_units("EJ/TSU or EJ/ISU") %>%
      add_comments("gamma_s,r = iota_s * M_r") %>%
      same_precursors_as(L1280.out_R_aicompute_Yh) ->
      L1280.gamma_R

    L1280.omega_R %>%
      add_title("Base-year regional AI scope-1 water coefficients") %>%
      add_units("km3/TSU or km3/ISU") %>%
      add_comments("Water coefficient equals WUE times facility-electricity coefficient") %>%
      add_precursors(
        "L1280.gamma_R", "water/A280.globaltech_water_coef") ->
      L1280.omega_R

    L1280.water_km3_R %>%
      add_title("Base-year data-center scope-1 water carve") %>%
      add_units("km3") %>%
      add_comments("AI plus conventional facility electricity times WUE") %>%
      add_precursors(
        "L1280.in_EJ_R_aicompute_F_Y",
        "L1280.in_EJ_R_convcompute_F_Y",
        "water/A280.globaltech_water_coef") ->
      L1280.water_km3_R

    return_data(
      L1280.out_R_aicompute_Yh,
      L1280.in_EJ_R_aicompute_F_Y,
      L1280.out_R_convcompute_Yh,
      L1280.in_EJ_R_convcompute_F_Y,
      L1280.in_EJ_R_bld_serv_F_Yh,
      L1280.base_service_EJ_serv,
      L1280.base_service_EJ_serv_fuel,
      L1280.in_EJ_R_bld_serv_F_tech_Yh_USA,
      L1280.base_service_EJ_serv_fuel_tech_USA,
      L1280.gamma_R,
      L1280.omega_R,
      L1280.water_km3_R)
  } else {
    stop("Unknown command")
  }
}
