# AI data-center scenario policies

These ten XML files are byte-identical copies of the final policy inputs used
by the frozen run matrix. Only the public filenames and directory name were
made descriptive.

The configuration axes are:

- demand: constant, low, medium, high
- efficiency: low, medium, high
- climate policy: reference or net-zero-2050
- trade: open in every final case

`carbon-policy-reference.xml` is the 2025 reference-policy peg.
`carbon-policy-net-zero-2050.xml` is the global CO2 net-zero-2050 policy.
The original-to-public path mapping and hashes are recorded in
`exe/ai-data-center/provenance/runtime-source-map.csv`.
