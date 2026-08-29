from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PUBLIC_EXPORT_MANIFEST = "PUBLIC_EXPORT.json"
GITHUB_API = "https://api.github.com"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt"}
MAX_CHANGED_FILES = 40
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class ProposalError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProposalFile:
    workspace_path: str
    repository_path: str
    content: bytes | None


@dataclass(frozen=True)
class ProposalResult:
    number: int
    url: str
    branch: str


@dataclass(frozen=True)
class PublicExportManifest:
    repository: str
    base_branch: str
    base_commit: str
    repository_root: str
    allowed_roots: tuple[Path, ...]
    baseline_sha256: dict[str, str]

    @classmethod
    def load(cls, baseline: Path) -> "PublicExportManifest":
        path = baseline / PUBLIC_EXPORT_MANIFEST
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 512 * 1024:
            raise ProposalError("The final public figure export is not ready")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProposalError("The public figure export manifest is invalid") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ProposalError("The public figure export manifest is invalid")
        if payload.get("status") != "public-ready":
            raise ProposalError("The final public figure export is not ready")

        repository = str(payload.get("repository", ""))
        base_branch = str(payload.get("base_branch", ""))
        base_commit = str(payload.get("base_commit", ""))
        repository_root = str(payload.get("repository_root", "")).strip("/")
        if not REPOSITORY.fullmatch(repository):
            raise ProposalError("The public figure repository is invalid")
        if not _valid_branch(base_branch) or not COMMIT.fullmatch(base_commit):
            raise ProposalError("The public figure branch is invalid")
        root_path = _safe_relative(repository_root)
        if not root_path.parts:
            raise ProposalError("The public figure repository root is invalid")

        raw_roots = payload.get("allowed_roots")
        if not isinstance(raw_roots, list) or not raw_roots:
            raise ProposalError("The public figure export has no allowed code roots")
        allowed_roots: list[Path] = []
        for raw_root in raw_roots:
            root = _safe_relative(str(raw_root))
            if root.parts[:1] != ("figures",) or len(root.parts) < 2:
                raise ProposalError("The public figure export contains an invalid code root")
            allowed_roots.append(root)

        raw_hashes = payload.get("baseline_sha256")
        if not isinstance(raw_hashes, dict) or not raw_hashes:
            raise ProposalError("The public figure export has no baseline hashes")
        hashes: dict[str, str] = {}
        for raw_path, raw_hash in raw_hashes.items():
            relative = _safe_relative(str(raw_path))
            digest = str(raw_hash)
            if not _under_any(relative, tuple(allowed_roots)) or not SHA256.fullmatch(digest):
                raise ProposalError("The public figure export contains an invalid baseline hash")
            hashes[relative.as_posix()] = digest

        return cls(
            repository=repository,
            base_branch=base_branch,
            base_commit=base_commit,
            repository_root=root_path.as_posix(),
            allowed_roots=tuple(allowed_roots),
            baseline_sha256=hashes,
        )


