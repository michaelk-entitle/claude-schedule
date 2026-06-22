# claude-schedule

![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Dependencies](https://img.shields.io/badge/runtime%20deps-none-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A Claude Code plugin that turns *"run this every weekday at 9am"* into a **persistent local
job on your Mac** — full repo + local file + MCP access, surviving the session closing and
the machine sleeping. No cloud sandbox, **nothing to install** beyond the plugin.

It's deliberately small: a **skill** (instructions) that writes a `launchd` job straight from
Bash, plus a tiny **hook** that catches the moments where Claude would otherwise reach for an
ephemeral `/loop` or a remote cloud routine.

> **Why this exists:** `/loop` jobs die when the session ends; cloud `/schedule` routines run
> remotely and can't touch your repo or local MCP servers. There was no built-in way to run a
> real headless `claude -p` on your own machine, on a timer, that survives logout and sleep.
> This fills that gap.

---

## Quickstart (macOS)

**Install the plugin — that's the only step.**

```text
# in Claude Code:
/plugin marketplace add michaelk-entitle/claude-schedule
/plugin install claude-schedule@claude-schedule
```

Then just say what you want — no CLI, no `pip install`:

> "review this repo every weekday at 9am and write a summary"

The bundled **skill** turns that into a persistent local `launchd` job (it asks only for a
timeout) and fires it once as a smoke test. By default it's **no-wake**: zero `sudo` — the
job runs whenever the machine is next awake. Wake-from-sleep is an opt-in you arm once.

---

## How it works

```
You: "review this repo every weekday at 9am"
      │
      ▼  the claude-schedule skill activates
Claude → writes a LaunchAgent + runner script from Bash, loads it with launchctl,
         and kickstarts one run to prove it works. Asks you only for a timeout.
```

Three things keep it on the rails:

1. **The skill** (`skills/claude-schedule/`) does the work: classifies the request (a
   sub-hourly `every 5 min` → that's a `crontab`/`loop`, not this; local files → a local job;
   pure remote analysis → cloud is fine), then emits a `launchd` job — `caffeinate` keeps the
   Mac awake for the run, a pure-shell timeout guard bounds it, and `launchctl kickstart`
   smoke-tests it.
2. **A `PreToolUse` hook on `CronCreate`** catches a recurring `/loop`: it denies the
   ephemeral, session-scoped cron and tells Claude to use the skill for a persistent job
   instead. Short interval polls and one-shots pass through untouched.
3. **A `UserPromptSubmit` hook on `/schedule`** steers Claude to a local job rather than a
   remote cloud routine — unless you explicitly ask for cloud. (Cloud routine creation isn't a
   tool call, so this is a steer, not a hard block.)

The hook is one stdlib-only Python file (`scripts/hook.py`); it fails safe — if anything is
off, it exits 0 and never blocks native scheduling.

---

## Permissions & wake

- **Default: no-wake, no `sudo`.** The job runs if the machine is awake at the time; launchd
  runs a missed job on the next wake. Most setups (machine on, or display-only sleep) need
  nothing privileged.
- **Wake-from-sleep is opt-in.** Arming the macOS wake slot needs root *once* —
  `sudo pmset repeat wakeorpoweron …`, a **repeating** wake, so that single arm covers every
  future run and the scheduled runs themselves are 100% `sudo`-free. The skill **prints** the
  command for you to run; it never runs `sudo` for you and never writes a `sudoers` file.
- **Managed Macs (BeyondTrust EPM / MDM):** the `sudo` prompt is corporate policy (a
  "Confirm Operation" dialog), not a password a local `sudoers` rule can suppress — the fix is
  asking IT to whitelist `pmset`. The skill detects this and says so. See
  [`skills/claude-schedule/reference.md`](skills/claude-schedule/reference.md).
- Unattended runs use `--permission-mode auto`: autonomous on safe steps, aborts on risky ones.

## Removing a job

```bash
NAME=daily-review; LABEL=com.claude-schedule.$NAME
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f ~/Library/LaunchAgents/$LABEL.plist \
      ~/Library/"Application Support"/claude-schedule/$NAME.{sh,log}
# if you armed a wake and no other job needs it: sudo pmset repeat cancel
```

## Scope & limitations

- **macOS / `launchd` only**, clock-time daily/weekly. Sub-hourly intervals route to
  `crontab` or `/loop`; Linux/Windows aren't supported by this minimal build.
- **Apple Silicon can't power on from a full shutdown** — "off" must mean *asleep*. Keep
  laptops on AC power.
- The `/schedule` steer is a steer, not a guarantee (it relies on Claude honoring the
  injected instruction). `/loop`'s `CronCreate` *is* hard-intercepted.
- A single macOS wake slot is shared system-wide; multiple wake jobs at different times aren't
  unioned by this build.

## Development

```bash
pip install ruff mypy pytest
ruff check .          # lint
mypy scripts/hook.py  # types
pytest                # hook logic (cron parsing, steers)
```

CI runs these on Linux across Python 3.10 + 3.13 (`.github/workflows/ci.yml`).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Keep it dependency-free and the diff small.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Michael Kosoy.
