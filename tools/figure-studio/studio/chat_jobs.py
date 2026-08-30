from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import secrets
import threading


TERMINAL_STATUSES = {"completed", "cancelled", "failed"}
ACTIVE_STATUSES = {"queued", "in_progress", "cancelling"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatJobError(RuntimeError):
    pass


@dataclass
class ChatJob:
    job_id: str
    session_id: str
    status: str = "queued"
    stage: str = "Queued"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    finished_at: str | None = None
    error: str = ""
    response_id: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def public(self) -> dict:
        return {
            "id": self.job_id,
            "session_id": self.session_id,
            "status": self.status,
            "stage": self.stage,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "cancellable": self.status in {"queued", "in_progress"},
        }


class ChatJobManager:
    def __init__(self, retention_minutes: int = 60, maximum_jobs: int = 200):
        self.retention = timedelta(minutes=max(5, min(retention_minutes, 1440)))
        self.maximum_jobs = max(20, min(maximum_jobs, 1000))
        self._jobs: dict[str, ChatJob] = {}
        self._active_by_session: dict[str, str] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.retention
        expired: list[str] = []
        for job_id, job in self._jobs.items():
            if not job.terminal or not job.finished_at:
                continue
            try:
                finished = datetime.fromisoformat(job.finished_at)
            except ValueError:
                finished = cutoff - timedelta(seconds=1)
            if finished < cutoff:
                expired.append(job_id)
        for job_id in expired:
            self._jobs.pop(job_id, None)
        if len(self._jobs) <= self.maximum_jobs:
            return
        terminal = sorted(
            (job for job in self._jobs.values() if job.terminal),
            key=lambda item: item.finished_at or item.updated_at,
        )
        for job in terminal[: len(self._jobs) - self.maximum_jobs]:
            self._jobs.pop(job.job_id, None)

    def create(self, session_id: str) -> ChatJob:
        with self._lock:
            self._prune()
            active_id = self._active_by_session.get(session_id)
            if active_id and active_id in self._jobs:
                raise ChatJobError("A revision is already running for this figure")
            job_id = "job_" + secrets.token_urlsafe(18).replace("-", "a").replace("_", "b")
            job = ChatJob(job_id=job_id, session_id=session_id)
            self._jobs[job_id] = job
            self._active_by_session[session_id] = job_id
            return job

    def get(self, session_id: str, job_id: str) -> ChatJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.session_id != session_id:
                raise ChatJobError("The revision job is unavailable")
            return job

    def active(self, session_id: str) -> ChatJob | None:
        with self._lock:
            job_id = self._active_by_session.get(session_id)
            job = self._jobs.get(job_id or "")
            return job if job and not job.terminal else None

    def update(self, job: ChatJob, status: str, stage: str) -> None:
        if status not in ACTIVE_STATUSES:
            raise ChatJobError("The revision job status is invalid")
        with self._lock:
            stored = self.get(job.session_id, job.job_id)
            if stored.terminal:
                return
            stored.status = status
            stored.stage = stage[:200]
            stored.updated_at = _now()

    def set_response_id(self, job: ChatJob, response_id: str) -> None:
        with self._lock:
            stored = self.get(job.session_id, job.job_id)
            stored.response_id = response_id[:200]
            stored.updated_at = _now()

    def cancel(self, session_id: str, job_id: str) -> ChatJob:
        with self._lock:
            job = self.get(session_id, job_id)
            if job.terminal:
                return job
            job.cancel_event.set()
            job.status = "cancelling"
            job.stage = "Stopping the revision"
            job.updated_at = _now()
            return job

    def finish(self, job: ChatJob, status: str, stage: str, error: str = "") -> None:
        if status not in TERMINAL_STATUSES:
            raise ChatJobError("The revision job terminal status is invalid")
        with self._lock:
            stored = self.get(job.session_id, job.job_id)
            stored.status = status
            stored.stage = stage[:200]
            stored.error = error[:1000]
            stored.updated_at = _now()
            stored.finished_at = stored.updated_at
            if self._active_by_session.get(job.session_id) == job.job_id:
                self._active_by_session.pop(job.session_id, None)
