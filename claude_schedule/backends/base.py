"""Backend interfaces.

Two independent concerns, deliberately kept apart:

* ``SchedulerBackend`` — *when* the job runs (launchd / cron / systemd / schtasks).
* ``WakeBackend``      — *whether the machine is awake* at that time (pmset / rtcwake / …).

Both receive an opaque ``run_argv`` (the command that runs the job). Building that
command — the "claude wrapper" — lives in ``runner.py``, separate from installation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from claude_schedule.jobspec import JobSpec


@dataclass
class GeneratedArtifact:
    """A file or command a backend would produce, for dry-run display."""

    label: str
    path: str | None  # file path if it writes a file, else None (a command)
    content: str


@dataclass
class InstallResult:
    backend: str
    artifacts: list[GeneratedArtifact] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class SchedulerBackend(ABC):
    name: str

    @abstractmethod
    def generate(self, job: JobSpec, run_argv: list[str]) -> list[GeneratedArtifact]:
        """Return files/commands this backend WOULD create. No side effects."""

    @abstractmethod
    def install(self, job: JobSpec, run_argv: list[str]) -> InstallResult:
        """Create and activate the scheduled job. Idempotent (re-install replaces)."""

    @abstractmethod
    def uninstall(self, name: str) -> InstallResult:
        """Remove the scheduled job. Idempotent."""

    @abstractmethod
    def is_installed(self, name: str) -> bool: ...


@dataclass
class WakeResult:
    backend: str
    commands: list[str] = field(default_factory=list)
    ran: bool = False
    notes: list[str] = field(default_factory=list)


class WakeBackend(ABC):
    name: str
    supported: bool = True

    @abstractmethod
    def plan(self, jobs: list[JobSpec]) -> WakeResult:
        """Commands sync() would run for these wake-enabled jobs. No side effects."""

    @abstractmethod
    def sync(self, jobs: list[JobSpec]) -> WakeResult:
        """Reconcile the OS wake schedule with these wake-enabled jobs. May need sudo."""

    @abstractmethod
    def clear(self) -> WakeResult:
        """Remove any wake schedule we manage."""
