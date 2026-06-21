# Contributing

Thanks for your interest! This is a small, dependency-free tool — contributions that keep
it that way are very welcome.

## Dev setup

```bash
git clone <your-fork>
cd claude-schedule
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Checks (all must pass — CI runs them on macOS + Linux, Python 3.10–3.13)

```bash
pytest            # tests
ruff check .      # lint
mypy claude_schedule   # types
```

Add a test for any new behavior. Unit tests should not touch the real scheduler/launchd/
crontab — test the pure generation/parse logic (see `tests/` for the pattern). For a quick
end-to-end check without side effects:

```bash
claude-schedule generate --name demo --time 09:00 --prompt "hi" --dry-run
```

## Project layout

See [docs/architecture.md](docs/architecture.md). In short: `cli.py`/`hook.py` are the two
front doors; `backends/` holds the scheduler + wake implementations behind small ABCs;
`runner.py` is what the scheduler actually invokes.

## Adding a scheduler or wake backend

1. Implement `SchedulerBackend` (or `WakeBackend`) from `backends/base.py`.
2. Register it in `backends/__init__.py` (`SCHEDULERS` / `select_wake`).
3. Keep day-of-week conversion local to the backend (canonical is `0=Mon … 6=Sun`).
4. Add a test that exercises the generated artifact (plist/unit/line), not the live install.

## Conventions

- Standard library only for runtime code (dev tools are fine as extras).
- Complete type hints; `mypy` is configured with `disallow_untyped_defs`.
- Surgical changes; no new dependencies for what a few lines can do.
