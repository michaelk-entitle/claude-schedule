import pytest

from claude_schedule.jobspec import (
    JobSpec,
    format_days,
    format_duration,
    parse_days,
    parse_duration,
    parse_time,
)


def _job(**over):
    base = dict(name="j", hour=9, minute=0, days=(0,), claude_path=__file__, prompt="hi")
    base.update(over)
    return JobSpec(**base)


# -- parse_days -----------------------------------------------------------


def test_parse_days_letters():
    assert parse_days("MWF") == (0, 2, 4)
    assert parse_days("U") == (6,)  # Sunday
    assert parse_days("mtwrfsu") == (0, 1, 2, 3, 4, 5, 6)


def test_parse_days_aliases():
    assert parse_days("daily") == (0, 1, 2, 3, 4, 5, 6)
    assert parse_days("weekdays") == (0, 1, 2, 3, 4)
    assert parse_days("weekends") == (5, 6)


def test_parse_days_invalid():
    with pytest.raises(ValueError):
        parse_days("XYZ")


def test_format_days_roundtrip():
    assert format_days(parse_days("weekdays")) == "MTWRF"


# -- parse_time -----------------------------------------------------------


@pytest.mark.parametrize("s,expected", [("09:00", (9, 0)), ("23:59", (23, 59)), ("0:05", (0, 5))])
def test_parse_time_ok(s, expected):
    assert parse_time(s) == expected


@pytest.mark.parametrize("s", ["24:00", "9", "09:60", "9:5", "abc"])
def test_parse_time_bad(s):
    with pytest.raises(ValueError):
        parse_time(s)


# -- parse_duration -------------------------------------------------------


@pytest.mark.parametrize(
    "s,secs",
    [("30m", 1800), ("90s", 90), ("1h", 3600), ("1h30m", 5400), ("2h", 7200), ("0", 0), ("none", 0)],
)
def test_parse_duration_ok(s, secs):
    assert parse_duration(s) == secs


@pytest.mark.parametrize("s", ["30", "30x", "m", "1h30", "-5m"])
def test_parse_duration_bad(s):
    with pytest.raises(ValueError):
        parse_duration(s)


def test_format_duration():
    assert format_duration(0) == "none"
    assert format_duration(1800) == "30m"
    assert format_duration(5400) == "1h30m"


# -- JobSpec --------------------------------------------------------------


def test_wake_time_subtracts_and_clamps():
    assert _job(hour=9, minute=0, wake_before_seconds=60).wake_time() == (8, 59)
    assert _job(hour=9, minute=0, wake_before_seconds=0).wake_time() == (9, 0)
    assert _job(hour=0, minute=0, wake_before_seconds=600).wake_time() == (0, 0)  # clamp at midnight


def test_validate_requires_exactly_one_prompt():
    with pytest.raises(ValueError):
        _job(prompt=None, prompt_file=None).validate()
    with pytest.raises(ValueError):
        _job(prompt="a", prompt_file="b").validate()


def test_validate_bad_name():
    with pytest.raises(ValueError):
        _job(name="has space").validate()
    with pytest.raises(ValueError):
        _job(name="-leading").validate()


def test_validate_missing_claude():
    with pytest.raises(ValueError):
        _job(claude_path="/no/such/claude").validate()


def test_validate_bad_permission_mode():
    with pytest.raises(ValueError):
        _job(permission_mode="yolo").validate()


def test_to_from_dict_roundtrip():
    j = _job(days=(0, 2, 4), extra_args=["--max-turns", "3"])
    back = JobSpec.from_dict(j.to_dict())
    assert back == j
    assert back.days == (0, 2, 4)


def test_from_dict_tolerates_unknown_keys():
    d = _job().to_dict()
    d["future_field"] = "ignored"
    assert JobSpec.from_dict(d).name == "j"
