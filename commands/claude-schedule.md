---
description: List your local claude-schedule launchd jobs and their runners/logs
allowed-tools: Bash(launchctl list*), Bash(ls *)
---

Your local claude-schedule jobs (launchd):

!`launchctl list 2>/dev/null | grep -i claude-schedule || echo "(no claude-schedule jobs installed)"`

Runners & logs:

!`ls -1 ~/Library/"Application Support"/claude-schedule/ 2>/dev/null || echo "(none yet)"`

To create, test, or remove a job, just say what you want (e.g. "run X every weekday at 9am") —
the claude-schedule skill handles it from there. $ARGUMENTS
