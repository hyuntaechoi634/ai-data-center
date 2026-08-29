# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_ai_compute_xml
#'
#' STUB (I/O contract aligned to the 2026-06 design; driver.MAKE = TODO).
#' Assemble the L2280 production + L2282 demand tables into ai_compute.xml, and the L2281 trade tables into
#' ai_compute_trade.xml. Mirror zenergy_xml_iron_steel.R / zenergy_xml_iron_steel_trade.R: create_xml ->
#' add_logit_tables_xml for Supplysector / SubsectorAll(To) -> add_xml_data for Tech*/Coef/Cost/
#' GlobalTechTrackCapital/Production/elasticity tables; include add_node_equiv_xml("input"); add_precursors.
#' @return XML = ai_compute.xml, ai_compute_trade.xml.
module_energy_ai_compute_xml <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(# production (L2280)
             "L2280.Supplysector_aicompute","L2280.SubsectorLogit_aicompute","L2280.SubsectorShrwtFllt_aicompute",
             "L2280.SubsectorInterp_aicompute","L2280.StubTech_aicompute","L2280.GlobalTechShrwt_aicompute",
             "L2280.GlobalTechCoef_aicompute","L2280.GlobalTechCost_aicompute","L2280.GlobalTechTrackCapital_aicompute",
             "L2280.StubTechCoef_aicompute","L2280.StubTechProd_aicompute",
             # demand (L2282)
             "L2282.PerCapitaBased_aicompute","L2282.BaseService_aicompute","L2282.IncomeElasticity_aicompute",
             "L2282.PriceElasticity_aicompute","L2282.aeei_aicompute",
             # trade (L2281)
             "L2281.Supplysector_tra","L2281.SectorUseTrialMarket_tra","L2281.SubsectorAll_tra",
             "L2281.TechShrwt_tra","L2281.TechCost_tra","L2281.TechCoef_tra","L2281.Production_tra",
             "L2281.Supplysector_reg","L2281.SubsectorAll_reg","L2281.TechShrwt_reg","L2281.TechCoef_reg",
             "L2281.Production_reg_imp","L2281.Production_reg_dom","L2281.RelLogitBaseValue_aitrade",
             # chip supply resource (L2283)
             "L2283.RenewRsrc_aichip","L2283.RenewRsrcPrice_aichip","L2283.SmthRenewRsrcCurves_aichip",
             "L2283.SmthRenewRsrcTechChange_aichip","L2283.ResTechShrwt_aichip"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c(XML = "ai_compute.xml",
             XML = "ai_compute_trade.xml",
             XML = "ai_chip_resource.xml"))
  } else if(command == driver.MAKE) {

    all_data <- list(...)[[1]]

    # Load required inputs — production (L2280)
    L2280.Supplysector_aicompute <- get_data(all_data, "L2280.Supplysector_aicompute")
    L2280.SubsectorLogit_aicompute <- get_data(all_data, "L2280.SubsectorLogit_aicompute")
    L2280.SubsectorShrwtFllt_aicompute <- get_data(all_data, "L2280.SubsectorShrwtFllt_aicompute")
    L2280.SubsectorInterp_aicompute <- get_data(all_data, "L2280.SubsectorInterp_aicompute")
    L2280.StubTech_aicompute <- get_data(all_data, "L2280.StubTech_aicompute")
    L2280.GlobalTechShrwt_aicompute <- get_data(all_data, "L2280.GlobalTechShrwt_aicompute")
    L2280.GlobalTechCoef_aicompute <- get_data(all_data, "L2280.GlobalTechCoef_aicompute")
    L2280.GlobalTechCost_aicompute <- get_data(all_data, "L2280.GlobalTechCost_aicompute")
    L2280.GlobalTechTrackCapital_aicompute <- get_data(all_data, "L2280.GlobalTechTrackCapital_aicompute")
    L2280.StubTechCoef_aicompute <- get_data(all_data, "L2280.StubTechCoef_aicompute")
    L2280.StubTechProd_aicompute <- get_data(all_data, "L2280.StubTechProd_aicompute")

    # Load required inputs — demand (L2282)
    L2282.PerCapitaBased_aicompute <- get_data(all_data, "L2282.PerCapitaBased_aicompute")
    L2282.BaseService_aicompute <- get_data(all_data, "L2282.BaseService_aicompute")
    L2282.IncomeElasticity_aicompute <- get_data(all_data, "L2282.IncomeElasticity_aicompute")
    L2282.PriceElasticity_aicompute <- get_data(all_data, "L2282.PriceElasticity_aicompute")
    L2282.aeei_aicompute <- get_data(all_data, "L2282.aeei_aicompute")

    # Load required inputs — trade (L2281)
    L2281.Supplysector_tra <- get_data(all_data, "L2281.Supplysector_tra")
    L2281.RelLogitBaseValue_aitrade <- get_data(all_data, "L2281.RelLogitBaseValue_aitrade")
    L2281.SectorUseTrialMarket_tra <- get_data(all_data, "L2281.SectorUseTrialMarket_tra")
    L2281.SubsectorAll_tra <- get_data(all_data, "L2281.SubsectorAll_tra")
    L2281.TechShrwt_tra <- get_data(all_data, "L2281.TechShrwt_tra")
    L2281.TechCost_tra <- get_data(all_data, "L2281.TechCost_tra")
    L2281.TechCoef_tra <- get_data(all_data, "L2281.TechCoef_tra")
    L2281.Production_tra <- get_data(all_data, "L2281.Production_tra")
    L2281.Supplysector_reg <- get_data(all_data, "L2281.Supplysector_reg")
    L2281.SubsectorAll_reg <- get_data(all_data, "L2281.SubsectorAll_reg")
    L2281.TechShrwt_reg <- get_data(all_data, "L2281.TechShrwt_reg")
    L2281.TechCoef_reg <- get_data(all_data, "L2281.TechCoef_reg")
    L2281.Production_reg_imp <- get_data(all_data, "L2281.Production_reg_imp")
    L2281.Production_reg_dom <- get_data(all_data, "L2281.Production_reg_dom")

    # Load required inputs — chip supply resource (L2283)
    L2283.RenewRsrc_aichip <- get_data(all_data, "L2283.RenewRsrc_aichip")
    L2283.RenewRsrcPrice_aichip <- get_data(all_data, "L2283.RenewRsrcPrice_aichip")
    L2283.SmthRenewRsrcCurves_aichip <- get_data(all_data, "L2283.SmthRenewRsrcCurves_aichip")
    L2283.SmthRenewRsrcTechChange_aichip <- get_data(all_data, "L2283.SmthRenewRsrcTechChange_aichip")
    L2283.ResTechShrwt_aichip <- get_data(all_data, "L2283.ResTechShrwt_aichip")

    # ===================================================
    # Produce outputs

    # ai_compute.xml: production (L2280) + demand (L2282). Mirror zenergy_xml_iron_steel.R.
    create_xml("ai_compute.xml") %>%
      add_logit_tables_xml(L2280.Supplysector_aicompute, "Supplysector") %>%
      add_logit_tables_xml(L2280.SubsectorLogit_aicompute, "SubsectorLogit") %>%
      add_xml_data(L2280.SubsectorShrwtFllt_aicompute, "SubsectorShrwtFllt") %>%
      add_xml_data(L2280.SubsectorInterp_aicompute, "SubsectorInterp") %>%
      add_xml_data(L2280.StubTech_aicompute, "StubTech") %>%
      add_xml_data(L2280.GlobalTechShrwt_aicompute, "GlobalTechShrwt") %>%
      add_node_equiv_xml("input") %>%
      add_xml_data(L2280.GlobalTechCoef_aicompute, "GlobalTechCoef") %>%
      add_xml_data(L2280.GlobalTechTrackCapital_aicompute, "GlobalTechTrackCapital") %>%
      add_xml_data(L2280.GlobalTechCost_aicompute, "GlobalTechCost") %>%
      add_xml_data(L2280.StubTechCoef_aicompute, "StubTechCoef") %>%
      add_xml_data(L2280.StubTechProd_aicompute, "StubTechProd") %>%
      add_xml_data(L2282.PerCapitaBased_aicompute, "PerCapitaBased") %>%
      add_xml_data(L2282.BaseService_aicompute, "BaseService") %>%
      add_xml_data(L2282.IncomeElasticity_aicompute, "IncomeElasticity") %>%
      add_xml_data(L2282.PriceElasticity_aicompute, "PriceElasticity") %>%
      add_xml_data(L2282.aeei_aicompute, "aeei") %>%
      add_precursors("L2280.Supplysector_aicompute", "L2280.SubsectorLogit_aicompute",
                     "L2280.SubsectorShrwtFllt_aicompute", "L2280.SubsectorInterp_aicompute",
                     "L2280.StubTech_aicompute", "L2280.GlobalTechShrwt_aicompute",
                     "L2280.GlobalTechCoef_aicompute", "L2280.GlobalTechCost_aicompute",
                     "L2280.GlobalTechTrackCapital_aicompute", "L2280.StubTechCoef_aicompute",
                     "L2280.StubTechProd_aicompute", "L2282.PerCapitaBased_aicompute",
                     "L2282.BaseService_aicompute", "L2282.IncomeElasticity_aicompute",
                     "L2282.PriceElasticity_aicompute", "L2282.aeei_aicompute") ->
      ai_compute.xml

    # ai_compute_trade.xml: trade (L2281). Mirror zenergy_xml_iron_steel_trade.R.
    create_xml("ai_compute_trade.xml") %>%
      add_logit_tables_xml(L2281.Supplysector_tra, "Supplysector") %>%
      add_xml_data(L2281.SectorUseTrialMarket_tra, "SectorUseTrialMarket") %>%
      add_logit_tables_xml(L2281.SubsectorAll_tra, "SubsectorAllTo", base_logit_header = "SubsectorLogit") %>%
      add_xml_data(L2281.TechShrwt_tra, "TechShrwt") %>%
      add_xml_data(L2281.TechCost_tra, "TechCost") %>%
      add_node_equiv_xml("input") %>%
      add_xml_data(L2281.TechCoef_tra, "TechCoef") %>%
      add_xml_data(L2281.Production_tra, "Production") %>%
      add_logit_tables_xml(L2281.Supplysector_reg, "Supplysector") %>%
      # column_order_lookup=NULL: this custom header has no LEVEL2_DATA_NAMES entry, and the
      # default lookup would silently reduce the table to zero columns (add_xml_data line 82).
      add_xml_data(L2281.RelLogitBaseValue_aitrade, "RelativeLogitBaseValueSector", NULL) %>%
      add_logit_tables_xml(L2281.SubsectorAll_reg, "SubsectorAllTo", base_logit_header = "SubsectorLogit") %>%
      add_xml_data(L2281.TechShrwt_reg, "TechShrwt") %>%
      add_xml_data(L2281.TechCoef_reg, "TechCoef") %>%
      add_xml_data(L2281.Production_reg_imp, "Production") %>%
      add_xml_data(L2281.Production_reg_dom, "Production") %>%
      add_precursors("L2281.Supplysector_tra", "L2281.SectorUseTrialMarket_tra", "L2281.SubsectorAll_tra",
                     "L2281.TechShrwt_tra", "L2281.TechCost_tra", "L2281.TechCoef_tra", "L2281.Production_tra",
                     "L2281.Supplysector_reg", "L2281.SubsectorAll_reg", "L2281.TechShrwt_reg",
                     "L2281.TechCoef_reg", "L2281.Production_reg_imp", "L2281.Production_reg_dom", "L2281.RelLogitBaseValue_aitrade") ->
      ai_compute_trade.xml

    # ai_chip_resource.xml: global AI-accelerator supply resource (L2283). Mirror zenergy_xml_resources.R.
    # Phase A: authored but not yet consumed by the compute technology.
    create_xml("ai_chip_resource.xml") %>%
      add_xml_data(L2283.RenewRsrc_aichip, "RenewRsrc") %>%
      add_node_equiv_xml("resource") %>%
      add_node_equiv_xml("subresource") %>%
      add_node_equiv_xml("technology") %>%
      add_xml_data(L2283.RenewRsrcPrice_aichip, "RenewRsrcPrice") %>%
      add_xml_data(L2283.SmthRenewRsrcCurves_aichip, "SmthRenewRsrcCurvesGdpElast") %>%
      add_xml_data(L2283.SmthRenewRsrcTechChange_aichip, "SmthRenewRsrcTechChange") %>%
      add_xml_data(L2283.ResTechShrwt_aichip, "ResTechShrwt") %>%
      add_precursors("L2283.RenewRsrc_aichip", "L2283.RenewRsrcPrice_aichip",
                     "L2283.SmthRenewRsrcCurves_aichip", "L2283.SmthRenewRsrcTechChange_aichip",
                     "L2283.ResTechShrwt_aichip") ->
      ai_chip_resource.xml

    return_data(ai_compute.xml, ai_compute_trade.xml, ai_chip_resource.xml)
  } else {
    stop("Unknown command")
  }
}
