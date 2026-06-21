#!/usr/bin/env bash
# Route a Claude Code hook event (JSON on stdin) to the claude-schedule engine.
#
# Fails safe: if the engine is not installed, do nothing (exit 0) so the user's
# native scheduling is never blocked or broken by a missing dependency.
set -euo pipefail

if command -v claude-schedule >/dev/null 2>&1; then
  exec claude-schedule _hook "$@"
fi

if command -v python3 >/dev/null 2>&1 && python3 -c 'import claude_schedule' >/dev/null 2>&1; then
  exec python3 -m claude_schedule _hook "$@"
fi

exit 0
