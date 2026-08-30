from __future__ import annotations

import difflib
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import tempfile
import threading
from datetime import datetime, timedelta, timezone
import zipfile

from .catalog import DEFAULT_FIGURE_ID, FIGURE_PROJECTS, project_manifest
from .panels import (
    PanelError,
    ensure_panel_previews,
    panel_catalog,
    panel_data_sources,
    validate_panel_id,
)


SESSION_ID = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
SAFE_NAME = re.compile(r"[^A-Za-z0-9._() +@-]+")
PROJECT_IGNORE = shutil.ignore_patterns(
    ".matplotlib-cache", "__pycache__", "*.pyc", ".DS_Store", ".revision.json", "defaults"
)
PROTECTED_DEFAULTS = (
    Path("results/derived/figure-data"),
    Path("figures/source-data"),
)
MAX_REVISIONS = 16
MAX_UPLOAD_FILE = 25 * 1024 * 1024
MAX_UPLOAD_TOTAL = 100 * 1024 * 1024
MAX_UPLOAD_FILES = 24
MAX_SESSION_BYTES = 750 * 1024 * 1024
MAX_SESSION_FILES = 5000
MAX_WORKSPACE_BYTES = 300 * 1024 * 1024
MAX_WORKSPACE_FILES = 2000
MAX_PROJECT_JSON = 1024 * 1024
RASTER_PREVIEWS = {"png", "jpg", "jpeg", "webp", "gif"}
REFERENCE_TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
}
TEMPLATE_REVISION_PATHS = (
    Path("defaults"),
    Path("results/derived/figure-data"),
    Path("figures/source-data"),
    Path("figures/figure-01"),
    Path("figures/figure-02"),
    Path("figures/figure-03"),
    Path("figures/figure-04"),
    Path("figures/figure-05"),
    Path("figures/figure-06"),
    Path("figures/helpers"),
    Path("AGENTS.md"),
    Path("README.md"),
    Path("render.py"),
    Path("requirements.txt"),
)


