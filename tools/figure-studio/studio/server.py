from __future__ import annotations

import base64
from collections import defaultdict, deque
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import traceback
from urllib.parse import parse_qs, quote, unquote, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .agent import AgentCancelled, AgentError, build_figure_agent
from .billing import BillingStatusReader
from .catalog import DEFAULT_FIGURE_ID, figure_catalog
from .chat_jobs import ChatJob, ChatJobError, ChatJobManager
from .github_pr import ProposalError
from .layout import (
    LayoutError,
    load_layout_catalog,
    prepare_layout_update,
    write_layout_update,
)
from .panels import (
    PanelError,
    capture_panel_snapshot,
    validate_panel_id,
    validate_panel_revision,
)
from .proposal_queue import ProposalQueue
from .rendering import RenderError, normalize_formats, render_project
from .sessions import SessionError, SessionStore


MAX_JSON_REQUEST = 40 * 1024 * 1024
EMAIL = re.compile(r"^[^\s@]{1,128}@[^\s@]{1,190}$")
ACTIVE_CONTENT = {"html", "htm", "svg", "xml", "js", "mjs"}
INLINE_RASTER = {"png", "jpg", "jpeg", "webp", "gif"}
SAFE_DOWNLOAD_NAME = re.compile(r"[^A-Za-z0-9._()@+-]+")
LOCAL_HOST = re.compile(
    r"^(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?$|^\[::1\](?::[0-9]{1,5})?$",
    re.IGNORECASE,
)


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True


