# Figure Studio integration branch

Status: AWAITING REV8 PUBLIC EXPORT

This branch is the public integration target for Figure Studio. Application
code lives under `tools/figure-studio/`. The future reviewed figure export will
live under `figure-studio/public/`.

The interim package under local `analysis/manuscript-figures/` remains ignored
and denylisted. It must not be copied or force-added here. After rev8 finishes,
create a distinct reviewed public export with new hashes and then enable Draft
PR publishing from the web application.

User proposal branches use `cht/figure-proposal/...` and target
`cht/proj/figure-studio`. They must not use a child name below the integration
branch because Git branch references would conflict.
