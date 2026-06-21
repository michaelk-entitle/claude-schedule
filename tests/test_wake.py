from claude_schedule.backends.base import WakeResult
from claude_schedule.cli import _apply_wake


class _StubWake:
    name = "stub"
    supported = True

    def __init__(self):
        self.synced = False

    def sync(self, jobs):
        self.synced = True
        return WakeResult("stub", ["sudo do-it"], True, [])

    def plan(self, jobs):
        return WakeResult("stub", ["sudo do-it"], False, ["a note"])


def test_no_sudo_by_default(capsys):
    # the whole point: without --arm-wake, claude-schedule never runs the privileged command,
    # it only prints it for the user to run themselves.
    w = _StubWake()
    _apply_wake([], arm=False, wake=w)
    assert w.synced is False
    assert "sudo do-it" in capsys.readouterr().out


def test_arm_wake_runs_it():
    w = _StubWake()
    _apply_wake([], arm=True, wake=w)
    assert w.synced is True
