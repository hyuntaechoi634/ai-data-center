# Figure Studio security boundary

Figure Studio must bind to `127.0.0.1` and sit behind authenticated access for
external collaborators. The browser is untrusted. Uploaded files are data and
are never executed. Generated plotting code runs in a network-disabled
Bubblewrap workspace with resource limits.

Interactive previews also render in disposable copies of the session
workspace. Preview requests cannot mutate Current, create an Undo revision, or
move individual scientific marks. Apply repeats the validated change against
the real workspace and retains the existing panel-boundary check.

OpenAI and GitHub credentials belong in separate, owned, mode-600 files outside
the repository. Do not put tokens in environment values, browser storage,
URLs, chat messages, session workspaces, or Git history. The web process must
be denied access to the OpenAI Admin key. It may read the repository-scoped
GitHub token only for the explicit owner-admin workflow below.

A Draft PR in this public repository is public immediately. Normal web
submissions therefore create a private local bundle only. Exact emails in
`FIGURE_STUDIO_ADMIN_EMAILS`, which must also be collaborators, are an explicit
exception: after the same local gates pass, their button creates and
immediately squash-merges a non-Draft PR into `cht/proj/figure-studio`.
Neither path may target `main`. GitHub publication requires all of the
following:

- authenticated collaborator submission
- explicit owner review of the local diff
- a reviewed `PUBLIC_EXPORT.json` manifest
- exact baseline hashes
- an unchanged pinned integration-branch commit
- an exact existing-file allowlist for the active figure and shared helpers
- credential-pattern scanning and strict file-size limits
- independent base-checkout CI validation of every changed path

The owner-admin exception does not wait for asynchronous CI. The integration
branch is therefore staging, and its promotion to `main` requires a separate
review. A refused merge leaves the PR visible for manual review and does not
force-update any branch.

The publisher excludes source data, derived result tables, uploads, rendered
figures, chat messages, and archives. Only the separately reviewed code and
caption export is valid for proposals.

The billing badge reads a sanitized cache only. A separate process may read
the OpenAI Admin key to refresh cost and hard-limit values. The badge must show
stale and unverified states and must describe `inactive` as not currently
blocking, rather than as an absent configured limit.