def _safe_relative(raw: str) -> Path:
    path = Path(raw.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ProposalError("The public figure export contains an unsafe path")
    return path


def _under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _under_any(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(_under(path, root) for root in roots)


def _valid_branch(value: str) -> bool:
    return bool(
        BRANCH.fullmatch(value)
        and not value.endswith(("/", "."))
        and "//" not in value
        and ".." not in value
        and "@{" not in value
    )


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _iter_text_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ProposalError("The revision contains a symbolic link")
        if path.is_file() and path.suffix.lower() in SAFE_TEXT_SUFFIXES:
            yield path


def _validate_public_text(path: Path, data: bytes) -> None:
    if path.suffix.lower() not in SAFE_TEXT_SUFFIXES:
        raise ProposalError(f"{path.as_posix()} is not an allowed public code file")
    if len(data) > MAX_FILE_BYTES:
        raise ProposalError(f"{path.as_posix()} is too large for a pull request")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProposalError(f"{path.as_posix()} is not UTF-8 text") from exc
    if "\x00" in text or any(len(line) > 20000 for line in text.splitlines()):
        raise ProposalError(f"{path.as_posix()} contains unsafe text")
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise ProposalError(f"{path.as_posix()} appears to contain a credential")


def collect_proposal_files(
    baseline: Path,
    workspace: Path,
    figure_id: str,
    manifest: PublicExportManifest,
) -> list[ProposalFile]:
    figure_root = Path("figures") / figure_id
    roots = tuple(
        root
        for root in manifest.allowed_roots
        if root == figure_root or root == Path("figures/helpers")
    )
    if figure_root not in roots:
        raise ProposalError("The selected figure is not in the public export")

    baseline_files: dict[str, Path] = {}
    workspace_files: dict[str, Path] = {}
    for root in roots:
        for path in _iter_text_files(baseline / root):
            relative = path.relative_to(baseline)
            baseline_files[relative.as_posix()] = path
        for path in _iter_text_files(workspace / root):
            relative = path.relative_to(workspace)
            workspace_files[relative.as_posix()] = path

    for relative, path in baseline_files.items():
        expected = manifest.baseline_sha256.get(relative)
        if expected is None or _hash(path) != expected:
            raise ProposalError("The session baseline does not match the reviewed public export")
    unexpected_hashes = {
        path for path in manifest.baseline_sha256 if _under_any(Path(path), roots)
    } - set(baseline_files)
    if unexpected_hashes:
        raise ProposalError("The session baseline is incomplete")

    changed: list[ProposalFile] = []
    for relative in sorted(set(baseline_files) | set(workspace_files)):
        before = baseline_files.get(relative)
        after = workspace_files.get(relative)
        before_bytes = before.read_bytes() if before else None
        after_bytes = after.read_bytes() if after else None
        if before_bytes == after_bytes:
            continue
        relative_path = Path(relative)
        if after_bytes is not None:
            _validate_public_text(relative_path, after_bytes)
        repository_path = (
            Path(manifest.repository_root) / relative_path
        ).as_posix()
        changed.append(
            ProposalFile(
                workspace_path=relative,
                repository_path=repository_path,
                content=after_bytes,
            )
        )

    if not changed:
        raise ProposalError("There are no public code or caption changes to propose")
    if len(changed) > MAX_CHANGED_FILES:
        raise ProposalError("The revision changes too many files for one pull request")
    total = sum(len(item.content or b"") for item in changed)
    if total > MAX_TOTAL_BYTES:
        raise ProposalError("The public revision is too large for one pull request")
    return changed


class GitHubClient:
    def __init__(
        self,
        repository: str,
        token: str,
        requester: Callable[[str, str, dict | None], dict] | None = None,
    ):
        if not REPOSITORY.fullmatch(repository):
            raise ProposalError("The GitHub repository is invalid")
        self.repository = repository
        self.token = token
        self.requester = requester or self._request

    def _request(self, method: str, endpoint: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{GITHUB_API}/repos/{self.repository}{endpoint}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "ai-data-center-figure-studio",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=25) as response:
                raw = response.read(2 * 1024 * 1024)
        except HTTPError as exc:
            raw = exc.read(8192)
            try:
                message = str(json.loads(raw).get("message", "request rejected"))
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                message = "request rejected"
            raise ProposalError(f"GitHub rejected the proposal with HTTP {exc.code}: {message}") from exc
        except (OSError, URLError) as exc:
            raise ProposalError("GitHub could not be reached") from exc
        if not raw:
            return {}
        try:
            result = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProposalError("GitHub returned an invalid response") from exc
        if not isinstance(result, dict):
            raise ProposalError("GitHub returned an invalid response")
        return result

    def create_draft_pull_request(
        self,
        manifest: PublicExportManifest,
        files: list[ProposalFile],
        title: str,
        figure_id: str,
        panel_id: str | None,
    ) -> ProposalResult:
        encoded_ref = quote(f"heads/{manifest.base_branch}", safe="/")
        base_ref = self.requester("GET", f"/git/ref/{encoded_ref}", None)
        base_commit = str(base_ref.get("object", {}).get("sha", ""))
        if base_commit != manifest.base_commit:
            raise ProposalError(
                "The public figure branch changed after this session began. Refresh the default figure"
            )
        commit = self.requester("GET", f"/git/commits/{base_commit}", None)
        base_tree = str(commit.get("tree", {}).get("sha", ""))
        if not COMMIT.fullmatch(base_tree):
            raise ProposalError("GitHub did not return the expected base tree")

        tree: list[dict] = []
        for item in files:
            if item.content is None:
                tree.append(
                    {"path": item.repository_path, "mode": "100644", "type": "blob", "sha": None}
                )
                continue
            blob = self.requester(
                "POST",
                "/git/blobs",
                {
                    "content": base64.b64encode(item.content).decode("ascii"),
                    "encoding": "base64",
                },
            )
            blob_sha = str(blob.get("sha", ""))
            if not COMMIT.fullmatch(blob_sha):
                raise ProposalError("GitHub did not create the expected file blob")
            tree.append(
                {
                    "path": item.repository_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                }
            )
        created_tree = self.requester(
            "POST", "/git/trees", {"base_tree": base_tree, "tree": tree}
        )
        tree_sha = str(created_tree.get("sha", ""))
        if not COMMIT.fullmatch(tree_sha):
            raise ProposalError("GitHub did not create the expected proposal tree")

        label = figure_id.replace("figure-", "Figure ")
        scope = f" panel {panel_id.upper()}" if panel_id else ""
        created_commit = self.requester(
            "POST",
            "/git/commits",
            {
                "message": f"Propose {label}{scope} revision",
                "tree": tree_sha,
                "parents": [base_commit],
            },
        )
        commit_sha = str(created_commit.get("sha", ""))
        if not COMMIT.fullmatch(commit_sha):
            raise ProposalError("GitHub did not create the expected proposal commit")

        suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        proposal_branch = f"{os.environ.get('FIGURE_STUDIO_GITHUB_PROPOSAL_PREFIX', 'cht/figure-proposal').rstrip('/')}/{figure_id}-{suffix}-{secrets.token_hex(3)}"
        if not _valid_branch(proposal_branch) or proposal_branch.startswith(
            manifest.base_branch.rstrip("/") + "/"
        ):
            raise ProposalError("The proposal branch prefix is invalid")
        self.requester(
            "POST",
            "/git/refs",
            {"ref": f"refs/heads/{proposal_branch}", "sha": commit_sha},
        )
        changed_paths = "\n".join(
            f"- `{item.repository_path}`" for item in files
        )
        body = (
            "Figure Studio generated this public code proposal from an authenticated editing "
            "session. Data tables, uploads, rendered outputs, and private source material are "
            "not included.\n\n"
            f"Figure: `{figure_id}`\n\n"
            f"Scope: `{panel_id or 'whole figure'}`\n\n"
            "Changed public files:\n\n"
            f"{changed_paths}\n\n"
            "This is a Draft PR. Review the code and rerender against the controlled source "
            "package before merging."
        )
        pull = self.requester(
            "POST",
            "/pulls",
            {
                "title": title,
                "head": proposal_branch,
                "base": manifest.base_branch,
                "body": body,
                "draft": True,
                "maintainer_can_modify": True,
            },
        )
        number = pull.get("number")
        url = str(pull.get("html_url", ""))
        if not isinstance(number, int) or not url.startswith("https://github.com/"):
            raise ProposalError("GitHub created the branch but did not return a pull request")
        return ProposalResult(number=number, url=url, branch=proposal_branch)


class GitHubProposalPublisher:
    def __init__(self, template: Path, require_cloudflare_access: bool):
        self.template = template.resolve()
        self.require_cloudflare_access = require_cloudflare_access
        self.repository = os.environ.get("FIGURE_STUDIO_GITHUB_REPOSITORY", "").strip()
        self.base_branch = os.environ.get(
            "FIGURE_STUDIO_GITHUB_BASE_BRANCH", "cht/proj/figure-studio"
        ).strip()
        raw_token = os.environ.get("FIGURE_STUDIO_GITHUB_TOKEN_FILE", "").strip()
        candidate = Path(raw_token).expanduser() if raw_token else None
        self.token_file = candidate if candidate and candidate.is_absolute() else None

    def _token(self) -> str:
        path = self.token_file
        if path is None:
            raise ProposalError("GitHub credentials are not configured")
        descriptor = None
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or details.st_mode & 0o077
                or details.st_size < 20
                or details.st_size > 4096
            ):
                raise ProposalError("GitHub credentials are not configured safely")
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                descriptor = None
                token = handle.read(4097).strip()
        except ProposalError:
            raise
        except (OSError, UnicodeDecodeError) as exc:
            raise ProposalError("GitHub credentials are not configured") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if not re.fullmatch(r"[A-Za-z0-9_=-]{20,4096}", token):
            raise ProposalError("GitHub credentials are invalid")
        return token

    def _manifest(self, baseline: Path | None = None) -> PublicExportManifest:
        manifest = PublicExportManifest.load(baseline or self.template)
        if self.repository and manifest.repository != self.repository:
            raise ProposalError("The configured repository does not match the public export")
        if manifest.base_branch != self.base_branch:
            raise ProposalError("The configured branch does not match the public export")
        return manifest

    def configuration(self) -> dict:
        result = {
            "available": False,
            "repository": self.repository,
            "base_branch": self.base_branch,
            "public": True,
            "message": "Pull request publishing is not configured",
        }
        if not self.require_cloudflare_access:
            result["message"] = "Pull requests require authenticated collaborator access"
            return result
        if not REPOSITORY.fullmatch(self.repository) or not _valid_branch(self.base_branch):
            return result
        try:
            self._manifest()
            self._token()
        except ProposalError as exc:
            result["message"] = str(exc)
            return result
        result["available"] = True
        result["message"] = "Creates a public Draft PR containing reviewed code paths only"
        return result

    def publish(
        self,
        session_dir: Path,
        figure_id: str,
        panel_id: str | None,
        title: str,
        requester: Callable[[str, str, dict | None], dict] | None = None,
    ) -> ProposalResult:
        if not self.require_cloudflare_access:
            raise ProposalError("Pull requests require authenticated collaborator access")
        normalized_title = " ".join(title.split())
        if not normalized_title or len(normalized_title) > 120:
            raise ProposalError("The pull request title is invalid")
        baseline = session_dir / "baseline"
        workspace = session_dir / "workspace"
        manifest = self._manifest(baseline)
        files = collect_proposal_files(baseline, workspace, figure_id, manifest)
        client = GitHubClient(manifest.repository, self._token(), requester=requester)
        return client.create_draft_pull_request(
            manifest, files, normalized_title, figure_id, panel_id
        )
