# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_conv_compute_xml
#'
#' Assemble the L2285 production + L2286 demand tables into conv_compute.xml (the non-traded conventional
#' data-center sector). Mirrors zenergy_xml_ai_compute.R's ai_compute.xml block, plus the aeei table
#' (header "aeei", as in the municipal water demand xml).
#' @return XML = conv_compute.xml.
module_energy_conv_compute_xml <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c("L2285.Supplysector_convcompute", "L2285.SubsectorLogit_convcompute",
             "L2285.SubsectorShrwtFllt_convcompute", "L2285.SubsectorInterp_convcompute",
             "L2285.StubTech_convcompute", "L2285.GlobalTechShrwt_convcompute",
             "L2285.GlobalTechCoef_convcompute", "L2285.GlobalTechCost_convcompute",
             "L2285.GlobalTechTrackCapital_convcompute", "L2285.StubTechCoef_convcompute",
             "L2285.StubTechProd_convcompute",
             "L2286.PerCapitaBased_convcompute", "L2286.BaseService_convcompute",
             "L2286.IncomeElasticity_convcompute", "L2286.PriceElasticity_convcompute",
             "L2286.aeei_convcompute"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c(XML = "conv_compute.xml"))
  } else if(command == driver.MAKE) {

    all_data <- list(...)[[1]]

    L2285.Supplysector_convcompute <- get_data(all_data, "L2285.Supplysector_convcompute")
    L2285.SubsectorLogit_convcompute <- get_data(all_data, "L2285.SubsectorLogit_convcompute")
    L2285.SubsectorShrwtFllt_convcompute <- get_data(all_data, "L2285.SubsectorShrwtFllt_convcompute")
    L2285.SubsectorInterp_convcompute <- get_data(all_data, "L2285.SubsectorInterp_convcompute")
    L2285.StubTech_convcompute <- get_data(all_data, "L2285.StubTech_convcompute")
    L2285.GlobalTechShrwt_convcompute <- get_data(all_data, "L2285.GlobalTechShrwt_convcompute")
    L2285.GlobalTechCoef_convcompute <- get_data(all_data, "L2285.GlobalTechCoef_convcompute")
    L2285.GlobalTechCost_convcompute <- get_data(all_data, "L2285.GlobalTechCost_convcompute")
    L2285.GlobalTechTrackCapital_convcompute <- get_data(all_data, "L2285.GlobalTechTrackCapital_convcompute")
    L2285.StubTechCoef_convcompute <- get_data(all_data, "L2285.StubTechCoef_convcompute")
    L2285.StubTechProd_convcompute <- get_data(all_data, "L2285.StubTechProd_convcompute")
    L2286.PerCapitaBased_convcompute <- get_data(all_data, "L2286.PerCapitaBased_convcompute")
    L2286.BaseService_convcompute <- get_data(all_data, "L2286.BaseService_convcompute")
    L2286.IncomeElasticity_convcompute <- get_data(all_data, "L2286.IncomeElasticity_convcompute")
    L2286.PriceElasticity_convcompute <- get_data(all_data, "L2286.PriceElasticity_convcompute")
    L2286.aeei_convcompute <- get_data(all_data, "L2286.aeei_convcompute")

    create_xml("conv_compute.xml") %>%
      add_logit_tables_xml(L2285.Supplysector_convcompute, "Supplysector") %>%
      add_logit_tables_xml(L2285.SubsectorLogit_convcompute, "SubsectorLogit") %>%
      add_xml_data(L2285.SubsectorShrwtFllt_convcompute, "SubsectorShrwtFllt") %>%
      add_xml_data(L2285.SubsectorInterp_convcompute, "SubsectorInterp") %>%
      add_xml_data(L2285.StubTech_convcompute, "StubTech") %>%
      add_xml_data(L2285.GlobalTechShrwt_convcompute, "GlobalTechShrwt") %>%
      add_node_equiv_xml("input") %>%
      add_xml_data(L2285.GlobalTechCoef_convcompute, "GlobalTechCoef") %>%
      add_xml_data(L2285.GlobalTechTrackCapital_convcompute, "GlobalTechTrackCapital") %>%
      add_xml_data(L2285.GlobalTechCost_convcompute, "GlobalTechCost") %>%
      add_xml_data(L2285.StubTechCoef_convcompute, "StubTechCoef") %>%
      add_xml_data(L2285.StubTechProd_convcompute, "StubTechProd") %>%
      add_xml_data(L2286.PerCapitaBased_convcompute, "PerCapitaBased") %>%
      add_xml_data(L2286.BaseService_convcompute, "BaseService") %>%
      add_xml_data(L2286.IncomeElasticity_convcompute, "IncomeElasticity") %>%
      add_xml_data(L2286.PriceElasticity_convcompute, "PriceElasticity") %>%
      add_xml_data(L2286.aeei_convcompute, "aeei") %>%
      add_precursors("L2285.Supplysector_convcompute", "L2285.SubsectorLogit_convcompute",
                     "L2285.SubsectorShrwtFllt_convcompute", "L2285.SubsectorInterp_convcompute",
                     "L2285.StubTech_convcompute", "L2285.GlobalTechShrwt_convcompute",
                     "L2285.GlobalTechCoef_convcompute", "L2285.GlobalTechCost_convcompute",
                     "L2285.GlobalTechTrackCapital_convcompute", "L2285.StubTechCoef_convcompute",
                     "L2285.StubTechProd_convcompute", "L2286.PerCapitaBased_convcompute",
                     "L2286.BaseService_convcompute", "L2286.IncomeElasticity_convcompute",
                     "L2286.PriceElasticity_convcompute", "L2286.aeei_convcompute") ->
      conv_compute.xml

    return_data(conv_compute.xml)
  } else {
    stop("Unknown command")
  }
}