class FigureStudioApplication:
    def __init__(
        self,
        app_root: Path,
        session_root: Path,
        access_token: str = "",
        require_cloudflare_access: bool = False,
        public_origin: str = "",
        allowed_emails: set[str] | None = None,
        max_sessions_per_user: int = 12,
        retention_days: int = 0,
        template_root: Path | None = None,
    ):
        self.app_root = app_root.resolve()
        self.static_root = self.app_root / "static"
        self.access_token = access_token
        self.require_cloudflare_access = require_cloudflare_access
        self.public_origin = public_origin.rstrip("/")
        parsed_origin = urlparse(self.public_origin) if self.public_origin else None
        self.public_host = parsed_origin.netloc if parsed_origin else ""
        self.allowed_emails = {email.strip().lower() for email in (allowed_emails or set())}
        if require_cloudflare_access and not self.allowed_emails:
            raise SessionError("Cloudflare Access mode requires an application email allowlist")
        if any(not EMAIL.fullmatch(email) for email in self.allowed_emails):
            raise SessionError("The application email allowlist contains an invalid address")
        self.max_sessions_per_user = max_sessions_per_user
        self.retention_days = retention_days
        self.store = SessionStore(template_root or self.app_root / "template", session_root)
        self.store.cleanup_expired(self.retention_days)
        self.proposals = ProposalQueue(
            self.store.template,
            require_cloudflare_access=require_cloudflare_access,
            allowed_emails=self.allowed_emails,
        )
        self.agent = build_figure_agent(external_mode=require_cloudflare_access)
        self.billing = BillingStatusReader()
        self.chat_jobs = ChatJobManager()
        if require_cloudflare_access and not self.agent.available():
            raise AgentError(
                "Cloudflare Access mode requires a dedicated OpenAI project key file"
            )
        self.limiter = SlidingWindowLimiter()
        self.jobs = threading.BoundedSemaphore(
            max(1, int(os.environ.get("FIGURE_STUDIO_MAX_CONCURRENT_JOBS", "1")))
        )

    def decorate_state(self, state: dict, identity: str = "") -> dict:
        session_id = state["session_id"]
        for collection in ("current", "default"):
            key = f"{collection}_artifacts"
            for artifact in state[key]:
                encoded = quote(artifact["path"], safe="")
                artifact["download_name"] = (
                    SAFE_DOWNLOAD_NAME.sub("_", artifact["name"])[:180] or "download"
                )
                artifact["url"] = (
                    f"/api/sessions/{session_id}/artifacts/{collection}/{encoded}"
                )
        for collection in ("current", "default"):
            preview = state.get(f"{collection}_preview")
            if preview:
                encoded = quote(preview, safe="")
                state[f"{collection}_preview_url"] = (
                    f"/api/sessions/{session_id}/artifacts/{collection}/{encoded}"
                )
            else:
                state[f"{collection}_preview_url"] = None
        state["agent_available"] = self.agent.available()
        state.update(self.agent.configuration())
        state["auth_mode"] = (
            "cloudflare_access" if self.require_cloudflare_access else "local_or_shared_token"
        )
        state["download_url"] = f"/api/sessions/{session_id}/download/project.zip"
        state["pull_request"] = self.proposals.configuration(identity)
        state["api_billing"] = self.billing.status()
        state["available_figures"] = figure_catalog()
        active_job = self.chat_jobs.active(session_id)
        state["active_chat_job"] = active_job.public() if active_job else None
        for panel in state.get("panels", []):
            panel_id = quote(str(panel.get("id", "")), safe="")
            panel["default_preview_url"] = (
                f"/api/sessions/{session_id}/panels/default/{panel_id}"
                if panel.get("default_available")
                else None
            )
            panel["current_preview_url"] = (
                f"/api/sessions/{session_id}/panels/current/{panel_id}"
                if panel.get("current_available")
                else None
            )
            panel["download_url"] = (
                f"/api/sessions/{session_id}/download/panel/{panel_id}.zip"
                if panel.get("default_available")
                else None
            )
        return state

    @staticmethod
    def _cancelled(cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            raise AgentCancelled()

    @staticmethod
    def _trigger_billing_refresh() -> None:
        unit = os.environ.get("FIGURE_STUDIO_BILLING_REFRESH_UNIT", "").strip()
        if unit != "figure-studio-billing.service":
            return
        try:
            subprocess.run(
                ["systemctl", "--user", "start", "--no-block", unit],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            traceback.print_exc()

    def _run_chat_job(self, job: ChatJob, request_payload: dict) -> None:
        warnings: list[str] = []
        revision_id: str | None = None
        panel_id: str | None = None
        message_recorded = False
        terminal_status = "failed"
        terminal_stage = "Revision failed"
        terminal_error = ""
        try:
            with self.store.lock(job.session_id):
                try:
                    self.chat_jobs.update(job, "in_progress", "Preparing the revision")
                    self._cancelled(job.cancel_event)
                    message = str(request_payload.get("message", "")).strip()
                    formats = normalize_formats(request_payload.get("formats"))
                    model, effort = self.agent.resolve_settings(
                        request_payload.get("model"), request_payload.get("effort")
                    )
                    current_state = self.store.state(job.session_id)
                    panel_id = validate_panel_id(
                        current_state["figure_id"], request_payload.get("panel_id")
                    )
                    panel_snapshot = None
                    if panel_id:
                        panel_snapshot = capture_panel_snapshot(
                            self.store.figure_output_path(job.session_id),
                            current_state["figure_id"],
                        )
                    scope = f"Panel {panel_id.upper()}: " if panel_id else ""
                    revision_id = self.store.snapshot(
                        job.session_id,
                        f"State before chat: {scope}{message[:80]}",
                    )
                    history = self.store.chat_context(job.session_id)
                    latest = history[-1] if history else {}
                    resumes_orphaned_request = (
                        latest.get("role") == "user"
                        and str(latest.get("text", "")).strip() == message
                        and (latest.get("panel_id") or None) == panel_id
                    )
                    if resumes_orphaned_request:
                        history = history[:-1]
                        message_recorded = True
                    else:
                        self.store.add_message(
                            job.session_id, "user", message, panel_id=panel_id
                        )
                        message_recorded = True
                    current_state = self.store.state(job.session_id)
                    upload_names = [item["path"] for item in current_state["uploads"]]
                    self.chat_jobs.update(job, "in_progress", "Waiting for the figure agent")
                    agent_result = self.agent.run(
                        self.store.workspace(job.session_id),
                        message,
                        formats,
                        upload_names,
                        history,
                        model=model,
                        effort=effort,
                        panel_id=panel_id,
                        figure_id=current_state["figure_id"],
                        cancel_event=job.cancel_event,
                        on_response_id=lambda response_id: self.chat_jobs.set_response_id(
                            job, response_id
                        ),
                    )
                    self._cancelled(job.cancel_event)
                    if not agent_result.changed:
                        if revision_id:
                            self.store.restore_snapshot(
                                job.session_id, revision_id, discard=True
                            )
                            revision_id = None
                        warnings.extend(
                            self.store.verify_and_restore_sources(job.session_id)
                        )
                        response = str(agent_result.response).replace(chr(0xB7), ", ")
                        self.store.add_message(
                            job.session_id, "assistant", response, panel_id=panel_id
                        )
                        self.store.update_result(
                            job.session_id,
                            response,
                            "No files changed because the current figure already satisfied the request.",
                            warnings,
                        )
                    else:
                        warnings.extend(
                            self.store.verify_and_restore_sources(job.session_id)
                        )
                        self._cancelled(job.cancel_event)
                        self.chat_jobs.update(job, "in_progress", "Rendering the revised figure")
                        render_result = render_project(
                            self.store.workspace(job.session_id), formats
                        )
                        self._cancelled(job.cancel_event)
                        warnings.extend(
                            self.store.verify_and_restore_sources(job.session_id)
                        )
                        if panel_id and panel_snapshot is not None:
                            self.chat_jobs.update(
                                job, "in_progress", "Checking the selected panel"
                            )
                            selected_changed = validate_panel_revision(
                                panel_snapshot,
                                self.store.figure_output_path(job.session_id),
                                panel_id,
                            )
                            if not selected_changed:
                                warnings.append(
                                    f"Panel {panel_id.upper()} rendered without a visible pixel change."
                                )
                        self._cancelled(job.cancel_event)
                        response = str(agent_result.response).replace(chr(0xB7), ", ")
                        self.store.add_message(
                            job.session_id, "assistant", response, panel_id=panel_id
                        )
                        self.store.update_result(
                            job.session_id, response, render_result.log, warnings
                        )
                    terminal_status = "completed"
                    terminal_stage = "Revision completed"
                except AgentCancelled:
                    if revision_id:
                        self.store.restore_snapshot(
                            job.session_id, revision_id, discard=True
                        )
                        revision_id = None
                    warnings.extend(
                        self.store.verify_and_restore_sources(job.session_id)
                    )
                    if not message_recorded:
                        current_state = self.store.state(job.session_id)
                        panel_id = validate_panel_id(
                            current_state["figure_id"], request_payload.get("panel_id")
                        )
                        self.store.add_message(
                            job.session_id,
                            "user",
                            str(request_payload.get("message", "")).strip(),
                            panel_id=panel_id,
                        )
                        message_recorded = True
                    response = "Revision cancelled. No figure changes were kept."
                    self.store.add_message(
                        job.session_id, "assistant", response, panel_id=panel_id
                    )
                    self.store.update_result(
                        job.session_id, response, "Revision cancelled by the user.", warnings
                    )
                    terminal_status = "cancelled"
                    terminal_stage = "Revision cancelled"
                except (AgentError, RenderError, PanelError) as exc:
                    if revision_id:
                        try:
                            self.store.restore_snapshot(
                                job.session_id, revision_id, discard=True
                            )
                        except Exception:
                            traceback.print_exc()
                    warnings.extend(
                        self.store.verify_and_restore_sources(job.session_id)
                    )
                    if self.require_cloudflare_access and not isinstance(exc, PanelError):
                        traceback.print_exc()
                        public_error = (
                            "The revision could not be completed safely. "
                            "Retry once or contact the project owner"
                        )
                    else:
                        public_error = str(exc)
                    response = f"The revision could not be completed. {public_error}"
                    self.store.add_message(
                        job.session_id, "assistant", response, panel_id=panel_id
                    )
                    self.store.update_result(
                        job.session_id, response, public_error, warnings
                    )
                    terminal_error = public_error
                except Exception:
                    traceback.print_exc()
                    if revision_id:
                        try:
                            self.store.restore_snapshot(
                                job.session_id, revision_id, discard=True
                            )
                        except Exception:
                            traceback.print_exc()
                    warnings.extend(
                        self.store.verify_and_restore_sources(job.session_id)
                    )
                    terminal_error = "The revision could not be completed safely"
                    response = f"The revision could not be completed. {terminal_error}"
                    self.store.add_message(
                        job.session_id, "assistant", response, panel_id=panel_id
                    )
                    self.store.update_result(
                        job.session_id, response, terminal_error, warnings
                    )
                finally:
                    try:
                        self.store.verify_and_restore_sources(job.session_id)
                    except Exception:
                        traceback.print_exc()
        finally:
            try:
                self.chat_jobs.finish(
                    job, terminal_status, terminal_stage, terminal_error
                )
            finally:
                self.jobs.release()
                self._trigger_billing_refresh()

    def start_chat_job(self, session_id: str, request_payload: dict) -> ChatJob:
        if not self.jobs.acquire(blocking=False):
            raise ChatJobError("Another figure job is running. Try again shortly")
        try:
            job = self.chat_jobs.create(session_id)
        except Exception:
            self.jobs.release()
            raise
        thread = threading.Thread(
            target=self._run_chat_job,
            args=(job, dict(request_payload)),
            name=f"figure-chat-{job.job_id[-8:]}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            self.chat_jobs.finish(
                job, "failed", "Revision failed", "The revision job could not start"
            )
            self.jobs.release()
            raise
        return job


class FigureStudioHandler(BaseHTTPRequestHandler):
    server_version = "FigureStudio"
    sys_version = ""

    @property
    def app(self) -> FigureStudioApplication:
        return self.server.app  # type: ignore[attr-defined]

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(60)

    def log_message(self, format: str, *args) -> None:
        path = urlparse(self.path).path
        identity = self._identity(required=False)
        identity_tag = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10] if identity else "local"
        print(
            f"[{self.log_date_time_string()}] {self.command} {path} "
            f"{getattr(self, '_last_status', '-')} user={identity_tag}"
        )

    def send_response(self, code: int, message: str | None = None) -> None:
        self._last_status = code
        super().send_response(code, message)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-src 'none'; frame-ancestors 'none'; "
            "worker-src 'none'; manifest-src 'none'; form-action 'none'",
        )
        if self.app.public_origin.startswith("https://"):
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        super().end_headers()

    def _query(self) -> dict[str, list[str]]:
        return parse_qs(urlparse(self.path).query)

    def _decorate_state(self, state: dict) -> dict:
        return self.app.decorate_state(state, self._identity(required=False))

    def _identity(self, required: bool = True) -> str:
        if not self.app.require_cloudflare_access:
            return ""
        assertion = self.headers.get("Cf-Access-Jwt-Assertion", "")
        email = self.headers.get("Cf-Access-Authenticated-User-Email", "").strip().lower()
        if (
            not assertion
            or len(assertion) > 32768
            or len(email) > 320
            or not EMAIL.fullmatch(email)
            or (
                self.app.allowed_emails
                and email not in self.app.allowed_emails
            )
        ):
            if required:
                return ""
            return ""
        return email

    def _authorized(self) -> bool:
        if self.app.require_cloudflare_access and not self._identity():
            return False
        if not self._valid_host():
            return False
        expected = self.app.access_token
        if not expected:
            return True
        header = self.headers.get("X-Figure-Studio-Token", "")
        return hmac.compare_digest(header, expected)

    def _valid_host(self) -> bool:
        if self.app.public_host:
            host = self.headers.get("Host", "").lower()
            if host != self.app.public_host.lower():
                return False
        elif not LOCAL_HOST.fullmatch(self.headers.get("Host", "")):
            return False
        return True

    def _require_static_authorized(self) -> bool:
        if self._valid_host() and (
            not self.app.require_cloudflare_access or bool(self._identity())
        ):
            return True
        self._json_response(403, {"ok": False, "error": "Authenticated access required"})
        return False

    def _require_authorized(self) -> bool:
        if self._authorized():
            return True
        self._json_response(403, {"ok": False, "error": "Authenticated access required"})
        return False

    def _require_same_origin(self) -> bool:
        origin = self.headers.get("Origin", "")
        fetch_site = self.headers.get("Sec-Fetch-Site", "")
        if self.app.public_origin:
            valid_origin = origin == self.app.public_origin
        else:
            parsed = urlparse(origin)
            origin_host = parsed.netloc
            valid_origin = (
                parsed.scheme == "http"
                and bool(LOCAL_HOST.fullmatch(origin_host))
                and not parsed.path
                and not parsed.params
                and not parsed.query
                and not parsed.fragment
            )
        if not valid_origin or fetch_site not in {"same-origin", "none", ""}:
            self._json_response(403, {"ok": False, "error": "Cross-origin request blocked"})
            return False
        return True

    def _require_rate(self, bucket: str, limit: int, window_seconds: int) -> bool:
        identity = self._identity(required=False) or self.client_address[0]
        if self.app.limiter.allow(f"{bucket}:{identity}", limit, window_seconds):
            return True
        self._json_response(429, {"ok": False, "error": "Request limit reached. Try again later"})
        return False

    def _require_owner(self, session_id: str) -> bool:
        try:
            self.app.store.assert_owner(session_id, self._identity(required=False))
            return True
        except SessionError as exc:
            self._json_response(404, {"ok": False, "error": str(exc)})
            return False

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        if length > MAX_JSON_REQUEST:
            raise SessionError("Request body exceeds 40 MB")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SessionError("Request body is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise SessionError("Request body must be a JSON object")
        return payload

    @staticmethod
    def _parts(path: str) -> list[str]:
        return [unquote(part) for part in path.split("/") if part]

    def _send_file(self, path: Path, download_name: str | None = None) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        extension = path.suffix.lower().lstrip(".")
        inline_allowed = extension in INLINE_RASTER and download_name is None
        if extension in ACTIVE_CONTENT:
            content_type = "application/octet-stream"
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        if not inline_allowed:
            safe_name = SAFE_DOWNLOAD_NAME.sub("_", download_name or path.name)[:180]
            safe_name = safe_name or "download"
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{safe_name}"',
            )
        self.end_headers()
        try:
            with path.open("rb") as handle:
                while block := handle.read(1024 * 1024):
                    self.wfile.write(block)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_static(self, relative: str) -> None:
        base = self.app.static_root.resolve()
        lexical = base / relative
        current = base
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                self.send_error(404)
                return
        target = lexical.resolve()
        if base != target and base not in target.parents:
            self.send_error(404)
            return
        if not target.is_file() or target.is_symlink():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Cache-Control",
            "no-store" if self.app.require_cloudflare_access else "no-cache",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            payload = {"ok": True}
            if not self.app.require_cloudflare_access:
                payload["agent_available"] = self.app.agent.available()
            self._json_response(200, payload)
            return
        if path == "/":
            if not self._require_static_authorized():
                return
            self._send_static("index.html")
            return
        if path in {"/app.js", "/styles.css"}:
            if not self._require_static_authorized():
                return
            self._send_static(path.lstrip("/"))
            return
        if not self._require_authorized():
            return
        if not path.startswith("/api/"):
            self.send_error(404)
            return
        if not self._require_rate("api-get", 60, 60):
            return
        try:
            parts = self._parts(path)
            if parts == ["api", "billing"]:
                self._json_response(
                    200,
                    {"ok": True, "api_billing": self.app.billing.status()},
                )
                return
            if (
                len(parts) == 5
                and parts[:2] == ["api", "sessions"]
                and parts[3] == "jobs"
            ):
                if not self._require_owner(parts[2]):
                    return
                job = self.app.chat_jobs.get(parts[2], parts[4])
                payload = {"ok": True, "job": job.public()}
                if job.terminal:
                    with self.app.store.lock(parts[2]):
                        state = self.app.store.state(parts[2])
                    payload["state"] = self._decorate_state(state)
                self._json_response(200, payload)
                return
            if len(parts) == 3 and parts[:2] == ["api", "sessions"]:
                if not self._require_owner(parts[2]):
                    return
                with self.app.store.lock(parts[2]):
                    state = self.app.store.state(parts[2])
                self._json_response(200, {"ok": True, "state": self._decorate_state(state)})
                return
            if (
                len(parts) == 5
                and parts[:2] == ["api", "sessions"]
                and parts[3] == "layout"
                and parts[4] in {"current", "default"}
            ):
                if not self._require_owner(parts[2]):
                    return
                with self.app.store.lock(parts[2]):
                    state = self.app.store.state(parts[2])
                    location = self.app.store.session_dir(parts[2])
                    collection = parts[4]
                    root = (
                        location / "workspace"
                        if collection == "current"
                        else location / "baseline"
                    )
                    layout = load_layout_catalog(root, state["figure_id"])
                    decorated = self._decorate_state(state)
                    preview_url = decorated.get(f"{collection}_preview_url")
                self._json_response(
                    200,
                    {
                        "ok": True,
                        "layout": layout,
                        "preview_url": preview_url,
                        "collection": collection,
                    },
                )
                return
            if (
                len(parts) == 6
                and parts[:2] == ["api", "sessions"]
                and parts[3] == "artifacts"
            ):
                if not self._require_owner(parts[2]):
                    return
                with self.app.store.lock(parts[2]):
                    target = self.app.store.resolve_artifact(parts[2], parts[4], parts[5])
                    download = self._query().get("download", ["0"])[0] == "1"
                    self._send_file(target, target.name if download else None)
                return
            if (
                len(parts) == 6
                and parts[:2] == ["api", "sessions"]
                and parts[3] == "panels"
            ):
                if not self._require_owner(parts[2]):
                    return
                with self.app.store.lock(parts[2]):
                    target = self.app.store.resolve_panel_artifact(
                        parts[2], parts[4], parts[5]
                    )
                    self._send_file(target)
                return
            if (
                len(parts) == 5
                and parts[:2] == ["api", "sessions"]
                and parts[3:] == ["download", "project.zip"]
            ):
                if not self._require_owner(parts[2]):
                    return
                if not self._require_rate("project-export", 10, 3600):
                    return
                if not self.app.jobs.acquire(blocking=False):
                    self._json_response(
                        429,
                        {"ok": False, "error": "Another figure job is running. Try again shortly"},
                    )
                    return
                try:
                    with self.app.store.lock(parts[2]):
                        export = self.app.store.export_zip(parts[2])
                        self._send_file(export, export.name)
                finally:
                    self.app.jobs.release()
                return
            if (
                len(parts) == 6
                and parts[:2] == ["api", "sessions"]
                and parts[3:5] == ["download", "panel"]
                and parts[5].endswith(".zip")
            ):
                if not self._require_owner(parts[2]):
                    return
                if not self._require_rate("panel-export", 20, 3600):
                    return
                if not self.app.jobs.acquire(blocking=False):
                    self._json_response(
                        429,
                        {"ok": False, "error": "Another figure job is running. Try again shortly"},
                    )
                    return
                try:
                    panel_id = parts[5][:-4]
                    with self.app.store.lock(parts[2]):
                        export = self.app.store.export_panel_zip(parts[2], panel_id)
                        self._send_file(export, export.name)
                finally:
                    self.app.jobs.release()
                return
            self.send_error(404)
        except (SessionError, ChatJobError) as exc:
            self._json_response(404, {"ok": False, "error": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            self._json_response(500, {"ok": False, "error": "Internal server error"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self.send_error(404)
            return
        if not self._require_authorized():
            return
        if not self._require_same_origin():
            return
        if not self._require_rate("api", 120, 60):
            return
        try:
            parts = self._parts(path)
            payload = self._read_json()
            if parts == ["api", "sessions"]:
                owner = self._identity(required=False)
                figure_id = str(payload.get("figure_id", DEFAULT_FIGURE_ID))
                self.app.store.cleanup_expired(self.app.retention_days)
                if owner and self.app.store.owner_session_count(owner) >= self.app.max_sessions_per_user:
                    self._json_response(
                        429,
                        {
                            "ok": False,
                            "error": (
                                f"Each collaborator may keep at most "
                                f"{self.app.max_sessions_per_user} sessions"
                            ),
                        },
                    )
                    return
                if not self._require_rate("session-create", 8, 3600):
                    return
                state = self.app.store.create(owner=owner, figure_id=figure_id)
                self._json_response(201, {"ok": True, "state": self._decorate_state(state)})
                return
            if (
                len(parts) == 6
                and parts[:2] == ["api", "sessions"]
                and parts[3] == "jobs"
                and parts[5] == "cancel"
            ):
                if not self._require_owner(parts[2]):
                    return
                if not self._require_rate("agent-cancel", 20, 3600):
                    return
                job = self.app.chat_jobs.cancel(parts[2], parts[4])
                self._json_response(202, {"ok": True, "job": job.public()})
                return
            if len(parts) != 4 or parts[:2] != ["api", "sessions"]:
                self.send_error(404)
                return
            session_id, action = parts[2], parts[3]
            if not self._require_owner(session_id):
                return
            with self.app.store.lock(session_id):
                if action == "upload":
                    decoded: list[tuple[str, bytes]] = []
                    for item in payload.get("files", []):
                        if not isinstance(item, dict):
                            raise SessionError("Invalid upload record")
                        name = str(item.get("name", ""))
                        content = str(item.get("content_base64", ""))
                        try:
                            data = base64.b64decode(content, validate=True)
                        except ValueError as exc:
                            raise SessionError(f"Invalid base64 data for {name}") from exc
                        decoded.append((name, data))
                    state = self.app.store.upload(session_id, decoded)
                    self._json_response(200, {"ok": True, "state": self._decorate_state(state)})
                    return
                if action == "remove-upload":
                    state = self.app.store.remove_upload(session_id, str(payload.get("name", "")))
                    self._json_response(200, {"ok": True, "state": self._decorate_state(state)})
                    return
                if action == "reset":
                    state = self.app.store.reset(
                        session_id, bool(payload.get("keep_uploads", True))
                    )
                    self._json_response(200, {"ok": True, "state": self._decorate_state(state)})
                    return
                if action == "undo":
                    state = self.app.store.undo(session_id)
                    self._json_response(200, {"ok": True, "state": self._decorate_state(state)})
                    return
                if action == "redo":
                    state = self.app.store.redo(session_id)
                    self._json_response(200, {"ok": True, "state": self._decorate_state(state)})
                    return
                if action == "layout":
                    if not self._require_rate("layout-edit", 30, 3600):
                        return
                    if not self.app.jobs.acquire(blocking=False):
                        self._json_response(
                            429,
                            {
                                "ok": False,
                                "error": "Another figure job is running. Try again shortly",
                            },
                        )
                        return
                    revision_id: str | None = None
                    warnings: list[str] = []
                    try:
                        current_state = self.app.store.state(session_id)
                        panel_id = validate_panel_id(
                            current_state["figure_id"], payload.get("panel_id")
                        )
                        update = prepare_layout_update(
                            self.app.store.workspace(session_id),
                            current_state["figure_id"],
                            payload.get("changes"),
                            panel_id=panel_id,
                        )
                        if not update.changed:
                            self._json_response(
                                200,
                                {
                                    "ok": True,
                                    "changed": False,
                                    "state": self._decorate_state(current_state),
                                },
                            )
                            return
                        panel_snapshot = None
                        if panel_id:
                            panel_snapshot = capture_panel_snapshot(
                                self.app.store.figure_output_path(session_id),
                                current_state["figure_id"],
                            )
                        revision_id = self.app.store.snapshot(
                            session_id, "State before interactive layout edit"
                        )
                        write_layout_update(update)
                        warnings.extend(
                            self.app.store.verify_and_restore_sources(session_id)
                        )
                        result = render_project(
                            self.app.store.workspace(session_id), ["jpg"]
                        )
                        warnings.extend(
                            self.app.store.verify_and_restore_sources(session_id)
                        )
                        if panel_id and panel_snapshot is not None:
                            selected_changed = validate_panel_revision(
                                panel_snapshot,
                                self.app.store.figure_output_path(session_id),
                                panel_id,
                            )
                            if not selected_changed:
                                warnings.append(
                                    f"Panel {panel_id.upper()} rendered without a visible pixel change."
                                )
                        response = (
                            f"Applied interactive layout changes to "
                            f"{update.changed_elements} element"
                            f"{'s' if update.changed_elements != 1 else ''}."
                        )
                        self.app.store.update_result(
                            session_id, response, result.log, warnings
                        )
                        revision_id = None
                        state = self.app.store.state(session_id)
                        self._json_response(
                            200,
                            {
                                "ok": True,
                                "changed": True,
                                "state": self._decorate_state(state),
                            },
                        )
                    except Exception:
                        if revision_id:
                            try:
                                self.app.store.restore_snapshot(
                                    session_id, revision_id, discard=True
                                )
                            except Exception:
                                traceback.print_exc()
                        raise
                    finally:
                        try:
                            self.app.store.verify_and_restore_sources(session_id)
                        except Exception:
                            traceback.print_exc()
                        self.app.jobs.release()
                    return
                if action == "pull-request":
                    if not self._require_rate("pull-request", 4, 3600):
                        return
                    current_state = self.app.store.state(session_id)
                    if not current_state.get("has_current_revision"):
                        raise SessionError("Revise the figure before proposing a pull request")
                    panel_id = validate_panel_id(
                        current_state["figure_id"], payload.get("panel_id")
                    )
                    label = current_state["figure_id"].replace("figure-", "Figure ")
                    scope = f" panel {panel_id.upper()}" if panel_id else ""
                    title = str(
                        payload.get("title") or f"Propose {label}{scope} revision"
                    )
                    proposal = self.app.proposals.submit(
                        self.app.store.session_dir(session_id),
                        current_state["figure_id"],
                        panel_id,
                        title,
                        self._identity(),
                    )
                    response: dict
                    if proposal.pull_request is not None:
                        pull_request = proposal.pull_request
                        self.app.store.record_pull_request(
                            session_id,
                            pull_request.number,
                            pull_request.url,
                            pull_request.branch,
                            status=proposal.status,
                            merge_commit_sha=pull_request.merge_commit_sha,
                        )
                        response = {
                            "pull_request": {
                                "number": pull_request.number,
                                "url": pull_request.url,
                                "branch": pull_request.branch,
                                "status": proposal.status,
                                "changed_files": proposal.changed_files,
                                "merge_commit_sha": pull_request.merge_commit_sha,
                            }
                        }
                    else:
                        if proposal.proposal_id is None:
                            raise ProposalError("The proposal result is invalid")
                        self.app.store.record_proposal(
                            session_id,
                            proposal.proposal_id,
                            proposal.status,
                            proposal.changed_files,
                        )
                        response = {
                            "proposal": {
                                "id": proposal.proposal_id,
                                "status": proposal.status,
                                "changed_files": proposal.changed_files,
                            }
                        }
                    state = self.app.store.state(session_id)
                    self._json_response(
                        201,
                        {
                            "ok": True,
                            "state": self._decorate_state(state),
                            **response,
                        },
                    )
                    return
                if action == "render":
                    if not self._require_rate("render", 20, 3600):
                        return
                    if not self.app.jobs.acquire(blocking=False):
                        self._json_response(
                            429,
                            {"ok": False, "error": "Another figure job is running. Try again shortly"},
                        )
                        return
                    warnings: list[str] = []
                    try:
                        formats = normalize_formats(payload.get("formats"))
                        self.app.store.snapshot(session_id, "State before manual render")
                        warnings = self.app.store.verify_and_restore_sources(session_id)
                        result = render_project(self.app.store.workspace(session_id), formats)
                        warnings.extend(self.app.store.verify_and_restore_sources(session_id))
                        self.app.store.update_result(
                            session_id,
                            "Rendered the current code without an AI edit.",
                            result.log,
                            warnings,
                        )
                        state = self.app.store.state(session_id)
                        self._json_response(
                            200, {"ok": True, "state": self._decorate_state(state)}
                        )
                    finally:
                        try:
                            self.app.store.verify_and_restore_sources(session_id)
                        except Exception:
                            traceback.print_exc()
                        self.app.jobs.release()
                    return
                if action == "chat":
                    if not self._require_rate("agent", 10, 3600):
                        return
                    message = str(payload.get("message", "")).strip()
                    if not message:
                        raise SessionError("Please enter a figure request")
                    if len(message) > 12000:
                        raise SessionError("The chat request exceeds 12,000 characters")
                    normalize_formats(payload.get("formats"))
                    try:
                        self.app.agent.resolve_settings(
                            payload.get("model"), payload.get("effort")
                        )
                    except AgentError as exc:
                        raise SessionError(str(exc)) from exc
                    current_state = self.app.store.state(session_id)
                    validate_panel_id(
                        current_state["figure_id"], payload.get("panel_id")
                    )
                    try:
                        job = self.app.start_chat_job(session_id, payload)
                    except ChatJobError as exc:
                        self._json_response(429, {"ok": False, "error": str(exc)})
                        return
                    self._json_response(202, {"ok": True, "job": job.public()})
                    return
            self.send_error(404)
        except (
            SessionError,
            RenderError,
            PanelError,
            LayoutError,
            ProposalError,
            ChatJobError,
        ) as exc:
            if self.app.require_cloudflare_access and isinstance(exc, RenderError):
                traceback.print_exc()
                error = "The generated figure did not render successfully"
            else:
                error = str(exc)
            self._json_response(400, {"ok": False, "error": error})
        except Exception as exc:
            traceback.print_exc()
            self._json_response(500, {"ok": False, "error": "Internal server error"})


class FigureStudioHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, *args, **kwargs):
        self._request_slots = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address) -> None:
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


def serve(
    app_root: Path,
    session_root: Path,
    host: str,
    port: int,
    access_token: str = "",
    require_cloudflare_access: bool = False,
    public_origin: str = "",
    allowed_emails: set[str] | None = None,
    max_sessions_per_user: int = 12,
    retention_days: int = 0,
    template_root: Path | None = None,
) -> None:
    application = FigureStudioApplication(
        app_root,
        session_root,
        access_token,
        require_cloudflare_access,
        public_origin,
        allowed_emails,
        max_sessions_per_user,
        retention_days,
        template_root,
    )
    server = FigureStudioHTTPServer((host, port), FigureStudioHandler)
    server.app = application  # type: ignore[attr-defined]
    print(f"Figure Studio listening on http://{host}:{port}")
    if access_token:
        print("Access token protection is enabled")
    if require_cloudflare_access:
        print(f"Cloudflare Access protection is required for {public_origin}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Figure Studio")
    finally:
        server.server_close()
