# Public figure code export

This directory contains the reviewed plotting code and captions for main
Figure 01 through Figure 06 and Supplementary Figure 01 through Figure 06.

It intentionally excludes source data, derived result tables, uploaded files,
rendered output, and session history. Figure Studio proposals may change only
the exact existing files recorded in `PROPOSAL_ALLOWLIST.json`. Internal run
labels remain only in local data lineage and are not public display names.

Each figure also has a small `layout-overrides.json` file. Figure Studio uses
it for reviewed movement, visibility, font-size, and font-family changes. The
scientific plotting code and input values remain the source of the plotted
data, and `layout_runtime.py` applies only those presentation overrides when a
figure is saved.
