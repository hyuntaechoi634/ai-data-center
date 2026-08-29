# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_L2281.ai_compute_trade
#'
#' Separate traded pools and regional Armington goods for training and
#' inference compute. All calibration flows retain their service key.
#' @importFrom dplyr bind_rows distinct filter if_else left_join mutate rename
#'   select
#' @importFrom tidyr replace_na
#' @author gcamdata-ai 2026
module_energy_L2281.ai_compute_trade <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(FILE = "common/GCAM_region_names",
             FILE = "energy/A_aicomp_TradedSector",
             FILE = "energy/A_aicomp_TradedSubsector",
             FILE = "energy/A_aicomp_TradedTechnology",
             FILE = "energy/A_aicomp_RegionalSector",
             FILE = "energy/A_aicomp_RegionalSubsector",
             FILE = "energy/A_aicomp_RegionalTechnology",
             FILE = "energy/A_aicomp_services",
             "LB1281.Tradebalance_aicompute_R_Y"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c("L2281.Supplysector_tra",
             "L2281.SectorUseTrialMarket_tra",
             "L2281.SubsectorAll_tra",
             "L2281.TechShrwt_tra",
             "L2281.TechCost_tra",
             "L2281.TechCoef_tra",
             "L2281.Production_tra",
             "L2281.Supplysector_reg",
             "L2281.SubsectorAll_reg",
             "L2281.TechShrwt_reg",
             "L2281.TechCoef_reg",
             "L2281.Production_reg_imp",
             "L2281.Production_reg_dom",
             "L2281.RelLogitBaseValue_aitrade"))
  } else if(command == driver.MAKE) {

    year <- region <- supplysector <- subsector <- technology <- value <-
      metric <- GCAM_region <- minicam.energy.input <- market.name <-
      calOutputValue <- subs.share.weight <- tech.share.weight <-
      share.weight.year <- service <- traded.good <- regional.good <-
      GrossExp <- GrossImp <- DomSup <- NULL

    all_data <- list(...)[[1]]
    GCAM_region_names <- get_data(
      all_data, "common/GCAM_region_names", strip_attributes = TRUE)
    A_aicomp_TradedSector <- get_data(
      all_data, "energy/A_aicomp_TradedSector", strip_attributes = TRUE)
    A_aicomp_TradedSubsector <- get_data(
      all_data, "energy/A_aicomp_TradedSubsector",
      strip_attributes = TRUE)
    A_aicomp_TradedTechnology <- get_data(
      all_data, "energy/A_aicomp_TradedTechnology",
      strip_attributes = TRUE)
    A_aicomp_RegionalSector <- get_data(
      all_data, "energy/A_aicomp_RegionalSector",
      strip_attributes = TRUE)
    A_aicomp_RegionalSubsector <- get_data(
      all_data, "energy/A_aicomp_RegionalSubsector",
      strip_attributes = TRUE)
    A_aicomp_RegionalTechnology <- get_data(
      all_data, "energy/A_aicomp_RegionalTechnology",
      strip_attributes = TRUE)
    A_aicomp_services <- get_data(
      all_data, "energy/A_aicomp_services", strip_attributes = TRUE)
    LB1281.Tradebalance_aicompute_R_Y <- get_data(
      all_data, "LB1281.Tradebalance_aicompute_R_Y",
      strip_attributes = TRUE)

    A_aicomp_TradedSector %>%
      mutate(region = gcam.USA_REGION,
             logit.year.fillout = min(MODEL_BASE_YEARS)) %>%
      select(c(LEVEL2_DATA_NAMES[["Supplysector"]], "logit.type")) ->
      L2281.Supplysector_tra

    A_aicomp_TradedSector %>%
      mutate(region = gcam.USA_REGION) %>%
      select(region, supplysector) %>%
      mutate(use.trial.market = 1) ->
      L2281.SectorUseTrialMarket_tra

    A_aicomp_TradedSubsector %>%
      write_to_all_regions(
        c(LEVEL2_DATA_NAMES[["SubsectorAllTo"]], "logit.type"),
        GCAM_region_names, has_traded = TRUE) ->
      L2281.SubsectorAll_tra

    A_aicomp_TradedTechnology %>%
      left_join_error_no_match(
        A_aicomp_services %>% select(service, traded.good),
        by = c("supplysector" = "traded.good")) %>%
      repeat_add_columns(tibble::tibble(year = MODEL_YEARS)) %>%
      repeat_add_columns(GCAM_region_names) %>%
      mutate(subsector = paste(region, subsector, sep = " "),
             technology = subsector,
             market.name = region,
             region = gcam.USA_REGION) ->
      L2281.TradedTechnology_R_Y

    L2281.TradedTechnology_R_Y %>%
      select(LEVEL2_DATA_NAMES[["TechShrwt"]]) ->
      L2281.TechShrwt_tra
    L2281.TradedTechnology_R_Y %>%
      mutate(minicam.non.energy.input = "trade costs") %>%
      select(LEVEL2_DATA_NAMES[["TechCost"]]) ->
      L2281.TechCost_tra
    L2281.TradedTechnology_R_Y %>%
      select(LEVEL2_DATA_NAMES[["TechCoef"]]) ->
      L2281.TechCoef_tra

    LB1281.Tradebalance_aicompute_R_Y %>%
      filter(metric == "exports_reval") %>%
      rename(GrossExp = value, market.region = GCAM_region) %>%
      select(service, market.region, year, GrossExp) ->
      L2281.GrossExports
    L2281.TradedTechnology_R_Y %>%
      filter(year %in% MODEL_BASE_YEARS) %>%
      left_join(
        L2281.GrossExports,
        by = c("service", "market.name" = "market.region", "year")) %>%
      mutate(
        GrossExp = replace_na(GrossExp, 0),
        calOutputValue = round(GrossExp, energy.DIGITS_CALOUTPUT),
        share.weight.year = year,
        subs.share.weight = if_else(calOutputValue > 0, 1, 0),
        tech.share.weight = subs.share.weight) %>%
      select(LEVEL2_DATA_NAMES[["Production"]]) ->
      L2281.Production_tra

    A_aicomp_RegionalSector %>%
      mutate(logit.year.fillout = min(MODEL_BASE_YEARS)) %>%
      write_to_all_regions(
        c(LEVEL2_DATA_NAMES[["Supplysector"]], "logit.type"),
        GCAM_region_names) ->
      L2281.Supplysector_reg
    A_aicomp_RegionalSubsector %>%
      write_to_all_regions(
        c(LEVEL2_DATA_NAMES[["SubsectorAllTo"]], "logit.type"),
        GCAM_region_names) ->
      L2281.SubsectorAll_reg

    A_aicomp_RegionalTechnology %>%
      left_join_error_no_match(
        A_aicomp_services %>% select(service, regional.good),
        by = c("supplysector" = "regional.good")) %>%
      repeat_add_columns(tibble::tibble(year = MODEL_YEARS)) %>%
      repeat_add_columns(GCAM_region_names["region"]) %>%
      mutate(market.name = if_else(
        market.name == "regional", region, market.name)) ->
      L2281.RegionalTechnology_R_Y
    L2281.RegionalTechnology_R_Y %>%
      select(LEVEL2_DATA_NAMES[["TechShrwt"]]) ->
      L2281.TechShrwt_reg
    L2281.RegionalTechnology_R_Y %>%
      select(LEVEL2_DATA_NAMES[["TechCoef"]]) ->
      L2281.TechCoef_reg

    LB1281.Tradebalance_aicompute_R_Y %>%
      filter(metric == "imports_reval") %>%
      rename(region = GCAM_region, GrossImp = value) %>%
      select(service, region, year, GrossImp) ->
      L2281.GrossImports
    L2281.RegionalTechnology_R_Y %>%
      filter(year %in% MODEL_BASE_YEARS, grepl("import", subsector)) %>%
      left_join(
        L2281.GrossImports, by = c("service", "region", "year")) %>%
      mutate(
        GrossImp = replace_na(GrossImp, 0),
        calOutputValue = round(GrossImp, energy.DIGITS_CALOUTPUT),
        share.weight.year = year,
        subs.share.weight = if_else(calOutputValue > 0, 1, 0),
        tech.share.weight = subs.share.weight) %>%
      select(LEVEL2_DATA_NAMES[["Production"]]) ->
      L2281.Production_reg_imp

    LB1281.Tradebalance_aicompute_R_Y %>%
      filter(metric == "domestic_supply") %>%
      rename(region = GCAM_region, DomSup = value) %>%
      select(service, region, year, DomSup) ->
      L2281.DomesticSupply
    L2281.RegionalTechnology_R_Y %>%
      filter(year %in% MODEL_BASE_YEARS, grepl("domestic", subsector)) %>%
      left_join(
        L2281.DomesticSupply, by = c("service", "region", "year")) %>%
      mutate(
        DomSup = replace_na(DomSup, 0),
        calOutputValue = round(DomSup, energy.DIGITS_CALOUTPUT),
        share.weight.year = year,
        subs.share.weight = if_else(calOutputValue > 0, 1, 0),
        tech.share.weight = subs.share.weight) %>%
      select(LEVEL2_DATA_NAMES[["Production"]]) ->
      L2281.Production_reg_dom

    bind_rows(
      select(L2281.Supplysector_tra, region, supplysector),
      select(L2281.Supplysector_reg, region, supplysector)) %>%
      distinct() %>%
      mutate(is.base.value.parsed = 1L, base.value = 1) ->
      L2281.RelLogitBaseValue_aitrade

    L2281.Supplysector_tra %>%
      add_title("Service-specific traded AI-compute sectors") %>%
      add_units("TSU or ISU") %>%
      add_precursors(
        "common/GCAM_region_names", "energy/A_aicomp_TradedSector") ->
      L2281.Supplysector_tra
    L2281.SectorUseTrialMarket_tra %>%
      add_title("Trial-market flags for traded AI compute") %>%
      add_units("None") %>%
      same_precursors_as(L2281.Supplysector_tra) ->
      L2281.SectorUseTrialMarket_tra
    L2281.SubsectorAll_tra %>%
      add_title("Subsectors for service-specific traded AI compute") %>%
      add_units("None") %>%
      add_precursors(
        "common/GCAM_region_names",
        "energy/A_aicomp_TradedSubsector") ->
      L2281.SubsectorAll_tra
    L2281.TechShrwt_tra %>%
      add_title("Technology share weights for traded AI compute") %>%
      add_units("None") %>%
      add_precursors("energy/A_aicomp_TradedTechnology") ->
      L2281.TechShrwt_tra
    L2281.TechCost_tra %>%
      add_title("Technology costs for traded AI compute") %>%
      add_units("service-specific price unit") %>%
      same_precursors_as(L2281.TechShrwt_tra) ->
      L2281.TechCost_tra
    L2281.TechCoef_tra %>%
      add_title("Technology coefficients for traded AI compute") %>%
      add_units("unitless") %>%
      same_precursors_as(L2281.TechShrwt_tra) ->
      L2281.TechCoef_tra
    L2281.Production_tra %>%
      add_title("Calibrated service-specific AI-compute exports") %>%
      add_units("TSU or ISU") %>%
      add_precursors(
        "LB1281.Tradebalance_aicompute_R_Y",
        "energy/A_aicomp_TradedTechnology") ->
      L2281.Production_tra

    L2281.Supplysector_reg %>%
      add_title("Regional training and inference compute sectors") %>%
      add_units("TSU or ISU") %>%
      add_precursors(
        "common/GCAM_region_names",
        "energy/A_aicomp_RegionalSector") ->
      L2281.Supplysector_reg
    L2281.SubsectorAll_reg %>%
      add_title("Domestic and imported AI-compute subsectors") %>%
      add_units("None") %>%
      add_precursors(
        "common/GCAM_region_names",
        "energy/A_aicomp_RegionalSubsector") ->
      L2281.SubsectorAll_reg
    L2281.TechShrwt_reg %>%
      add_title("Regional AI-compute technology share weights") %>%
      add_units("None") %>%
      add_precursors("energy/A_aicomp_RegionalTechnology") ->
      L2281.TechShrwt_reg
    L2281.TechCoef_reg %>%
      add_title("Regional AI-compute technology coefficients") %>%
      add_units("unitless") %>%
      same_precursors_as(L2281.TechShrwt_reg) ->
      L2281.TechCoef_reg
    L2281.Production_reg_imp %>%
      add_title("Calibrated service-specific AI-compute imports") %>%
      add_units("TSU or ISU") %>%
      add_precursors(
        "LB1281.Tradebalance_aicompute_R_Y",
        "energy/A_aicomp_RegionalTechnology") ->
      L2281.Production_reg_imp
    L2281.Production_reg_dom %>%
      add_title("Calibrated service-specific domestic AI compute") %>%
      add_units("TSU or ISU") %>%
      same_precursors_as(L2281.Production_reg_imp) ->
      L2281.Production_reg_dom
    L2281.RelLogitBaseValue_aitrade %>%
      add_title("Relative-logit base values for AI-compute trade") %>%
      add_units("None") %>%
      add_precursors(
        "energy/A_aicomp_TradedSector",
        "energy/A_aicomp_RegionalSector") ->
      L2281.RelLogitBaseValue_aitrade

    return_data(
      L2281.Supplysector_tra,
      L2281.SectorUseTrialMarket_tra,
      L2281.SubsectorAll_tra,
      L2281.TechShrwt_tra,
      L2281.TechCost_tra,
      L2281.TechCoef_tra,
      L2281.Production_tra,
      L2281.Supplysector_reg,
      L2281.SubsectorAll_reg,
      L2281.TechShrwt_reg,
      L2281.TechCoef_reg,
      L2281.Production_reg_imp,
      L2281.Production_reg_dom,
      L2281.RelLogitBaseValue_aitrade)
  } else {
    stop("Unknown command")
  }
}
