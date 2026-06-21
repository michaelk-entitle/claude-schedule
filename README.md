# claude-schedule

![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Dependencies](https://img.shields.io/badge/runtime%20deps-none-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

Run Claude Code jobs on a **local** schedule — on your own computer, with full repo
access and local MCP servers, without cloud sandbox limits. The machine wakes itself,
runs the job, stays awake only while it runs, then goes back to sleep.

It comes in two halves:

1. **A Claude Code plugin** that *automatically intercepts* schedule creation. When you
   ask Claude to run something on a recurring schedule (the `/loop` → `CronCreate` path),
   a hook steps in, asks you for a timeout, and installs a **persistent** OS-level job in
   place of the ephemeral session-scoped one. You never call a CLI by hand.
2. **A standalone CLI engine** (`claude-schedule`) that does the actual wrapping —
   detects your OS, picks the right scheduler, sets up a wake (it prints the one privileged
   command for you to run, or runs it with `--arm-wake`), keeps the machine awake during the
   run, and enforces a timeout. You can also drive it directly.

> **Why this exists:** Claude Code's built-in `/loop` jobs only fire while the session is
> open and the machine is awake; cloud Routines run remotely and can't touch your local
> repo or MCP servers. There is no built-in way to run a real headless `claude -p` on your
> own machine on a timer that survives logout and sleep. This fills that gap.

---

## How the automatic layer works

```
You: "review this repo every weekday at 9am and write a summary"
      │
      ▼
Claude → CronCreate(0 9 * * 1-5, "review the repo…")
      │
      ▼  PreToolUse hook fires
claude-schedule: ✋ denies the ephemeral schedule, tells Claude:
      "Ask the user for a timeout, then run:
       claude-schedule add --name review… --time 09:00 --days MTWRF --prompt '…' --timeout <TIMEOUT>"
      │
      ▼
Claude: "What timeout should it have? (default 30m)"  →  you answer  →  Claude runs the command
      │
      ▼
A persistent launchd job is installed; the one-time wake command is printed for you. Done.
```

At the scheduled time:

1. `pmset` (macOS) / `rtcwake` (Linux) / Task Scheduler WakeToRun (Windows) **wakes** the machine.
2. `launchd` / `systemd` / `cron` / `schtasks` **starts** the job.
3. `caffeinate` (macOS) / `systemd-inhibit` (Linux) **keeps it awake** only while it runs.
4. `claude -p` runs in your repo with full context; a built-in **timeout** stops a runaway run.
5. The wake lock releases and the OS returns to normal idle sleep.

Ephemeral things are left alone: short interval polls (`*/5 * * * *`) and one-shots pass
through untouched, so Claude's own quick `/loop` keeps working. Cloud `/schedule` routines
aren't blocked (they run remotely) — you just get a note offering the local wrapper instead.

---

## Install

The CLI engine (Python 3.10+, **zero runtime dependencies**):

```bash
pipx install claude-schedule        # recommended (isolated)
# or:  pip install claude-schedule
# or from source:  pipx install /path/to/claude-schedule
```

The plugin (so schedule creation is auto-intercepted):

```text
# in Claude Code:
/plugin marketplace add michaelk-entitle/claude-schedule
/plugin install claude-schedule@claude-schedule
```

Prefer no plugin? Add the same hook to `~/.claude/settings.json` (see
[docs/architecture.md](docs/architecture.md)). The plugin and CLI are independent — the
plugin just shells out to `claude-schedule`.

Check everything is wired up:

```bash
claude-schedule doctor
```

---

## Manual CLI usage

You normally won't need this, but the full engine is yours to drive:

```bash
# Full form
claude-schedule add \
  --name daily-repo-review \
  --time 09:00 \
  --days weekdays \
  --wake-before 1m \
  --timeout 30m \
  --repo /path/to/repo \
  --prompt "Review the repo, find issues, and write a summary"

# One-liners
claude-schedule daily   09:00 --name nightly --repo ~/proj --prompt "Run my local Claude job"
claude-schedule weekdays 08:30 --name standup --repo ~/proj --prompt "Summarize overnight changes"
```

Other commands:

| Command | Purpose |
|---|---|
| `claude-schedule list` | list jobs and whether each is installed |
| `claude-schedule run-now --name X` | run a job immediately (ignores schedule) |
| `claude-schedule logs --name X` | show the tail of a job's log |
| `claude-schedule remove --name X` | uninstall a job (and update the wake slot) |
| `claude-schedule generate ...` | print the exact plist/crontab/units + wake command (dry run) |
| `claude-schedule doctor` | OS / scheduler / wake / timeout support and gotchas |

Add `--dry-run` to `add` to preview without changing anything.

### Useful flags

| Flag | Default | Notes |
|---|---|---|
| `--time HH:MM` | — | 24-hour local time |
| `--days` | `daily` | `MTWRFSU` letters, or `daily` / `weekdays` / `weekends` |
| `--timeout` | `30m` | `30m`, `1h`, `1h30m`, `90s`, or `0` for none |
| `--wake-before` | `1m` | wake this long before the run |
| `--no-wake` | off | don't arm a wake at all (rely on scheduler catch-up) |
| `--arm-wake` | off | run the privileged wake command for you (one sudo prompt); default prints it to run yourself |
| `--repo` | cwd | working directory for the run |
| `--prompt` / `--prompt-file` | — | the task (exactly one) |
| `--permission-mode` | `auto` | `auto` / `default` / `acceptEdits` / `plan` / `bypassPermissions` (see below) |
| `--allowed-tools` | — | e.g. `"Bash(git *),Read,Edit"` |
| `--model` | claude default | `sonnet` / `opus` / `haiku` / `fable` or full name |
| `--bare` | off | skip repo CLAUDE.md/MCP/hooks (needs `ANTHROPIC_API_KEY`) |
| `--env-file` | — | `KEY=VALUE` file loaded before the run |
| `--backend` | auto | force `launchd` / `cron` / `systemd` / `schtasks` |
| `--claude` | auto-detected | path to the `claude` binary |

---

## Permissions (important for unattended runs)

Scheduled jobs default to **`--permission-mode auto`**: Claude acts autonomously on safe
steps and **aborts** on anything risky (it does *not* hang — there's no one to prompt). This
keeps unattended jobs useful out of the box without the all-or-nothing
`--dangerously-skip-permissions` bypass. To change the posture:

- `--permission-mode default` — read-only; aborts on the first action needing approval.
- `--permission-mode plan` — dry-run only, makes no changes.
- `--allowed-tools "Bash(git *),Read,Edit"` — narrow the autonomy to specific tools.

Stored data is private by default. Job specs and logs live under `~/.config/claude-schedule`
(`%APPDATA%` on Windows) with owner-only permissions (`0700` dirs, `0600` files), so your
prompts and run output aren't readable by other local users on a shared machine. And arming a
wake never goes through claude-schedule — `sudo` reads your password directly (see below).

---

## Platform support

| OS | Scheduler | Wake | Keep-awake |
|---|---|---|---|
| macOS (Apple Silicon / Intel) | **launchd** (cron fallback) | `pmset repeat wakeorpoweron` | `caffeinate` |
| Linux | **systemd** user timer (cron fallback) | `rtcwake` (best-effort) | `systemd-inhibit` |
| Windows | Task Scheduler (`schtasks`) | task `-WakeToRun` | `SetThreadExecutionState` |

### The hard truth about sleep vs. shutdown

- **Asleep** → the machine can wake itself for a job. ✅
- **Fully shut down / powered off** → **Apple Silicon cannot auto-power-on.** "Off" must
  mean *asleep*. This is a hardware limitation, not a bug. Keep laptops on **AC power**
  (lid-closed on AC is fine).
- macOS exposes exactly **one** repeating wake slot; claude-schedule manages it as the
  union of all your wake-enabled jobs. Arming it needs root, so by default `add` **prints**
  the one `sudo pmset …` command for you to run yourself (pass `--arm-wake` to have it run
  for you). **claude-schedule never sees or stores your password** — `sudo` reads it directly
  from the terminal, same as Homebrew. See [troubleshooting](docs/troubleshooting.md).
- On Linux, user `systemd` timers can't wake the machine; reliable wake needs a BIOS/RTC
  schedule. The timer uses `Persistent=true`, so a missed run fires as soon as the machine
  is next awake.

See [docs/troubleshooting.md](docs/troubleshooting.md) for fixes to common issues, and
[docs/architecture.md](docs/architecture.md) for the design.

---

## Limitations

- Apple Silicon can't power on from a full shutdown (sleep only).
- One macOS `pmset repeat` slot is shared system-wide; multiple jobs at different times
  wake for the earliest and rely on the scheduler's catch-up for the rest.
- Linux self-wake is best-effort (no clean unattended re-arm without root).
- The Windows backend is implemented but lightly tested.
- The exact `CronCreate` tool-input keys aren't documented; the hook parses defensively and
  fails safe (does nothing) if it can't read the schedule.

## Development

```bash
pip install -e ".[dev]"
pytest            # tests
ruff check .      # lint
mypy claude_schedule   # types
```

CI runs these on macOS + Linux across Python 3.10–3.13 (see `.github/workflows/ci.yml`).

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Changes that keep the tool
dependency-free and the diff small are the easiest to merge.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Michael Kosoy.
