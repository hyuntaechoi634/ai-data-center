from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from studio.github_pr import ProposalError
from studio.proposal_queue import ProposalQueue


BASE_COMMIT = "1" * 40
BASE_TREE = "2" * 40


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ProposalQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.template = root / "template"
        self.session = root / "session"
        self.queue_root = root / "queue"
        original = b"print('original')\n"
        relative = Path("figures/figure-01/make_figure.py")
        for location in (
            self.template,
            self.session / "baseline",
            self.session / "workspace",
        ):
            target = location / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(original)
        manifest = {
            "schema_version": 2,
            "status": "public-ready",
            "repository": "hyuntaechoi634/ai-data-center",
            "base_branch": "cht/proj/figure-studio",
            "base_commit": BASE_COMMIT,
            "repository_root": "figure-studio/public",
            "allowed_roots": ["figures/figure-01"],
            "allowed_files": [relative.as_posix()],
            "baseline_sha256": {relative.as_posix(): digest(original)},
        }
        for location in (self.template, self.session / "baseline"):
            (location / "PUBLIC_EXPORT.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
        (self.session / "workspace" / relative).write_text(
            "print('revised')\n", encoding="utf-8"
        )
        self.admin_token = root / "github-admin.token"
        self.admin_token.write_text(
            "token-for-test-only-1234567890\n", encoding="utf-8"
        )
        self.admin_token.chmod(0o600)
        self.environment = mock.patch.dict(
            os.environ,
            {
                "FIGURE_STUDIO_PROPOSAL_QUEUE_ROOT": str(self.queue_root),
                "FIGURE_STUDIO_GITHUB_REPOSITORY": "hyuntaechoi634/ai-data-center",
                "FIGURE_STUDIO_GITHUB_BASE_BRANCH": "cht/proj/figure-studio",
                "FIGURE_STUDIO_ADMIN_EMAILS": "admin@example.org",
                "FIGURE_STUDIO_GITHUB_TOKEN_FILE": str(self.admin_token),
            },
        )
        self.environment.start()
        self.queue = ProposalQueue(
            self.template,
            require_cloudflare_access=True,
            allowed_emails={"author@example.org", "admin@example.org"},
        )

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def test_web_submission_creates_private_review_bundle_only(self) -> None:
        result = self.queue.submit(
            self.session,
            "figure-01",
            "a",
            "Propose Figure 01 panel A revision",
            "author@example.org",
        )
        self.assertEqual(result.status, "pending-owner-review")
        bundle = self.queue_root / result.proposal_id
        self.assertEqual(bundle.stat().st_mode & 0o777, 0o700)
        self.assertEqual((bundle / "proposal.json").stat().st_mode & 0o777, 0o600)
        payload = json.loads((bundle / "proposal.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "pending-owner-review")
        self.assertNotIn("pull_request", payload)
        _, _, files = self.queue.load_pending(result.proposal_id)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].content, b"print('revised')\n")

    def test_pre_export_session_uses_the_reviewed_template_manifest(self) -> None:
        (self.session / "baseline" / "PUBLIC_EXPORT.json").unlink()
        result = self.queue.submit(
            self.session,
            "figure-01",
            None,
            "Propose a revision from an existing session",
            "author@example.org",
        )
        self.assertEqual(result.status, "pending-owner-review")
        payload = json.loads(
            (
                self.queue_root / result.proposal_id / "proposal.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["base_commit"], BASE_COMMIT)

    def test_owner_publish_is_separate_and_marks_bundle(self) -> None:
        queued = self.queue.submit(
            self.session,
            "figure-01",
            None,
            "Propose Figure 01 revision",
            "author@example.org",
        )
        token = Path(self.temporary.name) / "github.token"
        token.write_text("token-for-test-only-1234567890\n", encoding="utf-8")
        token.chmod(0o600)
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
                    "number": 19,
                    "html_url": "https://github.com/hyuntaechoi634/ai-data-center/pull/19",
                }
            self.fail(f"Unexpected endpoint {endpoint}")

        result = self.queue.publish_pending(queued.proposal_id, token, requester=request)
        self.assertEqual(result.number, 19)
        payload = json.loads(
            (self.queue_root / queued.proposal_id / "proposal.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["status"], "published-draft-pr")

    def test_tampered_bundle_is_rejected(self) -> None:
        queued = self.queue.submit(
            self.session,
            "figure-01",
            None,
            "Propose Figure 01 revision",
            "author@example.org",
        )
        content = self.queue_root / queued.proposal_id / "files" / "000.txt"
        content.write_text("changed after review\n", encoding="utf-8")
        with self.assertRaisesRegex(ProposalError, "hash"):
            self.queue.load_pending(queued.proposal_id)

    def test_exact_admin_creates_and_immediately_merges_pr(self) -> None:
        calls: list[tuple[str, str, dict | None]] = []

        def request(method: str, endpoint: str, payload: dict | None) -> dict:
            calls.append((method, endpoint, payload))
            if endpoint.startswith("/git/ref/"):
                return {"object": {"sha": BASE_COMMIT}}
            if method == "GET" and endpoint == f"/git/commits/{BASE_COMMIT}":
                return {"tree": {"sha": BASE_TREE}}
            if endpoint == "/git/blobs":
                return {"sha": "3" * 40}
            if endpoint == "/git/trees":
                return {"sha": "4" * 40}
            if method == "POST" and endpoint == "/git/commits":
                return {"sha": "5" * 40}
            if endpoint == "/git/refs":
                return {"ref": payload["ref"]}
            if endpoint == "/pulls":
                return {
                    "number": 23,
                    "html_url": "https://github.com/hyuntaechoi634/ai-data-center/pull/23",
                }
            if method == "PUT" and endpoint == "/pulls/23/merge":
                return {"merged": True, "sha": "6" * 40, "message": "merged"}
            if method == "DELETE" and endpoint.startswith("/git/refs/heads/"):
                return {}
            self.fail(f"Unexpected endpoint {method} {endpoint}")

        result = self.queue.submit(
            self.session,
            "figure-01",
            "a",
            "Apply Figure 01 panel A revision",
            "ADMIN@example.org",
            requester=request,
        )
        self.assertEqual(result.status, "merged-integration-branch")
        self.assertIsNone(result.proposal_id)
        self.assertIsNotNone(result.pull_request)
        self.assertTrue(result.pull_request.merged)
        self.assertEqual(result.pull_request.merge_commit_sha, "6" * 40)
        pull_payload = next(
            payload for method, endpoint, payload in calls if endpoint == "/pulls"
        )
        self.assertFalse(pull_payload["draft"])
        self.assertTrue(
            any(method == "PUT" and endpoint == "/pulls/23/merge" for method, endpoint, _ in calls)
        )
        self.assertFalse(self.queue_root.exists())

    def test_admin_cannot_publish_a_new_file(self) -> None:
        target = self.session / "workspace" / "figures/figure-01/uploaded-notes.txt"
        target.write_text("not reviewed\n", encoding="utf-8")
        calls: list[tuple[str, str, dict | None]] = []
        with self.assertRaisesRegex(ProposalError, "unreviewed public path"):
            self.queue.submit(
                self.session,
                "figure-01",
                None,
                "Apply Figure 01 revision",
                "admin@example.org",
                requester=lambda method, endpoint, payload: calls.append(
                    (method, endpoint, payload)
                ),
            )
        self.assertEqual(calls, [])

    def test_failed_admin_merge_leaves_the_pr_for_review(self) -> None:
        calls: list[tuple[str, str, dict | None]] = []

        def request(method: str, endpoint: str, payload: dict | None) -> dict:
            calls.append((method, endpoint, payload))
            if endpoint.startswith("/git/ref/"):
                return {"object": {"sha": BASE_COMMIT}}
            if method == "GET" and endpoint == f"/git/commits/{BASE_COMMIT}":
                return {"tree": {"sha": BASE_TREE}}
            if endpoint == "/git/blobs":
                return {"sha": "3" * 40}
            if endpoint == "/git/trees":
                return {"sha": "4" * 40}
            if method == "POST" and endpoint == "/git/commits":
                return {"sha": "5" * 40}
            if endpoint == "/git/refs":
                return {"ref": payload["ref"]}
            if endpoint == "/pulls":
                return {
                    "number": 24,
                    "html_url": "https://github.com/hyuntaechoi634/ai-data-center/pull/24",
                }
            if method == "PUT" and endpoint == "/pulls/24/merge":
                return {"merged": False, "sha": "", "message": "checks required"}
            self.fail(f"Unexpected endpoint {method} {endpoint}")

        with self.assertRaisesRegex(ProposalError, r"pull/24.*checks required"):
            self.queue.submit(
                self.session,
                "figure-01",
                None,
                "Apply Figure 01 revision",
                "admin@example.org",
                requester=request,
            )
        self.assertFalse(any(method == "DELETE" for method, _, _ in calls))


if __name__ == "__main__":
    unittest.main()
