# Solver validation lineage

Public runtime file: `cal_broyden_kaist.xml`

Status: final adopted solver for the calibrated 2026-08-29 run

SHA-256: `4ff58fc647c365724fdd41e64ad8c1801e33bbdcce43a956680e34d923fce06e`

The internal source filename and revision labels below are retained only as
historical validation provenance. They are not public scenario names or
runtime interfaces.

Frozen source filename: `cal_broyden_diag10k_waterfix_kaist.xml`

## Historical validation record

rev5 (2026-08-29, historical checkpoint, validated 4/4 on the full ELow NZ gauntlet): waterfix + ONE added stage that re-brackets only unsolved NEGATIVE-price Trial-Value markets (filter: market-type="Trial-Value" && !(price-greater-than="0")). This matches the 2026-08-21 coverage defect exactly — the stock price>0 stages skip negative trials — while leaving healthy positive trials to the stock path.

Validation (analysis/pipeline/brp7d8pair/solver_forensics/): all four brp7d8 ELow NZ cells solve period 7 (2030) in 2,037-3,744 iterations (budget 10k) and complete 2050 with empty solve_failed — the mildest behavior any tested configuration produced on this landscape. Failure map that led here:
- waterfix: DMedium fails (negative-trial jam, 48 markets).
- rev2+rev3 (trialbracket): DConstant fails at 10k AND 20k (rev3 Forest re-bracket perturbs the land complex; ag jam + distributed_solar runaway).
- rev4 (rev2 only): DLow fails (all-trial coverage destabilizes positive wind/offshore/budget-fraction trials; Africa_Western NaN storm, 10,411 iters).
- rev5: 4/4, and previously-failing cells solve FASTER than anywhere else (DLow 2,037; DConstant 2,189; DMedium 3,316; DHigh 3,744).
History: rev1 unfiltered (reverted, CO2 NaN) -> rev2 all-trial stage -> rev3 Forest runaway stage -> rev4 = rev2 only -> rev5 = negative-only filter. Tolerances and budgets identical to the audited waterfix base throughout.

## rev6 (2026-08-29, superseded)
rev5 + per-good max-price-change=3 for 7 runaway goods (capital, water_td_elec_W/C,
seawater, nuclearFuelGenIII, distributed_solar, offshorewindresource).
Result: eliminated the DLow_EHigh_ref NaN storm (48k lines -> 0) but the cell
still failed 2030 at 10,025 iterations — NaN was symptom, not cause.

## rev7 (2026-08-29, superseded, sha 04184c79)
rev6 + three additions targeted from the rev6 2030 failure log:
1. Forest re-bracket stage RESTORED with price-greater-than="20" gate
   (rev3 redux, but fires only on already-runaway Forest; healthy land
   markets untouched — DConstant_ELow_nz protection preserved).
2. GDP_Trial: per-good max-price-change=3 + negative-price-only re-bracket
   stage (GDP_Trial is strictly positive in any sane state; observed
   runaway Brazil X=-4.27e12).
3. solution-floor 0.005 for good "offshore wind resource" (near-empty
   markets: absolute imbalance 1e-4..3e-3 misjudged via relative RED).
Adoption gauntlet 5/5: DLow_EHigh_ref exe SOLVED to 2050 (2030 in 1,290 it;
rev5/rev6 failed at 10,025), ELow NZ wrapper 4 cells solve_failed==[] with
2030 iterations improved vs rev5 (1494/1911/2247/3006 vs 2189/2037/3316/3744).
Isolation record: rev5 x wrapper x DLow_EHigh_ref also failed 2030 at 10,025
(not path-specific; genuine rev5 deficiency). Forensics:
analysis/pipeline/brp7d8pair/solver_forensics/

## rev8b (2026-08-29, adopted source label, sha 4ff58fc647c3)
Design reset: the rev5-rev7 lineage is retired wholesale. rev8b rebuilds from
the audited TRIALBRACKET variant (waterfix + gentle all-trial re-bracket at
interval 0.05 — the stage that solved DMedium_ELow_nz without destabilizing
legitimately-negative trials such as energy net export) and splits its Forest
stage in two:
  - runaway stage: market-matches="Forest" && price-greater-than="20"
  - negative stage: market-matches="Forest" && !(price-greater-than="0")
Healthy land markets (0 < price <= 20) are touched by neither — this resolves
the rev3-era conflict (ungated Forest re-bracket broke DConstant_ELow_nz)
while still rescuing UkraineForest-style negative collapses (X=-326 killed the
single-gate rev8 in DMedium_ELow_nz 2030 at 10,726 it).
Retired: per-good max-price-change caps (rev6), offshore wind solution-floor,
GDP_Trial guard, coarse negative-trial stage (rev5) — scaffolding around
damage the coarse trial stage itself caused (it broke waterfix-solvable
DLow_EHigh_ref; rev7's global caps then broke DConstant_EMedium_nz).
Adoption gauntlet (exe probes, all four record cells, all to 2050, zero NaN):
  DMedium_ELow_nz    2030: 1,333  (waterfix FAILED, rev8 FAILED 10,726)
  DConstant_ELow_nz  2030: 3,311  (rev2+rev3 FAILED — land complex intact)
  DLow_EHigh_ref     2030:   858  (rev5/rev6 FAILED 10k+; rev7 1,290)
  DConstant_EMedium_nz 2030: 2,509 (rev7 FAILED 10,037)
Full-run logs: solver_forensics/probe_rev8b-*.log
