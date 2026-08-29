# Copyright 2019 Battelle Memorial Institute; see the LICENSE file.
#' module_energy_L2283.ai_chip_resource
#'
#' SUPPLY-CURVE layer (Phase 2 of the chip side): a global "AI accelerators" renewresource whose supply is a
#' SMOOTH renewable subresource, Q(P) = maxSubResource * P^b / (mid.price^b + P^b). This endogenizes the chip
#' price that the compute production sector pays: within a period the price climbs the curve toward the capacity
#' ceiling Qbar (= maxSubResource) as compute demand pulls chip demand; across periods mid.price falls via
#' techChange (Moore/Wright cost decline) and Qbar scales with GDP^gdpSupplyElast (fab buildout). Mirrors the
#' renewable-resource authoring of module_energy_L210.resources (RenewRsrc / RenewRsrcPrice /
#' SmthRenewRsrcCurvesGdpElast / SmthRenewRsrcTechChange / ResTechShrwt). Hosted in one global market so all
#' regions face a single world chip price (spec sec:semi). PHASE A: the resource is authored but not yet
#' consumed by the compute technology (that wiring + base-year calibration is Phase B).
#' @return L2283.* tibbles.
#' @importFrom dplyr mutate select
#' @importFrom tibble tibble
#' @author gcamdata-ai 2026
module_energy_L2283.ai_chip_resource <- function(command, ...) {
  if(command == driver.DECLARE_INPUTS) {
    return(c(FILE = "energy/A28.chip_resource"))
  } else if(command == driver.DECLARE_OUTPUTS) {
    return(c("L2283.RenewRsrc_aichip",
             "L2283.RenewRsrcPrice_aichip",
             "L2283.SmthRenewRsrcCurves_aichip",
             "L2283.SmthRenewRsrcTechChange_aichip",
             "L2283.ResTechShrwt_aichip"))
  } else if(command == driver.MAKE) {

    # Silence package checks
    host.region <- renewresource <- smooth.renewable.subresource <- output.unit <- price.unit <-
      market <- base.price <- maxSubResource <- mid.price <- curve.exponent <- techChange <-
      gdpSupplyElast <- region <- resource <- subresource <- technology <- year <-
      share.weight <- year.fillout <- price <- NULL

    all_data <- list(...)[[1]]
    A28.chip_resource <- get_data(all_data, "energy/A28.chip_resource", strip_attributes = TRUE)
    R <- A28.chip_resource  # single-row parameter table

    # ---- RenewRsrc: resource sector (output unit, price unit, market) ----
    tibble(region = R$host.region, renewresource = R$renewresource,
           output.unit = R$output.unit, price.unit = R$price.unit, market = R$market) ->
      L2283.RenewRsrc_aichip

    # ---- RenewRsrcPrice: read-in price for the model base years (pins base-year price; future is solved) ----
    tibble(region = R$host.region, renewresource = R$renewresource) %>%
      repeat_add_columns(tibble(year = MODEL_BASE_YEARS)) %>%
      mutate(price = R$base.price) %>%
      select(region, renewresource, year, price) ->
      L2283.RenewRsrcPrice_aichip

    # ---- SmthRenewRsrcCurvesGdpElast: the smooth supply curve (Qbar, mid-price, b) + GDP scaling of Qbar ----
    tibble(region = R$host.region, renewresource = R$renewresource,
           smooth.renewable.subresource = R$smooth.renewable.subresource,
           year.fillout = min(MODEL_BASE_YEARS),
           maxSubResource = R$maxSubResource, mid.price = R$mid.price,
           curve.exponent = R$curve.exponent, gdpSupplyElast = R$gdpSupplyElast) %>%
      select(LEVEL2_DATA_NAMES[["SmthRenewRsrcCurvesGdpElast"]]) ->
      L2283.SmthRenewRsrcCurves_aichip

    # ---- SmthRenewRsrcTechChange: mid-price decline over time (Moore/Wright) ----
    tibble(region = R$host.region, renewresource = R$renewresource,
           smooth.renewable.subresource = R$smooth.renewable.subresource,
           year.fillout = min(MODEL_BASE_YEARS), techChange = R$techChange) %>%
      select(LEVEL2_DATA_NAMES[["SmthRenewRsrcTechChange"]]) ->
      L2283.SmthRenewRsrcTechChange_aichip

    # ---- ResTechShrwt: the resource's shell technology (resource -> resource good), active in all model years ----
    tibble(region = R$host.region, resource = R$renewresource,
           subresource = R$smooth.renewable.subresource, technology = R$renewresource) %>%
      repeat_add_columns(tibble(year = MODEL_YEARS)) %>%
      mutate(share.weight = 1) %>%
      select(LEVEL2_DATA_NAMES[["ResTechShrwt"]]) ->
      L2283.ResTechShrwt_aichip

    # ===================================================
    # Produce outputs
    # ===================================================
    L2283.RenewRsrc_aichip %>%
      add_title("AI accelerator (chip) renewresource sector") %>%
      add_units("RFLOP/yr; 1975$/EFLOP-yr") %>%
      add_comments("Global chip-supply market hosting the smooth supply curve") %>%
      add_precursors("energy/A28.chip_resource") ->
      L2283.RenewRsrc_aichip

    L2283.RenewRsrcPrice_aichip %>%
      add_title("AI accelerator base-year read-in price") %>%
      add_units("1975$/EFLOP-yr") %>%
      add_comments("Pins the chip price in the model base years; future years solve on the supply curve") %>%
      add_precursors("energy/A28.chip_resource") ->
      L2283.RenewRsrcPrice_aichip

    L2283.SmthRenewRsrcCurves_aichip %>%
      add_title("AI accelerator smooth supply curve (Qbar, mid-price, curve-exponent, gdpSupplyElast)") %>%
      add_units("RFLOP/yr; 1975$/EFLOP-yr; unitless") %>%
      add_comments("Q(P)=Qbar*P^b/(mid.price^b+P^b); Qbar scales with GDP^gdpSupplyElast") %>%
      add_precursors("energy/A28.chip_resource") ->
      L2283.SmthRenewRsrcCurves_aichip

    L2283.SmthRenewRsrcTechChange_aichip %>%
      add_title("AI accelerator subresource technical change (mid-price decline)") %>%
      add_units("fraction/yr") %>%
      add_comments("Moore/Wright cost decline shifting the supply curve down over time") %>%
      add_precursors("energy/A28.chip_resource") ->
      L2283.SmthRenewRsrcTechChange_aichip

    L2283.ResTechShrwt_aichip %>%
      add_title("AI accelerator resource shell-technology share-weights") %>%
      add_units("unitless") %>%
      add_comments("Resource internal technology, active across model years") %>%
      add_precursors("energy/A28.chip_resource") ->
      L2283.ResTechShrwt_aichip

    return_data(L2283.RenewRsrc_aichip, L2283.RenewRsrcPrice_aichip, L2283.SmthRenewRsrcCurves_aichip,
                L2283.SmthRenewRsrcTechChange_aichip, L2283.ResTechShrwt_aichip)
  } else {
    stop("Unknown command")
  }
}
