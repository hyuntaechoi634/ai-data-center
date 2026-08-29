# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_L2285.conv_compute_prod
#'
#' PRODUCTION layer for CONVENTIONAL (non-AI) data-center compute: the non-traded twin of "AI compute".
#' One regional supplysector, single subsector = technology, NO chip input and NO trade layer -- the only
#' inputs are electricity at gamma_conv,r(t) = iota_conv(t) * M_r(t) plus
#' scope-1 water and a general-purpose non-energy
#' cost. Capital tracked like AI compute (GlobalTechTrackCapital). Calibrated
#' by output from the L1280 conventional carve in CSU.
#' @return L2285.* tibbles.
#' @importFrom assertthat assert_that
#' @importFrom dplyr arrange bind_rows distinct filter if_else group_by left_join mutate rename select ungroup
#' @importFrom tidyr complete gather nesting
#' @author gcamdata-ai 2026
module_energy_L2285.conv_compute_prod <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(FILE = "common/GCAM_region_names",
             FILE = "energy/A281.sector",
             FILE = "energy/A281.subsector_logit",
             FILE = "energy/A281.subsector_interp",
             FILE = "energy/A281.globaltech_shrwt",
             FILE = "energy/A281.globaltech_eff",        # iota_conv(t), EJ/CSU
             FILE = "energy/A281.globaltech_cost",       # general-purpose server + facility non-energy cost
             FILE = "water/A281.globaltech_water_coef",  # omega_W / omega_C
             FILE = "energy/pue_R",
             "L1280.out_R_convcompute_Yh"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c("L2285.Supplysector_convcompute",
             "L2285.SubsectorLogit_convcompute",
             "L2285.SubsectorShrwtFllt_convcompute",
             "L2285.SubsectorInterp_convcompute",
             "L2285.StubTech_convcompute",
             "L2285.GlobalTechShrwt_convcompute",
             "L2285.GlobalTechCoef_convcompute",
             "L2285.GlobalTechCost_convcompute",
             "L2285.GlobalTechTrackCapital_convcompute",
             "L2285.StubTechCoef_convcompute",
             "L2285.StubTechProd_convcompute"))
  } else if(command == driver.MAKE) {

    # Silence package checks
    year <- value <- GCAM_region_ID <- region <- supplysector <- subsector <- technology <-
      minicam.energy.input <- minicam.non.energy.input <- minicam.water.input <- coefficient <-
      input.cost <- share.weight <- calOutputValue <- subs.share.weight <- tech.share.weight <-
      share.weight.year <- stub.technology <- market.name <- sector.name <- subsector.name <-
      gamma <- omega <- year.fillout <- M <- iota <- NULL

    all_data <- list(...)[[1]]

    GCAM_region_names <- get_data(all_data, "common/GCAM_region_names", strip_attributes = TRUE)
    A281.sector <- get_data(all_data, "energy/A281.sector", strip_attributes = TRUE)
    A281.subsector_logit <- get_data(all_data, "energy/A281.subsector_logit", strip_attributes = TRUE)
    A281.subsector_interp <- get_data(all_data, "energy/A281.subsector_interp", strip_attributes = TRUE)
    A281.globaltech_shrwt <- get_data(all_data, "energy/A281.globaltech_shrwt", strip_attributes = TRUE)
    A281.globaltech_eff <- get_data(all_data, "energy/A281.globaltech_eff", strip_attributes = TRUE)
    A281.globaltech_cost <- get_data(all_data, "energy/A281.globaltech_cost", strip_attributes = TRUE)
    A281.globaltech_water_coef <- get_data(all_data, "water/A281.globaltech_water_coef", strip_attributes = TRUE)
    pue_R <- get_data(all_data, "energy/pue_R", strip_attributes = TRUE)
    L1280.out_R_convcompute_Yh <- get_data(all_data, "L1280.out_R_convcompute_Yh", strip_attributes = TRUE)

    # Expand the selectively authored regional M path to every GCAM model
    # year before joining. An exact-year join leaves 2055, 2065, ... unmatched
    # and creates an invalid synthetic region="NA" in the generated XML.
    pue_R %>%
      complete(nesting(region), year = c(year, MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      arrange(region, year) %>%
      group_by(region) %>%
      mutate(M = approx_fun(year, M, rule = 2)) %>%
      ungroup() %>%
      filter(year %in% c(MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      select(region, year, M) ->
      pue_R_interp

    # ===================================================
    # 1. Supplysector / subsector (mirror L2280 exactly)
    # ===================================================
    A281.sector %>%
      write_to_all_regions(c(LEVEL2_DATA_NAMES[["Supplysector"]], LOGIT_TYPE_COLNAME), GCAM_region_names) ->
      L2285.Supplysector_convcompute

    A281.subsector_logit %>%
      write_to_all_regions(c(LEVEL2_DATA_NAMES[["SubsectorLogit"]], LOGIT_TYPE_COLNAME), GCAM_region_names) ->
      L2285.SubsectorLogit_convcompute

    A281.subsector_logit %>%
      select(supplysector, subsector) %>%
      mutate(year.fillout = min(MODEL_BASE_YEARS), share.weight = 1) %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["SubsectorShrwtFllt"]], GCAM_region_names) ->
      L2285.SubsectorShrwtFllt_convcompute

    A281.subsector_interp %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["SubsectorInterp"]], GCAM_region_names) ->
      L2285.SubsectorInterp_convcompute

    # ===================================================
    # 2. Technology (single technology; no chip input, no trade)
    # ===================================================
    A281.globaltech_shrwt %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["Tech"]], GCAM_region_names) %>%
      rename(stub.technology = technology) ->
      L2285.StubTech_convcompute

    A281.globaltech_shrwt %>%
      gather_years() %>%
      complete(nesting(supplysector, subsector, technology), year = c(year, MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      arrange(supplysector, subsector, technology, year) %>%
      group_by(supplysector, subsector, technology) %>%
      mutate(share.weight = approx_fun(year, value, rule = 1)) %>%
      ungroup() %>%
      filter(year %in% c(MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      rename(sector.name = supplysector, subsector.name = subsector) %>%
      select(LEVEL2_DATA_NAMES[["GlobalTechYr"]], "share.weight") ->
      L2285.GlobalTechShrwt_convcompute

    # gamma_conv(t) on elect_td_ind (rule=2 holds the 2021 value for earlier base years; inert, zero share-weight)
    A281.globaltech_eff %>%
      gather_years() %>%
      complete(nesting(supplysector, subsector, technology, minicam.energy.input),
               year = c(year, MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      arrange(supplysector, subsector, technology, minicam.energy.input, year) %>%
      group_by(supplysector, subsector, technology, minicam.energy.input) %>%
      mutate(coefficient = approx_fun(year, value, rule = 2),
             coefficient = round(coefficient, energy.DIGITS_COEFFICIENT)) %>%
      ungroup() %>%
      filter(year %in% c(MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      rename(sector.name = supplysector, subsector.name = subsector) %>%
      select(LEVEL2_DATA_NAMES[["GlobalTechCoef"]]) ->
      L2285.GlobalTechCoef_convcompute

    # v3.2 (2026-08-27, V32_SPEC.md): A281.globaltech_cost carries THREE rows
    # (hw-capital / facility-capital / opex) replacing the composite
    # "non-energy" row; linear interpolation preserves the sum identity with
    # the former composite at every model year. Rounded to 7 decimals, not
    # energy.DIGITS_COST (4), so component rounding cannot breach the 5e-4
    # sum-identity gate (V32_SPEC step 5; see L2280 for the arithmetic).
    A281.globaltech_cost %>%
      gather_years() %>%
      complete(nesting(supplysector, subsector, technology, minicam.non.energy.input),
               year = c(year, MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      arrange(supplysector, subsector, technology, minicam.non.energy.input, year) %>%
      group_by(supplysector, subsector, technology, minicam.non.energy.input) %>%
      mutate(input.cost = approx_fun(year, value, rule = 2),
             input.cost = round(input.cost, 7)) %>%
      ungroup() %>%
      filter(year %in% c(MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      rename(sector.name = supplysector, subsector.name = subsector) %>%
      select(LEVEL2_DATA_NAMES[["GlobalTechCost"]]) ->
      L2285.GlobalTechCost_convcompute

    # v3.2 facility-only capital tracking (2026-08-27, V32_SPEC.md; see L2280
    # for the full derivation). v3.3 2026-08-29: hw-capital is now ALSO tracked (payback 5, ratio 1.0508688874, dep 1/5.32); prior facility-only text: Only facility-capital (share 0.2008 of nu at
    # the 13.75-yr life) is tracked; hw-capital (0.7662, annualized global
    # procurement) and opex (0.0330) are plain inputs. S2 block: interest
    # 0.0872 (TCO WACC), integer payback 14, capital-ratio
    # CRF(.0872,14)/CRF(.0872,13.75) = 0.9905009939 (exact overnight
    # identity, cost x 7.835197), depreciation-rate 1/13.75 = 0.0727272727.
    bind_rows(
      L2285.GlobalTechCost_convcompute %>%
        filter(minicam.non.energy.input == "facility-capital") %>%
        mutate(capital.ratio = 0.9905009939,
               payback.years = 14,
               depreciation.rate = 0.0727272727),
      L2285.GlobalTechCost_convcompute %>%
        filter(minicam.non.energy.input == "hw-capital") %>%
        mutate(capital.ratio = 1.0508688874,
               payback.years = 5,
               depreciation.rate = 0.1879699248)) %>%
      mutate(interest.rate = 0.0872,
             invest.unit.conversion = 1,
             tracking.market = socioeconomics.EN_CAPITAL_MARKET_NAME) %>%
      select(LEVEL2_DATA_NAMES[["GlobalTechTrackCapital"]]) ->
      L2285.GlobalTechTrackCapital_convcompute

    # ===================================================
    # 3. Calibration (by OUTPUT) and regional coefficients
    # ===================================================
    L1280.out_R_convcompute_Yh %>%
      filter(year %in% MODEL_BASE_YEARS) %>%
      left_join_error_no_match(GCAM_region_names, by = c("GCAM_region_ID", "region")) %>%
      mutate(supplysector = A281.sector[["supplysector"]][1],
             subsector = supplysector,
             stub.technology = supplysector,
             calOutputValue = round(value, energy.DIGITS_CALOUTPUT),
             share.weight.year = year,
             subs.share.weight = if_else(calOutputValue > 0, 1, 0),
             tech.share.weight = subs.share.weight) %>%
      select(LEVEL2_DATA_NAMES[["StubTechProd"]]) ->
      L2285.StubTechProd_convcompute

    convcomp_names <- A281.globaltech_eff %>%
      select(supplysector, subsector, technology) %>%
      distinct()

    # Regional facility coefficient gamma_conv,r,t = iota_conv,t * M_r,t.
    L2285.GlobalTechCoef_convcompute %>%
      filter(year >= max(MODEL_BASE_YEARS)) %>%
      rename(iota = coefficient) %>%
      left_join(
        pue_R_interp,
        by = "year") %>%
      mutate(supplysector = sector.name,
             subsector = subsector.name,
             stub.technology = technology,
             coefficient = round(iota * M, energy.DIGITS_COEFFICIENT),
             market.name = region) %>%
      select(LEVEL2_DATA_NAMES[["StubTechCoef"]]) ->
      L2285.StubTechCoef_elec

    # Scope-1 water equals WUE times the facility-electricity coefficient.
    omega_tbl <- A281.globaltech_water_coef %>%
      select(minicam.water.input, omega = coefficient) %>%
      distinct()
    L2285.StubTechCoef_elec %>%
      rename(gamma = coefficient) %>%
      select(region, supplysector, subsector, stub.technology, year, gamma) %>%
      repeat_add_columns(omega_tbl) %>%
      mutate(
             minicam.energy.input = minicam.water.input,
             coefficient = round(omega * gamma, energy.DIGITS_COEFFICIENT),
             market.name = region) %>%
      select(LEVEL2_DATA_NAMES[["StubTechCoef"]]) ->
      L2285.StubTechCoef_water

    bind_rows(L2285.StubTechCoef_elec, L2285.StubTechCoef_water) ->
      L2285.StubTechCoef_convcompute

    # ===================================================
    # Produce outputs
    # ===================================================
    L2285.Supplysector_convcompute %>%
      add_title("Conventional-compute supplysector") %>% add_units("NA") %>%
      add_comments("Non-traded twin of AI compute; A281.sector to all regions") %>%
      add_precursors("energy/A281.sector", "common/GCAM_region_names") -> L2285.Supplysector_convcompute
    L2285.SubsectorLogit_convcompute %>%
      add_title("Conventional-compute subsector logit") %>% add_units("Unitless") %>%
      add_comments("Single subsector") %>%
      add_precursors("energy/A281.subsector_logit", "common/GCAM_region_names") -> L2285.SubsectorLogit_convcompute
    L2285.SubsectorShrwtFllt_convcompute %>%
      add_title("Conventional-compute subsector share-weights") %>% add_units("Unitless") %>%
      add_comments("Share-weight 1 from first base year") %>%
      add_precursors("energy/A281.subsector_logit", "common/GCAM_region_names") -> L2285.SubsectorShrwtFllt_convcompute
    L2285.SubsectorInterp_convcompute %>%
      add_title("Conventional-compute subsector interpolation") %>% add_units("NA") %>%
      add_comments("Linear share-weight interpolation") %>%
      add_precursors("energy/A281.subsector_interp", "common/GCAM_region_names") -> L2285.SubsectorInterp_convcompute
    L2285.StubTech_convcompute %>%
      add_title("Conventional-compute stub technologies") %>% add_units("NA") %>%
      add_comments("Single technology") %>%
      add_precursors("energy/A281.globaltech_shrwt", "common/GCAM_region_names") -> L2285.StubTech_convcompute
    L2285.GlobalTechShrwt_convcompute %>%
      add_title("Conventional-compute global tech share-weights") %>% add_units("Unitless") %>%
      add_comments("Interpolated over model years") %>%
      add_precursors("energy/A281.globaltech_shrwt") -> L2285.GlobalTechShrwt_convcompute
    L2285.GlobalTechCoef_convcompute %>%
      add_title("Conventional-compute IT-electricity intensity iota_conv(t)") %>%
      add_units("EJ IT electricity per CSU") %>%
      add_comments("Audited SPECpower benchmark path; regional M is applied in StubTechCoef") %>%
      add_precursors("energy/A281.globaltech_eff") -> L2285.GlobalTechCoef_convcompute
    L2285.GlobalTechCost_convcompute %>%
      add_title("Conventional-compute non-energy costs (v3.2 three-input split)") %>%
      add_units("1975 billion$/CSU") %>%
      add_comments("v3.2: three inputs (hw-capital nu0*0.7662/H, facility-capital nu0*0.2008/B, opex nu0*0.0330 flat); sum equals the former composite nu by construction") %>%
      add_precursors("energy/A281.globaltech_cost") -> L2285.GlobalTechCost_convcompute
    L2285.GlobalTechTrackCapital_convcompute %>%
      add_title("Conventional-compute facility-capital tracking (v3.2 S2 facility-only)") %>% add_units("mixed") %>%
      add_comments("v3.3 (2026-08-29), same convention as AI compute: hw AND facility tracked (hw payback 5, ratio 1.0508688874, dep 1/5.32); v3.2 text: interest 0.0872, payback 14, ratio 0.9905009939, depreciation 1/13.75, capital-energy market; hardware untracked (annualized global procurement); 2026-08-27") %>%
      add_precursors("energy/A281.globaltech_cost") -> L2285.GlobalTechTrackCapital_convcompute
    L2285.StubTechCoef_convcompute %>%
      add_title("Conventional-compute regional electricity and water coefficients") %>%
      add_units("EJ/CSU; km3/CSU water") %>%
      add_comments("gamma_conv,r,t=iota_conv,t*M_r,t; water equals WUE times gamma") %>%
      add_precursors("common/GCAM_region_names", "energy/A281.globaltech_eff",
                     "energy/pue_R", "water/A281.globaltech_water_coef") ->
      L2285.StubTechCoef_convcompute
    L2285.StubTechProd_convcompute %>%
      add_title("Conventional-compute base-year calibrated output") %>% add_units("CSU") %>%
      add_comments("Recovered from conventional IT electricity and the matching benchmark") %>%
      add_precursors("L1280.out_R_convcompute_Yh", "energy/A281.sector", "common/GCAM_region_names") ->
      L2285.StubTechProd_convcompute

    return_data(L2285.Supplysector_convcompute, L2285.SubsectorLogit_convcompute,
                L2285.SubsectorShrwtFllt_convcompute, L2285.SubsectorInterp_convcompute,
                L2285.StubTech_convcompute, L2285.GlobalTechShrwt_convcompute,
                L2285.GlobalTechCoef_convcompute, L2285.GlobalTechCost_convcompute,
                L2285.GlobalTechTrackCapital_convcompute, L2285.StubTechCoef_convcompute,
                L2285.StubTechProd_convcompute)
  } else {
    stop("Unknown command")
  }
}
