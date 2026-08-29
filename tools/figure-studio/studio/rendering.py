from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import secrets
import sys

from .sandbox import SandboxError, run_renderer_isolated


FORMAT_NAME = re.compile(r"^[a-zA-Z0-9]{1,12}$")
PREVIEW_FORMATS = {"png", "jpg", "jpeg", "webp"}
DEFAULT_RENDER_PYTHON = Path(
    os.environ.get(
        "FIGURE_STUDIO_RENDER_PYTHON",
        sys.executable,
    )
)


def _complete_exports(workspace: Path, requested: list[str]) -> list[str]:
    worker_source = Path(__file__).with_name("postprocess_worker.py")
    worker_name = f".studio-postprocess-{secrets.token_hex(12)}.py"
    worker = workspace / worker_name
    descriptor = os.open(
        worker,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(worker_source.read_bytes())
        result = run_renderer_isolated(
            workspace,
            Path(sys.executable),
            ["--formats", *requested],
            timeout=180,
            script_relative=worker_name,
        )
    except SandboxError as exc:
        raise RenderError(str(exc)) from exc
    finally:
        if worker.exists() or worker.is_symlink():
            worker.unlink()
    if result.returncode != 0:
        log = "\n\n".join(
            piece.strip() for piece in (result.stdout, result.stderr) if piece.strip()
        )
        raise RenderError(log or "Sandboxed postprocessing failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


class RenderError(RuntimeError):
    pass


@dataclass
class RenderResult:
    formats: list[str]
    stdout: str
    stderr: str
    returncode: int

    @property
    def log(self) -> str:
        pieces = []
        if self.stdout.strip():
            pieces.append(self.stdout.strip())
        if self.stderr.strip():
            pieces.append(self.stderr.strip())
        return "\n\n".join(pieces)


def normalize_formats(values: list[str] | None, ensure_preview: bool = True) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        for raw in str(value).split(","):
            item = raw.strip().lower().lstrip(".")
            if not item:
                continue
            if not FORMAT_NAME.fullmatch(item):
                raise RenderError(f"Unsupported format name {item!r}")
            if item not in normalized:
                normalized.append(item)
    if not normalized:
        normalized = ["png", "svg", "pdf", "jpg"]
    if ensure_preview and not PREVIEW_FORMATS.intersection(normalized):
        normalized.append("png")
    return normalized


def render_project(
    workspace: Path,
    formats: list[str] | None,
    timeout: int = 360,
) -> RenderResult:
    python = DEFAULT_RENDER_PYTHON
    if not python.is_file():
        python = Path(sys.executable)
    render_script = workspace / "render.py"
    if not render_script.is_file():
        raise RenderError("The project no longer contains render.py")
    requested = normalize_formats(formats)
    arguments = [
        "--formats",
        *requested,
        "--clean",
    ]
    try:
        completed = run_renderer_isolated(workspace, python, arguments, timeout)
    except SandboxError as exc:
        raise RenderError(str(exc)) from exc
    result = RenderResult(
        formats=requested,
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )
    if completed.returncode != 0:
        raise RenderError(result.log or f"Renderer exited with code {completed.returncode}")
    output_dir = workspace / "outputs" / "current"
    if not any(path.is_file() for path in output_dir.rglob("*")):
        raise RenderError("The renderer completed without creating an artifact")
    additions = _complete_exports(workspace, requested)
    if additions:
        result.stdout = result.stdout.rstrip() + "\n" + "\n".join(additions) + "\n"
    return result
