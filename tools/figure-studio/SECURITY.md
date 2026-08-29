# Figure Studio security boundary

Figure Studio must bind to `127.0.0.1` and sit behind authenticated access for
external collaborators. The browser is untrusted. Uploaded files are data and
are never executed. Generated plotting code runs in a network-disabled
Bubblewrap workspace with resource limits.

OpenAI and GitHub credentials belong in separate, owned, mode-600 files outside
the repository. Do not put tokens in environment values, browser storage,
URLs, chat messages, session workspaces, or Git history.

A Draft PR in this public repository is public immediately. GitHub publishing
therefore requires all of the following:

- authenticated collaborator mode
- a reviewed `PUBLIC_EXPORT.json` manifest
- exact baseline hashes
- an unchanged pinned integration-branch commit
- a text-only path allowlist for the active figure and shared helpers
- credential-pattern scanning and strict file-size limits

The publisher excludes source data, derived result tables, uploads, rendered
figures, chat messages, and archives. The local interim figure package is not a
valid public export.
