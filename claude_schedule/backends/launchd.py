"""macOS launchd backend (the native, recommended macOS scheduler).

Why launchd over cron on macOS: it survives reboots, and it *runs missed
StartCalendarInterval jobs on the next wake* — a built-in catch-up that covers
us if the wake fires slightly late or not at all.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from claude_schedule.backends.base import GeneratedArtifact, InstallResult, SchedulerBackend
from claude_schedule.jobspec import JobSpec

LABEL_PREFIX = "com.claude-schedule"


def label_for(name: str) -> str:
    return f"{LABEL_PREFIX}.{name}"


def plist_path(name: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label_for(name)}.plist"


def _calendar_intervals(job: JobSpec) -> list[dict]:
    # launchd Weekday: 0 (and 7) == Sunday, 1==Mon .. 6==Sat.
    # canonical days: 0==Mon .. 6==Sun  ->  (d + 1) % 7  maps Sun(6)->0.
    return [{"Weekday": (d + 1) % 7, "Hour": job.hour, "Minute": job.minute} for d in job.days]


def _env_vars(job: JobSpec) -> dict[str, str]:
    parts: list[str] = []
    if job.node_bin_dir:
        parts.append(job.node_bin_dir)
    if job.claude_path:
        parts.append(str(Path(job.claude_path).parent))
    parts += ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    seen: set[str] = set()
    path: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            path.append(p)
    return {"PATH": ":".join(path), "HOME": str(Path.home())}


def build_plist(job: JobSpec, run_argv: list[str]) -> bytes:
    plist: dict = {
        "Label": label_for(job.name),
        "ProgramArguments": list(run_argv),
        "StartCalendarInterval": _calendar_intervals(job),
        "RunAtLoad": False,  # never run on login/load, only on schedule
        "ProcessType": "Background",
        "EnvironmentVariables": _env_vars(job),
    }
    if job.log_path:
        launchd_log = str(Path(job.log_path).with_suffix(".launchd.log"))
        plist["StandardOutPath"] = launchd_log
        plist["StandardErrorPath"] = launchd_log
    return plistlib.dumps(plist)


class LaunchdBackend(SchedulerBackend):
    name = "launchd"

    def generate(self, job: JobSpec, run_argv: list[str]) -> list[GeneratedArtifact]:
        content = build_plist(job, run_argv).decode("utf-8")
        return [GeneratedArtifact("LaunchAgent plist", str(plist_path(job.name)), content)]

    def install(self, job: JobSpec, run_argv: list[str]) -> InstallResult:
        path = plist_path(job.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._bootout(job.name)  # replace any existing instance
        path.write_bytes(build_plist(job, run_argv))

        domain = f"gui/{os.getuid()}"
        cmds: list[str] = []
        notes: list[str] = []
        r = subprocess.run(["launchctl", "bootstrap", domain, str(path)], capture_output=True, text=True)
        cmds.append(f"launchctl bootstrap {domain} {path}")
        if r.returncode != 0:
            subprocess.run(["launchctl", "load", "-w", str(path)], capture_output=True, text=True)
            cmds.append(f"launchctl load -w {path}")
            if r.stderr.strip():
                notes.append(f"bootstrap note: {r.stderr.strip()}")
        return InstallResult(self.name, self.generate(job, run_argv), cmds, notes)

    def _bootout(self, name: str) -> None:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{label_for(name)}"], capture_output=True, text=True
        )
        subprocess.run(["launchctl", "unload", str(plist_path(name))], capture_output=True, text=True)

    def uninstall(self, name: str) -> InstallResult:
        self._bootout(name)
        p = plist_path(name)
        existed = p.is_file()
        p.unlink(missing_ok=True)
        notes = [] if existed else ["plist was not present"]
        return InstallResult(self.name, [], [f"launchctl bootout gui/{os.getuid()}/{label_for(name)}"], notes)

    def is_installed(self, name: str) -> bool:
        return plist_path(name).is_file()
