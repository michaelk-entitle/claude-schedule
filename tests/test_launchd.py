import plistlib

from claude_schedule.backends.launchd import _calendar_intervals, build_plist, label_for
from claude_schedule.jobspec import JobSpec


def _job(**over):
    base = dict(
        name="j", hour=9, minute=0, days=(0,), claude_path="/bin/echo", prompt="hi",
        log_path="/tmp/j.log", node_bin_dir="/opt/node/bin",
    )
    base.update(over)
    return JobSpec(**base)


def test_weekday_mapping():
    # canonical Mon=0 -> launchd 1 ; Sun=6 -> launchd 0
    assert [d["Weekday"] for d in _calendar_intervals(_job(days=(0,)))] == [1]
    assert [d["Weekday"] for d in _calendar_intervals(_job(days=(6,)))] == [0]
    assert sorted(d["Weekday"] for d in _calendar_intervals(_job(days=(0, 1, 2, 3, 4, 5, 6)))) == [0, 1, 2, 3, 4, 5, 6]


def test_label():
    assert label_for("j") == "com.claude-schedule.j"


def test_plist_roundtrip():
    pl = plistlib.loads(build_plist(_job(days=(0, 2, 4)), ["py", "-m", "claude_schedule", "_run", "--name", "j"]))
    assert pl["Label"] == "com.claude-schedule.j"
    assert pl["RunAtLoad"] is False
    assert pl["ProgramArguments"][-1] == "j"
    assert "/opt/node/bin" in pl["EnvironmentVariables"]["PATH"]
    assert len(pl["StartCalendarInterval"]) == 3
    assert pl["StandardOutPath"].endswith(".launchd.log")
