cal_broyden_kaist.xml is the public filename for the project's unified
canonical solver. Its frozen source filename was
cal_broyden_diag10k_waterfix_kaist.xml.

rev5 (2026-08-29, CURRENT — VALIDATED 4/4 on the full ELow NZ gauntlet): waterfix + ONE added stage that re-brackets only unsolved NEGATIVE-price Trial-Value markets (filter: market-type="Trial-Value" && !(price-greater-than="0")). This matches the 2026-08-21 coverage defect exactly — the stock price>0 stages skip negative trials — while leaving healthy positive trials to the stock path.

Validation (analysis/pipeline/brp7d8pair/solver_forensics/): all four brp7d8 ELow NZ cells solve period 7 (2030) in 2,037-3,744 iterations (budget 10k) and complete 2050 with empty solve_failed — the mildest behavior any tested configuration produced on this landscape. Failure map that led here:
- waterfix: DMedium fails (negative-trial jam, 48 markets).
- rev2+rev3 (trialbracket): DConstant fails at 10k AND 20k (rev3 Forest re-bracket perturbs the land complex; ag jam + distributed_solar runaway).
- rev4 (rev2 only): DLow fails (all-trial coverage destabilizes positive wind/offshore/budget-fraction trials; Africa_Western NaN storm, 10,411 iters).
- rev5: 4/4, and previously-failing cells solve FASTER than anywhere else (DLow 2,037; DConstant 2,189; DMedium 3,316; DHigh 3,744).
History: rev1 unfiltered (reverted, CO2 NaN) -> rev2 all-trial stage -> rev3 Forest runaway stage -> rev4 = rev2 only -> rev5 = negative-only filter. Tolerances and budgets identical to the audited waterfix base throughout.
