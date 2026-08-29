# Figure Studio integration branch

Status: FINAL CALIBRATED CODE EXPORT READY

This branch is the public integration target for Figure Studio. Application
code lives under `tools/figure-studio/`. The reviewed plotting-code and caption
export lives under `figure-studio/public/`.

The complete local package under `analysis/manuscript-figures/` remains ignored
and denylisted. It must not be copied or force-added here. Only the exact
reviewed plotting files and captions may enter the public export. Source data,
derived tables, and rendered figures remain excluded.

User proposal branches use `cht/figure-proposal/...` and target
`cht/proj/figure-studio`. They must not use a child name below the integration
branch because Git branch references would conflict.
