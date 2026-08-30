from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import time


class SandboxError(RuntimeError):
    pass


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str


MAX_WORKSPACE_BYTES = 300 * 1024 * 1024
MAX_WORKSPACE_FILES = 2000
MAX_COMBINED_LOG_BYTES = 8 * 1024 * 1024


def _workspace_usage(workspace: Path) -> tuple[int, int]:
    files = 0
    total = 0
    for current, directories, names in os.walk(workspace, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories if not (current_path / name).is_symlink()
        ]
        for name in names:
            path = current_path / name
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                # Figure wrappers create and retire a canonical JPG while the
                # renderer is running. A quota scan may cross that rename.
                continue
            if stat.S_ISREG(metadata.st_mode):
                files += 1
                total += metadata.st_size
    return files, total


def _descendant_count(root_pid: int, limit: int) -> int:
    seen: set[int] = set()
    pending = [root_pid]
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        if len(seen) > limit:
            return len(seen)
        children_file = Path(f"/proc/{pid}/task/{pid}/children")
        try:
            children = children_file.read_text(encoding="ascii").split()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        pending.extend(int(child) for child in children if child.isdigit())
    return len(seen)


def _mount_if_present(command: list[str], option: str, source: Path, target: str) -> None:
    if source.exists():
        command.extend([option, str(source), target])


def renderer_command(
    workspace: Path,
    python: Path,
    arguments: list[str],
    script_relative: str = "render.py",
) -> list[str]:
    bubblewrap = shutil.which("bwrap")
    limiter = shutil.which("prlimit")
    setpriv = shutil.which("setpriv")
    if not bubblewrap or not limiter or not setpriv:
        raise SandboxError(
            "Bubblewrap, prlimit and setpriv are required for isolated rendering"
        )
    workspace = workspace.resolve()
    python = python.resolve()
    environment_root = python.parent.parent
    if not workspace.is_dir() or workspace.is_symlink():
        raise SandboxError("Invalid renderer workspace")
    if not python.is_file() or environment_root == Path("/"):
        raise SandboxError("Invalid renderer Python environment")
    script = Path(script_relative)
    if script.is_absolute() or ".." in script.parts or not script.parts:
        raise SandboxError("Invalid sandbox script path")
    script_host = workspace / script
    if not script_host.is_file() or script_host.is_symlink():
        raise SandboxError("The sandbox script is missing")

    sandbox = [
        bubblewrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    _mount_if_present(sandbox, "--ro-bind", Path("/bin"), "/bin")
    _mount_if_present(sandbox, "--ro-bind", Path("/lib"), "/lib")
    _mount_if_present(sandbox, "--ro-bind", Path("/lib64"), "/lib64")
    sandbox.extend(["--dir", "/etc"])
    _mount_if_present(sandbox, "--ro-bind", Path("/etc/fonts"), "/etc/fonts")
    _mount_if_present(sandbox, "--ro-bind", Path("/etc/localtime"), "/etc/localtime")
    sandbox.extend(
        [
            "--dir",
            "/opt",
            "--ro-bind",
            str(environment_root),
            "/opt/render-env",
            "--bind",
            str(workspace),
            "/workspace",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/var",
            "--tmpfs",
            "/var/tmp",
            "--dir",
            "/run",
            "--chdir",
            "/workspace",
            "--setenv",
            "HOME",
            "/workspace/.sandbox-home",
            "--setenv",
            "PATH",
            "/opt/render-env/bin:/usr/bin:/bin",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "LC_ALL",
            "C.UTF-8",
            "--setenv",
            "MPLCONFIGDIR",
            "/workspace/.matplotlib-cache",
            "--setenv",
            "FONTCONFIG_FILE",
            "/etc/fonts/fonts.conf",
            "--setenv",
            "FONTCONFIG_PATH",
            "/etc/fonts",
            "--setenv",
            "PYTHONUNBUFFERED",
            "1",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "OMP_NUM_THREADS",
            "4",
            "--setenv",
            "OPENBLAS_NUM_THREADS",
            "4",
            "--setenv",
            "MKL_NUM_THREADS",
            "4",
            "--setenv",
            "NUMEXPR_NUM_THREADS",
            "4",
            "--",
            "/opt/render-env/bin/python",
            f"/workspace/{script.as_posix()}",
            *arguments,
        ]
    )
    return [
        limiter,
        "--core=0",
        "--cpu=420",
        "--as=8589934592",
        "--fsize=67108864",
        "--nofile=256",
        "--nproc=4096",
        "--",
        setpriv,
        "--no-new-privs",
        "--",
        *sandbox,
    ]


def run_renderer_isolated(
    workspace: Path,
    python: Path,
    arguments: list[str],
    timeout: int,
    max_bytes: int = MAX_WORKSPACE_BYTES,
    max_files: int = MAX_WORKSPACE_FILES,
    script_relative: str = "render.py",
) -> SandboxResult:
    workspace = workspace.resolve()
    (workspace / ".sandbox-home").mkdir(mode=0o700, exist_ok=True)
    command = renderer_command(workspace, python, arguments, script_relative)
    process = subprocess.Popen(
        command,
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        bufsize=0,
    )
    deadline = time.monotonic() + timeout
    if process.stdout is None or process.stderr is None:
        raise SandboxError("Could not capture renderer output")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    emitted = 0
    reason = ""
    next_resource_check = time.monotonic()
    while selector.get_map() or process.poll() is None:
        for key, _ in selector.select(timeout=0.05):
            try:
                block = os.read(key.fileobj.fileno(), 65536)
            except BlockingIOError:
                continue
            if not block:
                selector.unregister(key.fileobj)
                continue
            captured[key.data].extend(block)
            emitted += len(block)
            if emitted > MAX_COMBINED_LOG_BYTES:
                reason = "Rendering exceeded the output-log limit"
                break
        if reason:
            break
        now = time.monotonic()
        if now >= deadline:
            reason = f"Rendering exceeded {timeout} seconds"
            break
        if now < next_resource_check:
            continue
        next_resource_check = now + 0.10
        files, total = _workspace_usage(workspace)
        if files > max_files or total > max_bytes:
            reason = "Rendering exceeded the session storage quota"
            break
        if _descendant_count(process.pid, 64) > 64:
            reason = "Rendering exceeded the process limit"
            break
    if reason:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()
    for stream in (process.stdout, process.stderr):
        try:
            while block := os.read(stream.fileno(), 65536):
                name = "stdout" if stream is process.stdout else "stderr"
                if emitted <= MAX_COMBINED_LOG_BYTES:
                    remaining = MAX_COMBINED_LOG_BYTES - emitted
                    captured[name].extend(block[:remaining])
                emitted += len(block)
        except OSError:
            pass
        stream.close()
    selector.close()
    stdout = bytes(captured["stdout"]).decode("utf-8", errors="replace")
    stderr = bytes(captured["stderr"]).decode("utf-8", errors="replace")
    if reason:
        raise SandboxError(reason + "\n" + stdout[-2000:] + stderr[-2000:])
    return SandboxResult(process.returncode, stdout, stderr)
