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

Unattended jobs use Claude's **read-only** permissions by default and abort on the first
action needing approval. Give the job permission to act:

```bash
claude-schedule add … --permission-mode acceptEdits          # file edits
claude-schedule add … --allowed-tools "Bash(git *),Read,Edit"  # granular
claude-schedule add … --dangerously-skip-permissions          # full autonomy (trusted machine; not root)
```

If you use `--bare`, Claude skips repo CLAUDE.md/MCP/hooks **and** keychain auth — set
`ANTHROPIC_API_KEY` (e.g. via `--env-file`).

## It keeps asking for a sudo password

Arming a macOS/Linux wake needs root once. At `add` time you're prompted interactively.
If you're in a non-interactive context or decline, the scheduler is still installed — only
the wake isn't armed, and you'll see the exact command to run yourself:

```bash
sudo pmset repeat wakeorpoweron MTWRF 08:59:00   # macOS example
```

Use `--no-wake` to skip wake entirely and rely on the scheduler's catch-up (launchd /
systemd `Persistent`) when the machine is next awake.

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
- `/schedule` (cloud Routines) is **not** intercepted — it runs remotely. You'll get a note
  suggesting the local wrapper instead.

## Remove everything

```bash
claude-schedule remove --name <job>     # one job (also re-syncs the wake slot)
```

Jobs and logs live under `~/.config/claude-schedule` (override with `$CLAUDE_SCHEDULE_HOME`).
launchd plists are in `~/Library/LaunchAgents/com.claude-schedule.*`.
