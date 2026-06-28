---
name: claude-schedule
description: Schedule a Claude Code job to run on THIS Mac on a recurring clock schedule — "run X every weekday at 9am", tasks that must survive the session closing, or tasks that need local repo + file access. macOS/launchd only. Can wake the Mac from sleep (not from full power-off). Invoke when the user says /schedule, wants a recurring /loop that persists, or asks to "run X every [day/time]".
---

# claude-schedule — persistent local Claude jobs on macOS

Turn "run this every weekday at 9am" into a real launchd job that survives session close and sleep — using only Bash, nothing to install.

**Infer and act.** Ask at most one question (timeout). Don't open modals or list options.

---

## Step 0 — classify (one-line echo)

| Request | Route |
|---|---|
| Interval < 1 hour | Not this skill. Offer a plain `crontab` line or `/loop`. Say so once, stop. |
| Needs local repo / local MCP | **This skill.** Cloud sandbox can't reach the disk. |
| Pure remote, ≥ 1h | Default to this skill; mention cloud `/schedule` only if asked. |
| Clock-time, persistent, local | **This skill.** Happy path. |

---

## Step 1 — infer, ask at most one thing

From the request infer:
- **NAME** — slug (e.g. `daily-review`)
- **HOUR / MIN** — 24h clock
- **WEEKDAYS** — launchd numbers: Mon=1 Tue=2 Wed=3 Thu=4 Fri=5 Sat=6 Sun=0; weekdays = `1 2 3 4 5`; every day = `""`
- **REPO** — cwd unless stated
- **PERM** — default `auto`
- **PROMPT** — the `claude -p` prompt text

Ask **only** the timeout if not given. Suggest `30m`. Don't ask anything else.

---

## Step 2 — install the job

Fill in the variables, then run the block as-is. The runner needs no privileges — `caffeinate` keeps the Mac awake during the run, a pure-shell guard bounds it by `$TIMEOUT`. Waking the Mac from sleep is handled separately in Step 4 (no daily sudo).

```bash
NAME="daily-review"
HOUR=9; MIN=0
WEEKDAYS="1 2 3 4 5"          # "" = every day
REPO="$HOME/Projects/myrepo"
TIMEOUT=1800                   # seconds
PROMPT='Review today'\''s changes and post a summary.'
PERM=auto                      # auto | acceptEdits | default | plan

# resolve real claude binary
CLAUDE="$(command -v claude 2>/dev/null)"
case "$CLAUDE" in /*) ;; *)
  for c in "$HOME/.local/bin/claude" /opt/homebrew/bin/claude /usr/local/bin/claude; do
    [ -x "$c" ] && CLAUDE="$c" && break
  done;;
esac

LABEL="com.claude-schedule.$NAME"
DIR="$HOME/Library/Application Support/claude-schedule"; mkdir -p "$DIR"
RUN="$DIR/$NAME.sh"; LOG="$DIR/$NAME.log"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# runner: caffeinate keeps the Mac awake for the run; pure-shell timeout guard (no deps, no sudo)
# For a long prompt with quotes, write it to "$DIR/$NAME.prompt.md" and use
#   "$CLAUDE" -p "$(cat '$DIR/$NAME.prompt.md')" ...   instead of the inline PROMPT.
cat > "$RUN" <<RUNNER
#!/bin/sh
cd "$REPO" 2>/dev/null
"$CLAUDE" -p '$PROMPT' --permission-mode $PERM &
pid=\$!
( sleep $TIMEOUT; kill \$pid 2>/dev/null ) & watcher=\$!
wait \$pid; rc=\$?
kill \$watcher 2>/dev/null
echo "[claude-schedule] $NAME exited rc=\$rc at \$(date)"
exit \$rc
RUNNER
chmod +x "$RUN"

# build StartCalendarInterval XML
INTERVAL=""
while IFS= read -r wd; do
  [ -n "$wd" ] || continue
  INTERVAL="$INTERVAL<dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MIN</integer></dict>"
done <<DAYS
$(printf '%s' "$WEEKDAYS" | tr ' ' '\n')
DAYS
if [ -n "$INTERVAL" ]; then INTERVAL="<array>$INTERVAL</array>"
else INTERVAL="<dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MIN</integer></dict>"; fi

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/caffeinate</string><string>-i</string><string>/bin/sh</string><string>$RUN</string></array>
  <key>StartCalendarInterval</key>$INTERVAL
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/Users/$USER/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
</dict></plist>
PLIST

if plutil -lint "$PLIST" >/dev/null; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
  launchctl bootstrap "gui/$(id -u)" "$PLIST" && echo "installed $LABEL ($HOUR:$MIN, log: $LOG)"
else
  echo "plist invalid — not installing"; cat "$PLIST"
fi
```

