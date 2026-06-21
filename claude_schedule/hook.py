"""Claude Code hook entrypoint — the automatic front door.

Wired by the bundled plugin (``hooks/hooks.json``) so users never call the CLI by
hand. Two events:

* ``PreToolUse`` on ``CronCreate`` — when Claude creates a *recurring clock-time*
  schedule, we DENY the session-scoped cron (it dies on session exit and can't wake
  the machine) and instruct Claude, via the denial reason, to ask the user for a
  timeout and then run ``claude-schedule add`` — installing a persistent OS-level job
  in its place. Ephemeral interval polls and one-shots are left alone so Claude's own
  short ``/loop`` mechanism keeps working.

* ``UserPromptSubmit`` — if the user invokes ``/schedule`` (cloud Routines, which run
  remotely and don't use this machine), add a non-blocking note offering the local
  wrapper instead. We never block cloud routines.

Hooks have no TTY (can't prompt) and can't call tools, so all steering is plain text
Claude reads. Anything we don't understand → stay silent (exit 0) so native scheduling
is never broken. Refs: https://code.claude.com/docs/en/hooks
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

from claude_schedule.jobspec import DAY_LETTERS, NAME_RE
from claude_schedule.registry import app_subdir

_CRON_KEYS = ("cron", "schedule", "expression", "cronExpression", "cron_expression", "crontab")
_PROMPT_KEYS = ("prompt", "task", "message", "text", "instruction")
_RECUR_KEYS = ("recurring", "recurs", "repeat", "recur", "recurrence")


# -- cron parsing (common "M H * * DOW" clock-time shape only) -------------


def _single_int(field: str) -> int | None:
    return int(field) if field.isdigit() else None


def _cron_dow_to_days(dow: str) -> tuple[int, ...]:
    """cron DOW (0/7=Sun, 1=Mon..6=Sat) -> canonical days (0=Mon..6=Sun). Numeric forms only."""
    if dow == "*":
        return tuple(range(7))
    days: set[int] = set()
    for part in dow.split(","):
        lo, hi = (part.split("-", 1) + [part])[:2] if "-" in part else (part, part)
        for c in range(int(lo), int(hi) + 1):
            days.add(6 if c in (0, 7) else c - 1)
    return tuple(sorted(days))


def parse_cron(expr: str) -> tuple[int, int, tuple[int, ...]] | None:
    """Return (hour, minute, days) for a recurring clock-time cron, else None."""
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts
    m, h = _single_int(minute), _single_int(hour)
    if m is None or h is None or dom != "*" or month != "*":
        return None  # interval / sub-daily / day-of-month specific: not a simple clock job
    try:
        return h, m, _cron_dow_to_days(dow)
    except ValueError:
        return None  # named days (MON-FRI) etc. — punt safely


# -- helpers ---------------------------------------------------------------


def _extract(tool_input: dict) -> tuple[str | None, str | None, bool]:
    def first(keys: tuple[str, ...]) -> object | None:
        return next((tool_input[k] for k in keys if k in tool_input), None)

    cron = first(_CRON_KEYS)
    prompt = first(_PROMPT_KEYS)
    recurring = first(_RECUR_KEYS)
    return (
        str(cron) if cron else None,
        str(prompt) if prompt else None,
        True if recurring is None else bool(recurring),
    )


def _slug(text: str, fallback: str = "claude-job") -> str:
    s = "-".join(re.findall(r"[A-Za-z0-9]+", text.lower())[:4])[:48].strip("-")
    return s if s and NAME_RE.match(s) else fallback


def _suggest_command(hour: int, minute: int, days: tuple[int, ...], prompt: str | None) -> str:
    letters = "".join(DAY_LETTERS[i] for i in days)
    safe_prompt = (prompt or "").replace("'", "'\\''")
    return (
        f"claude-schedule add --name {_slug(prompt or '')} --time {hour:02d}:{minute:02d} "
        f"--days {letters} --prompt '{safe_prompt}' --timeout <TIMEOUT>"
    )


def _emit(obj: dict) -> None:
    print(json.dumps(obj))


# -- deny-loop guard (so an explicit ephemeral retry isn't blocked forever) -


def _marker(session: str, cron: str) -> Path:
    h = hashlib.sha1(f"{session}:{cron}".encode()).hexdigest()[:16]
    return app_subdir("hookstate") / h


def _recently_denied(session: str, cron: str, ttl: int = 120) -> bool:
    # ponytail: file-mtime marker, TTL 120s. If the same schedule is re-issued quickly,
    # the user explicitly wants the ephemeral version — let it through.
    p = _marker(session, cron)
    if p.is_file() and (time.time() - p.stat().st_mtime) < ttl:
        p.unlink(missing_ok=True)
        return True
    return False


# -- event handlers --------------------------------------------------------


def _handle_pretooluse(data: dict) -> int:
    if data.get("tool_name") != "CronCreate":
        return 0
    cron, prompt, recurring = _extract(data.get("tool_input") or {})
    if not cron:
        return 0  # can't understand the schedule — let the native tool proceed
    parsed = parse_cron(cron)
    if not recurring or parsed is None:
        return 0  # one-shot / interval / unparseable — ephemeral by nature, leave it alone
    session = str(data.get("session_id", ""))
    if _recently_denied(session, cron):
        return 0  # explicit retry of an ephemeral loop — allow it

    hour, minute, days = parsed
    cmd = _suggest_command(hour, minute, days, prompt)
    _marker(session, cron).write_text(str(time.time()))
    reason = (
        "claude-schedule intercepted a recurring schedule. A session-scoped /loop job stops when "
        "this session exits and cannot wake the machine. To make it persistent — survives restart, "
        "wakes the computer at the right time, stays awake during the run, and enforces a timeout — "
        "do this instead:\n"
        "1. Ask the user what timeout the job should have (suggest 30m).\n"
        "2. Run this in Bash, replacing <TIMEOUT> with their answer:\n"
        f"     {cmd}\n"
        "If the user actually wanted only a short in-session reminder/poll, say so and re-issue "
        "CronCreate with the same schedule — it will be allowed the second time."
    )
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )
    return 0


def _handle_userprompt(data: dict) -> int:
    if "/schedule" not in (data.get("prompt") or "").lower():
        return 0
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "Note: /schedule creates a CLOUD routine on Anthropic infrastructure — it does not "
                    "use this machine, its files, or local MCP servers. If the user wants the job to run "
                    "LOCALLY here with full repo + MCP access, offer to set it up with the claude-schedule "
                    "wrapper (claude-schedule add ...) instead."
                ),
            }
        }
    )
    return 0


def handle(event: str | None = None) -> int:
    """Read the hook event JSON from stdin and act. Always returns 0 (never break native flow)."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    event = data.get("hook_event_name", event)
    try:
        if event == "PreToolUse":
            return _handle_pretooluse(data)
        if event == "UserPromptSubmit":
            return _handle_userprompt(data)
    except Exception:  # noqa: BLE001 - a hook must never crash the user's session
        return 0
    return 0