class SessionError(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_regular_files(base: Path):
    if not base.exists():
        return
    try:
        base_mode = base.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISREG(base_mode):
        yield base
        return
    for current, directories, files in os.walk(base, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories if not (current_path / name).is_symlink()
        )
        for name in sorted(files):
            path = current_path / name
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISREG(mode):
                yield path


def tree_fingerprint(root: Path, paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        target = root / relative
        for path in iter_regular_files(target):
            rel = path.relative_to(root).as_posix()
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            digest.update(hash_file(path).encode("ascii"))
            digest.update(b"\0")
    return digest.hexdigest()


def directory_fingerprint(base: Path) -> str:
    digest = hashlib.sha256()
    if not base.exists():
        return digest.hexdigest()
    for path in iter_regular_files(base):
        rel = path.relative_to(base).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hash_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = set(PROJECT_IGNORE(directory, names))
    base = Path(directory)
    for name in names:
        path = base / name
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            ignored.add(name)
            continue
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            ignored.add(name)
    return ignored


def copy_project(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=_copy_ignore)


def remove_symlinks(base: Path) -> list[str]:
    removed: list[str] = []
    if not base.exists():
        return removed
    for current, directories, files in os.walk(base, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in list(directories):
            path = current_path / name
            if path.is_symlink():
                path.unlink()
                directories.remove(name)
                removed.append(path.relative_to(base).as_posix())
        for name in files:
            path = current_path / name
            if path.is_symlink():
                path.unlink()
                removed.append(path.relative_to(base).as_posix())
    return removed


def remove_unsafe_nodes(base: Path) -> list[str]:
    """Remove links, FIFOs, sockets and device nodes from a generated project."""
    removed: list[str] = []
    if not base.exists():
        return removed
    for current, directories, files in os.walk(base, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in list(directories):
            path = current_path / name
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                directories.remove(name)
                continue
            if not stat.S_ISDIR(mode):
                path.unlink(missing_ok=True)
                directories.remove(name)
                removed.append(path.relative_to(base).as_posix())
        for name in files:
            path = current_path / name
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                path.unlink(missing_ok=True)
                removed.append(path.relative_to(base).as_posix())
    return removed


def tree_usage(base: Path) -> tuple[int, int]:
    count = 0
    total = 0
    for path in iter_regular_files(base):
        count += 1
        total += path.lstat().st_size
    return count, total


def enforce_tree_quota(base: Path) -> tuple[int, int]:
    count, total = tree_usage(base)
    if count > MAX_SESSION_FILES:
        raise SessionError(f"A session may contain at most {MAX_SESSION_FILES} files")
    if total > MAX_SESSION_BYTES:
        raise SessionError("A session may use at most 750 MB")
    return count, total


def enforce_workspace_quota(base: Path) -> tuple[int, int]:
    count, total = tree_usage(base)
    if count > MAX_WORKSPACE_FILES:
        raise SessionError(f"A project may contain at most {MAX_WORKSPACE_FILES} files")
    if total > MAX_WORKSPACE_BYTES:
        raise SessionError("A project may use at most 300 MB")
    return count, total


def remove_local_path(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISDIR(mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def replace_project(source: Path, destination: Path) -> None:
    parent = destination.parent.resolve()
    if parent == Path("/") or destination.name not in {"baseline", "workspace"}:
        raise SessionError("Refusing to replace an unexpected workspace path")
    replacement = parent / f".{destination.name}-replacement-{secrets.token_hex(5)}"
    retired = parent / f".{destination.name}-retired-{secrets.token_hex(5)}"
    copy_project(source, replacement)
    if destination.exists():
        destination.rename(retired)
    replacement.rename(destination)
    if retired.exists() or retired.is_symlink():
        remove_local_path(retired)


def sanitize_filename(name: str) -> str:
    leaf = Path(name.replace("\\", "/")).name.strip()
    leaf = SAFE_NAME.sub("_", leaf)
    leaf = leaf.lstrip(".")
    if not leaf or leaf in {".", ".."}:
        raise SessionError("The uploaded filename is not valid")
    return leaf[:180]


class SessionStore:
    def __init__(self, template: Path, root: Path):
        self.template = template.resolve()
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        if not (self.template / "project.json").is_file():
            raise SessionError(f"Invalid template at {self.template}")
        self.template_revision = tree_fingerprint(
            self.template,
            TEMPLATE_REVISION_PATHS,
        )

    def lock(self, session_id: str) -> threading.RLock:
        self._validate_id(session_id)
        with self._locks_guard:
            return self._locks.setdefault(session_id, threading.RLock())

    def _validate_id(self, session_id: str) -> None:
        if not SESSION_ID.fullmatch(session_id):
            raise SessionError("Invalid session id")

    def session_dir(self, session_id: str) -> Path:
        self._validate_id(session_id)
        lexical = self.root / session_id
        if lexical.is_symlink():
            raise SessionError("Session not found")
        path = lexical.resolve()
        if path.parent != self.root:
            raise SessionError("Invalid session path")
        if not path.is_dir():
            raise SessionError("Session not found")
        path.chmod(0o700)
        return path

    def workspace(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "workspace"

    def _metadata_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.json"

    def load(self, session_id: str) -> dict:
        return json.loads(self._metadata_path(session_id).read_text(encoding="utf-8"))

    def save(self, session_id: str, metadata: dict) -> None:
        metadata["updated_at"] = utcnow()
        atomic_json(self._metadata_path(session_id), metadata)

    def assert_owner(self, session_id: str, owner: str) -> None:
        expected = str(self.load(session_id).get("owner", ""))
        if expected and expected != owner:
            raise SessionError("Session not found")

    def owner_session_count(self, owner: str) -> int:
        if not owner:
            return 0
        count = 0
        for location in self.root.iterdir():
            metadata_path = location / "session.json"
            if not location.is_dir() or location.is_symlink() or not metadata_path.is_file():
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if metadata.get("owner") == owner:
                count += 1
        return count

    def cleanup_expired(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        removed = 0
        for location in list(self.root.iterdir()):
            if not location.is_dir() or location.is_symlink():
                continue
            try:
                self._validate_id(location.name)
            except SessionError:
                continue
            metadata_path = location / "session.json"
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                updated = datetime.fromisoformat(str(metadata.get("updated_at", "")))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated >= cutoff:
                continue
            retired = self.root / f".expired-{location.name}-{secrets.token_hex(4)}"
            location.rename(retired)
            remove_local_path(retired)
            removed += 1
        return removed

    def _configure_project(self, root: Path, figure_id: str) -> None:
        try:
            manifest = project_manifest(figure_id)
        except ValueError as exc:
            raise SessionError("Unknown figure") from exc
        output = root / "outputs" / "current"
        if output.exists():
            remove_local_path(output)
        output.mkdir(parents=True, exist_ok=True)
        source = self.template / "defaults" / FIGURE_PROJECTS[figure_id]["default_image"]
        if not source.is_file() or source.is_symlink():
            raise SessionError(f"The default image for {figure_id} is unavailable")
        shutil.copy2(source, output / f"{manifest['output_stem']}.jpg")
        atomic_json(root / "project.json", manifest)

    def create(self, owner: str = "", figure_id: str = DEFAULT_FIGURE_ID) -> dict:
        if figure_id not in FIGURE_PROJECTS:
            raise SessionError("Unknown figure")
        session_id = secrets.token_urlsafe(12).replace("-", "a").replace("_", "b")
        location = self.root / session_id
        location.mkdir(parents=True, exist_ok=False, mode=0o700)
        location.chmod(0o700)
        copy_project(self.template, location / "baseline")
        copy_project(self.template, location / "workspace")
        self._configure_project(location / "baseline", figure_id)
        self._configure_project(location / "workspace", figure_id)
        (location / "baseline").chmod(0o700)
        (location / "workspace").chmod(0o700)
        (location / "revisions").mkdir(mode=0o700)
        (location / "upload-originals").mkdir(mode=0o700)
        (location / "exports").mkdir(mode=0o700)
        metadata = {
            "session_id": session_id,
            "owner": owner,
            "figure_id": figure_id,
            "created_at": utcnow(),
            "updated_at": utcnow(),
            "messages": [],
            "undo_stack": [],
            "redo_stack": [],
            "revision_counter": 0,
            "latest_agent_response": "",
            "latest_render_log": "",
            "latest_warnings": [],
            "active_uploads": [],
            "template_revision": self.template_revision,
        }
        atomic_json(location / "session.json", metadata)
        enforce_tree_quota(location)
        return self.state(session_id)

    def _refresh_untouched_session(
        self,
        location: Path,
        metadata: dict,
    ) -> tuple[dict, bool]:
        if metadata.get("template_revision") == self.template_revision:
            return metadata, False
        untouched = (
            not metadata.get("messages")
            and not metadata.get("undo_stack")
            and not metadata.get("redo_stack")
            and not metadata.get("active_uploads")
            and int(metadata.get("revision_counter", 0) or 0) == 0
        )
        if not untouched:
            return metadata, True
        figure_id = str(metadata.get("figure_id", ""))
        if figure_id not in FIGURE_PROJECTS:
            return metadata, True

        prepared = location / f".template-refresh-{secrets.token_hex(5)}"
        try:
            copy_project(self.template, prepared)
            self._configure_project(prepared, figure_id)
            replace_project(prepared, location / "baseline")
            replace_project(prepared, location / "workspace")
        finally:
            remove_local_path(prepared)
        for export in iter_regular_files(location / "exports"):
            export.unlink()
        metadata["template_revision"] = self.template_revision
        metadata["template_refreshed_at"] = utcnow()
        self.save(str(metadata["session_id"]), metadata)
        return self.load(str(metadata["session_id"])), False

    @staticmethod
    def _load_project(path: Path) -> dict:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_PROJECT_JSON:
            raise SessionError("The project manifest is missing or too large")
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SessionError("The project manifest is not valid JSON") from exc
        if not isinstance(project, dict):
            raise SessionError("The project manifest must be a JSON object")
        return project

    def _artifact_list(self, base: Path) -> list[dict]:
        artifacts: list[dict] = []
        if not base.exists():
            return artifacts
        for path in iter_regular_files(base):
            rel = path.relative_to(base).as_posix()
            suffix = path.suffix.lower().lstrip(".")
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            artifacts.append(
                {
                    "path": rel,
                    "name": path.name,
                    "extension": suffix,
                    "mime": mime,
                    "bytes": path.stat().st_size,
                    "sha256": hash_file(path),
                    "previewable": (
                        suffix in RASTER_PREVIEWS
                        and path.stat().st_size <= 50 * 1024 * 1024
                    ),
                }
            )
        return artifacts

    @staticmethod
    def _choose_preview(artifacts: list[dict], project: dict) -> str | None:
        priorities = project.get("preview_priority", ["png", "jpg", "svg"])
        for extension in priorities:
            for artifact in artifacts:
                if artifact["extension"] == extension and artifact["previewable"]:
                    return artifact["path"]
        for artifact in artifacts:
            if artifact["previewable"]:
                return artifact["path"]
        return None

    def state(self, session_id: str) -> dict:
        location = self.session_dir(session_id)
        enforce_tree_quota(location)
        workspace = location / "workspace"
        enforce_workspace_quota(workspace)
        baseline = location / "baseline"
        metadata = self.load(session_id)
        metadata, template_update_available = self._refresh_untouched_session(
            location,
            metadata,
        )
        workspace = location / "workspace"
        baseline = location / "baseline"
        project = self._load_project(workspace / "project.json")
        figure_id = str(
            metadata.get("figure_id")
            or project.get("figure_id")
            or ("figure-06" if project.get("project_id") == "figure-06-regional" else "")
        )
        if figure_id not in FIGURE_PROJECTS:
            raise SessionError("The session refers to an unknown figure")
        entrypoint = Path(str(project.get("entrypoint", "")))
        if entrypoint.is_absolute() or not entrypoint.parts or ".." in entrypoint.parts:
            raise SessionError("The project entrypoint is invalid")
        if entrypoint.parent != Path("figures") / figure_id:
            raise SessionError("The project entrypoint is outside the active figure directory")
        code_paths = (
            entrypoint.parent,
            Path("figures/helpers"),
            Path("render.py"),
            Path("project.json"),
            Path("requirements.txt"),
            Path("AGENTS.md"),
            Path("README.md"),
        )
        current = self._artifact_list(workspace / "outputs" / "current")
        default = self._artifact_list(baseline / "outputs" / "current")
        uploads = self._artifact_list(workspace / "uploads")
        code_is_default = tree_fingerprint(workspace, code_paths) == tree_fingerprint(
            baseline, code_paths
        )
        current_outputs_are_default = [
            (item["path"], item["bytes"], item["sha256"]) for item in current
        ] == [
            (item["path"], item["bytes"], item["sha256"]) for item in default
        ]
        has_current_revision = not code_is_default or not current_outputs_are_default
        if not has_current_revision and uploads:
            mode = "default_with_uploads"
        elif not has_current_revision:
            mode = "default"
        else:
            mode = "custom"
        panels = panel_catalog(figure_id)
        if panels:
            default_panels_available = False
            current_panels_available = False
            try:
                self.figure_output_path(session_id, "default")
                default_panels_available = True
            except SessionError:
                default_panels_available = False
            if has_current_revision:
                try:
                    self.figure_output_path(session_id, "current")
                    current_panels_available = True
                except SessionError:
                    current_panels_available = False
            for panel in panels:
                panel["default_available"] = default_panels_available
                panel["current_available"] = current_panels_available
        return {
            "session_id": session_id,
            "figure_id": figure_id,
            "project": project,
            "mode": mode,
            "code_is_default": code_is_default,
            "current_outputs_are_default": current_outputs_are_default,
            "has_current_revision": has_current_revision,
            "current_artifacts": current,
            "default_artifacts": default,
            "current_preview": self._choose_preview(current, project),
            "default_preview": self._choose_preview(default, project),
            "uploads": uploads,
            "messages": metadata.get("messages", []),
            "can_undo": bool(metadata.get("undo_stack")),
            "can_redo": bool(metadata.get("redo_stack")),
            "latest_agent_response": metadata.get("latest_agent_response", ""),
            "latest_render_log": metadata.get("latest_render_log", ""),
            "warnings": metadata.get("latest_warnings", []),
            "updated_at": metadata.get("updated_at"),
            "panels": panels,
            "template_update_available": template_update_available,
            "pull_requests": metadata.get("pull_requests", []),
        }

    def _snapshot_raw(self, session_id: str, label: str) -> str:
        location = self.session_dir(session_id)
        workspace = location / "workspace"
        workspace_count, workspace_bytes = enforce_workspace_quota(workspace)
        metadata = self.load(session_id)
        changed = False

        for export in iter_regular_files(location / "exports"):
            export.unlink()
            changed = True

        referenced = set(metadata.get("undo_stack", [])) | set(
            metadata.get("redo_stack", [])
        )
        revision_root = location / "revisions"
        candidates: list[str] = []
        for path in sorted(revision_root.iterdir()):
            if path.is_dir() and not path.is_symlink() and path.name not in referenced:
                candidates.append(path.name)
        candidates.extend(metadata.get("undo_stack", [])[:-1])
        candidates.extend(metadata.get("redo_stack", [])[:-1])

        def projected_over_quota() -> bool:
            count, total = tree_usage(location)
            return (
                count + workspace_count + 1 > MAX_SESSION_FILES
                or total + workspace_bytes + 4096 > MAX_SESSION_BYTES
            )

        for revision in dict.fromkeys(candidates):
            if not projected_over_quota():
                break
            target = revision_root / revision
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            metadata["undo_stack"] = [
                item for item in metadata.get("undo_stack", []) if item != revision
            ]
            metadata["redo_stack"] = [
                item for item in metadata.get("redo_stack", []) if item != revision
            ]
            changed = True

        if projected_over_quota():
            if changed:
                self.save(session_id, metadata)
            raise SessionError(
                "The current project is too large to save another revision. "
                "Remove large outputs or uploads first"
            )
        if changed:
            self.save(session_id, metadata)

        metadata["revision_counter"] += 1
        revision_id = f"rev-{metadata['revision_counter']:04d}"
        target = location / "revisions" / revision_id
        try:
            copy_project(workspace, target)
            atomic_json(
                target / ".revision.json",
                {
                    "revision_id": revision_id,
                    "label": label,
                    "created_at": utcnow(),
                    "active_uploads": metadata.get("active_uploads", []),
                },
            )
            enforce_tree_quota(location)
        except Exception:
            remove_local_path(target)
            raise
        self.save(session_id, metadata)
        return revision_id

    def snapshot(self, session_id: str, label: str) -> str:
        metadata = self.load(session_id)
        revision_id = self._snapshot_raw(session_id, label)
        metadata = self.load(session_id)
        metadata.setdefault("undo_stack", []).append(revision_id)
        metadata["redo_stack"] = []
        while len(metadata["undo_stack"]) > MAX_REVISIONS:
            expired = metadata["undo_stack"].pop(0)
            path = self.session_dir(session_id) / "revisions" / expired
            if path.is_dir():
                shutil.rmtree(path)
        self.save(session_id, metadata)
        return revision_id

    def restore_snapshot(
        self,
        session_id: str,
        revision_id: str,
        discard: bool = False,
    ) -> None:
        location = self.session_dir(session_id)
        target = location / "revisions" / revision_id
        revision_metadata_path = target / ".revision.json"
        if not target.is_dir() or target.is_symlink() or not revision_metadata_path.is_file():
            raise SessionError("The saved project version is unavailable")
        revision_metadata = json.loads(
            revision_metadata_path.read_text(encoding="utf-8")
        )
        replace_project(target, self.workspace(session_id))
        metadata = self.load(session_id)
        metadata["active_uploads"] = revision_metadata.get("active_uploads", [])
        metadata["undo_stack"] = [
            item for item in metadata.get("undo_stack", []) if item != revision_id
        ]
        metadata["redo_stack"] = [
            item for item in metadata.get("redo_stack", []) if item != revision_id
        ]
        if discard:
            remove_local_path(target)
        self.save(session_id, metadata)

    def undo(self, session_id: str) -> dict:
        metadata = self.load(session_id)
        stack = metadata.get("undo_stack", [])
        if not stack:
            raise SessionError("There is no earlier version to restore")
        current_id = self._snapshot_raw(session_id, "State before undo")
        metadata = self.load(session_id)
        target_id = metadata["undo_stack"].pop()
        target = self.session_dir(session_id) / "revisions" / target_id
        revision_metadata = json.loads(
            (target / ".revision.json").read_text(encoding="utf-8")
        )
        replace_project(target, self.workspace(session_id))
        metadata["active_uploads"] = revision_metadata.get("active_uploads", [])
        metadata.setdefault("redo_stack", []).append(current_id)
        metadata["latest_agent_response"] = "Restored the previous project version."
        metadata["latest_warnings"] = []
        self.save(session_id, metadata)
        return self.state(session_id)

    def redo(self, session_id: str) -> dict:
        metadata = self.load(session_id)
        stack = metadata.get("redo_stack", [])
        if not stack:
            raise SessionError("There is no later version to restore")
        current_id = self._snapshot_raw(session_id, "State before redo")
        metadata = self.load(session_id)
        target_id = metadata["redo_stack"].pop()
        target = self.session_dir(session_id) / "revisions" / target_id
        revision_metadata = json.loads(
            (target / ".revision.json").read_text(encoding="utf-8")
        )
        replace_project(target, self.workspace(session_id))
        metadata["active_uploads"] = revision_metadata.get("active_uploads", [])
        metadata.setdefault("undo_stack", []).append(current_id)
        metadata["latest_agent_response"] = "Restored the later project version."
        metadata["latest_warnings"] = []
        self.save(session_id, metadata)
        return self.state(session_id)

    def reset(self, session_id: str, keep_uploads: bool = True) -> dict:
        self.snapshot(session_id, "State before reset to default")
        location = self.session_dir(session_id)
        metadata = self.load(session_id)
        replace_project(location / "baseline", location / "workspace")
        if keep_uploads:
            originals = location / "upload-originals"
            uploads = location / "workspace" / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            for name in metadata.get("active_uploads", []):
                source = originals / name
                if source.is_file() and not source.is_symlink():
                    shutil.copy2(source, uploads / name)
        else:
            metadata["active_uploads"] = []
        metadata["latest_agent_response"] = "Restored the authors' default code and figure."
        metadata["latest_render_log"] = ""
        metadata["latest_warnings"] = []
        metadata.setdefault("messages", []).append(
            {"role": "system", "text": "The project was reset to the default version.", "at": utcnow()}
        )
        self.save(session_id, metadata)
        return self.state(session_id)

    def upload(self, session_id: str, files: list[tuple[str, bytes]]) -> dict:
        if not files:
            raise SessionError("No files were provided")
        active_count = len(self.load(session_id).get("active_uploads", []))
        if active_count + len(files) > MAX_UPLOAD_FILES:
            raise SessionError(f"A session may contain at most {MAX_UPLOAD_FILES} uploads")
        total_existing = sum(
            path.stat().st_size
            for path in iter_regular_files(self.session_dir(session_id) / "upload-originals")
        )
        total_new = sum(len(content) for _, content in files)
        if total_existing + total_new > MAX_UPLOAD_TOTAL:
            raise SessionError("The session upload limit is 100 MB")
        for name, content in files:
            if len(content) > MAX_UPLOAD_FILE:
                raise SessionError(f"{name} exceeds the 25 MB per-file limit")

        self.snapshot(session_id, "State before file upload")
        location = self.session_dir(session_id)
        originals = location / "upload-originals"
        uploads = location / "workspace" / "uploads"
        originals.mkdir(parents=True, exist_ok=True)
        uploads.mkdir(parents=True, exist_ok=True)
        metadata = self.load(session_id)
        active = list(metadata.get("active_uploads", []))
        for raw_name, content in files:
            name = sanitize_filename(raw_name)
            stem = Path(name).stem
            suffix = Path(name).suffix
            candidate = name
            counter = 2
            while (originals / candidate).exists():
                candidate = f"{stem}-{counter}{suffix}"
                counter += 1
            name = candidate
            (originals / name).write_bytes(content)
            (uploads / name).write_bytes(content)
            (originals / name).chmod(0o600)
            (uploads / name).chmod(0o600)
            active.append(name)
        metadata["active_uploads"] = active
        metadata["latest_agent_response"] = f"Added {len(files)} source file(s) to the session."
        metadata["latest_warnings"] = []
        self.save(session_id, metadata)
        enforce_tree_quota(location)
        return self.state(session_id)

    def remove_upload(self, session_id: str, raw_name: str) -> dict:
        name = sanitize_filename(raw_name)
        self.snapshot(session_id, f"State before removing {name}")
        location = self.session_dir(session_id)
        metadata = self.load(session_id)
        active = list(metadata.get("active_uploads", []))
        if name not in active:
            raise SessionError("Upload not found")
        target = location / "workspace" / "uploads" / name
        if target.is_file() and not target.is_symlink():
            target.unlink()
        active.remove(name)
        metadata["active_uploads"] = active
        self.save(session_id, metadata)
        return self.state(session_id)

    def verify_and_restore_sources(self, session_id: str) -> list[str]:
        location = self.session_dir(session_id)
        workspace = location / "workspace"
        baseline = location / "baseline"
        warnings: list[str] = []
        removed = remove_unsafe_nodes(workspace)
        if removed:
            warnings.append(
                f"Removed {len(removed)} unsafe link or special file node(s) from the generated project."
            )
        metadata = self.load(session_id)
        legacy_session = not metadata.get("figure_id")
        expected_figure = str(metadata.get("figure_id", ""))
        if legacy_session:
            baseline_project = self._load_project(baseline / "project.json")
            expected_figure = str(
                baseline_project.get("figure_id")
                or (
                    "figure-06"
                    if baseline_project.get("project_id") == "figure-06-regional"
                    else ""
                )
            )
        project = self._load_project(workspace / "project.json")
        entrypoint = Path(str(project.get("entrypoint", "")))
        project_matches = project.get("figure_id") == expected_figure or (
            legacy_session
            and expected_figure == "figure-06"
            and project.get("project_id") == "figure-06-regional"
        )
        if (
            expected_figure not in FIGURE_PROJECTS
            or not project_matches
            or entrypoint.is_absolute()
            or ".." in entrypoint.parts
            or entrypoint.parent != Path("figures") / expected_figure
        ):
            shutil.copy2(baseline / "project.json", workspace / "project.json")
            warnings.append("Restored the selected figure boundary in project.json.")
        for relative in PROTECTED_DEFAULTS:
            current = workspace / relative
            canonical = baseline / relative
            if tree_fingerprint(workspace, (relative,)) != tree_fingerprint(
                baseline, (relative,)
            ):
                if current.exists():
                    remove_local_path(current)
                shutil.copytree(canonical, current)
                warnings.append(f"Restored protected default source files under {relative}.")

        uploads = workspace / "uploads"
        originals = location / "upload-originals"
        active = list(metadata.get("active_uploads", []))
        expected = {
            name: hash_file(originals / name)
            for name in active
            if (originals / name).is_file() and not (originals / name).is_symlink()
        }
        current = {
            path.name: hash_file(path)
            for path in iter_regular_files(uploads)
        }
        if current != expected:
            if uploads.exists() or uploads.is_symlink():
                remove_local_path(uploads)
            uploads.mkdir(parents=True, exist_ok=True)
            for name in active:
                source = originals / name
                if source.is_file() and not source.is_symlink():
                    shutil.copy2(source, uploads / name)
            warnings.append("Restored the immutable copies of uploaded source files.")
        enforce_tree_quota(location)
        enforce_workspace_quota(workspace)
        return warnings

    def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        panel_id: str | None = None,
    ) -> None:
        metadata = self.load(session_id)
        record = {"role": role, "text": text, "at": utcnow()}
        if panel_id:
            record["panel_id"] = panel_id
        metadata.setdefault("messages", []).append(record)
        metadata["messages"] = metadata["messages"][-40:]
        self.save(session_id, metadata)

    def update_result(
        self,
        session_id: str,
        response: str,
        render_log: str,
        warnings: list[str],
    ) -> None:
        metadata = self.load(session_id)
        metadata["latest_agent_response"] = response
        metadata["latest_render_log"] = render_log[-30000:]
        metadata["latest_warnings"] = warnings
        self.save(session_id, metadata)

    def record_pull_request(
        self,
        session_id: str,
        number: int,
        url: str,
        branch: str,
        status: str = "created",
        merge_commit_sha: str | None = None,
    ) -> None:
        metadata = self.load(session_id)
        records = metadata.setdefault("pull_requests", [])
        records.append(
            {
                "number": number,
                "url": url,
                "branch": branch,
                "status": status,
                "merge_commit_sha": merge_commit_sha,
                "created_at": utcnow(),
            }
        )
        metadata["pull_requests"] = records[-10:]
        if status == "merged-integration-branch":
            metadata.setdefault("messages", []).append(
                {
                    "role": "system",
                    "text": (
                        f"PR #{number} passed the exact public-file checks and was "
                        "merged into the integration branch."
                    ),
                    "at": utcnow(),
                }
            )
            metadata["messages"] = metadata["messages"][-40:]
        self.save(session_id, metadata)

    def record_proposal(
        self,
        session_id: str,
        proposal_id: str,
        status: str,
        changed_files: int,
    ) -> None:
        metadata = self.load(session_id)
        records = metadata.setdefault("proposals", [])
        records.append(
            {
                "id": proposal_id,
                "status": status,
                "changed_files": changed_files,
                "created_at": utcnow(),
            }
        )
        metadata["proposals"] = records[-10:]
        metadata.setdefault("messages", []).append(
            {
                "role": "system",
                "text": (
                    f"Proposal {proposal_id} is waiting for owner review. "
                    "No public GitHub branch has been created."
                ),
                "at": utcnow(),
            }
        )
        metadata["messages"] = metadata["messages"][-40:]
        self.save(session_id, metadata)

    def chat_context(self, session_id: str, limit: int = 10) -> list[dict]:
        return self.load(session_id).get("messages", [])[-limit:]

    def resolve_artifact(self, session_id: str, kind: str, relative: str) -> Path:
        location = self.session_dir(session_id)
        if kind == "current":
            base = location / "workspace" / "outputs" / "current"
        elif kind == "default":
            base = location / "baseline" / "outputs" / "current"
        else:
            raise SessionError("Unknown artifact collection")
        lexical = base / relative
        current = base
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                raise SessionError("Artifact not found")
        target = lexical.resolve()
        base_resolved = base.resolve()
        if base_resolved != target and base_resolved not in target.parents:
            raise SessionError("Invalid artifact path")
        if not target.is_file() or target.is_symlink():
            raise SessionError("Artifact not found")
        return target

    def figure_output_path(self, session_id: str, kind: str = "current") -> Path:
        location = self.session_dir(session_id)
        if kind == "current":
            root = location / "workspace"
        elif kind == "default":
            root = location / "baseline"
        else:
            raise SessionError("Unknown artifact collection")
        project = self._load_project(root / "project.json")
        stem = str(project.get("output_stem", ""))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", stem):
            raise SessionError("The figure output name is invalid")
        output = root / "outputs" / "current"
        for extension in ("jpg", "jpeg", "png", "webp"):
            candidate = output / f"{stem}.{extension}"
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
        raise SessionError("The full figure preview is unavailable")

    def resolve_panel_artifact(
        self,
        session_id: str,
        kind: str,
        raw_panel_id: object,
    ) -> Path:
        location = self.session_dir(session_id)
        metadata = self.load(session_id)
        figure_id = str(metadata.get("figure_id", ""))
        try:
            panel_id = validate_panel_id(figure_id, raw_panel_id)
        except PanelError as exc:
            raise SessionError(str(exc)) from exc
        if panel_id is None:
            raise SessionError("The selected panel is invalid")
        if kind in {"default", "current"}:
            try:
                source = self.figure_output_path(session_id, kind)
                previews = ensure_panel_previews(
                    source,
                    location / "panel-previews" / kind,
                    figure_id,
                )
            except PanelError as exc:
                raise SessionError(str(exc)) from exc
            target = previews.get(panel_id, Path())
        else:
            raise SessionError("Unknown panel collection")
        if not target.is_file() or target.is_symlink():
            raise SessionError("Panel preview not found")
        return target

    def export_zip(self, session_id: str) -> Path:
        location = self.session_dir(session_id)
        workspace = location / "workspace"
        removed = remove_unsafe_nodes(workspace)
        if removed:
            raise SessionError("Unsafe links or special files were removed. Review the project before export")
        enforce_tree_quota(location)
        export = location / "exports" / f"figure-studio-{session_id}.zip"
        if export.exists():
            export.unlink()
        checksums: list[dict] = []
        with zipfile.ZipFile(export, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in iter_regular_files(workspace):
                if ".matplotlib-cache" in path.parts or "__pycache__" in path.parts:
                    continue
                rel = path.relative_to(workspace).as_posix()
                if (
                    "\\" in rel
                    or ":" in rel
                    or any(ord(character) < 32 for character in rel)
                    or any(part in {"", ".", ".."} for part in Path(rel).parts)
                ):
                    raise SessionError("The project contains a filename that is unsafe for ZIP export")
                archive.write(path, f"figure-project/{rel}")
                checksums.append(
                    {"path": rel, "bytes": path.stat().st_size, "sha256": hash_file(path)}
                )
            metadata = self.load(session_id)
            archive.writestr(
                "figure-project/STUDIO_SESSION.json",
                json.dumps(
                    {
                        "session_id": session_id,
                        "exported_at": utcnow(),
                        "messages": metadata.get("messages", []),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
            )
            archive.writestr(
                "figure-project/CHECKSUMS.json",
                json.dumps(checksums, indent=2, ensure_ascii=False) + "\n",
            )
        export.chmod(0o600)
        return export

    def export_panel_zip(self, session_id: str, raw_panel_id: object) -> Path:
        location = self.session_dir(session_id)
        workspace = self.workspace(session_id)
        metadata = self.load(session_id)
        figure_id = str(metadata.get("figure_id", ""))
        try:
            panel_id = validate_panel_id(figure_id, raw_panel_id)
        except PanelError as exc:
            raise SessionError(str(exc)) from exc
        if panel_id is None:
            raise SessionError("The selected panel is invalid")
        removed = remove_unsafe_nodes(workspace)
        if removed:
            raise SessionError(
                "Unsafe links or special files were removed. Review the project before export"
            )
        enforce_tree_quota(location)

        source_figure = self.figure_output_path(session_id, "current")
        panel_image = self.resolve_panel_artifact(session_id, "current", panel_id)
        project = self._load_project(workspace / "project.json")
        entrypoint = Path(str(project.get("entrypoint", "")))
        active_figure = entrypoint.parent
        if (
            len(active_figure.parts) != 2
            or active_figure.parts[0] != "figures"
            or active_figure.parts[1] != figure_id
        ):
            raise SessionError("The active figure directory is invalid")

        included: dict[str, Path] = {}

        def include(relative: Path) -> None:
            candidate = workspace / relative
            if not candidate.is_file() or candidate.is_symlink():
                return
            rel = relative.as_posix()
            if (
                "\\" in rel
                or ":" in rel
                or any(ord(character) < 32 for character in rel)
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                raise SessionError("The project contains a filename that is unsafe for ZIP export")
            included[rel] = candidate

        for relative in (
            Path("AGENTS.md"),
            Path("README.md"),
            Path("project.json"),
            Path("render.py"),
            Path("provenance.json"),
        ):
            include(relative)

        output_stem = str(project.get("output_stem", ""))
        source_roots = (active_figure, Path("figures/helpers"))
        for root in source_roots:
            for path in iter_regular_files(workspace / root):
                relative = path.relative_to(workspace)
                if "__pycache__" in relative.parts or ".matplotlib-cache" in relative.parts:
                    continue
                if (
                    "panels" in relative.parts
                    or relative.name in {"make_panels.py", "PANELS.md"}
                ):
                    continue
                if path.suffix.lower() not in REFERENCE_TEXT_SUFFIXES:
                    continue
                if (
                    path.stem == output_stem
                    and path.suffix.lower().lstrip(".") in RASTER_PREVIEWS | {"pdf", "svg"}
                ):
                    continue
                if "panels" in relative.parts and path.suffix.lower() in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                }:
                    continue
                include(relative)

        for relative in panel_data_sources(figure_id, panel_id):
            include(relative)

        reference_parts: list[str] = []
        baseline = location / "baseline"
        for root in source_roots:
            for current_path in iter_regular_files(workspace / root):
                relative = current_path.relative_to(workspace)
                if current_path.suffix.lower() not in REFERENCE_TEXT_SUFFIXES:
                    continue
                baseline_path = baseline / relative
                try:
                    current_lines = current_path.read_text(encoding="utf-8").splitlines()
                    baseline_lines = (
                        baseline_path.read_text(encoding="utf-8").splitlines()
                        if baseline_path.is_file()
                        else []
                    )
                except (OSError, UnicodeDecodeError):
                    continue
                reference_parts.extend(
                    line[2:]
                    for line in difflib.ndiff(baseline_lines, current_lines)
                    if line.startswith("+ ")
                )
        panel_messages = [
            message
            for message in metadata.get("messages", [])
            if message.get("panel_id") == panel_id
        ]
        reference_parts.extend(str(message.get("text", "")) for message in panel_messages)
        references = "\n".join(reference_parts)

        data_roots = (
            Path("results/derived/figure-data"),
            Path("figures/source-data"),
            Path("uploads"),
            Path("data/derived"),
            active_figure,
        )
        for root in data_roots:
            for path in iter_regular_files(workspace / root):
                relative = path.relative_to(workspace)
                if path.suffix.lower() in REFERENCE_TEXT_SUFFIXES:
                    continue
                if path.name.startswith(f"{figure_id}-") and path.suffix.lower() in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                }:
                    continue
                if path.name in references or relative.as_posix() in references:
                    include(relative)

        panel_record = next(
            (panel for panel in panel_catalog(figure_id) if panel["id"] == panel_id),
            None,
        )
        if panel_record is None:
            raise SessionError("The selected panel is invalid")

        export = location / "exports" / f"{figure_id}-panel-{panel_id}.zip"
        export.parent.mkdir(parents=True, exist_ok=True)
        if export.exists():
            export.unlink()
        checksums: list[dict] = []
        data_files = sorted(
            rel
            for rel in included
            if Path(rel).suffix.lower() not in REFERENCE_TEXT_SUFFIXES
        )
        with zipfile.ZipFile(export, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            panel_name = f"{figure_id}-{panel_id}.jpg"
            archive.write(panel_image, f"panel-project/{panel_name}")
            checksums.append(
                {
                    "path": panel_name,
                    "bytes": panel_image.stat().st_size,
                    "sha256": hash_file(panel_image),
                }
            )
            for rel, path in sorted(included.items()):
                archive.write(path, f"panel-project/{rel}")
                checksums.append(
                    {"path": rel, "bytes": path.stat().st_size, "sha256": hash_file(path)}
                )
            archive.writestr(
                "panel-project/PANEL_EXPORT.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "session_id": session_id,
                        "figure_id": figure_id,
                        "panel": panel_record,
                        "panel_image": panel_name,
                        "derivation": "pixel crop of the current full figure",
                        "source_full_figure": {
                            "name": source_figure.name,
                            "bytes": source_figure.stat().st_size,
                            "sha256": hash_file(source_figure),
                        },
                        "data_files": data_files,
                        "exported_at": utcnow(),
                        "messages": panel_messages,
                        "note": (
                            "The selected panel image is packaged with the active figure "
                            "renderer and the input files referenced by that renderer."
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
            )
            archive.writestr(
                "panel-project/CHECKSUMS.json",
                json.dumps(checksums, indent=2, ensure_ascii=False) + "\n",
            )
        export.chmod(0o600)
        return export
