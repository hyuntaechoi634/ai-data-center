# AI data-center GCAM runs

This directory contains the final 2050 runtime contract for the AI data-center
extension to GCAM v9.1. The public names state the three scenario axes
directly:

- `demand-low`, `demand-medium`, `demand-high`, or `demand-constant`
- `efficiency-low`, `efficiency-medium`, or `efficiency-high`
- `reference` or `net-zero-2050`

For example,
`ai-data-center_demand-low_efficiency-high_net-zero-2050.xml` is the low
demand, high efficiency, net-zero-2050 case. The internal calibration label
is retained only in the reversible source map.

## Configuration sets

`configurations/scenarios/` contains all 24 cases with database output
disabled. `configurations/database-archive/` contains the same 24 cases with
database output enabled and split into four independent groups of six:

- `efficiency-low`, `efficiency-medium`, and `efficiency-high` each hold
  three nonconstant demand levels under two climate policies.
- `demand-constant` holds all three efficiency levels under two climate
  policies.

The 24 unique scenario cells are represented by two execution profiles, for
48 configuration files in total. Both profiles use:

- calibrated inputs in `input/gcamdata/xml-ai-data-center-calibrated/`
- policy overlays in `input/policy/ai-data-center/`
- `input/solution/cal_broyden_kaist.xml`
- the local-only seven-part warm restart in
  `exe/restart/ai-data-center-warm-start/`
- stop period 11 and stop year 2050

`configuration-map.csv` records every original filename and scenario name,
its descriptive public replacement, and both hashes.

## Publication boundary

The current calibrated XML, demand-policy, and warm-restart lineage depends on
restricted regional calibration evidence. The restart bytes remain available
for local verification and execution but are ignored and denylisted for
publication. These configurations document the audited runtime contract; they
do not make a public clone runnable until an open-data profile regenerates the
restricted inputs, policies, XML snapshot, and restart under a distinct
lineage.

## Verify

From the repository root:

```bash
python3 exe/ai-data-center/verify-runtime.py
```

During migration, an additional read-only comparison can be requested:

```bash
python3 exe/ai-data-center/verify-runtime.py \
  --canonical-matrix /path/to/read-only/gcam-matrix
```

The verifier checks all 226 calibrated gcamdata XML files, the 24 scenario
cells in both execution profiles, every referenced runtime file, solver and
policy hashes, the seven restart pieces, and the GCAM v9.1 source revision.
It requires a locally built `exe/gcam.exe`, but does not compare its byte hash
because equivalent builds can differ while using the same unmodified v9.1
C++ source.

## Build the four databases

```bash
bash exe/ai-data-center/run-database-archive.sh
```

The command starts one worker for each database group. A scenario passes only
when its full saved log contains `Period 11: 2050` and does not contain
`did not solve`. The runner stops a group after its first failed case and
retains every log under `output/ai-data-center-run-logs/`.

The runner refuses to overwrite an existing database. Use `--replace` only
when an intentional rebuild is required; existing databases are moved into a
timestamped backup rather than deleted.

## Solver and executable boundary

The final solver is `input/solution/cal_broyden_kaist.xml`. It uses a gentle
all-trial rebracketing stage and separate recovery gates for runaway and
negative-price Forest markets. This is an XML-only solver configuration
change; no GCAM C++ solver source was modified. The public, build, and matrix
core source trees all resolve to GCAM v9.1 commit
`11e128fb7ce3e14e9c4daf3903ba73123046a7aa`.

The migrated repository has its own Git history, so the runtime verifier does
not compare the repository HEAD with the upstream GCAM commit. It instead
checks the frozen Git index fingerprint in `gcam-core-origin.txt` and rejects
tracked changes within `cvs/objects/`.

The executable is a local build product and remains ignored by Git, following
the upstream GCAM repository convention.
