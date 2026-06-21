"""cron backend (Linux fallback, and an alternative on macOS).

Edits are surgical: we only ever touch the block delimited by our BEGIN/END
markers for this job name. Every other crontab line is preserved verbatim.

Caveat vs launchd/systemd: cron does NOT run missed jobs — if the machine is
asleep at the scheduled minute, that run is simply skipped (no catch-up).
"""

from __future__ import annotations

import shlex
import subprocess

from claude_schedule.backends.base import GeneratedArtifact, InstallResult, SchedulerBackend
from claude_schedule.jobspec import JobSpec

BEGIN = "# >>> claude-schedule:{name} >>>"
END = "# <<< claude-schedule:{name} <<<"


def _cron_days(job: JobSpec) -> str:
    # cron weekday: 0 (and 7) == Sunday, 1==Mon .. 6==Sat. canonical -> (d+1)%7.
    if len(job.days) == 7:
        return "*"
    return ",".join(str((d + 1) % 7) for d in job.days)


def cron_line(job: JobSpec, run_argv: list[str]) -> str:
    cmd = " ".join(shlex.quote(a) for a in run_argv)
    log = shlex.quote(job.log_path) if job.log_path else "/dev/null"
    return f"{job.minute} {job.hour} * * {_cron_days(job)} {cmd} >> {log} 2>&1"


def _block(job: JobSpec, run_argv: list[str]) -> str:
    return "\n".join([BEGIN.format(name=job.name), cron_line(job, run_argv), END.format(name=job.name)])


def _read_crontab() -> str:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""  # non-zero == no crontab yet


def _write_crontab(content: str) -> None:
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)


def _strip_block(content: str, name: str) -> str:
    begin, end = BEGIN.format(name=name), END.format(name=name)
    out, skipping = [], False
    for ln in content.splitlines():
        if ln.strip() == begin:
            skipping = True
            continue
        if ln.strip() == end:
            skipping = False
            continue
        if not skipping:
            out.append(ln)
    return "\n".join(out)


class CronBackend(SchedulerBackend):
    name = "cron"

    def generate(self, job: JobSpec, run_argv: list[str]) -> list[GeneratedArtifact]:
        return [GeneratedArtifact("crontab block", None, _block(job, run_argv))]

    def install(self, job: JobSpec, run_argv: list[str]) -> InstallResult:
        stripped = _strip_block(_read_crontab(), job.name).rstrip("\n")
        new = (stripped + "\n" if stripped else "") + _block(job, run_argv) + "\n"
        _write_crontab(new)
        return InstallResult(self.name, self.generate(job, run_argv), [f"crontab - (set block {job.name})"], [])

    def uninstall(self, name: str) -> InstallResult:
        current = _read_crontab()
        if BEGIN.format(name=name) not in current:
            return InstallResult(self.name, [], [], ["no crontab block for this job"])
        stripped = _strip_block(current, name).rstrip("\n")
        _write_crontab(stripped + "\n" if stripped else "")
        return InstallResult(self.name, [], [f"crontab - (removed block {name})"], [])

    def is_installed(self, name: str) -> bool:
        return BEGIN.format(name=name) in _read_crontab()
