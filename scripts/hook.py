"""claude-schedule hook — the plugin's automatic front door (self-contained, stdlib only).

Wired by hooks/hooks.json via hook.sh. Two events, both pure text steering (hooks have no
TTY and can't call tools); anything we don't understand → exit 0 so native scheduling is
never broken. Refs: https://code.claude.com/docs/en/hooks

* PreToolUse on CronCreate — a recurring clock-time /loop is session-scoped (dies when the
  session ends) and can't wake the machine. DENY it and tell Claude to use the
  **claude-schedule skill** to install a persistent local launchd job instead. Interval
  polls and one-shots pass through untouched.
* UserPromptSubmit — /schedule makes a remote CLOUD routine with no access to this machine.
  Steer Claude to set up a LOCAL job via the skill unless the user explicitly wants cloud.
  (Cloud routine creation isn't a tool call, so this is a steer, not a hard block.)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

DAY_LETTERS = "MTWRFSU"  # M=Mon T=Tue W=Wed R=Thu F=Fri S=Sat U=Sun
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

    cron, prompt, recurring = first(_CRON_KEYS), first(_PROMPT_KEYS), first(_RECUR_KEYS)
    return (
        str(cron) if cron else None,
        str(prompt) if prompt else None,
        True if recurring is None else bool(recurring),
    )


def _emit(obj: dict) -> None:
    print(json.dumps(obj))


def _marker(session: str, cron: str) -> Path:
    # deny-loop guard dir, owner-only; same schedule re-issued within the TTL is let through
    base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") if os.name == "nt" \
        else Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / "claude-schedule" / "hookstate"
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.parent.chmod(0o700)
        d.chmod(0o700)
    except OSError:
        pass
    return d / hashlib.sha1(f"{session}:{cron}".encode()).hexdigest()[:16]


def _recently_denied(session: str, cron: str, ttl: int = 120) -> bool:
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
        return 0  # can't read the schedule — let the native tool proceed
    parsed = parse_cron(cron)
    if not recurring or parsed is None:
        return 0  # one-shot / interval / unparseable — ephemeral by nature, leave it alone
    session = str(data.get("session_id", ""))
    if _recently_denied(session, cron):
        return 0  # explicit retry of an ephemeral loop — allow it

    hour, minute, days = parsed
    letters = "".join(DAY_LETTERS[i] for i in days)
    _marker(session, cron).write_text(str(time.time()))
    reason = (
        "claude-schedule intercepted a recurring schedule. A session-scoped /loop job stops when this "
        "session exits and cannot wake the machine. Make it persistent instead — use the "
        "**claude-schedule skill** to install a local launchd job for this schedule:\n"
        f"  time {hour:02d}:{minute:02d}, days {letters}, task: {prompt or '(from the request)'}\n"
        "1. Ask the user what timeout the job should have (suggest 30m).\n"
        "2. Follow the claude-schedule skill (its SKILL.md) to write the LaunchAgent and load it.\n"
        "If the user actually wanted a short in-session reminder/poll, say so and re-issue CronCreate "
        "with the same schedule — it will be allowed the second time."
    )
    _emit({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }})
    return 0


def _handle_userprompt(data: dict) -> int:
    if "/schedule" not in (data.get("prompt") or "").lower():
        return 0
    _emit({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": (
            "The user invoked /schedule. /schedule creates a CLOUD routine that runs remotely on "
            "Anthropic infrastructure with NO access to this machine, its repository, or local MCP "
            "servers. On a developer's own machine the intent is almost always to run LOCALLY (full "
            "repo + MCP + local files). So unless the user EXPLICITLY asks for a cloud/remote routine "
            "(e.g. 'run in the cloud' or 'while my laptop is closed'), do NOT create a cloud routine. "
            "Instead use the **claude-schedule skill** to install a persistent local launchd job: confirm "
            "the time and days, ask what timeout it should have (suggest 30m), then follow the skill's "
            "SKILL.md. Only if the user truly wants cloud execution, let the native /schedule routine proceed."
        ),
    }})
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


def main() -> int:
    argv = sys.argv[1:]
    event = argv[argv.index("--event") + 1] if "--event" in argv and argv.index("--event") + 1 < len(argv) else None
    return handle(event)


if __name__ == "__main__":
    sys.exit(main())
