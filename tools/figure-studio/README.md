# Figure Studio

This directory contains the public application code for the AI Data Center
Figure Studio. The full reviewed template remains local because its source
tables and rendered outputs are outside the public code-only boundary.

The application edits an isolated copy of a local template. Point the server
at that template explicitly:

```bash
python tools/figure-studio/run_server.py \
  --template /path/to/reviewed/figure-template
```

The default local address is `http://127.0.0.1:8765`. The server refuses a
non-loopback bind. Use the existing authenticated reverse tunnel for named
collaborators.

## Reviewed GitHub proposal workflow

The integration branch is `cht/proj/figure-studio`. A collaborator can submit
a private local review bundle only after the local template contains a
reviewed `PUBLIC_EXPORT.json` file with status `public-ready`.

Normal collaborators create no public branch. Their submissions remain in the
private owner-review queue. An exact email listed in
`FIGURE_STUDIO_ADMIN_EMAILS` may instead create a non-Draft PR and immediately
squash-merge it into `cht/proj/figure-studio`. That owner-admin exception never
targets `main`. Both paths accept only exact existing UTF-8 paths in the
reviewed manifest. New files are rejected even inside an allowed directory.
Source data, result tables, uploads, rendered outputs, chat history and session
archives are not included.

Configure the private review queue:

```bash
export FIGURE_STUDIO_GITHUB_REPOSITORY=hyuntaechoi634/ai-data-center
export FIGURE_STUDIO_GITHUB_BASE_BRANCH=cht/proj/figure-studio
export FIGURE_STUDIO_PROPOSAL_QUEUE_ROOT=/absolute/private/proposal/queue
export FIGURE_STUDIO_ADMIN_EMAILS=owner@example.org
export FIGURE_STUDIO_GITHUB_TOKEN_FILE=/absolute/private/github-owner-admin.token
```

The owner reviews the local diff and separately publishes it:

```bash
python tools/figure-studio/review_proposal.py <proposal-id>
python tools/figure-studio/review_proposal.py <proposal-id> \
  --publish --approve-reviewed --github-token-file /path/to/github.token
```

The owner command reads the mode-600 fine-grained GitHub token for queued
proposals. The web service reads it only for the exact owner-admin identity.
Restrict it to this repository with Contents and Pull requests read/write
access. PR creation failure triggers proposal-branch cleanup. CI independently
compares the PR checkout with the trusted base checkout and exact public
allowlist. Owner-admin immediate merges do not wait for asynchronous CI, so
promotion from the integration branch to `main` remains separately reviewed.

The Pull request button remains disabled until the code-only export, exact
hashes, and pinned integration commit have passed review. Do not create
`PUBLIC_EXPORT.json` merely to bypass that gate.

## API cost display

The composer reads sanitized month-to-date cost and hard-limit values from a
mode-600 cache. A separate owner process refreshes it with an OpenAI Admin key:

```bash
python tools/figure-studio/refresh_openai_billing.py --expected-limit-usd 30
```

The web service never receives the Admin key. It marks stale or unverified
values as warnings and shows whether the hard limit is currently blocking
requests.

## Application files

- `run_server.py` starts the loopback service
- `studio/server.py` provides the HTTP and JSON API
- `studio/sessions.py` provides isolated editing sessions and version history
- `studio/proposal_queue.py` routes collaborator and owner-admin submissions
- `studio/github_pr.py` validates Draft PR and immediate integration workflows
- `studio/billing.py` reads sanitized API billing status
- `studio/agent.py` performs bounded figure-code revisions
- `studio/rendering.py` invokes the network-disabled renderer
- `static` contains the browser interface

## Tests

The proposal and billing boundary tests are self-contained:

```bash
python -m unittest discover -s tools/figure-studio/tests -v
```

The complete rendering and web suite remains in the local authoring tree until
a redistributable test template replaces the interim manuscript package.
