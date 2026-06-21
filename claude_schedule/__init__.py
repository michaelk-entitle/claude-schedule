"""claude-schedule: run Claude Code jobs on a local schedule.

The machine wakes itself, runs ``claude -p`` with full repo + MCP context,
keeps awake only while the job runs, then returns to normal idle sleep.
"""

__version__ = "0.1.0"
