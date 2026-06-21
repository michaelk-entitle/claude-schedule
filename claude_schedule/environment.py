"""Detect the host: OS, architecture, claude binary, schedulers, wake + timeout support.

Detection drives backend selection and the ``doctor`` report. Everything here is
best-effort and side-effect free (apart from short ``--version`` / capability probes).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Common places a claude binary lives when it is not on a bare PATH.
CLAUDE_FALLBACK_PATHS = (
    "~/.local/bin/claude",
    "~/.claude/local/claude",
    "/usr/local/bin/claude",
    "/opt/homebrew/bin/claude",
)


def detect_system() -> str:
    return {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "unknown")


def resolve_claude(override: str | None = None) -> str | None:
    """Resolve an absolute path to the claude binary (launchd/cron get a bare PATH)."""
    if override:
        p = Path(override).expanduser()
        return str(p) if p.exists() else None
    found = shutil.which("claude")
    if found:
        return found
    for cand in CLAUDE_FALLBACK_PATHS:
        p = Path(cand).expanduser()
        if p.exists():
            return str(p)
    return None


def claude_version(path: str | None) -> str | None:
    if not path:
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout or out.stderr).strip() or None


def node_bin_dir() -> str | None:
    node = shutil.which("node")
    return str(Path(node).parent) if node else None


def _sudo_noninteractive() -> bool:
    if os.name != "posix" or not shutil.which("sudo"):
        return False
    try:
        return subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _systemd_user_available() -> bool:
    if detect_system() != "linux" or not shutil.which("systemctl"):
        return False
    try:
        return subprocess.run(
            ["systemctl", "--user", "show-environment"], capture_output=True, timeout=5
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@dataclass
class Environment:
    system: str
    arch: str
    is_apple_silicon: bool
    shell: str | None
    python_executable: str
    claude_path: str | None
    claude_version: str | None
    node_bin_dir: str | None
    has_launchd: bool
    has_systemd_user: bool
    has_cron: bool
    has_schtasks: bool
    has_pmset: bool
    has_caffeinate: bool
    has_rtcwake: bool
    has_systemd_inhibit: bool
    has_gnu_timeout: bool
    has_gtimeout: bool
    is_root: bool
    sudo_noninteractive: bool

    @property
    def default_scheduler(self) -> str:
        if self.system == "macos" and self.has_launchd:
            return "launchd"
        if self.system == "linux":
            return "systemd" if self.has_systemd_user else "cron"
        if self.system == "windows" and self.has_schtasks:
            return "schtasks"
        return "cron" if self.has_cron else "none"

    @property
    def default_wake(self) -> str:
        if self.system == "macos" and self.has_pmset:
            return "pmset"
        if self.system == "linux" and self.has_rtcwake:
            return "rtcwake (one-shot, best-effort)"
        if self.system == "windows":
            return "schtasks WakeToRun"
        return "none"

    @property
    def keep_awake(self) -> str:
        if self.system == "macos" and self.has_caffeinate:
            return "caffeinate"
        if self.system == "linux" and self.has_systemd_inhibit:
            return "systemd-inhibit"
        if self.system == "windows":
            return "SetThreadExecutionState"
        return "none"


def detect(with_claude_version: bool = True) -> Environment:
    system = detect_system()
    arch = platform.machine()
    claude = resolve_claude()
    return Environment(
        system=system,
        arch=arch,
        is_apple_silicon=(system == "macos" and arch in ("arm64", "aarch64")),
        shell=os.environ.get("SHELL"),
        python_executable=sys.executable,
        claude_path=claude,
        claude_version=claude_version(claude) if with_claude_version else None,
        node_bin_dir=node_bin_dir(),
        has_launchd=(system == "macos" and shutil.which("launchctl") is not None),
        has_systemd_user=_systemd_user_available(),
        has_cron=shutil.which("crontab") is not None,
        has_schtasks=shutil.which("schtasks") is not None,
        has_pmset=shutil.which("pmset") is not None,
        has_caffeinate=shutil.which("caffeinate") is not None,
        has_rtcwake=shutil.which("rtcwake") is not None,
        has_systemd_inhibit=shutil.which("systemd-inhibit") is not None,
        has_gnu_timeout=shutil.which("timeout") is not None,
        has_gtimeout=shutil.which("gtimeout") is not None,
        is_root=(os.name == "posix" and os.geteuid() == 0),
        sudo_noninteractive=_sudo_noninteractive(),
    )
