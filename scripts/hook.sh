#!/usr/bin/env bash
# Route a Claude Code hook event (JSON on stdin) to hook.py.
# Fails safe: if python3 is missing, do nothing (exit 0) so native scheduling is never broken.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$DIR/hook.py" "$@"
fi
exit 0
