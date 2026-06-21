"""On-disk job registry: where job specs and logs live, and CRUD over them.

Layout (override the root with ``$CLAUDE_SCHEDULE_HOME``)::

    ~/.config/claude-schedule/        (XDG; %APPDATA%\\claude-schedule on Windows)
        jobs/<name>.json
        logs/<name>.log
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from claude_schedule.jobspec import JobSpec

APP_NAME = "claude-schedule"


def config_home() -> Path:
    override = os.environ.get("CLAUDE_SCHEDULE_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / APP_NAME


def jobs_dir() -> Path:
    d = config_home() / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = config_home() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_file(name: str) -> Path:
    return jobs_dir() / f"{name}.json"


def default_log_path(name: str) -> str:
    return str(logs_dir() / f"{name}.log")


def save_job(job: JobSpec) -> Path:
    p = job_file(job.name)
    p.write_text(json.dumps(job.to_dict(), indent=2) + "\n", encoding="utf-8")
    return p


def load_job(name: str) -> JobSpec:
    p = job_file(name)
    if not p.is_file():
        raise FileNotFoundError(f"no job named {name!r} (looked in {p})")
    return JobSpec.from_dict(json.loads(p.read_text(encoding="utf-8")))


def list_jobs() -> list[JobSpec]:
    out: list[JobSpec] = []
    for p in sorted(jobs_dir().glob("*.json")):
        try:
            out.append(JobSpec.from_dict(json.loads(p.read_text(encoding="utf-8"))))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return out


def delete_job(name: str) -> None:
    job_file(name).unlink(missing_ok=True)


def job_exists(name: str) -> bool:
    return job_file(name).is_file()
