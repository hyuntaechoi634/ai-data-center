# Figure Studio

This directory contains the public application code for the AI Data Center
Figure Studio. The reviewed figure template is deliberately not bundled while
the rev8 model run and publication review are in progress.

The application edits an isolated copy of a local template. Point the server
at that template explicitly:

```bash
python tools/figure-studio/run_server.py \
  --template /path/to/reviewed/figure-template
```

The default local address is `http://127.0.0.1:8765`. The server refuses a
non-loopback bind. Use the existing authenticated reverse tunnel for named
collaborators.

## GitHub proposal workflow

The integration branch is `cht/proj/figure-studio`. A collaborator can create
a Draft PR only after the local template contains a reviewed
`PUBLIC_EXPORT.json` file with status `public-ready`.

Each proposal uses a separate branch under `cht/figure-proposal/` and targets
the integration branch. The exporter accepts only UTF-8 plotting code,
configuration, and captions from the active figure plus reviewed shared
helpers. It does not publish source data, result tables, uploads, rendered
outputs, chat history, or session archives.

Configure the server with a fine-grained GitHub token stored in an owned,
mode-600 file outside the repository:

```bash
export FIGURE_STUDIO_GITHUB_REPOSITORY=hyuntaechoi634/ai-data-center
export FIGURE_STUDIO_GITHUB_BASE_BRANCH=cht/proj/figure-studio
export FIGURE_STUDIO_GITHUB_PROPOSAL_PREFIX=cht/figure-proposal
export FIGURE_STUDIO_GITHUB_TOKEN_FILE=/path/to/github.token
```

The token needs Contents and Pull requests write permissions for this
repository only. It is read by the server and is never sent to the browser.

Until rev8 and the public export are finalized, the Pull request button remains
visible but disabled. Do not create `PUBLIC_EXPORT.json` merely to bypass that
gate.

## Application files

- `run_server.py` starts the loopback service
- `studio/server.py` provides the HTTP and JSON API
- `studio/sessions.py` provides isolated editing sessions and version history
- `studio/github_pr.py` validates and creates public Draft PRs
- `studio/agent.py` performs bounded figure-code revisions
- `studio/rendering.py` invokes the network-disabled renderer
- `static` contains the browser interface

## Tests

The GitHub publication-boundary unit test is self-contained:

```bash
python -m unittest discover -s tools/figure-studio/tests -v
```

The complete rendering and web suite remains in the local authoring tree until
a redistributable test template replaces the interim manuscript package.
