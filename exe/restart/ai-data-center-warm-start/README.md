# Calibrated warm restart

The seven `restart.0` through `restart.6` files are the byte-identical warm
restart used by the final 2050 scenario and database configurations.

Unlike ordinary generated restarts, this calibrated restart is a required
runtime input. Its hashes are locked in
`exe/ai-data-center/runtime-hashes.sha256` and verified before a database run.

## Publication boundary

These restart bytes were generated from the restricted final calibrated XML
layer. They remain a local runtime asset and are ignored by Git. The
publication denylist rejects `restart.*` even if it is force-added. A future
open-data profile must generate a distinct restart lineage rather than
relabeling these files.
