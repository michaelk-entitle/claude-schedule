---
description: Show local scheduled Claude jobs and environment readiness (claude-schedule)
allowed-tools: Bash(claude-schedule *)
---

Current local scheduled Claude jobs and environment readiness:

!`claude-schedule list 2>/dev/null || echo "(claude-schedule not installed — see the plugin README)"`

!`claude-schedule doctor 2>/dev/null || true`

To add, test, remove, or inspect a job, use the `claude-schedule` skill or the CLI directly
(`claude-schedule add|run-now|logs|remove`). $ARGUMENTS
