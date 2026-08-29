# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_L2280.ai_compute_prod
#'
#' PRODUCTION layer for separate training and inference sectors. Electricity
#' coefficients combine the service-specific IT coefficient with the regional
#' facility multiplier: gamma_s,r,t = iota_s,t * M_r,t.
#' Mirrors zenergy_L2323.iron_steel.R (+ aluminum L2326 for the capital-tracking record). See spec §13.
#' @return L2280.* tibbles.
#' @importFrom assertthat assert_that
#' @importFrom dplyr arrange bind_rows distinct filter if_else group_by left_join mutate rename select
#' @importFrom tidyr complete gather nesting
#' @author gcamdata-ai 2026
module_energy_L2280.ai_compute_prod <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(FILE = "common/GCAM_region_names",
             FILE = "energy/A280.sector",
             FILE = "energy/A280.subsector_logit",
             FILE = "energy/A280.subsector_interp",
             FILE = "energy/A280.globaltech_shrwt",
             FILE = "energy/A280.globaltech_eff",        # gamma_r(t) electricity intensity (PUE_r * iota)
             FILE = "energy/A280.globaltech_cost",
             FILE = "water/A280.globaltech_water_coef",  # omega_r scope-1
             FILE = "energy/A_aicomp_services",
             FILE = "energy/pue_R",
             "L1280.out_R_aicompute_Yh"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c("L2280.Supplysector_aicompute",
             "L2280.SubsectorLogit_aicompute",
             "L2280.SubsectorShrwtFllt_aicompute",
             "L2280.SubsectorInterp_aicompute",
             "L2280.StubTech_aicompute",
             "L2280.GlobalTechShrwt_aicompute",
             "L2280.GlobalTechCoef_aicompute",        # electricity intensity gamma_r(t)
             "L2280.GlobalTechCost_aicompute",        # v3.2 three non-energy inputs (hw-capital/facility-capital/opex)
             "L2280.GlobalTechTrackCapital_aicompute",# v3.2 facility-only tracking (S2 interest .0872, payback 14, ratio .9905009939, dep 1/13.75)
             "L2280.StubTechCoef_aicompute",          # scope-1 water + base-year electricity coef
             "L2280.StubTechProd_aicompute"))         # 2021 TSU/ISU output calibration
  } else if(command == driver.MAKE) {

    # Silence package checks
    year <- value <- GCAM_region_ID <- region <- sector <- fuel <- supplysector <- subsector <-
      technology <- minicam.energy.input <- minicam.non.energy.input <- minicam.water.input <-
      coefficient <- input.cost <- share.weight <- calOutputValue <- subs.share.weight <-
      tech.share.weight <- share.weight.year <- stub.technology <- market.name <- sector.name <-
      subsector.name <- gamma <- omega <- service <- year.fillout <-
      production.good <- M <- iota <- NULL

    all_data <- list(...)[[1]]

    # Load required inputs
    GCAM_region_names <- get_data(all_data, "common/GCAM_region_names", strip_attributes = TRUE)
    A280.sector <- get_data(all_data, "energy/A280.sector", strip_attributes = TRUE)
    A280.subsector_logit <- get_data(all_data, "energy/A280.subsector_logit", strip_attributes = TRUE)
    A280.subsector_interp <- get_data(all_data, "energy/A280.subsector_interp", strip_attributes = TRUE)
    A280.globaltech_shrwt <- get_data(all_data, "energy/A280.globaltech_shrwt", strip_attributes = TRUE)
    A280.globaltech_eff <- get_data(all_data, "energy/A280.globaltech_eff", strip_attributes = TRUE)
    A280.globaltech_cost <- get_data(all_data, "energy/A280.globaltech_cost", strip_attributes = TRUE)
    A280.globaltech_water_coef <- get_data(all_data, "water/A280.globaltech_water_coef", strip_attributes = TRUE)
    A_aicomp_services <- get_data(all_data, "energy/A_aicomp_services", strip_attributes = TRUE)
    pue_R <- get_data(all_data, "energy/pue_R", strip_attributes = TRUE)
    L1280.out_R_aicompute_Yh <- get_data(all_data, "L1280.out_R_aicompute_Yh", strip_attributes = TRUE)

    # pue_R is authored at selected reporting years, while GCAM includes
    # five-year periods after 2050. Interpolate by region before joining;
    # otherwise unmatched years create a synthetic region="NA" with NA
    # coefficients, which aborts GCAM during completeInit.
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
    # 1. Supplysector / subsector
    # ===================================================
    # L2280.Supplysector_aicompute: supply-sector info expanded to all regions
    A280.sector %>%
      write_to_all_regions(c(LEVEL2_DATA_NAMES[["Supplysector"]], LOGIT_TYPE_COLNAME), GCAM_region_names) ->
      L2280.Supplysector_aicompute

    # L2280.SubsectorLogit_aicompute: subsector logit exponents
    A280.subsector_logit %>%
      write_to_all_regions(c(LEVEL2_DATA_NAMES[["SubsectorLogit"]], LOGIT_TYPE_COLNAME), GCAM_region_names) ->
      L2280.SubsectorLogit_aicompute

    # L2280.SubsectorShrwtFllt_aicompute: single subsector, base-year share-weight 1 filled out.
    # A280.subsector_logit has no year.fillout/share.weight columns, so we synthesise the
    #   SubsectorShrwtFllt table directly (one subsector, share.weight = 1 from the first base year).
    A280.subsector_logit %>%
      select(supplysector, subsector) %>%
      mutate(year.fillout = min(MODEL_BASE_YEARS), share.weight = 1) %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["SubsectorShrwtFllt"]], GCAM_region_names) ->
      L2280.SubsectorShrwtFllt_aicompute

    # L2280.SubsectorInterp_aicompute: subsector share-weight interpolation rule
    A280.subsector_interp %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["SubsectorInterp"]], GCAM_region_names) ->
      L2280.SubsectorInterp_aicompute

    # ===================================================
    # 2. Technology (single technology)
    # ===================================================
    # L2280.StubTech_aicompute: identification of stub technologies
    A280.globaltech_shrwt %>%
      write_to_all_regions(LEVEL2_DATA_NAMES[["Tech"]], GCAM_region_names) %>%
      rename(stub.technology = technology) ->
      L2280.StubTech_aicompute

    # L2280.GlobalTechShrwt_aicompute: global tech share-weights interpolated over model years
    A280.globaltech_shrwt %>%
      gather_years() %>%
      complete(nesting(supplysector, subsector, technology), year = c(year, MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      arrange(supplysector, subsector, technology, year) %>%
      group_by(supplysector, subsector, technology) %>%
      mutate(share.weight = approx_fun(year, value, rule = 1)) %>%
      ungroup() %>%
      filter(year %in% c(MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      rename(sector.name = supplysector, subsector.name = subsector) %>%
      select(LEVEL2_DATA_NAMES[["GlobalTechYr"]], "share.weight") ->
      L2280.GlobalTechShrwt_aicompute

    # Service-specific IT intensity iota_s(t). Regional M is applied below.
    A280.globaltech_eff %>%
      gather_years() %>%
      complete(nesting(supplysector, subsector, technology, minicam.energy.input),
               year = c(year, MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      arrange(supplysector, subsector, technology, minicam.energy.input, year) %>%
      group_by(supplysector, subsector, technology, minicam.energy.input) %>%
      mutate(coefficient = approx_fun(year, value, rule = 2),  # rule=2: hold 2021 value for pre-2021 (no AI then; finite, inert)
             coefficient = round(coefficient, energy.DIGITS_COEFFICIENT)) %>%
      ungroup() %>%
      filter(year %in% c(MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      rename(sector.name = supplysector, subsector.name = subsector) %>%
      select(LEVEL2_DATA_NAMES[["GlobalTechCoef"]]) ->
      L2280.GlobalTechCoef_aicompute

    # Service-specific non-energy cost. CSV is authored in 1975$.
    # v3.2 (2026-08-27, V32_SPEC.md): A280.globaltech_cost carries THREE rows per
    # service (hw-capital / facility-capital / opex) replacing the composite
    # "non-energy" row; each row flows through the same interpolation, which is
    # linear, so the sum identity with the former composite holds at every model
    # year. Rounded to 7 decimals, not energy.DIGITS_COST (4): rounding the three
    # components at 4 decimals can move the deployed sum by up to 2e-4 absolute
    # (~7e-4 relative at the 2025 AI cost level), breaching the 5e-4
    # sum-identity gate (V32_SPEC step 5).
    A280.globaltech_cost %>%
      gather_years() %>%
      complete(nesting(supplysector, subsector, technology, minicam.non.energy.input),
               year = c(year, MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      arrange(supplysector, subsector, technology, minicam.non.energy.input, year) %>%
      group_by(supplysector, subsector, technology, minicam.non.energy.input) %>%
      mutate(input.cost = approx_fun(year, value, rule = 2),  # rule=2: hold 2021 cost for pre-2021 (finite, inert)
             input.cost = round(input.cost, 7)) %>%
      ungroup() %>%
      filter(year %in% c(MODEL_BASE_YEARS, MODEL_FUTURE_YEARS)) %>%
      rename(sector.name = supplysector, subsector.name = subsector) %>%
      select(LEVEL2_DATA_NAMES[["GlobalTechCost"]]) ->
      L2280.GlobalTechCost_aicompute

    # L2280.GlobalTechTrackCapital_aicompute: v3.2 facility-only capital tracking
    # (2026-08-27, analysis/brp7-capital-audit/V32_SPEC.md; supersedes the v3.1
    # composite full-TCO block after AUDIT_RESULT.md C-2b + C-3a FAIL).
    # v3.3 (author ruling 2026-08-29): BOTH capital inputs are tracked in the
    # deploying region; only opex stays plain. hw-capital tracking:
    #   payback-years 5 (nearest int to the 5.32-yr hardware life), capital-ratio
    #   1.0508688874 = CRF(.0872,5)/CRF(.0872,5.32) (exact overnight identity,
    #   cost x 4.117383; ratio>1 so nonCapCost is -5.1 percent -- mechanically valid,
    #   the sum telescopes), depreciation-rate 0.1879699248 = 1/5.32 books the
    #   hardware refresh stream. Prior v3.2 facility-only stance below is kept
    #   for the record. [superseded text] hw-capital and opex stay plain
    # inputs: hardware is annualized GLOBAL procurement -- its full recurring
    # cost (incl. the implicit ~5.32-yr refresh) remains in the compute service
    # price but books no regional capital-energy demand (standing facility-only
    # ruling, analysis/ukraine-capital-price/DIAGNOSIS.md:37).
    # S2 tracked block:
    #   interest-rate 0.0872 = the TCO's own WACC;
    #   payback-years 14 = nearest INTEGER to the 13.75-yr facility life
    #     (the parser is int, non_energy_input.h:226 -- fractional crashes);
    #   capital-ratio 0.9905009939 = CRF(.0872,14)/CRF(.0872,13.75), which
    #     compensates the int-14 payback exactly: overnight =
    #     cost/CRF(.0872,14) x ratio = cost x 7.835197 = cost/CRF(.0872,13.75)
    #     for EVERY year and scenario (the input is pure facility capital, so
    #     the ratio is time-constant -- C-2b closes by construction);
    #   depreciation-rate 0.0727272727 = 1/13.75 books facility replacement
    #     investment at the true facility life (C-3a closes for the capital
    #     actually attributed regionally).
    # invest.unit.conversion = 1 because the cost already uses the output unit.
    bind_rows(
      L2280.GlobalTechCost_aicompute %>%
        filter(minicam.non.energy.input == "facility-capital") %>%
        mutate(capital.ratio = 0.9905009939,
               payback.years = 14,
               depreciation.rate = 0.0727272727),
      L2280.GlobalTechCost_aicompute %>%
        filter(minicam.non.energy.input == "hw-capital") %>%
        mutate(capital.ratio = 1.0508688874,
               payback.years = 5,
               depreciation.rate = 0.1879699248)) %>%
      mutate(interest.rate = 0.0872,
             invest.unit.conversion = 1,
             tracking.market = socioeconomics.EN_CAPITAL_MARKET_NAME) %>%
      select(LEVEL2_DATA_NAMES[["GlobalTechTrackCapital"]]) ->
      L2280.GlobalTechTrackCapital_aicompute

    # ===================================================
    # 3. Calibration (by OUTPUT) and region-specific coefficients
    # ===================================================
    # Calibrate each service in its own unit. No TSU/ISU sum is constructed.
    L1280.out_R_aicompute_Yh %>%
      filter(year %in% MODEL_BASE_YEARS) %>%
      left_join_error_no_match(GCAM_region_names, by = c("GCAM_region_ID", "region")) %>%
      left_join_error_no_match(
        A_aicomp_services %>% select(service, production.good),
        by = "service") %>%
      mutate(supplysector = production.good,
             subsector = supplysector,
             stub.technology = supplysector,
             calOutputValue = round(value, energy.DIGITS_CALOUTPUT),
             share.weight.year = year,
             subs.share.weight = if_else(calOutputValue > 0, 1, 0),
             tech.share.weight = subs.share.weight) %>%
      select(LEVEL2_DATA_NAMES[["StubTechProd"]]) ->
      L2280.StubTechProd_aicompute

    # Region- and service-specific facility coefficient for all model years.
    # L2280.GlobalTechCoef contains iota_s,t; pue_R contains M_r,t.
    L2280.GlobalTechCoef_aicompute %>%
      filter(year >= max(MODEL_BASE_YEARS)) %>%
      left_join_error_no_match(
        A_aicomp_services %>%
          select(service, production.good),
        by = c("sector.name" = "production.good")) %>%
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
      L2280.StubTechCoef_elec

    # Scope-1 water tracks the same facility electricity coefficient.
    omega_tbl <- A280.globaltech_water_coef %>%
      select(supplysector, minicam.water.input, omega = coefficient)
    L2280.StubTechCoef_elec %>%
      rename(gamma = coefficient) %>%
      select(region, supplysector, subsector, stub.technology, year, gamma) %>%
      left_join(omega_tbl, by = "supplysector") %>%
      mutate(
             minicam.energy.input = minicam.water.input,
             coefficient = round(omega * gamma, energy.DIGITS_COEFFICIENT),
             market.name = region) %>%
      select(LEVEL2_DATA_NAMES[["StubTechCoef"]]) ->
      L2280.StubTechCoef_water

    bind_rows(L2280.StubTechCoef_elec, L2280.StubTechCoef_water) ->
      L2280.StubTechCoef_aicompute

    # ===================================================
    # Produce outputs
    # ===================================================
    L2280.Supplysector_aicompute %>%
      add_title("Supply-sector information for the AI compute production sector") %>%
      add_units("varies") %>%
      add_comments("A280.sector expanded to all GCAM regions") %>%
      add_precursors("energy/A280.sector", "common/GCAM_region_names") ->
      L2280.Supplysector_aicompute

    L2280.SubsectorLogit_aicompute %>%
      add_title("Subsector logit exponents for AI compute") %>%
      add_units("Unitless") %>%
      add_comments("Single subsector; A280.subsector_logit expanded to all GCAM regions") %>%
      add_precursors("energy/A280.subsector_logit", "common/GCAM_region_names") ->
      L2280.SubsectorLogit_aicompute

    L2280.SubsectorShrwtFllt_aicompute %>%
      add_title("Subsector share-weights for AI compute") %>%
      add_units("Unitless") %>%
      add_comments("Single subsector with base-year share-weight 1") %>%
      add_precursors("energy/A280.subsector_logit", "common/GCAM_region_names") ->
      L2280.SubsectorShrwtFllt_aicompute

    L2280.SubsectorInterp_aicompute %>%
      add_title("Subsector share-weight interpolation for AI compute") %>%
      add_units("NA") %>%
      add_comments("A280.subsector_interp expanded to all GCAM regions") %>%
      add_precursors("energy/A280.subsector_interp", "common/GCAM_region_names") ->
      L2280.SubsectorInterp_aicompute

    L2280.StubTech_aicompute %>%
      add_title("Stub-technology identification for AI compute") %>%
      add_units("NA") %>%
      add_comments("A280.globaltech_shrwt expanded to all GCAM regions") %>%
      add_precursors("energy/A280.globaltech_shrwt", "common/GCAM_region_names") ->
      L2280.StubTech_aicompute

    L2280.GlobalTechShrwt_aicompute %>%
      add_title("Global technology share-weights for AI compute") %>%
      add_units("Unitless") %>%
      add_comments("A280.globaltech_shrwt interpolated over model years") %>%
      add_precursors("energy/A280.globaltech_shrwt") ->
      L2280.GlobalTechShrwt_aicompute

    L2280.GlobalTechCoef_aicompute %>%
      add_title("Global technology electricity coefficients for AI compute") %>%
      add_units("EJ IT electricity per TSU or ISU") %>%
      add_comments("Service-specific iota path; regional M is applied in StubTechCoef") %>%
      add_precursors("energy/A280.globaltech_eff") ->
      L2280.GlobalTechCoef_aicompute

    L2280.GlobalTechCost_aicompute %>%
      add_title("Global technology non-energy costs for AI compute (v3.2 three-input split)") %>%
      add_units("1975 billion$/TSU or 1975 billion$/ISU") %>%
      add_comments("v3.2: three inputs per service (hw-capital nu0*w_hw/H, facility-capital nu0*w_fac/B, opex nu0*w_opex); sum equals the former composite nu by construction") %>%
      add_precursors("energy/A280.globaltech_cost") ->
      L2280.GlobalTechCost_aicompute

    L2280.GlobalTechTrackCapital_aicompute %>%
      add_title("AI-compute facility-capital tracking (v3.2 S2 facility-only)") %>%
      add_units("Coefficients") %>%
      add_comments("v3.3 (2026-08-29 author ruling, supersedes V32_SPEC facility-only): hw-capital AND facility-capital tracked in the deploying region (hw payback 5, ratio 1.0508688874, dep 1/5.32); v3.2 text: interest 0.0872 (TCO WACC), integer payback 14 with ratio CRF(.0872,14)/CRF(.0872,13.75)=0.9905009939, depreciation 1/13.75; hardware is annualized global procurement (untracked)") %>%
      same_precursors_as(L2280.GlobalTechCost_aicompute) ->
      L2280.GlobalTechTrackCapital_aicompute

    L2280.StubTechCoef_aicompute %>%
      add_title("Region-specific AI-compute coefficients (electricity gamma_r + scope-1 water omega_r)") %>%
      add_units("EJ/TSU or EJ/ISU electricity; km3/service-unit water") %>%
      add_comments("gamma_s,r,t=iota_s,t*M_r,t; water equals WUE times gamma") %>%
      add_precursors("energy/A280.globaltech_eff", "energy/pue_R",
                     "water/A280.globaltech_water_coef", "common/GCAM_region_names") ->
      L2280.StubTechCoef_aicompute

    L2280.StubTechProd_aicompute %>%
      add_title("Calibrated 2021 AI-compute output by service") %>%
      add_units("TSU or ISU") %>%
      add_comments("Each service is independently normalized to world output one in 2021") %>%
      add_precursors("L1280.out_R_aicompute_Yh", "energy/A280.sector", "common/GCAM_region_names") ->
      L2280.StubTechProd_aicompute

    return_data(L2280.Supplysector_aicompute, L2280.SubsectorLogit_aicompute, L2280.SubsectorShrwtFllt_aicompute,
                L2280.SubsectorInterp_aicompute, L2280.StubTech_aicompute, L2280.GlobalTechShrwt_aicompute,
                L2280.GlobalTechCoef_aicompute, L2280.GlobalTechCost_aicompute, L2280.GlobalTechTrackCapital_aicompute,
                L2280.StubTechCoef_aicompute, L2280.StubTechProd_aicompute)
  } else {
    stop("Unknown command")
  }
}
