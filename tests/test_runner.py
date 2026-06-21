import sys

from claude_schedule.jobspec import JobSpec
from claude_schedule.runner import _load_env_file, build_claude_argv, build_run_env, wrap_keep_awake


def _job(**over):
    base = dict(name="j", hour=9, minute=0, days=(0,), claude_path="/bin/echo", prompt="hi")
    base.update(over)
    return JobSpec(**base)


def test_build_argv_minimal():
    assert build_claude_argv(_job()) == ["/bin/echo", "-p", "hi"]


def test_build_argv_all_flags():
    argv = build_claude_argv(
        _job(
            model="sonnet",
            permission_mode="acceptEdits",
            skip_permissions=True,
            allowed_tools="Bash,Read",
            bare=True,
            output_format="json",
            extra_args=["--max-turns", "3"],
        )
    )
    assert argv[:3] == ["/bin/echo", "-p", "hi"]
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "--dangerously-skip-permissions" in argv
    assert argv[argv.index("--allowed-tools") + 1] == "Bash,Read"
    assert "--bare" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[-2:] == ["--max-turns", "3"]


def test_build_argv_prompt_file(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("from file")
    assert build_claude_argv(_job(prompt=None, prompt_file=str(f)))[2] == "from file"


def test_build_run_env_prepends_paths(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    env = build_run_env(_job(node_bin_dir="/opt/node/bin", claude_path="/opt/claude/bin/claude"))
    assert env["PATH"].startswith("/opt/node/bin")
    assert "/opt/claude/bin" in env["PATH"]


def test_load_env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# comment\nexport FOO=bar\nBAZ="q u x"\nNOEQUALS\n')
    assert _load_env_file(str(f)) == {"FOO": "bar", "BAZ": "q u x"}


def test_wrap_keep_awake_mac():
    if sys.platform == "darwin":
        assert wrap_keep_awake(["claude", "-p"])[0] == "/usr/bin/caffeinate"
