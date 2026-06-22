import contextlib
import io
import json
import sys

from claude_schedule import hook
from claude_schedule.hook import _cron_dow_to_days, _slug, parse_cron


def test_parse_cron_daily():
    assert parse_cron("0 9 * * *") == (9, 0, (0, 1, 2, 3, 4, 5, 6))


def test_parse_cron_weekdays():
    assert parse_cron("30 8 * * 1-5") == (8, 30, (0, 1, 2, 3, 4))


def test_parse_cron_sunday():
    assert parse_cron("0 7 * * 0") == (7, 0, (6,))


def test_parse_cron_rejects_non_clock():
    assert parse_cron("*/5 * * * *") is None  # interval
    assert parse_cron("0 9 1 * *") is None  # day-of-month
    assert parse_cron("0 9 * * MON-FRI") is None  # named days (punt)
    assert parse_cron("bad") is None


def test_dow_mapping():
    assert _cron_dow_to_days("0") == (6,)
    assert _cron_dow_to_days("7") == (6,)
    assert _cron_dow_to_days("1,3,5") == (0, 2, 4)


def test_slug():
    assert _slug("Review the repo now please") == "review-the-repo-now"  # first 4 words
    assert _slug("") == "claude-job"


def _run(data):
    sys.stdin = io.StringIO(json.dumps(data))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        hook.handle()
    out = buf.getvalue().strip()
    return json.loads(out) if out else None


def test_recurring_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SCHEDULE_HOME", str(tmp_path))
    r = _run({"hook_event_name": "PreToolUse", "tool_name": "CronCreate", "session_id": "a",
              "tool_input": {"cron": "0 9 * * *", "prompt": "do it", "recurring": True}})
    assert r["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "claude-schedule add" in r["hookSpecificOutput"]["permissionDecisionReason"]


def test_interval_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SCHEDULE_HOME", str(tmp_path))
    assert _run({"hook_event_name": "PreToolUse", "tool_name": "CronCreate", "session_id": "b",
                 "tool_input": {"cron": "*/5 * * * *", "prompt": "x"}}) is None


def test_retry_escape_hatch(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SCHEDULE_HOME", str(tmp_path))
    data = {"hook_event_name": "PreToolUse", "tool_name": "CronCreate", "session_id": "c",
            "tool_input": {"cron": "0 9 * * *", "prompt": "x", "recurring": True}}
    assert _run(data) is not None  # first time: denied
    assert _run(data) is None  # explicit retry: allowed


def test_non_cron_tool_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SCHEDULE_HOME", str(tmp_path))
    assert _run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}}) is None


def test_schedule_prompt_steers_to_local(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SCHEDULE_HOME", str(tmp_path))
    r = _run({"hook_event_name": "UserPromptSubmit", "prompt": "please /schedule this daily"})
    ctx = r["hookSpecificOutput"]["additionalContext"]
    assert "claude-schedule add" in ctx  # steers to the local wrapper, not just a note
