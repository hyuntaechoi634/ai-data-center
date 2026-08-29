# Repository agent instructions

## Current migration rule

Treat migration as a non-destructive copy until the user explicitly approves
deletion from an older tree. The authoring and analysis source of record is
`/data/home/hyuntae-choi/ai-datacenter/`. The public GCAM v9.1 repository is
`/home/hyuntae-choi/ai-data-center/`. Preserve user changes in both trees and
inspect Git status before editing.

## Run-matrix freeze

`/data/home/hyuntae-choi/gcam-matrix/` is currently rebuilding three
databases. Do not move, rename, delete, deploy into, or otherwise mutate that
tree until the rebuild is complete. Use only read-only status checks while it
is running. Completion does not waive the verification requirements below.

After any later move of the run matrix:

1. Revalidate every frozen label against its existing SHA-256 manifest.
2. Confirm the v9.1 input mirror hashes.
3. Run a one-cell `gcamwrapper` smoke test because `gcam_module.so` may
   contain a build-time absolute path.
4. Record the verification output before launching new runs.

## Other trees

- Build tree: `/data/home/hyuntae-choi/gcam-v9.1/`
- Run tree: `/data/home/hyuntae-choi/gcam-matrix/`
- Public repository: `/home/hyuntae-choi/ai-data-center/`

Read from the old build tree when provenance is needed, but do not modify it
during this migration. Configuration XML paths such as `../input/...` are
tree-relative and remain valid when their complete tree is moved.

## Absolute-path migration checklist

Before moving the corresponding components, find and replace hardcoded paths
in all of the following:

- `scripts/pipeline/recalibrate.sh`: `ROOT`, `GCAM_V91`, and `MATRIX`
- `deploy_ai_overlay.sh`: `SRC` and `DST`
- `analysis/figrun/scripts/run_figrun_batch.py`: `V91`, `OUT`,
  `STATUS`, and `PY`
- `build_timeseries.py` and `build_figdata.py`
- bridge part scripts, while preserving their repository-root working
  directory contract
- `foldback.py`
- `make_figrun_configs.py`
- temporary job runners

Search again for old absolute roots after edits. Do not assume this list is
exhaustive.

## Environments

- Use conda environment `gcam-ai-wrap` for wrapper execution.
- Use conda environment `dissertation` for figures and `gcamreader`.
- Wrapper runs require
  `LD_PRELOAD=/usr/local/lib64/libtbb.so.12` unless the runtime linkage has
  been deliberately rebuilt and reverified.

## Frozen outputs and naming

Frozen labels such as `brp6-cal`, `brp7d3-cal`, and `brp7d8-cal` remain
immutable evidence. Verify them by SHA-256 after any move. Do not silently
regenerate a frozen label in place.

For public files, prefer descriptive names. When GCAM requires conventional
chunk or dataset identifiers, keep a checked, reversible mapping rather than
performing an unverified semantic rename. For the gcamdata overlay, follow
`input/gcamdata/ai-data-center/filename-map.csv` and
`supplemental-file-map.csv`, then run both `verify.py` and
`generation/regenerate.py`. A complete public gcamdata snapshot has 226 XML
files, including the separately locked direct-air-capture scenario overlay.

## Public-release gate

Do not commit or push the migrated gcamdata layer to a public remote until
`input/gcamdata/ai-data-center/provenance/PUBLICATION_REVIEW.md` is resolved.
The regional data-center electricity targets and derived table are identified
as based on restricted BNEF material. Preserve the audited brp7d8 evidence
unchanged. If redistribution is not permitted, create a separate open-data
release profile and new manifests.

## Research evidence and local papers

The migrated derivation package is under the repository-root
`analysis/research/`. The complete `analysis/` tree is local and ignored by
Git because it is not required to execute GCAM and includes third-party papers
with mixed redistribution rights. Keep its executable code, compact inputs,
source mappings, SHA-256 manifests, and PDF library intact locally.

Verify the local research package with
`python3 analysis/research/verify-research.py`. Use its `--pdfs` option only
when the local library is present. Portable scripts must not embed personal
absolute paths; accept an explicit argument or a documented environment
variable instead. Mutation-capable calibration commands must require an
explicit apply flag and must never default to the active run matrix.

## Final local runtime and public boundary

The descriptive final configurations and runner are under
`exe/ai-data-center/`. They use
`input/gcamdata/xml-ai-data-center-calibrated/`,
`input/policy/ai-data-center/`, and
`input/solution/cal_broyden_kaist.xml`. The calibrated seven-part restart is
required for local reproduction of the 2050 runs, but it was generated from
the restricted calibrated brp7d8 XML layer. Keep `restart.*` ignored and
denylisted. A future open-data profile must generate a distinct restart
lineage.

Run `python3 exe/ai-data-center/verify-runtime.py` before any model launch.
The solver rev5 change is XML-only. Do not require byte-identical executable
hashes from independent builds when all builds use the unmodified GCAM v9.1
core source at commit `11e128fb7ce3e14e9c4daf3903ba73123046a7aa`.
