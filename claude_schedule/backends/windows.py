"""Windows Task Scheduler backend via PowerShell (lightly tested — see docs).

Uses ``Register-ScheduledTask`` with ``-WakeToRun`` so the task itself carries
the wake request (the Windows analogue of macOS ``pmset``; no separate wake step).
The user must also enable "Allow wake timers" in the active power plan.
"""

from __future__ import annotations

import subprocess

from claude_schedule.backends.base import GeneratedArtifact, InstallResult, SchedulerBackend
from claude_schedule.jobspec import JobSpec

DAY_TOKENS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]  # canonical 0..6


def task_name(name: str) -> str:
    return f"claude-schedule\\{name}"


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def ps_install_script(job: JobSpec, run_argv: list[str]) -> str:
    exe = run_argv[0]
    arg_string = subprocess.list2cmdline(run_argv[1:])
    days = ",".join(DAY_TOKENS[d] for d in job.days)
    wake = "$true" if job.wake else "$false"
    return (
        f"$action = New-ScheduledTaskAction -Execute {_ps_quote(exe)} -Argument {_ps_quote(arg_string)};\n"
        f"$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek {days} -At {job.hour:02d}:{job.minute:02d};\n"
        f"$settings = New-ScheduledTaskSettingsSet -WakeToRun:{wake} -AllowStartIfOnBatteries "
        f"-DontStopIfGoingOnBatteries -StartWhenAvailable;\n"
        f"Register-ScheduledTask -TaskName {_ps_quote(task_name(job.name))} "
        f"-Action $action -Trigger $trigger -Settings $settings -Force"
    )


def _powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)


class SchtasksBackend(SchedulerBackend):
    name = "schtasks"

    def generate(self, job: JobSpec, run_argv: list[str]) -> list[GeneratedArtifact]:
        return [GeneratedArtifact("PowerShell scheduled task", None, ps_install_script(job, run_argv))]

    def install(self, job: JobSpec, run_argv: list[str]) -> InstallResult:
        _powershell(ps_install_script(job, run_argv))
        return InstallResult(
            self.name,
            self.generate(job, run_argv),
            ["powershell Register-ScheduledTask"],
            ["Enable 'Allow wake timers' in Windows power settings for WakeToRun to take effect."],
        )

    def uninstall(self, name: str) -> InstallResult:
        _powershell(f"Unregister-ScheduledTask -TaskName {_ps_quote(task_name(name))} -Confirm:$false")
        return InstallResult(self.name, [], ["powershell Unregister-ScheduledTask"], [])

    def is_installed(self, name: str) -> bool:
        r = _powershell(f"Get-ScheduledTask -TaskName {_ps_quote(task_name(name))} -ErrorAction SilentlyContinue")
        return bool(r.stdout.strip())
