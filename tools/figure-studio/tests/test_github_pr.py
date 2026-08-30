from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from studio.github_pr import (
    GitHubClient,
    GitHubProposalPublisher,
    ProposalError,
    ProposalFile,
    PublicExportManifest,
    collect_proposal_files,
)


BASE_COMMIT = "1" * 40
BASE_TREE = "2" * 40


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GitHubProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.baseline = root / "baseline"
        self.workspace = root / "workspace"
        for location in (self.baseline, self.workspace):
            (location / "figures" / "figure-01").mkdir(parents=True)
            (location / "figures" / "helpers").mkdir(parents=True)
        self.original = b"print('original')\n"
        for location in (self.baseline, self.workspace):
            (location / "figures" / "figure-01" / "make_figure.py").write_bytes(
                self.original
            )
            (location / "figures" / "helpers" / "style.py").write_text(
                "COLOR = 'blue'\n", encoding="utf-8"
            )
        self.manifest = PublicExportManifest(
            repository="hyuntaechoi634/ai-data-center",
            base_branch="cht/proj/figure-studio",
            base_commit=BASE_COMMIT,
            repository_root="figure-studio/public",
            allowed_roots=(Path("figures/figure-01"), Path("figures/helpers")),
            allowed_files=frozenset(
                {
                    "figures/figure-01/make_figure.py",
                    "figures/helpers/style.py",
                }
            ),
            baseline_sha256={
                "figures/figure-01/make_figure.py": digest(self.original),
                "figures/helpers/style.py": digest(b"COLOR = 'blue'\n"),
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_collects_only_changed_reviewed_text(self) -> None:
        revised = b"print('revised')\n"
        (self.workspace / "figures" / "figure-01" / "make_figure.py").write_bytes(
            revised
        )
        (self.workspace / "figures" / "figure-01" / "preview.jpg").write_bytes(
            b"not published"
        )
        files = collect_proposal_files(
            self.baseline, self.workspace, "figure-01", self.manifest
        )
        self.assertEqual(len(files), 1)
        self.assertEqual(
            files[0].repository_path,
            "figure-studio/public/figures/figure-01/make_figure.py",
        )
        self.assertEqual(files[0].content, revised)

    def test_rejects_unreviewed_or_secret_code(self) -> None:
        (self.baseline / "figures" / "figure-01" / "make_figure.py").write_text(
            "print('stale')\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ProposalError, "baseline"):
            collect_proposal_files(
                self.baseline, self.workspace, "figure-01", self.manifest
            )

        (self.baseline / "figures" / "figure-01" / "make_figure.py").write_bytes(
            self.original
        )
        (self.workspace / "figures" / "figure-01" / "make_figure.py").write_text(
            "TOKEN = '" + "sk-" + "abcdefghijklmnopqrstuvwxyz123456'\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ProposalError, "credential"):
            collect_proposal_files(
                self.baseline, self.workspace, "figure-01", self.manifest
            )

    def test_rejects_new_text_file_even_inside_allowed_root(self) -> None:
        (self.workspace / "figures" / "figure-01" / "uploaded-notes.txt").write_text(
            "restricted source notes\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ProposalError, "unreviewed public path"):
            collect_proposal_files(
                self.baseline, self.workspace, "figure-01", self.manifest
            )

    def test_ignores_only_unchanged_internal_text_files(self) -> None:
        for location in (self.baseline, self.workspace):
            (location / "figures" / "figure-01" / "internal_helper.py").write_text(
                "INTERNAL = True\n", encoding="utf-8"
            )
        revised = b"print('revised')\n"
        (self.workspace / "figures" / "figure-01" / "make_figure.py").write_bytes(
            revised
        )
        files = collect_proposal_files(
            self.baseline, self.workspace, "figure-01", self.manifest
        )
        self.assertEqual([item.content for item in files], [revised])

        (self.workspace / "figures" / "figure-01" / "internal_helper.py").write_text(
            "INTERNAL = False\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ProposalError, "unreviewed public path"):
            collect_proposal_files(
                self.baseline, self.workspace, "figure-01", self.manifest
            )

    def test_creates_draft_pr_from_pinned_base(self) -> None:
        calls: list[tuple[str, str, dict | None]] = []

        def request(method: str, endpoint: str, payload: dict | None) -> dict:
            calls.append((method, endpoint, payload))
            if endpoint.startswith("/git/ref/"):
                return {"object": {"sha": BASE_COMMIT}}
            if endpoint == f"/git/commits/{BASE_COMMIT}":
                return {"tree": {"sha": BASE_TREE}}
            if endpoint == "/git/blobs":
                return {"sha": "3" * 40}
            if endpoint == "/git/trees":
                return {"sha": "4" * 40}
            if endpoint == "/git/commits":
                return {"sha": "5" * 40}
            if endpoint == "/git/refs":
                return {"ref": payload["ref"]}
            if endpoint == "/pulls":
                return {
                    "number": 17,
                    "html_url": "https://github.com/hyuntaechoi634/ai-data-center/pull/17",
                }
            self.fail(f"Unexpected endpoint {endpoint}")

        client = GitHubClient(
            self.manifest.repository,
            "token-for-test-only-1234567890",
            requester=request,
        )
        result = client.create_draft_pull_request(
            self.manifest,
            [
                ProposalFile(
                    workspace_path="figures/figure-01/make_figure.py",
                    repository_path=(
                        "figure-studio/public/figures/figure-01/make_figure.py"
                    ),
                    content=b"print('revised')\n",
                )
            ],
            "Propose Figure 01 revision",
            "figure-01",
            "a",
        )
        self.assertEqual(result.number, 17)
        pull_payload = next(payload for method, endpoint, payload in calls if endpoint == "/pulls")
        self.assertTrue(pull_payload["draft"])
        self.assertEqual(pull_payload["base"], "cht/proj/figure-studio")
        self.assertTrue(pull_payload["head"].startswith("cht/figure-proposal/"))

    def test_refuses_a_moved_base_branch(self) -> None:
        def request(method: str, endpoint: str, payload: dict | None) -> dict:
            return {"object": {"sha": "9" * 40}}

        client = GitHubClient(
            self.manifest.repository,
            "token-for-test-only-1234567890",
            requester=request,
        )
        with self.assertRaisesRegex(ProposalError, "changed"):
            client.create_draft_pull_request(
                self.manifest,
                [],
                "Propose Figure 01 revision",
                "figure-01",
                None,
            )

    def test_removes_branch_when_pull_request_creation_fails(self) -> None:
        calls: list[tuple[str, str, dict | None]] = []

        def request(method: str, endpoint: str, payload: dict | None) -> dict:
            calls.append((method, endpoint, payload))
            if endpoint.startswith("/git/ref/"):
                return {"object": {"sha": BASE_COMMIT}}
            if endpoint == f"/git/commits/{BASE_COMMIT}":
                return {"tree": {"sha": BASE_TREE}}
            if endpoint == "/git/blobs":
                return {"sha": "3" * 40}
            if endpoint == "/git/trees":
                return {"sha": "4" * 40}
            if endpoint == "/git/commits":
                return {"sha": "5" * 40}
            if endpoint == "/git/refs":
                return {"ref": payload["ref"]}
            if endpoint == "/pulls":
                raise ProposalError("simulated pull request failure")
            if method == "DELETE" and endpoint.startswith("/git/refs/heads/"):
                return {}
            self.fail(f"Unexpected endpoint {endpoint}")

        client = GitHubClient(
            self.manifest.repository,
            "token-for-test-only-1234567890",
            requester=request,
        )
        with self.assertRaisesRegex(ProposalError, "simulated"):
            client.create_draft_pull_request(
                self.manifest,
                [
                    ProposalFile(
                        workspace_path="figures/figure-01/make_figure.py",
                        repository_path=(
                            "figure-studio/public/figures/figure-01/make_figure.py"
                        ),
                        content=b"print('revised')\n",
                    )
                ],
                "Propose Figure 01 revision",
                "figure-01",
                None,
            )
        self.assertTrue(
            any(
                method == "DELETE" and endpoint.startswith("/git/refs/heads/")
                for method, endpoint, _ in calls
            )
        )

    def test_token_file_must_be_private_regular_file(self) -> None:
        token = Path(self.temporary.name) / "github.token"
        token.write_text("token-for-test-only-1234567890\n", encoding="utf-8")
        environment = {
            "FIGURE_STUDIO_GITHUB_REPOSITORY": "hyuntaechoi634/ai-data-center",
            "FIGURE_STUDIO_GITHUB_BASE_BRANCH": "cht/proj/figure-studio",
            "FIGURE_STUDIO_GITHUB_TOKEN_FILE": str(token),
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            publisher = GitHubProposalPublisher(self.baseline, True)
            token.chmod(0o644)
            with self.assertRaisesRegex(ProposalError, "safely"):
                publisher._token()
            token.chmod(0o600)
            self.assertEqual(publisher._token(), "token-for-test-only-1234567890")

            link = token.with_name("github-link.token")
            link.symlink_to(token)
            os.environ["FIGURE_STUDIO_GITHUB_TOKEN_FILE"] = str(link)
            linked = GitHubProposalPublisher(self.baseline, True)
            with self.assertRaisesRegex(ProposalError, "configured"):
                linked._token()


if __name__ == "__main__":
    unittest.main()
