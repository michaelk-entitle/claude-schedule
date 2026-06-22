---
name: claude-schedule
description: Use when the user wants a recurring Claude Code job to run on THIS macOS machine at a clock time — "run X every weekday at 9am", a daily/weekly task that must survive closing the session, full repo + local file access — or types /schedule, or a recurring /loop, or the CronCreate hook fires. macOS / launchd. Not for sub-hourly intervals or cloud routines.
---

# claude-schedule — seamless local schedules

Turn a scheduling request into a **persistent local launchd job** on macOS, directly from
Bash. **Nothing to install** — no `pip`, no CLI, no engine. The plugin being present is
enough. `/loop` is session-scoped (dies when the session ends) and cloud `/schedule` routines
run in a remote sandbox with no access to the user's disk; this fills the gap: a real
`claude -p` on a clock schedule, on the user's machine, that survives logout and sleep.

**Infer and act — confirm once.** The failure mode this skill exists to prevent is bouncing
the user through tool-picker modals. Run the classifier silently, state the routing decision
in one line, ask at most one question (the timeout), then install.

## Step 0 — Classify the request (do this first, silently)

| Signal in the request | Route |
|---|---|
| Interval **< 1 hour** (`every 5 min`, `*/15`) | **Not a persistent local job** — neither this nor cloud does sub-hourly. Offer a plain `crontab` one-liner or session `/loop`. Say so once, stop. |
| Touches a **local path / repo / local MCP** | **Local job (this skill).** A cloud sandbox can't reach the user's disk. |
| Pure remote analysis, **≥ 1h**, no local deps | Either works → **default local**; mention cloud `/schedule` only if they want off-machine. |
| **Clock-time, persistent, local** | **Local job (this skill).** The happy path. |

Echo it in one line ("local + sub-hourly → that's a `crontab` line, not a Claude job") — do
**not** open a modal to ask which tool.

## Step 1 — Infer, ask at most one thing

Infer from the request: **name** (slug of the task), **repo** (cwd unless stated), **days**
+ **time** (from the phrasing), **model** (default), **permission-mode** (`auto`). Ask **only**
the **timeout** if the user didn't give one (suggest `30m`). Don't ask anything else.

Day → launchd weekday number: Mon=1 Tue=2 Wed=3 Thu=4 Fri=5 Sat=6 Sun=0. `weekdays`=`1 2 3 4 5`.

## Step 2 — Install the job (verified recipe)

Fill the variables, then run as-is. This emits a runner script + a LaunchAgent and loads it.
**Default is no-wake** (no `sudo`, no prompt): the job runs if the machine is awake at the
time, and launchd runs a missed job on the next wake. (Wake-from-sleep is opt-in — see
[reference.md](reference.md).)

```bash
NAME="daily-review"                  # slug
HOUR=9; MIN=0                        # 24h clock time
WEEKDAYS="1 2 3 4 5"                 # launchd nums; "" = every day; weekdays = 1 2 3 4 5
REPO="$HOME/Projects/myrepo"         # working dir for the run
TIMEOUT=1800                         # seconds (30m)
PROMPT='Review today’s changes and write a short summary.'
PERM=auto                            # auto | acceptEdits | default | plan

# resolve the real claude binary (the `claude` you type may be a shell function)
CLAUDE="$(command -v claude 2>/dev/null)"
case "$CLAUDE" in /*) ;; *) for c in "$HOME/.local/bin/claude" /opt/homebrew/bin/claude /usr/local/bin/claude; do [ -x "$c" ] && CLAUDE="$c" && break; done;; esac

LABEL="com.claude-schedule.$NAME"
DIR="$HOME/Library/Application Support/claude-schedule"; mkdir -p "$DIR"
RUN="$DIR/$NAME.sh"; LOG="$DIR/$NAME.log"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# runner: caffeinate keeps the mac awake for the run; pure-shell timeout guard (no timeout/gtimeout dep)
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

# StartCalendarInterval: one dict for daily, an array of dicts for specific weekdays.
# (tr+read splits portably — zsh doesn't word-split an unquoted $WEEKDAYS)
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
    <key>PATH</key><string>$(dirname "$CLAUDE"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
</dict></plist>
PLIST

if plutil -lint "$PLIST" >/dev/null; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null   # replace any prior copy
  launchctl bootstrap "gui/$(id -u)" "$PLIST" && echo "installed $LABEL ($HOUR:$MIN, log: $LOG)"
else echo "plist invalid — not installing"; fi
```

## Step 3 — Smoke-test now, then report

Don't make the user wait until the scheduled time — fire it once and show the log:

```bash
launchctl kickstart -k "gui/$(id -u)/com.claude-schedule.$NAME"   # runs it now
sleep 1; tail -n 20 "$HOME/Library/Application Support/claude-schedule/$NAME.log"
```

Then tell the user: it's installed, when it runs, the log path, and how to remove it
(`launchctl bootout "gui/$(id -u)/com.claude-schedule.$NAME"` + delete the plist & runner).

## Scope & escape hatches

- **macOS only.** On Linux/Windows, or for multi-job wake-slot management, fall back to the
  full `claude-schedule` CLI if it's installed (`claude-schedule add …`), else tell the user
  this seamless path is macOS-only for now.
- **Wake-from-sleep, managed Macs (BeyondTrust EPM / MDM), DST/catch-up, removal:** read
  [reference.md](reference.md) before doing anything privileged. Default stays no-wake.
- **Never** write a `sudoers` file or run a privileged command for the user — print it, they run it.
