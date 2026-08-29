# Publication review gate

Status: **BLOCKED PENDING REDISTRIBUTION REVIEW OR OPEN-DATA REBUILD**

The local migration, regeneration, and runtime checks may pass while this
publication gate remains blocked. Local reproducibility is not permission to
redistribute restricted evidence or its derived regional values.

## Restricted regional calibration chain

The following compact generation inputs contain or reconstruct regional
values derived from BNEF material:

- `generation/ai_constants.py`
- `generation/inputs/regional-data-center-electricity-targets-2021-2025.csv`
- `generation/inputs/frozen-calibration-foldback-evidence.csv`
- `data/locked/energy/regional-demand-calibration-2025.csv`

The ignored research archive retains the corresponding local evidence tables:

- `analysis/research/calibration/inputs/restricted-regional-soft-calibration-targets-2025.csv`
- `analysis/research/calibration/inputs/regional-service-electricity-targets-2021-2025.csv`

The known deployed and generated descendants include:

- `data/generated/energy/data-center-electricity-by-region-2021.csv`
- `data/generated/energy/conventional-data-center-electricity-share-by-region.csv`
- `data/generated/energy/ai-share-of-data-center-electricity-by-region-and-year.csv`
- `data/generated/energy/ai-compute-trade-balance-by-region-2021.csv`
- `data/generated/energy/power-usage-effectiveness-by-region-and-year.csv`
- `input/gcamdata/inst/extdata/energy/datacenter_elec_EJ_R_Yh.csv`
- `input/gcamdata/inst/extdata/energy/aeei_calib_2025_R.csv`
- `input/gcamdata/inst/extdata/energy/datacenter_convshare_R.csv`
- `input/gcamdata/inst/extdata/energy/ai_share_fAI_R_Y.csv`
- `input/gcamdata/inst/extdata/energy/datacenter_tradebalance_R_Y.csv`
- `input/gcamdata/inst/extdata/energy/pue_R.csv`
- `input/policy/ai-data-center/demand-low.xml`
- `input/policy/ai-data-center/demand-medium.xml`
- `input/policy/ai-data-center/demand-high.xml`
- `input/policy/ai-data-center/demand-constant.xml`
- the private calibrated XML snapshot under
  `input/gcamdata/xml-ai-data-center-calibrated/`
- the seven warm restart parts matching
  `exe/restart/ai-data-center-warm-start/restart.*`

The conventional share and regional trade balance directly reflect the
restricted regional electricity allocation. The PUE path is normalized with
the 2021 and 2025 regional BNEF weights. The warm restart was generated from
the restricted calibrated XML layer and is therefore kept private under the
same conservative downstream boundary.

This is a conservative publication boundary. It does not assert that every
downstream number is independently copyrightable. It records that the
redistribution question has not been resolved and prevents accidental public
commit while that review is open.

## Mechanical protection

The repository root `.gitignore` excludes the known restricted chain.
`restricted-publication-paths.txt` is the matching machine-readable
denylist. `restricted-publication-lineage.csv` records the upstream source,
derivation stage, and reason for every pattern. The verifier requires an exact
denylist-to-lineage match and checks all six restricted descriptive-to-deployed
pairs against `filename-map.csv`. Run:

```bash
python3 input/gcamdata/ai-data-center/provenance/verify_publication_boundary.py
```

The command fails if a denylisted path is tracked, staged, or present as an
unignored untracked file. The same command runs in
`.github/workflows/publication-boundary.yml`, so a forced add is rejected in
CI even if it bypasses `.gitignore`.

The gate verifies exclusion only. A passing result does not certify a complete
or runnable public profile.

## Resolution

Resolve this gate through one of the following documented paths:

1. Record permission that explicitly covers redistribution of the listed
   regional inputs and the intended derived outputs.
2. Build an open-data profile using a redistributable regional proxy,
   regenerate all affected gcamdata and policy inputs, and create new source,
   generated-input, policy, XML, and runtime manifests.

Do not rewrite or relabel the frozen calibrated evidence as an open profile.
Keep the audited private hashes intact and give the open profile a distinct
name and lineage.

## Other third-party materials

The R chunks retain their upstream Battelle copyright notices and remain
subject to the repository license.

The complete paper collection is stored only under the ignored
`analysis/research/pdf-library/` tree. Its bibliographic and cryptographic
manifest is not permission to redistribute the underlying works. Non-PDF
third-party snapshots, including vendor HTML and research datasets, also
require a source and license review before any future decision to publish the
ignored analysis tree.
