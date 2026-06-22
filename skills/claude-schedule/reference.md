# claude-schedule skill — wake, managed Macs, calibration, removal

Read this before doing anything privileged. The default path (in SKILL.md) is **no-wake** and
needs **zero** privileged steps. Everything here is opt-in or cleanup.

## Wake-from-sleep (opt-in only)

By default the job has **no** wake — it runs if the machine is awake at the scheduled time,
and launchd runs a missed job on the next wake (`StartCalendarInterval` catch-up). Most users
leave the machine on or only sleep the display, so this is enough and needs no `sudo`.

Only if the user explicitly wants the machine to **wake itself from sleep**, offer this — and
**print the command for them to run; never run it, never write a `sudoers` file**:

```bash
# one-time arm. <DAYS> = MTWRFSU letters (weekdays = MTWRF). HH:MM:SS = the job's time.
sudo pmset repeat wakeorpoweron MTWRF 09:00:00
```

Key facts to tell the user:
- This is a **repeating** wake: arming it **once** covers **every** future run at that time.
  The scheduled runs themselves are 100% `sudo`-free. If a design ever needs root at fire
  time, it's wrong.
- macOS has exactly **one** `pmset repeat` slot. Re-arm **only when the wake time changes**.
  Adding more jobs at the **same** time reuses the slot — do **not** re-prompt.
- Apple Silicon wakes from **sleep** only; it **cannot power on from a full shutdown**. "Off"
  must mean asleep. Keep laptops on **AC power** (lid-closed on AC is fine).

## Managed Macs (BeyondTrust EPM / Jamf / MDM)

Detect before suggesting `sudo`:

```bash
profiles status -type enrollment 2>/dev/null | grep -qi "MDM enrollment: Yes" && echo "MDM-managed"
pgrep -qi -f "Defendpoint|PrivilegeManagement|EndpointSecurity" && echo "EPM present"
ls -d /Applications/*Privilege* 2>/dev/null
```

If managed, warn the user plainly:
- The prompt they'll hit on `sudo pmset` is likely the **corporate "Confirm Operation"
  Yes/No** (BeyondTrust EPM), **not** a Unix password.
- A local `sudoers` `NOPASSWD` rule **cannot** suppress it — it's central policy (and writing
  `sudoers` is the wrong boundary anyway; don't).
- The real fix is asking **IT to whitelist `pmset repeat`** for them.
- They can still use the job with **no-wake** (the default) and just keep the machine awake.

## Calibration & reliability

- Real clocks drift and DST shifts; `StartCalendarInterval` fires on wall-clock local time and
  launchd handles DST. Rely on launchd **catch-up** for runs missed while asleep.
- A machine that was **fully powered off** at fire time can't self-start (see Apple Silicon
  note above) — the job runs on next boot/login if still due.

## Removing a job

```bash
NAME="daily-review"; LABEL="com.claude-schedule.$NAME"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" \
      "$HOME/Library/Application Support/claude-schedule/$NAME.sh" \
      "$HOME/Library/Application Support/claude-schedule/$NAME.log"
```

If a wake was armed **and** no other job still needs that wake time, print (don't run):
`sudo pmset repeat cancel`.

## Out of scope for this skill

Multi-job wake-slot **union** (several wake jobs at different times sharing the one slot),
Linux/systemd, and Windows/schtasks. For those, use the full `claude-schedule` CLI if
installed; otherwise tell the user this seamless path is macOS + single-wake-time for now.