---

## Step 3 — smoke-test

Fire it once immediately, then show the log tail:

```bash
launchctl kickstart -k "gui/$(id -u)/com.claude-schedule.$NAME"
sleep 2
tail -n 20 "$HOME/Library/Application Support/claude-schedule/$NAME.log"
```

Tell the user: job installed, next scheduled run, log path, how to remove (Step 5).

---

## Step 4 — wake from sleep (batch pre-arm — one approval per job, no IT)

**Default is no-wake**: the job runs if the Mac is awake at its time; launchd runs a missed job on the next wake. Offer wake only if the user wants the Mac to wake *itself*.

> **Apple Silicon: wakes from sleep only — cannot power on from a full shutdown. Keep the Mac on AC power (lid-closed on AC is fine).**

**How it works — and why this approach.** `pmset schedule` holds a *list* of one-time wake entries (unlike `pmset repeat`, which has a single global slot). So this job pre-arms many days of wakes at its own time in **one `sudo` call** = **one approval**. Multiple jobs at different times each pre-arm their own entries; they coexist — 3 jobs at 9:00 / 11:00 / 12:00 → 3 approvals total, once, at creation, and the Mac wakes at all three times.

On a managed Mac (EPM / MDM) that one `sudo` triggers a "Confirm Operation" dialog the user approves by hand — **no passwordless sudoers, no IT request**. The runner itself never calls sudo (it's unattended and would be blocked), so there's no daily prompt.

The pre-armed list covers a **horizon** (default 60 days), then lapses — re-run the same command to renew (one approval again). The wake fires **every day** at the time; the job still only *runs* on its scheduled `WEEKDAYS` because launchd enforces that — so a weekday-only job may wake the Mac on a weekend, find nothing to do, and idle back to sleep (a harmless extra wake, traded for a dead-simple command).

Compute and print this job's batch command (the user runs it once and approves — **never run `sudo` yourself**):

```bash
HORIZON=60        # days of wakes to pre-arm in one approval
TIME_STR=$(printf '%02d:%02d:00' "$HOUR" "$MIN")
printf '\nRun once and approve the EPM dialog — pre-arms %d days of %s wakes for "%s":\n' "$HORIZON" "$TIME_STR" "$NAME"
printf '  sudo sh -c '\''for d in $(seq 0 %d); do pmset schedule wakeorpoweron "$(date -v+${d}d "+%%m/%%d/%%y %s")"; done'\''\n' "$((HORIZON-1))" "$TIME_STR"
printf '(One approval = %d days. Re-run to renew. Other jobs at other times keep their own wake entries — this only adds.)\n\n' "$HORIZON"
```

Inspect what's armed any time (no sudo): `pmset -g sched`

---

## Step 5 — remove a job

```bash
NAME="daily-review"; LABEL="com.claude-schedule.$NAME"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" \
      "$HOME/Library/Application Support/claude-schedule/$NAME.sh" \
      "$HOME/Library/Application Support/claude-schedule/$NAME.log" \
      "$HOME/Library/Application Support/claude-schedule/$NAME.prompt.md"
echo "removed $NAME"
```

The job's pre-armed wake entries simply lapse on their own. To clear pending wakes sooner, inspect with `pmset -g sched`; **note `sudo pmset schedule cancelall` clears *all* jobs' wake entries**, so only use it if no other claude-schedule job needs its wakes (then re-arm those from their Step 4).
