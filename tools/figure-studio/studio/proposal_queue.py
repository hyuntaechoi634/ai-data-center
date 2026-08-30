from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import tempfile

from .github_pr import (
    PUBLIC_EXPORT_MANIFEST,
    GitHubClient,
    ProposalError,
    ProposalFile,
    ProposalResult,
    PublicExportManifest,
    _validate_public_text,
    collect_proposal_files,
    read_private_token_file,
)


PROPOSAL_ID = re.compile(r"^proposal-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$")
EMAIL = re.compile(r"^[^\s@]{1,128}@[^\s@]{1,190}$")
MAX_BUNDLE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class QueuedProposal:
    proposal_id: str | None
    status: str
    changed_files: int
    pull_request: ProposalResult | None = None


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _write_private_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _secure_directory(path: Path, create: bool = False) -> Path:
    if not path.is_absolute():
        raise ProposalError("The proposal review queue must use an absolute path")
    if create and not path.exists():
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.chmod(0o700)
    try:
        details = path.lstat()
    except OSError as exc:
        raise ProposalError("The proposal review queue is unavailable") from exc
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_mode & 0o077
    ):
        raise ProposalError("The proposal review queue is not configured safely")
    return path


class ProposalQueue:
    def __init__(
        self,
        template: Path,
        require_cloudflare_access: bool,
        allowed_emails: set[str] | None = None,
    ):
        self.template = template.resolve()
        self.require_cloudflare_access = require_cloudflare_access
        self.allowed_emails = {
            email.strip().lower() for email in (allowed_emails or set())
        }
        configured = os.environ.get("FIGURE_STUDIO_PROPOSAL_QUEUE_ROOT", "").strip()
        candidate = Path(configured).expanduser() if configured else None
        self.queue_root = candidate if candidate and candidate.is_absolute() else None
        self.repository = os.environ.get("FIGURE_STUDIO_GITHUB_REPOSITORY", "").strip()
        self.base_branch = os.environ.get(
            "FIGURE_STUDIO_GITHUB_BASE_BRANCH", "cht/proj/figure-studio"
        ).strip()
        raw_admins = os.environ.get("FIGURE_STUDIO_ADMIN_EMAILS", "")
        self.admin_emails = {
            email.strip().lower() for email in raw_admins.split(",") if email.strip()
        }
        if any(not EMAIL.fullmatch(email) for email in self.admin_emails):
            raise ProposalError("The Figure Studio admin email list is invalid")
        if self.admin_emails - self.allowed_emails:
            raise ProposalError(
                "Every Figure Studio admin must also be in the collaborator allowlist"
            )
        raw_token = os.environ.get("FIGURE_STUDIO_GITHUB_TOKEN_FILE", "").strip()
        token_candidate = Path(raw_token).expanduser() if raw_token else None
        self.github_token_file = (
            token_candidate
            if token_candidate and token_candidate.is_absolute()
            else None
        )

    def _manifest_root(self, baseline: Path | None = None) -> Path:
        if baseline is None:
            return self.template
        manifest_path = baseline / PUBLIC_EXPORT_MANIFEST
        try:
            manifest_path.lstat()
        except FileNotFoundError:
            return self.template
        except OSError:
            return baseline
        return baseline

    def _manifest(self, baseline: Path | None = None) -> PublicExportManifest:
        manifest = PublicExportManifest.load(self._manifest_root(baseline))
        if self.repository and manifest.repository != self.repository:
            raise ProposalError("The configured repository does not match the public export")
        if manifest.base_branch != self.base_branch:
            raise ProposalError("The configured branch does not match the public export")
        return manifest

    def _root(self, create: bool = False) -> Path:
        if self.queue_root is None:
            raise ProposalError("The local proposal review queue is not configured")
        return _secure_directory(self.queue_root, create=create)

    def _github_token(self) -> str:
        return read_private_token_file(
            self.github_token_file,
            "GitHub owner-admin credentials",
        )

    def is_admin(self, submitter: str) -> bool:
        return submitter.strip().lower() in self.admin_emails

    def configuration(self, submitter: str = "") -> dict:
        normalized_submitter = submitter.strip().lower()
        admin_mode = self.is_admin(normalized_submitter)
        result = {
            "available": False,
            "repository": self.repository,
            "base_branch": self.base_branch,
            "public": admin_mode,
            "mode": (
                "owner-admin-immediate-merge"
                if admin_mode
                else "owner-review-queue"
            ),
            "message": (
                "GitHub owner-admin integration is not configured"
                if admin_mode
                else "The local proposal review queue is not configured"
            ),
        }
        if not self.require_cloudflare_access:
            result["message"] = "Proposals require authenticated collaborator access"
            return result
        try:
            manifest = self._manifest()
            if admin_mode:
                self._github_token()
            else:
                self._root(create=True)
        except ProposalError as exc:
            result["message"] = str(exc)
            return result
        result["available"] = True
        result["repository"] = manifest.repository
        if admin_mode:
            result["message"] = (
                "Creates and immediately merges an allowlisted PR into the integration branch"
            )
        else:
            result["message"] = (
                "Submits a private local proposal for owner review before any GitHub branch exists"
            )
        return result

    def submit(
        self,
        session_dir: Path,
        figure_id: str,
        panel_id: str | None,
        title: str,
        submitter: str,
        requester=None,
    ) -> QueuedProposal:
        if not self.require_cloudflare_access:
            raise ProposalError("Proposals require authenticated collaborator access")
        normalized_title = " ".join(title.split())
        if not normalized_title or len(normalized_title) > 120:
            raise ProposalError("The proposal title is invalid")
        normalized_submitter = submitter.strip().lower()
        if not normalized_submitter or len(normalized_submitter) > 320:
            raise ProposalError("The proposal submitter is invalid")

        baseline = session_dir / "baseline"
        workspace = session_dir / "workspace"
        manifest = self._manifest(baseline)
        files = collect_proposal_files(baseline, workspace, figure_id, manifest)
        if self.is_admin(normalized_submitter):
            token = self._github_token()
            client = GitHubClient(manifest.repository, token, requester=requester)
            result = client.create_and_merge_pull_request(
                manifest,
                files,
                normalized_title,
                figure_id,
                panel_id,
            )
            return QueuedProposal(
                proposal_id=None,
                status="merged-integration-branch",
                changed_files=len(files),
                pull_request=result,
            )

        queue_root = self._root(create=True)
        proposal_id = (
            datetime.now(timezone.utc).strftime("proposal-%Y%m%dT%H%M%SZ-")
            + secrets.token_hex(4)
        )
        destination = queue_root / proposal_id
        temporary = Path(tempfile.mkdtemp(prefix=".proposal-", dir=queue_root))
        temporary.chmod(0o700)
        try:
            content_root = temporary / "files"
            content_root.mkdir(mode=0o700)
            records: list[dict] = []
            for index, item in enumerate(files):
                record = {
                    "workspace_path": item.workspace_path,
                    "repository_path": item.repository_path,
                    "action": "delete" if item.content is None else "replace",
                    "sha256": None,
                    "content_file": None,
                }
                if item.content is not None:
                    name = f"{index:03d}.txt"
                    target = content_root / name
                    descriptor = os.open(
                        target,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )
                    try:
                        with os.fdopen(descriptor, "wb") as handle:
                            descriptor = -1
                            handle.write(item.content)
                    finally:
                        if descriptor >= 0:
                            os.close(descriptor)
                    record["sha256"] = _sha256_bytes(item.content)
                    record["content_file"] = f"files/{name}"
                records.append(record)

            manifest_path = self._manifest_root(baseline) / PUBLIC_EXPORT_MANIFEST
            payload = {
                "schema_version": 1,
                "proposal_id": proposal_id,
                "status": "pending-owner-review",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "submitter": normalized_submitter,
                "title": normalized_title,
                "figure_id": figure_id,
                "panel_id": panel_id,
                "repository": manifest.repository,
                "base_branch": manifest.base_branch,
                "base_commit": manifest.base_commit,
                "public_export_sha256": _sha256_file(manifest_path),
                "files": records,
            }
            _write_private_json(temporary / "proposal.json", payload)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
        return QueuedProposal(
            proposal_id=proposal_id,
            status="pending-owner-review",
            changed_files=len(files),
        )

    def load_pending(
        self, proposal_id: str
    ) -> tuple[dict, PublicExportManifest, list[ProposalFile]]:
        if not PROPOSAL_ID.fullmatch(proposal_id):
            raise ProposalError("The proposal identifier is invalid")
        root = self._root()
        bundle = _secure_directory(root / proposal_id)
        metadata_path = bundle / "proposal.json"
        if metadata_path.is_symlink() or not metadata_path.is_file():
            raise ProposalError("The proposal bundle is invalid")
        if metadata_path.stat().st_size > MAX_BUNDLE_BYTES:
            raise ProposalError("The proposal bundle is too large")
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProposalError("The proposal bundle is invalid") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or payload.get("proposal_id") != proposal_id
            or payload.get("status") != "pending-owner-review"
        ):
            raise ProposalError("The proposal is not pending owner review")

        manifest = self._manifest()
        manifest_path = self.template / PUBLIC_EXPORT_MANIFEST
        if (
            payload.get("repository") != manifest.repository
            or payload.get("base_branch") != manifest.base_branch
            or payload.get("base_commit") != manifest.base_commit
            or payload.get("public_export_sha256") != _sha256_file(manifest_path)
        ):
            raise ProposalError("The proposal does not match the current public export")

        raw_files = payload.get("files")
        if not isinstance(raw_files, list) or not raw_files or len(raw_files) > 40:
            raise ProposalError("The proposal file list is invalid")
        files: list[ProposalFile] = []
        total = 0
        for record in raw_files:
            if not isinstance(record, dict):
                raise ProposalError("The proposal file list is invalid")
            workspace_path = str(record.get("workspace_path", ""))
            repository_path = str(record.get("repository_path", ""))
            if workspace_path not in manifest.allowed_files:
                raise ProposalError("The proposal contains an unreviewed path")
            expected_repository_path = (
                Path(manifest.repository_root) / workspace_path
            ).as_posix()
            if repository_path != expected_repository_path:
                raise ProposalError("The proposal repository path is invalid")
            action = record.get("action")
            content: bytes | None
            if action == "delete":
                if record.get("content_file") is not None or record.get("sha256") is not None:
                    raise ProposalError("The proposal deletion record is invalid")
                content = None
            elif action == "replace":
                relative_content = str(record.get("content_file", ""))
                if not re.fullmatch(r"files/[0-9]{3}\.txt", relative_content):
                    raise ProposalError("The proposal content path is invalid")
                content_path = bundle / relative_content
                details = content_path.lstat()
                if (
                    not stat.S_ISREG(details.st_mode)
                    or stat.S_ISLNK(details.st_mode)
                    or details.st_uid != os.getuid()
                    or details.st_mode & 0o077
                ):
                    raise ProposalError("The proposal content file is unsafe")
                content = content_path.read_bytes()
                if _sha256_bytes(content) != record.get("sha256"):
                    raise ProposalError("The proposal content hash does not match")
                _validate_public_text(Path(workspace_path), content)
                total += len(content)
            else:
                raise ProposalError("The proposal action is invalid")
            files.append(
                ProposalFile(
                    workspace_path=workspace_path,
                    repository_path=repository_path,
                    content=content,
                )
            )
        if total > MAX_BUNDLE_BYTES:
            raise ProposalError("The proposal bundle is too large")
        return payload, manifest, files

    def publish_pending(
        self,
        proposal_id: str,
        token_file: Path,
        requester=None,
    ) -> ProposalResult:
        payload, manifest, files = self.load_pending(proposal_id)
        token = read_private_token_file(token_file, "GitHub credentials")
        client = GitHubClient(manifest.repository, token, requester=requester)
        result = client.create_draft_pull_request(
            manifest,
            files,
            str(payload["title"]),
            str(payload["figure_id"]),
            str(payload["panel_id"]) if payload.get("panel_id") else None,
        )
        bundle = self._root() / proposal_id
        payload["status"] = "published-draft-pr"
        payload["published_at"] = datetime.now(timezone.utc).isoformat()
        payload["pull_request"] = {
            "number": result.number,
            "url": result.url,
            "branch": result.branch,
        }
        replacement = bundle / ".proposal.json.new"
        _write_private_json(replacement, payload)
        os.replace(replacement, bundle / "proposal.json")
        return result
