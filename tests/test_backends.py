import pytest

from claude_schedule.backends import select_scheduler, select_wake
from claude_schedule.backends.cron import CronBackend
from claude_schedule.backends.launchd import LaunchdBackend
from claude_schedule.backends.systemd import SystemdBackend
from claude_schedule.backends.wake import LinuxWake, MacWake, NoopWake
from claude_schedule.environment import Environment


def _env(**over):
    base = dict(
        system="macos", arch="arm64", is_apple_silicon=True, shell="/bin/zsh",
        python_executable="/usr/bin/python3", claude_path="/bin/claude", claude_version=None, node_bin_dir=None,
        has_launchd=True, has_systemd_user=False, has_cron=True, has_schtasks=False,
        has_pmset=True, has_caffeinate=True, has_rtcwake=False, has_systemd_inhibit=False,
        has_gnu_timeout=False, has_gtimeout=False, is_root=False, sudo_noninteractive=False,
    )
    base.update(over)
    return Environment(**base)


def test_default_scheduler_macos():
    assert isinstance(select_scheduler(_env()), LaunchdBackend)


def test_default_scheduler_linux_systemd():
    assert isinstance(select_scheduler(_env(system="linux", has_launchd=False, has_systemd_user=True)), SystemdBackend)


def test_default_scheduler_linux_cron_fallback():
    assert isinstance(select_scheduler(_env(system="linux", has_launchd=False, has_systemd_user=False)), CronBackend)


def test_override():
    assert isinstance(select_scheduler(_env(), "cron"), CronBackend)


def test_unknown_backend():
    with pytest.raises(ValueError):
        select_scheduler(_env(), "bogus")


def test_no_scheduler():
    with pytest.raises(RuntimeError):
        select_scheduler(_env(system="unknown", has_launchd=False, has_cron=False, has_schtasks=False))


def test_select_wake():
    assert isinstance(select_wake(_env()), MacWake)
    assert isinstance(select_wake(_env(system="linux")), LinuxWake)
    assert isinstance(select_wake(_env(system="unknown")), NoopWake)
