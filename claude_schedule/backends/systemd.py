"""Linux systemd user-timer backend (preferred on Linux when available).

Writes a ``.service`` + ``.timer`` pair under ``~/.config/systemd/user``.
``Persistent=true`` gives catch-up: a run missed while the machine was off fires
as soon as it is next up. Note: user timers cannot themselves wake the machine
(that needs a root timer with WakeSystem=true) — see the wake backend + docs.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from claude_schedule.backends.base import GeneratedArtifact, InstallResult, SchedulerBackend
from claude_schedule.jobspec import JobSpec

DAY_TOKENS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # canonical 0..6


def unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def service_name(name: str) -> str:
    return f"claude-schedule-{name}.service"


def timer_name(name: str) -> str:
    return f"claude-schedule-{name}.timer"


def _oncalendar(job: JobSpec) -> str:
    days = "" if len(job.days) == 7 else ",".join(DAY_TOKENS[d] for d in job.days)
    return f"{days} {job.hour:02d}:{job.minute:02d}:00".strip()


def build_service(job: JobSpec, run_argv: list[str]) -> str:
    exec_start = " ".join(shlex.quote(a) for a in run_argv)
    return f"[Unit]\nDescription=claude-schedule job {job.name}\n\n[Service]\nType=oneshot\nExecStart={exec_start}\n"


def build_timer(job: JobSpec) -> str:
    return (
        f"[Unit]\nDescription=claude-schedule timer for {job.name}\n\n"
        f"[Timer]\nOnCalendar={_oncalendar(job)}\nPersistent=true\n\n"
        f"[Install]\nWantedBy=timers.target\n"
    )


class SystemdBackend(SchedulerBackend):
    name = "systemd"

    def generate(self, job: JobSpec, run_argv: list[str]) -> list[GeneratedArtifact]:
        d = unit_dir()
        return [
            GeneratedArtifact("systemd service", str(d / service_name(job.name)), build_service(job, run_argv)),
            GeneratedArtifact("systemd timer", str(d / timer_name(job.name)), build_timer(job)),
        ]

    def install(self, job: JobSpec, run_argv: list[str]) -> InstallResult:
        d = unit_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / service_name(job.name)).write_text(build_service(job, run_argv))
        (d / timer_name(job.name)).write_text(build_timer(job))
        cmds: list[str] = []
        for c in (
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", timer_name(job.name)],
        ):
            subprocess.run(c, capture_output=True, text=True)
            cmds.append(" ".join(c))
        return InstallResult(
            self.name,
            self.generate(job, run_argv),
            cmds,
            ["To run while logged out: loginctl enable-linger $USER"],
        )

    def uninstall(self, name: str) -> InstallResult:
        subprocess.run(["systemctl", "--user", "disable", "--now", timer_name(name)], capture_output=True, text=True)
        d = unit_dir()
        for f in (d / service_name(name), d / timer_name(name)):
            f.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True)
        return InstallResult(self.name, [], [f"systemctl --user disable --now {timer_name(name)}"], [])

    def is_installed(self, name: str) -> bool:
        return (unit_dir() / timer_name(name)).is_file()
