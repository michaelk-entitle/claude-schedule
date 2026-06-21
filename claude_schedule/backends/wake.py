"""Wake backends — make the machine awake at run time. Kept separate from scheduling.

macOS (``pmset``): the OS exposes exactly ONE repeating wake slot, so we manage it
as the union of all wake-enabled jobs (earliest wake time across them, on the union
of their days). It is set once with sudo and repeats forever — no unattended re-arm.
Apple Silicon wakes from SLEEP only; it cannot power on from a full shutdown.

Linux (``rtcwake``): only a one-shot RTC alarm is practical without root re-arming,
so this is best-effort; the systemd timer's Persistent=true is the real safety net.

Windows: wake is carried by the scheduled task's WakeToRun flag (set at install).
"""

from __future__ import annotations

import datetime
import shutil
import subprocess

from claude_schedule.backends.base import WakeBackend, WakeResult
from claude_schedule.jobspec import JobSpec, format_days


def _combined(jobs: list[JobSpec]) -> tuple[tuple[int, ...], int]:
    """Union of wake days, and the earliest wake clock-time (minutes past midnight)."""
    days: set[int] = set()
    earliest: int | None = None
    for j in jobs:
        days.update(j.days)
        h, m = j.wake_time()
        earliest = h * 60 + m if earliest is None else min(earliest, h * 60 + m)
    return tuple(sorted(days)), (earliest or 0)


def _next_occurrence_epoch(jobs: list[JobSpec]) -> int | None:
    now = datetime.datetime.now()
    best: datetime.datetime | None = None
    for j in jobs:
        wh, wm = j.wake_time()
        for offset in range(8):
            cand = (now + datetime.timedelta(days=offset)).replace(hour=wh, minute=wm, second=0, microsecond=0)
            if cand > now and cand.weekday() in j.days:
                best = cand if best is None else min(best, cand)
                break
    return int(best.timestamp()) if best else None


class MacWake(WakeBackend):
    name = "pmset"

    def __init__(self) -> None:
        self.supported = shutil.which("pmset") is not None

    def _cmd(self, jobs: list[JobSpec]) -> list[str]:
        days, earliest = _combined(jobs)
        h, m = divmod(earliest, 60)
        return ["sudo", "pmset", "repeat", "wakeorpoweron", format_days(days), f"{h:02d}:{m:02d}:00"]

    def plan(self, jobs: list[JobSpec]) -> WakeResult:
        if not jobs:
            return WakeResult(self.name, ["sudo pmset repeat cancel"], False, ["No wake jobs; would clear the slot."])
        return WakeResult(
            self.name,
            [" ".join(self._cmd(jobs))],
            False,
            [
                "macOS has ONE repeating wake slot; claude-schedule manages it as the union of all wake jobs.",
                "Requires sudo (you will be prompted). Apple Silicon wakes from SLEEP only, never from shutdown.",
            ],
        )

    def sync(self, jobs: list[JobSpec]) -> WakeResult:
        if not jobs:
            return self.clear()
        cmd = self._cmd(jobs)
        r = subprocess.run(cmd)  # inherit stdio so sudo can prompt for a password
        notes = [] if r.returncode == 0 else [f"pmset failed; run it yourself:\n  {' '.join(cmd)}"]
        return WakeResult(self.name, [" ".join(cmd)], r.returncode == 0, notes)

    def clear(self) -> WakeResult:
        cmd = ["sudo", "pmset", "repeat", "cancel"]
        r = subprocess.run(cmd)
        notes = [] if r.returncode == 0 else [f"run it yourself: {' '.join(cmd)}"]
        return WakeResult(self.name, [" ".join(cmd)], r.returncode == 0, notes)


class LinuxWake(WakeBackend):
    name = "rtcwake"

    def __init__(self) -> None:
        self.supported = shutil.which("rtcwake") is not None

    _LIMITS = [
        "Linux RTC wake is a one-shot alarm for the next run; it cannot be re-armed unattended (sudo).",
        "Reliable recurring wake needs a BIOS/RTC schedule or a root systemd timer with WakeSystem=true.",
        "The systemd timer uses Persistent=true, so a missed run fires when the machine is next awake.",
    ]

    def plan(self, jobs: list[JobSpec]) -> WakeResult:
        if not self.supported or not jobs:
            return WakeResult(self.name, [], False, ["rtcwake unavailable or no wake jobs."])
        epoch = _next_occurrence_epoch(jobs)
        cmds = [f"sudo rtcwake -m no -t {epoch}"] if epoch else []
        return WakeResult(self.name, cmds, False, self._LIMITS)

    def sync(self, jobs: list[JobSpec]) -> WakeResult:
        if not self.supported or not jobs:
            return WakeResult(self.name, [], False, ["nothing to do"])
        epoch = _next_occurrence_epoch(jobs)
        if epoch is None:
            return WakeResult(self.name, [], False, ["could not compute next wake"])
        cmd = ["sudo", "rtcwake", "-m", "no", "-t", str(epoch)]
        r = subprocess.run(cmd)
        return WakeResult(self.name, [" ".join(cmd)], r.returncode == 0, ["One-shot alarm armed for the next run only."])

    def clear(self) -> WakeResult:
        subprocess.run(["sudo", "rtcwake", "-m", "disable"])
        return WakeResult(self.name, ["sudo rtcwake -m disable"], True, [])


class WindowsWake(WakeBackend):
    name = "schtasks-waketorun"

    def plan(self, jobs: list[JobSpec]) -> WakeResult:
        return WakeResult(
            self.name,
            [],
            False,
            [
                "Wake is configured on the scheduled task itself (-WakeToRun).",
                "Also enable 'Allow wake timers' in Windows power settings.",
            ],
        )

    def sync(self, jobs: list[JobSpec]) -> WakeResult:
        return self.plan(jobs)

    def clear(self) -> WakeResult:
        return WakeResult(self.name, [], True, [])


class NoopWake(WakeBackend):
    name = "none"
    supported = False

    def plan(self, jobs: list[JobSpec]) -> WakeResult:
        return WakeResult(self.name, [], False, ["wake not supported on this platform"])

    def sync(self, jobs: list[JobSpec]) -> WakeResult:
        return self.plan(jobs)

    def clear(self) -> WakeResult:
        return WakeResult(self.name, [], True, [])
