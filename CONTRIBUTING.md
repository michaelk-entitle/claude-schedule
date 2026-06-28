# Contributing

Thanks for your interest! This is a small, dependency-free Claude Code plugin — a **skill**
(instructions) plus one stdlib-only **hook** script. Contributions that keep it minimal are
very welcome.

## Dev setup & checks

```bash
git clone <your-fork> && cd claude-schedule
pip install ruff mypy pytest
ruff check .          # lint
mypy scripts/hook.py  # types
pytest                # hook logic (cron parsing, the steers)
```

CI runs these on Linux across Python 3.10 + 3.13.

## Project layout

See [docs/architecture.md](docs/architecture.md). In short:

- `skills/claude-schedule/` — the self-contained skill (`SKILL.md`) that writes the `launchd`
  job from Bash and handles wake-from-sleep (batch pre-arm). Most behavior lives here.
- `scripts/hook.py` — the stdlib-only hook (CronCreate interception + `/schedule` steer),
  launched by `scripts/hook.sh` and wired in `hooks/hooks.json`.

## Conventions

- **Standard library only** for the hook (dev tools are fine).
- Complete type hints; `mypy` runs with `disallow_untyped_defs`.
- Surgical changes; no new dependencies for what a few lines can do.
- The skill is launchd/macOS-only by design — keep new behavior scoped and honest rather than
  half-reimplementing a cross-platform engine in Markdown.
- Add a test in `tests/test_hook.py` for any new hook logic; don't touch the live scheduler.
