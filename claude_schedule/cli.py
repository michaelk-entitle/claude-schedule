"""Command-line interface.

This is the *engine* surface. End users normally never type these commands —
the Claude Code plugin hook (see ``hook.py``) calls ``add`` for them when they
create a scheduled job. The commands remain available for manual use and debugging.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from claude_schedule import __version__, hook, registry, runner
from claude_schedule.backends import select_scheduler, select_wake
from claude_schedule.backends.base import InstallResult, SchedulerBackend, WakeBackend, WakeResult
from claude_schedule.doctor import run_doctor
from claude_schedule.environment import Environment, detect, resolve_claude
from claude_schedule.jobspec import JobSpec, format_duration, parse_days, parse_duration, parse_time
from claude_schedule.runner import build_claude_argv


class CliError(Exception):
    """A user-facing error; printed without a traceback."""


# -- argument wiring ------------------------------------------------------


def _add_common_job_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", help="unique job name (letters/digits/._-)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--prompt", help="the prompt text for claude -p")
    g.add_argument("--prompt-file", help="path to a file containing the prompt")
    p.add_argument("--repo", help="working directory for the run (default: current directory)")
    p.add_argument("--timeout", default="30m", help="max run time: 30m, 1h, 1h30m, or 0 for none (default 30m)")
    p.add_argument("--wake-before", default="1m", help="wake the machine this long before the run (default 1m)")
    p.add_argument("--no-wake", action="store_true", help="do not schedule a wake at all")
    p.add_argument(
        "--arm-wake",
        action="store_true",
        help="run the privileged wake command for you (one sudo prompt); default just prints it to run yourself",
    )
    p.add_argument("--model", help="claude model alias (sonnet/opus/haiku/fable) or full name")
    p.add_argument(
        "--permission-mode",
        default="auto",
        help="default|acceptEdits|plan|auto|dontAsk|bypassPermissions (default: auto)",
    )
    p.add_argument("--allowed-tools", help="pre-approve tools, e.g. 'Bash,Read,Edit' or 'Bash(git *),Read'")
    p.add_argument(
        "--bare", action="store_true",
        help="claude --bare: skip repo CLAUDE.md/MCP/hooks (needs ANTHROPIC_API_KEY)",
    )
    p.add_argument("--output-format", choices=["text", "json", "stream-json"], help="claude --output-format")
    p.add_argument("--env-file", help="file of KEY=VALUE lines to load before running")
    p.add_argument("--log", help="log file path (default: <config>/logs/<name>.log)")
    p.add_argument("--backend", choices=["launchd", "cron", "systemd", "schtasks"], help="override the scheduler")
    p.add_argument("--claude", help="path to the claude binary (default: auto-detect)")
    p.add_argument(
        "--claude-arg", action="append", default=[], dest="extra_args",
        help="extra arg passed to claude (repeatable)",
    )
    p.add_argument("--dry-run", action="store_true", help="print what would be created; change nothing")
    p.add_argument("--force", action="store_true", help="replace an existing job with the same name")


def _add_full_add_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--time", help="run time, 24-hour HH:MM (e.g. 09:00)")
    p.add_argument("--days", default="daily", help="MTWRFSU letters or alias daily/weekdays/weekends (default daily)")
    _add_common_job_args(p)


def _add_sugar_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("at", help="run time, 24-hour HH:MM")
    _add_common_job_args(p)


# -- building a JobSpec from args -----------------------------------------


def _abs(path: str | None) -> str | None:
    return str(Path(path).expanduser().resolve()) if path else None


def _build_job(args: argparse.Namespace, env: Environment) -> JobSpec:
    if not getattr(args, "name", None):
        raise CliError("--name is required")
    time_str = getattr(args, "time", None)
    if not time_str:
        raise CliError("--time is required (24-hour HH:MM)")
    hour, minute = parse_time(time_str)
    days = parse_days(getattr(args, "days", "daily"))
    claude_path = resolve_claude(args.claude) or (args.claude or "")
    log_path = str(Path(args.log).expanduser()) if args.log else registry.default_log_path(args.name)
    job = JobSpec(
        name=args.name,
        hour=hour,
        minute=minute,
        days=days,
        claude_path=claude_path,
        prompt=args.prompt,
        prompt_file=_abs(args.prompt_file),
        repo=_abs(args.repo) or os.getcwd(),
        model=args.model,
        permission_mode=args.permission_mode,
        allowed_tools=args.allowed_tools,
        bare=args.bare,
        output_format=args.output_format,
        extra_args=list(args.extra_args or []),
        timeout_seconds=parse_duration(args.timeout),
        env_file=_abs(args.env_file),
        log_path=log_path,
        node_bin_dir=env.node_bin_dir,
        backend=args.backend or env.default_scheduler,
        wake=not args.no_wake,
        wake_before_seconds=parse_duration(args.wake_before),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    job.validate()
    return job


# -- printers -------------------------------------------------------------


def _print_dry_run(job: JobSpec, scheduler: SchedulerBackend, wake: WakeBackend, run_argv: list[str]) -> None:
    print("DRY RUN — nothing will be changed.\n")
    wake_s = "on" if job.wake else "off"
    print(f"Job '{job.name}': {job.schedule_summary()}  "
          f"(backend={scheduler.name}, wake={wake_s}, timeout={format_duration(job.timeout_seconds)})")
    print(f"claude argv: {build_claude_argv(job)}")
    print(f"scheduler invokes: {' '.join(run_argv)}\n")
    for art in scheduler.generate(job, run_argv):
        print(f"# {art.label}" + (f"  ->  {art.path}" if art.path else ""))
        print(art.content.rstrip("\n"))
        print()
    if job.wake:
        wr = wake.plan([job])
        print("# wake plan")
        for c in wr.commands:
            print(f"$ {c}")
        for note in wr.notes:
            print(f"  note: {note}")


def _print_install_result(job: JobSpec, result: InstallResult) -> None:
    print(f"Installed '{job.name}' via {result.backend}.")
    for art in result.artifacts:
        if art.path:
            print(f"  wrote {art.path}")
    for c in result.commands_run:
        print(f"  $ {c}")
    for note in result.notes:
        print(f"  note: {note}")


def _print_wake_result(wr: WakeResult) -> None:
    if not wr.commands and not wr.notes:
        return
    print(f"  wake ({wr.backend}): {'armed' if wr.ran else 'not armed'}")
    for c in wr.commands:
        print(f"    $ {c}")
    for note in wr.notes:
        print(f"    note: {note}")


def _apply_wake(jobs: list[JobSpec], arm: bool, wake: WakeBackend) -> None:
    """Arm the wake only if explicitly asked (--arm-wake); otherwise print the one
    privileged command for the user to run themselves. claude-schedule never reads
    or stores the password either way — sudo prompts on the terminal directly."""
    if arm:
        _print_wake_result(wake.sync(jobs))
        return
    wr = wake.plan(jobs)
    if wr.commands:
        print("  wake: not armed (no password needed). To wake the machine from sleep, run this once yourself:")
        for c in wr.commands:
            print(f"    $ {c}")
        print("    The password goes straight to sudo — claude-schedule never sees it. "
              "(Or re-run with --arm-wake to have it run for you.)")
    for note in wr.notes:
        print(f"    note: {note}")


# -- command handlers -----------------------------------------------------


def cmd_add(args: argparse.Namespace, dry: bool = False) -> int:
    env = detect(with_claude_version=False)
    job = _build_job(args, env)
    scheduler = select_scheduler(env, job.backend)
    wake = select_wake(env)
    run_argv = [env.python_executable, "-m", "claude_schedule", "_run", "--name", job.name]

    if dry or args.dry_run:
        _print_dry_run(job, scheduler, wake, run_argv)
        return 0

    if registry.job_exists(job.name) and not args.force:
        raise CliError(f"job {job.name!r} already exists; pass --force to replace it, or 'remove' it first")

    registry.save_job(job)
    _print_install_result(job, scheduler.install(job, run_argv))

    if job.wake and wake.supported:
        _apply_wake([j for j in registry.list_jobs() if j.wake], args.arm_wake, wake)
    elif job.wake:
        print(f"  wake: not supported on {env.system}; relying on scheduler catch-up.")

    print(f"\nDone. '{job.name}' runs {job.schedule_summary()}. Logs: {job.log_path}")
    print(f"Test it now:  claude-schedule run-now --name {job.name}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    return cmd_add(args, dry=True)


def cmd_daily(args: argparse.Namespace) -> int:
    args.time = args.at
    args.days = "daily"
    if not args.name:
        args.name = "daily"
    return cmd_add(args)


def cmd_weekdays(args: argparse.Namespace) -> int:
    args.time = args.at
    args.days = "weekdays"
    if not args.name:
        args.name = "weekdays"
    return cmd_add(args)


def cmd_remove(args: argparse.Namespace) -> int:
    env = detect(with_claude_version=False)
    try:
        job = registry.load_job(args.name)
        backend_name = job.backend
    except FileNotFoundError:
        job = None
        backend_name = env.default_scheduler
    result = select_scheduler(env, backend_name).uninstall(args.name)
    registry.delete_job(args.name)

    print(f"Removed '{args.name}' ({result.backend}).")
    for c in result.commands_run:
        print(f"  $ {c}")
    for note in result.notes:
        print(f"  note: {note}")

    wake = select_wake(env)
    if wake.supported:
        remaining = [j for j in registry.list_jobs() if j.wake]
        if remaining:
            _apply_wake(remaining, getattr(args, "arm_wake", False), wake)
        elif job and job.wake:
            # only touch the shared wake slot if this job actually armed one; plan([]) shows the cancel command
            _apply_wake([], getattr(args, "arm_wake", False), wake)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    env = detect(with_claude_version=False)
    jobs = registry.list_jobs()
    if not jobs:
        print("No jobs yet.")
        return 0
    for j in jobs:
        try:
            installed = select_scheduler(env, j.backend).is_installed(j.name)
        except (RuntimeError, ValueError):
            installed = False
        mark = "●" if installed else "○"
        preview = (j.prompt or (f"@{j.prompt_file}" if j.prompt_file else "")).replace("\n", " ")[:60]
        print(f"{mark} {j.name}")
        wake_s = "on" if j.wake else "off"
        print(f"    when:    {j.schedule_summary()}   backend={j.backend}  "
              f"wake={wake_s}  timeout={format_duration(j.timeout_seconds)}")
        print(f"    repo:    {j.repo}")
        print(f"    prompt:  {preview}")
        print(f"    log:     {j.log_path}")
    print("\n● installed   ○ recorded but not installed")
    return 0


def cmd_run_now(args: argparse.Namespace) -> int:
    print(f"Running '{args.name}' now…")
    rc = runner.run_job(args.name)
    job = registry.load_job(args.name)
    print(f"\nExit code: {rc}.  Log: {job.log_path}")
    p = Path(job.log_path)
    if p.is_file():
        print("--- last 20 log lines ---")
        print("\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]))
    return rc


def cmd_logs(args: argparse.Namespace) -> int:
    job = registry.load_job(args.name)
    p = Path(job.log_path)
    if not p.is_file():
        print(f"(no log yet at {p})")
        return 0
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()[-args.lines :]:
        print(ln)
    return 0


def cmd_run_internal(args: argparse.Namespace) -> int:
    return runner.run_job(args.name)


def cmd_hook(args: argparse.Namespace) -> int:
    return hook.handle(args.event)


# -- parser + entrypoint --------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude-schedule", description="Run Claude Code jobs on a local schedule.")
    p.add_argument("--version", action="version", version=f"claude-schedule {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("doctor", help="check OS, claude, scheduler, wake, timeout support").set_defaults(
        func=lambda a: run_doctor()
    )

    padd = sub.add_parser("add", help="add a scheduled job")
    _add_full_add_args(padd)
    padd.set_defaults(func=cmd_add)

    pgen = sub.add_parser("generate", help="print what 'add' would create (dry run)")
    _add_full_add_args(pgen)
    pgen.set_defaults(func=cmd_generate)

    pdaily = sub.add_parser("daily", help="shortcut: run every day at TIME")
    _add_sugar_args(pdaily)
    pdaily.set_defaults(func=cmd_daily)

    pweek = sub.add_parser("weekdays", help="shortcut: run Mon–Fri at TIME")
    _add_sugar_args(pweek)
    pweek.set_defaults(func=cmd_weekdays)

    prm = sub.add_parser("remove", aliases=["rm"], help="remove a job")
    prm.add_argument("--name", required=True)
    prm.add_argument(
        "--arm-wake", action="store_true",
        help="run the privileged wake re-sync for you (sudo); default prints it",
    )
    prm.set_defaults(func=cmd_remove)

    sub.add_parser("list", aliases=["ls"], help="list jobs").set_defaults(func=cmd_list)

    prun = sub.add_parser("run-now", help="run a job immediately (ignores schedule)")
    prun.add_argument("--name", required=True)
    prun.set_defaults(func=cmd_run_now)

    plogs = sub.add_parser("logs", help="show the tail of a job's log")
    plogs.add_argument("--name", required=True)
    plogs.add_argument("--lines", type=int, default=40)
    plogs.set_defaults(func=cmd_logs)

    prun2 = sub.add_parser("_run", help=argparse.SUPPRESS)  # internal: invoked by the scheduler
    prun2.add_argument("--name", required=True)
    prun2.set_defaults(func=cmd_run_internal)

    phook = sub.add_parser("_hook", help=argparse.SUPPRESS)  # internal: invoked by the plugin hook
    phook.add_argument("--event", default=None)
    phook.set_defaults(func=cmd_hook)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 1
    try:
        return args.func(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
