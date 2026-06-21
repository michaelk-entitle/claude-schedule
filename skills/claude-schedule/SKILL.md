---
name: claude-schedule
description: Use when the user wants a Claude Code job to run on a recurring LOCAL schedule on their own machine (daily/weekly at a clock time) that survives closing the session, wakes the computer, and times out. Also used when the PreToolUse hook denies a CronCreate and asks to set up a persistent job. Translates the request into a persistent OS-level job via the claude-schedule CLI.
---

# claude-schedule — persistent local schedules

Claude Code's built-in `/loop` schedules are **session-scoped**: they stop when the
session exits and cannot wake a sleeping machine. This skill installs a **persistent**
OS-level job (launchd / cron / systemd / Windows Task Scheduler) that wakes the machine,
keeps it awake during the run (caffeinate / systemd-inhibit), and enforces a timeout.

## When to use
- The user asks to run a Claude job daily/weekly at a clock time on **this** machine.
- The `PreToolUse` hook denied a `CronCreate` and asked you to set up a persistent job.

## How to set one up
1. **Confirm the timeout** with the user (suggest `30m`). Also ask whether the job needs
   to edit files or run commands — unattended runs are read-only by default and abort on
   the first action that needs approval (see Permissions).
2. Run the CLI (it auto-detects OS, scheduler, and wake support):

   ```bash
   claude-schedule add \
     --name <slug> \
     --time HH:MM \
     --days <MTWRFSU | daily | weekdays | weekends> \
     --repo <path-to-repo> \
     --prompt "<the task>" \
     --timeout 30m
   ```
3. Tell the user it's installed, and how to test immediately:
   `claude-schedule run-now --name <slug>`.

Tip: add `--dry-run` to preview the exact plist/crontab/units and wake command without
changing anything.

## Day letters
`M`=Mon `T`=Tue `W`=Wed `R`=Thu `F`=Fri `S`=Sat `U`=Sun. Aliases: `daily`, `weekdays`, `weekends`.

## Permissions for unattended runs
Jobs default to `--permission-mode auto`: Claude acts autonomously on safe steps and aborts
on anything risky (no TTY to prompt). To change it:
- `--permission-mode default` — read-only; aborts on the first action needing approval.
- `--permission-mode plan` — dry-run only.
- `--allowed-tools "Bash(git *),Read,Edit"` — narrow the autonomy to specific tools.

## Managing jobs
- `claude-schedule list` — jobs and whether they are installed.
- `claude-schedule logs --name <slug>` — recent output.
- `claude-schedule remove --name <slug>` — uninstall.
- `claude-schedule doctor` — OS / scheduler / wake support and gotchas.

## macOS note
Arming the wake needs root once. By default `add` prints the `sudo pmset …` command for the
user to run themselves (pass `--arm-wake` to have the CLI run it). claude-schedule never sees
the password — `sudo` reads it directly. Apple Silicon wakes from **sleep** only — it cannot
power on from a full shutdown. Keep laptops on AC power.
