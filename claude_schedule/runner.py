"""The job runner — what the scheduler actually invokes (``_run --name <job>``).

Responsibilities, all portable and dependency-free:
  * build the ``claude -p ...`` command line from the JobSpec (the "wrapper"),
  * keep the machine awake for the run (caffeinate / systemd-inhibit / Windows API),
  * enforce a timeout in-process (no reliance on ``timeout``/``gtimeout``),
  * append a timestamped record to the job log.
"""

from __future__ import annotations

import os
import signal
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from claude_schedule import registry
from claude_schedule.jobspec import JobSpec

TIMEOUT_EXIT_CODE = 124  # match GNU timeout's convention


def build_claude_argv(job: JobSpec) -> list[str]:
    """Translate a JobSpec into a ``claude`` argv. No shell, so no quoting needed."""
    prompt = Path(job.prompt_file).read_text(encoding="utf-8") if job.prompt_file else (job.prompt or "")
    argv = [job.claude_path, "-p", prompt]
    if job.model:
        argv += ["--model", job.model]
    if job.permission_mode:
        argv += ["--permission-mode", job.permission_mode]
    if job.skip_permissions:
        argv.append("--dangerously-skip-permissions")
    if job.allowed_tools:
        argv += ["--allowed-tools", job.allowed_tools]
    if job.bare:
        argv.append("--bare")
    if job.output_format:
        argv += ["--output-format", job.output_format]
    argv += job.extra_args
    return argv


def _load_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def build_run_env(job: JobSpec) -> dict[str, str]:
    """Process env for the job: ensure node + claude dirs are on PATH, then apply env-file."""
    env = dict(os.environ)
    extra = [d for d in (job.node_bin_dir, str(Path(job.claude_path).parent)) if d]
    env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    if job.env_file:
        env.update(_load_env_file(job.env_file))
    return env


def wrap_keep_awake(argv: list[str]) -> list[str]:
    """Prefix argv with a keep-awake wrapper so the machine stays up for the run."""
    if sys.platform == "darwin":
        return ["/usr/bin/caffeinate", "-i", "-s", *argv]
    if sys.platform.startswith("linux") and shutil.which("systemd-inhibit"):
        return [
            "systemd-inhibit", "--what=idle:sleep", "--who=claude-schedule",
            "--why=running scheduled Claude job", "--mode=block", *argv,
        ]
    return argv  # Windows handled separately via SetThreadExecutionState


def _win_keep_awake(on: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        es_continuous = 0x80000000
        es_system_required = 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | (es_system_required if on else 0))
    except Exception:  # noqa: BLE001 - best effort, never fail the run over keep-awake
        pass


def _terminate(proc: subprocess.Popen) -> None:
    posix = os.name == "posix"
    try:
        if posix:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            if posix:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, OSError):
            pass


def _run_with_timeout(argv: list[str], cwd: str, env: dict[str, str], timeout: int, log: TextIO) -> int:
    kwargs: dict = {"cwd": cwd, "env": env, "stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if os.name == "posix":
        kwargs["start_new_session"] = True  # own process group => clean group kill on timeout
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    log.flush()
    try:
        proc = subprocess.Popen(argv, **kwargs)
    except (FileNotFoundError, OSError) as exc:
        log.write(f"error: could not execute {argv[0]!r}: {exc}\n")
        return 127
    try:
        return proc.wait(timeout=timeout or None)
    except subprocess.TimeoutExpired:
        log.write(f"\n!! timeout after {timeout}s — terminating job\n")
        log.flush()
        _terminate(proc)
        return TIMEOUT_EXIT_CODE


def run_job(name: str) -> int:
    """Run a stored job now. Returns the process exit code (124 on timeout)."""
    job = registry.load_job(name)
    log: TextIO = open(job.log_path, "a", encoding="utf-8") if job.log_path else sys.stdout

    def w(msg: str) -> None:
        log.write(msg + "\n")
        log.flush()

    start = datetime.now()
    cwd = job.repo or str(Path.home())
    w(f"\n===== claude-schedule: {job.name} =====")
    w(f"start:   {start.isoformat(timespec='seconds')}")
    w(f"cwd:     {cwd}")
    if job.timeout_seconds:
        w(f"timeout: {job.timeout_seconds}s")

    rc = 1
    _win_keep_awake(True)
    try:
        argv = wrap_keep_awake(build_claude_argv(job))
        w(f"exec:    {argv[0]} ({len(argv)} args)")
        rc = _run_with_timeout(argv, cwd, build_run_env(job), job.timeout_seconds, log)
    except Exception as exc:  # noqa: BLE001 - log and surface as failure, never crash the scheduler
        w(f"error:   {type(exc).__name__}: {exc}")
    finally:
        _win_keep_awake(False)
        end = datetime.now()
        w(f"end:     {end.isoformat(timespec='seconds')} (exit {rc}, {int((end - start).total_seconds())}s)")
        if log is not sys.stdout:
            log.close()
    return rc
