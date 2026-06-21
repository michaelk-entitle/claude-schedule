# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0]

Initial release.

### Added
- **Claude Code plugin** that intercepts schedule creation:
  - `PreToolUse` hook on `CronCreate` — replaces ephemeral, session-scoped recurring
    schedules with a persistent OS-level job (asks for a timeout in chat first). Interval
    polls and one-shots pass through untouched; a 120s marker prevents a deny-loop.
  - `UserPromptSubmit` hook — non-blocking note steering `/schedule` (cloud routines)
    toward the local wrapper.
- **CLI engine** (`claude-schedule`), zero runtime dependencies:
  - Commands: `add`, `remove`, `list`, `run-now`, `logs`, `generate` (dry-run), `doctor`,
    plus `daily` / `weekdays` one-liners.
  - Scheduler backends: launchd (macOS), systemd user timer (Linux), cron (fallback),
    Task Scheduler (Windows).
  - Wake backends: `pmset` (macOS), `rtcwake` (Linux, best-effort), Task Scheduler
    WakeToRun (Windows). Wake arming defaults to **printing** the one privileged command
    for the user to run; `--arm-wake` runs it (single sudo prompt). claude-schedule never
    reads or stores the password — `sudo` prompts on the terminal directly.
  - Unattended runs default to `--permission-mode auto`: autonomous on safe steps, aborts
    on risky ones. No `--dangerously-skip-permissions` flag.
  - Stored jobs and logs are owner-only: config dirs created `0700`, job specs and logs
    `0600` (best-effort; no-op on Windows). Keeps prompts and run output off other local
    users on shared machines.
  - Keep-awake during runs (`caffeinate` / `systemd-inhibit` / Windows API) and an
    in-process timeout (no external `timeout`/`gtimeout` dependency).
  - OS / scheduler / wake / privilege auto-detection with explicit overrides.
- Docs: README, architecture, troubleshooting; test suite; CI (pytest + mypy across
  macOS/Linux, Python 3.10–3.13).

[Unreleased]: https://github.com/michaelk-entitle/claude-schedule/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/michaelk-entitle/claude-schedule/releases/tag/v0.1.0
