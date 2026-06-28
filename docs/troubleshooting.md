# Troubleshooting

Jobs are `launchd` LaunchAgents (`com.claude-schedule.<name>`); the runner + log live under
`~/Library/Application Support/claude-schedule/`.

## The job didn't run

1. **Was the machine on?** Fully shut down (not asleep) can't run, and Apple Silicon can't
   power itself on. "Off" must mean *asleep*. Default jobs are no-wake — they run on the next
   wake via launchd catch-up.
2. **Is it loaded?** `launchctl print gui/$(id -u)/com.claude-schedule.<name>` shows the
   state and the last exit code.
3. **Check the log.** `~/Library/Application Support/claude-schedule/<name>.log`.

## "claude: command not found" in the log

launchd runs with a bare `PATH`. The skill bakes the **absolute** claude path into the runner
and sets `PATH` in the plist, so this shouldn't happen — but the `claude` you type may be a
shell *function*; the real binary is usually `~/.local/bin/claude`. If you moved it, re-create
the job so the skill re-resolves the path.

## The run aborts immediately / does nothing useful

Unattended runs use `--permission-mode auto`: autonomous on safe steps, aborts on risky ones
(no TTY to approve). If the task needs to edit files or run commands, have the skill use
`--permission-mode acceptEdits` (or narrow it with `--allowed-tools`).

## Does claude-schedule have my (or my users') password?

**No.** It never reads, stores, or transmits a password. Default jobs need no `sudo` at all.
Wake-from-sleep is opt-in and the skill only **prints** the `sudo pmset …` command — you run
it, and `sudo` reads the password directly. Same trust model as Homebrew. It never writes a
`sudoers` file. Stored runners/logs are owner-only (`0700`/`0600`).

## The wake doesn't happen (macOS)

- Default is **no-wake**. To wake from sleep, run the one command the skill printed:
  `sudo pmset repeat wakeorpoweron MTWRF 08:59:00` (a repeating wake — once covers all runs).
- macOS has **one** repeating wake slot; check it with `pmset -g sched`.
- **Managed Mac (EPM / MDM):** the prompt is a corporate "Confirm Operation"
  dialog, not a password — a local `sudoers` rule can't suppress it. Ask IT to whitelist
  `pmset`. You can still use the job with no-wake.
- Laptops on battery may sleep deeply; keep on AC for reliable wake.

## The job ran forever / drained the battery

The runner has a pure-shell timeout guard (default 30m) that kills the run on expiry. Lower
the timeout when re-creating the job.

## The hook didn't intercept my schedule

- The plugin must be enabled (`/plugin` → enabled list) and `python3` must be on `PATH`
  (`scripts/hook.sh` exits 0 if it isn't — failing safe).
- Only **recurring clock-time** schedules are intercepted. Interval polls (`*/5 * * * *`) and
  one-shots are left to the native ephemeral `/loop`.
- `/schedule` (cloud Routines) can't be hard-intercepted — its creation isn't a tool call.
  The `UserPromptSubmit` hook *steers* Claude to a local job instead, unless you explicitly
  ask for cloud.

## Remove a job

```bash
NAME=daily-review; LABEL=com.claude-schedule.$NAME
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f ~/Library/LaunchAgents/$LABEL.plist \
      ~/Library/"Application Support"/claude-schedule/$NAME.{sh,log}
# if you armed a wake and no other job needs it: sudo pmset repeat cancel
```
