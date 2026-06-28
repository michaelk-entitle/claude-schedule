# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0]

### Changed
- Self-contained `SKILL.md` (no `reference.md`): folded wake guidance into the skill.
- Wake-from-sleep reworked to **batch pre-arm** — one `sudo pmset schedule` loop at creation
  pre-arms a 60-day horizon of wakes per job (one approval each), so multiple jobs at
  different times coexist with no daily sudo. Replaces the self-re-arming/`pmset repeat`
  approaches, which can't run unattended under managed-Mac (EPM) sudo prompts.
- Runner no longer calls `sudo`.

### Removed
- `skills/claude-schedule/reference.md` (merged into `SKILL.md`).

## [0.1.0]

Initial release.

A minimal Claude Code plugin: a **skill** (instructions) plus one stdlib-only **hook**.
Nothing to install beyond the plugin; no CLI engine.

### Added
- **Seamless skill (macOS).** Turns a natural-language or `/schedule` request into a
  persistent `launchd` job directly from Bash — plugin-present is enough. It classifies the
  request first (sub-hourly → `crontab`/`loop`, local-file work → a local job, off-machine
  analysis → cloud), infers name/repo/days/time and asks only the timeout, defaults to
  **no-wake** (zero `sudo`), keeps the run awake with `caffeinate`, guards the timeout in pure
  shell (no `timeout`/`gtimeout` dep), runs at `--permission-mode auto`, and smoke-tests with
  `launchctl kickstart`. Wake-from-sleep and managed-Mac (EPM) handling are opt-in
  in the skill's `reference.md`. macOS / single-wake-time by design.
- **Hook** (`scripts/hook.py`, stdlib only), wired by the plugin:
  - `PreToolUse` on `CronCreate` — denies a recurring, session-scoped `/loop` and steers
    Claude to set up a persistent local job via the skill. Interval polls and one-shots pass
    through; a 120s marker prevents a deny-loop.
  - `UserPromptSubmit` on `/schedule` — steers Claude to a local job rather than a remote
    cloud routine, unless the user explicitly wants cloud. (Cloud routine creation isn't a
    tool call, so this is a steer, not a hard block.)
  - Fails safe: anything unrecognized → exit 0, never blocking native scheduling.
- Docs (README, architecture, troubleshooting, the seamless-wrapper design note); hook tests;
  CI (ruff + mypy + pytest on Python 3.10 + 3.13).

[Unreleased]: https://github.com/michaelk-entitle/claude-schedule/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/michaelk-entitle/claude-schedule/releases/tag/v0.1.0
