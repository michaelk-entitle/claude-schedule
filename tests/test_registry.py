import stat
import sys

import pytest

from claude_schedule import registry
from claude_schedule.jobspec import JobSpec

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")


def test_jobs_and_config_dirs_are_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SCHEDULE_HOME", str(tmp_path / "home"))
    assert stat.S_IMODE(registry.jobs_dir().stat().st_mode) == 0o700
    assert stat.S_IMODE(registry.config_home().stat().st_mode) == 0o700


def test_saved_job_file_is_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SCHEDULE_HOME", str(tmp_path / "home"))
    job = JobSpec(name="j", hour=9, minute=0, days=(0,), claude_path="/bin/echo", prompt="secret prompt")
    p = registry.save_job(job)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
