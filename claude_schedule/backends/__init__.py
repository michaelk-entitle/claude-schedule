"""Backend selection: pick a scheduler + wake backend from the detected environment."""

from __future__ import annotations

from claude_schedule.backends.base import SchedulerBackend, WakeBackend
from claude_schedule.backends.cron import CronBackend
from claude_schedule.backends.launchd import LaunchdBackend
from claude_schedule.backends.systemd import SystemdBackend
from claude_schedule.backends.wake import LinuxWake, MacWake, NoopWake, WindowsWake
from claude_schedule.backends.windows import SchtasksBackend
from claude_schedule.environment import Environment

SCHEDULERS: dict[str, type[SchedulerBackend]] = {
    "launchd": LaunchdBackend,
    "cron": CronBackend,
    "systemd": SystemdBackend,
    "schtasks": SchtasksBackend,
}


def select_scheduler(env: Environment, override: str | None = None) -> SchedulerBackend:
    name = override or env.default_scheduler
    if name in (None, "none"):
        raise RuntimeError("no supported scheduler found (need launchd, systemd, cron, or schtasks)")
    if name not in SCHEDULERS:
        raise ValueError(f"unknown scheduler {name!r}; choose from {sorted(SCHEDULERS)}")
    return SCHEDULERS[name]()


def select_wake(env: Environment) -> WakeBackend:
    if env.system == "macos":
        return MacWake()
    if env.system == "linux":
        return LinuxWake()
    if env.system == "windows":
        return WindowsWake()
    return NoopWake()


__all__ = ["SCHEDULERS", "select_scheduler", "select_wake", "SchedulerBackend", "WakeBackend"]
