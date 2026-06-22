# Troubleshooting

Start with `claude-schedule doctor` — it reports OS, the chosen scheduler, wake/keep-awake
support, privileges, and the known gotchas for your platform.

## The job didn't run at all

1. **Was the machine on?** If it was fully shut down (not asleep), it cannot run — and on
   Apple Silicon it cannot power itself on. "Off" must mean *asleep*.
2. **Is it installed?** `claude-schedule list` — a `●` means installed, `○` means recorded
   but not active. Re-run `add` (with `--force`) if it shows `○`.
3. **Check the logs.** `claude-schedule logs --name <job>`. The launchd wrapper's own
   stdout/stderr goes to the sibling `*.launchd.log` next to the job log.
4. **macOS:** `launchctl print gui/$(id -u)/com.claude-schedule.<name>` shows state and the
   last exit code.
5. **Linux:** `systemctl --user list-timers | grep claude-schedule` and
   `journalctl --user -u claude-schedule-<name>.service`.

## "claude: command not found" in the log

The scheduler runs with a bare `PATH` that doesn't include `~/.local/bin` or your nvm node.
claude-schedule bakes the **absolute** claude path and prepends node's directory, so this
should not happen — but if you moved the binary, re-run `add` (it re-resolves the path), or
pass `--claude /abs/path/to/claude`.

## The run aborts immediately / does nothing useful

Unattended jobs default to `--permission-mode auto`: Claude acts autonomously on safe steps
and aborts on anything risky. Change the posture if you want:

```bash
claude-schedule add … --permission-mode default              # read-only (aborts on first action)
claude-schedule add … --permission-mode plan                 # dry-run only
claude-schedule add … --allowed-tools "Bash(git *),Read,Edit"  # narrow the autonomy
```

If you use `--bare`, Claude skips repo CLAUDE.md/MCP/hooks **and** keychain auth — set
`ANTHROPIC_API_KEY` (e.g. via `--env-file`).

## Does claude-schedule have my (or my users') password?

**No.** It never reads, stores, logs, or transmits a password. Arming a wake on macOS/Linux
needs root, so it runs `sudo pmset …` / `sudo rtcwake …` — and `sudo` (the OS's own program)
reads the password directly from the terminal. The password never passes through
claude-schedule. Same trust model as Homebrew or any installer that calls sudo. And by
default claude-schedule doesn't even run sudo for you (see below).

Stored jobs and logs are kept owner-only too: the config dir is `0700` and job specs / logs
are `0600`, so your prompts and run output aren't readable by other users on a shared machine.

## Arming the wake

By default `add` does **not** run sudo. It installs the scheduler (no privileges needed) and
**prints** the one privileged command for you to run once yourself:

```bash
sudo pmset repeat wakeorpoweron MTWRF 08:59:00   # macOS example — run this once to enable wake
```

Run that and wake-from-sleep is enabled (it persists forever; you won't be asked again).
Prefer claude-schedule to run it for you? Pass `--arm-wake` and you'll get a single sudo
prompt. Don't want self-wake at all? Use `--no-wake` and rely on launchd/systemd catch-up
(the job runs when the machine is next awake).

## The wake doesn't happen (macOS)

- macOS has **one** repeating wake slot. claude-schedule sets it to the earliest wake time
  across all wake-enabled jobs. Jobs at later times rely on launchd catch-up.
- Check it: `pmset -g sched`. If a *different* repeat schedule is there, something else
  (or you) set it — claude-schedule owns the single slot when it arms one.
- Laptops on battery may still sleep deeply; keep on AC for reliable wake.

## The wake doesn't happen (Linux)

User `systemd` timers cannot wake the machine. Options:
- Configure an RTC/BIOS wake out of band.
- Rely on `Persistent=true`: the job runs as soon as the machine is next awake.
- For jobs to run while logged out: `loginctl enable-linger $USER`.

## The job ran forever / drained the battery

Set a `--timeout` (default `30m`). On expiry the whole process group is terminated and the
keep-awake lock is released. `--timeout 0` disables it (not recommended for unattended jobs).

## The hook didn't intercept my schedule

- The plugin must be enabled (`/plugin` → enabled list) and `claude-schedule` installed
  (`command -v claude-schedule`). The hook fails safe — if the engine is missing it does
  nothing.
- Only **recurring clock-time** schedules are intercepted. Interval polls (`*/5 * * * *`)
  and one-shots are intentionally left to the native ephemeral loop.
- `/schedule` (cloud Routines) can't be hard-intercepted — its creation isn't a tool call,
  so no hook fires on it. Instead the `UserPromptSubmit` hook steers Claude to set up a local
  job when you type `/schedule`, unless you explicitly ask for cloud execution.

## Remove everything

```bash
claude-schedule remove --name <job>     # one job (also re-syncs the wake slot)
```

Jobs and logs live under `~/.config/claude-schedule` (override with `$CLAUDE_SCHEDULE_HOME`).
launchd plists are in `~/Library/LaunchAgents/com.claude-schedule.*`.
