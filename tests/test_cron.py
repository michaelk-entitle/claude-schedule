from claude_schedule.backends.cron import _block, _cron_days, _strip_block, cron_line
from claude_schedule.jobspec import JobSpec


def _job(**over):
    base = dict(
        name="rev", hour=9, minute=0, days=(0, 1, 2, 3, 4),
        claude_path="/bin/echo", prompt="hi", log_path="/tmp/j.log",
    )
    base.update(over)
    return JobSpec(**base)


def test_cron_days():
    assert _cron_days(_job(days=(0, 1, 2, 3, 4, 5, 6))) == "*"
    assert _cron_days(_job(days=(0, 1, 2, 3, 4))) == "1,2,3,4,5"  # MTWRF -> cron Mon..Fri
    assert _cron_days(_job(days=(6,))) == "0"  # Sunday


def test_cron_line_quotes_and_redirects():
    line = cron_line(_job(), ["/p y/python", "-m", "claude_schedule", "_run", "--name", "rev"])
    assert line.startswith("0 9 * * 1,2,3,4,5 ")
    assert "'/p y/python'" in line  # spaces are shell-quoted
    assert line.endswith(">> /tmp/j.log 2>&1")


def test_strip_block_preserves_other_lines():
    existing = "# my own job\n0 0 * * * backup.sh\n"
    merged = existing + _block(_job(), ["x"]) + "\n"
    stripped = _strip_block(merged, "rev").strip()
    assert stripped == "# my own job\n0 0 * * * backup.sh"
    assert "claude-schedule:rev" not in stripped
