# Architecture

claude-schedule is deliberately small: a **skill** (instructions) and a **hook** (one
stdlib-only Python file). There is no installable engine — the skill writes the OS artifacts
directly from Bash, so installing the plugin is the only step.

## Files

```
.claude-plugin/        plugin + marketplace manifests
hooks/hooks.json       wires the two hook events to scripts/hook.sh
scripts/
  hook.sh              thin launcher: exec python3 hook.py (exit 0 if no python3)
  hook.py              the hook logic — stdlib only, ~210 LOC
skills/claude-schedule/
  SKILL.md             classify → emit launchd → smoke-test → wake (batch pre-arm) → remove
docs/                  this file + troubleshooting + the seamless-wrapper design note
tests/test_hook.py     hook logic (cron parsing, the steers)
```

## The skill (does the work)

On a scheduling request the skill, straight from Bash:

1. **Classifies** the request — sub-hourly intervals route to `crontab`/`loop`, local-file
   work to a local job, pure remote analysis to cloud — and echoes the decision in one line
   instead of opening tool-picker modals.
2. **Infers** name/repo/days/time/model/permission-mode and asks only the timeout.
3. **Emits** a `launchd` job: a runner script (`/usr/bin/caffeinate -i` to keep the Mac awake
   + a pure-shell timeout guard around `claude -p` — no `timeout`/`gtimeout` dependency) and a
   LaunchAgent plist with `StartCalendarInterval`, loaded via `launchctl bootstrap gui/$UID`.
4. **Smoke-tests** with `launchctl kickstart -k` and tails the log.

Default is **no-wake** (zero `sudo`). Wake-from-sleep, managed-Mac (EPM) handling, and removal
live in `SKILL.md` (Steps 4–5); wake uses batch pre-arm — one approval per job, no IT. macOS-only by design.

### Why launchd
It survives reboots and runs missed `StartCalendarInterval` jobs on the next wake — built-in
catch-up that covers a wake firing late, or a no-wake job that was asleep at the scheduled time.

## The hook (keeps Claude on the rails)

`scripts/hook.py`, wired by `hooks/hooks.json` through `hook.sh`. Pure text steering — hooks
have no TTY and can't call tools. Anything unrecognized → exit 0, so native scheduling is
never broken.

- **`PreToolUse` on `CronCreate`.** A recurring clock-time `/loop` is denied (it's
  session-scoped and can't wake the machine); the denial reason tells Claude to use the
  **skill** for a persistent job instead. Interval polls and one-shots pass through. A 120s
  per-(session,cron) marker prevents a deny-loop: re-issuing the same schedule is allowed, so
  a genuinely-wanted ephemeral loop still works.
- **`UserPromptSubmit` on `/schedule`.** Injects context steering Claude to a local job via
  the skill rather than a remote cloud routine, unless the user explicitly wants cloud. Cloud
  routine creation isn't a tool call, so this is a steer, not a hard block.
