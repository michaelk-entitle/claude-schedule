# Architecture

Two cleanly separated halves: a **plugin front door** (hook) and a **CLI engine**. The
plugin only steers Claude with text and shells out to the engine; the engine does all the
real work and is fully usable on its own.

## Module map

```
claude_schedule/
  cli.py            argparse front end; builds a JobSpec, drives backends, prints results
  hook.py           Claude Code hook entrypoint (PreToolUse CronCreate + UserPromptSubmit)
  jobspec.py        JobSpec model + parsing/validation (days, time, duration)
  environment.py    detect OS / arch / claude / schedulers / wake / timeout / privileges
  registry.py       on-disk job + log store (~/.config/claude-schedule)
  runner.py         the "_run" path: build claude argv, keep-awake, timeout, logging
  doctor.py         diagnostics report
  backends/
    base.py         SchedulerBackend + WakeBackend ABCs, result dataclasses
    launchd.py      macOS LaunchAgent
    cron.py         crontab (Linux fallback / macOS alternative)
    systemd.py      Linux user timer + service
    windows.py      Task Scheduler via PowerShell
    wake.py         MacWake (pmset) / LinuxWake (rtcwake) / WindowsWake / NoopWake
    __init__.py     select_scheduler() / select_wake() factories
```

## Three independent concerns

The design deliberately keeps these apart (per the project goals):

1. **Command wrapping** (`runner.build_claude_argv`) — turning a `JobSpec` into a
   `claude -p …` argv. No shell, so no quoting risk.
2. **Scheduler installation** (`backends/*`) — *when* the job runs. Each backend receives
   an opaque `run_argv` and formats it for its system. Selection is by environment, with an
   explicit override.
3. **Wake scheduling** (`backends/wake.py`) — *whether the machine is awake* then. Separate
   from the scheduler because it has different lifecycle and privilege needs (sudo).

A fourth concern, **keep-awake during the run**, lives in the runner (caffeinate /
systemd-inhibit / Windows API) because it must wrap the live process.

## What the scheduler actually invokes

Every backend schedules the same simple command:

```
<python> -m claude_schedule _run --name <job>
```

`_run` (in `runner.py`) loads the stored `JobSpec` and:

1. Builds the `claude` argv from the spec.
2. Wraps it to keep the machine awake (`caffeinate -i -s …` / `systemd-inhibit …`).
3. Runs it in its own process group with an **in-process timeout** (no dependency on
   `timeout`/`gtimeout`): on expiry it sends `SIGTERM` to the group, then `SIGKILL`.
4. Appends a timestamped record (start, cwd, exit code, duration) to the job log; the
   child's stdout/stderr also go there. Exit code is propagated (`124` on timeout).

This centralizes execution so timeout/keep-awake/logging are identical across schedulers
and across OSes, and are unit-testable without installing anything.

## Why launchd over cron on macOS

launchd survives reboots and **runs missed `StartCalendarInterval` jobs on the next wake**.
That catch-up means the wake mechanism is a timeliness optimization, not a correctness
requirement — if a wake fires late or not at all, launchd still runs the job when the
machine next comes up. systemd timers get the same property via `Persistent=true`. Plain
cron does **not** catch up, so it's a fallback only.

## The hook flow (plugin front door)

`hooks/hooks.json` registers two events, both routed through `scripts/hook.sh` →
`claude-schedule _hook`:

- **`PreToolUse` matcher `CronCreate`.** For a *recurring clock-time* schedule, the hook
  returns `permissionDecision: "deny"` with a reason that hands Claude a ready-to-run
  `claude-schedule add …` (timeout left as `<TIMEOUT>`). Hooks have no TTY and can't call
  tools, so this text-steering is the supported pattern: Claude relays the timeout question,
  the user answers, Claude runs the command. Ephemeral interval/one-shot schedules are
  allowed through untouched. A 120s marker prevents a deny-loop if the user explicitly wants
  the ephemeral version (re-issuing the same schedule is then allowed).
- **`UserPromptSubmit`.** If the prompt mentions `/schedule` (cloud Routines), it injects
  context steering Claude to set up a local job via `claude-schedule add` instead — unless
  the user explicitly wants cloud execution. Cloud routine creation isn't a tool call (no
  hook fires on it), so this is a steer, not a hard block.

`hook.sh` fails safe: if the engine isn't installed, it exits 0 so native scheduling is
never broken.

## Data model

A `JobSpec` (see `jobspec.py`) is the single source of truth, serialized to
`~/.config/claude-schedule/jobs/<name>.json`. Days are stored canonically as `0=Mon … 6=Sun`;
each backend converts (launchd/cron `0/7=Sun`, systemd `Mon..Sun`, Windows `MON..SUN`,
pmset `MTWRFSU`). Paths are resolved to absolutes at `add` time, in the user's full
environment, because the scheduler runs later with a bare `PATH`.
