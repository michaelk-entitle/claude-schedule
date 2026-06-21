"""``doctor`` — report what claude-schedule can and cannot do on this machine."""

from __future__ import annotations

from claude_schedule.environment import Environment, detect

OK, BAD, WARN = "✓", "✗", "⚠"  # ✓ ✗ ⚠


def _mark(cond: bool) -> str:
    return OK if cond else BAD


def _line(mark: str, label: str, detail: str = "") -> str:
    return f"  {mark} {label}" + (f": {detail}" if detail else "")


def build_report(env: Environment) -> tuple[list[str], bool]:
    """Return (lines, ready). ``ready`` is True when scheduling is actually possible."""
    out: list[str] = []
    scheduler = env.default_scheduler
    ready = bool(env.claude_path) and scheduler != "none"

    out.append("claude-schedule doctor")
    out.append("")
    out.append("System")
    out.append(_line(OK, "OS", f"{env.system} ({env.arch})"))
    out.append(_line(OK, "shell", env.shell or "unknown"))
    if env.is_apple_silicon:
        out.append(_line(WARN, "Apple Silicon", "wakes from SLEEP only — cannot power on from a full shutdown"))

    out.append("")
    out.append("Claude Code")
    claude_status = env.claude_path or "NOT FOUND (install Claude Code, or pass --claude)"
    out.append(_line(_mark(bool(env.claude_path)), "claude binary", claude_status))
    if env.claude_version:
        out.append(_line(OK, "version", env.claude_version))

    out.append("")
    out.append("Scheduler")
    out.append(_line(_mark(scheduler != "none"), "chosen backend", scheduler))
    out.append(_line(_mark(env.has_launchd), "launchd", "macOS native" if env.has_launchd else "n/a"))
    out.append(_line(_mark(env.has_systemd_user), "systemd --user", "available" if env.has_systemd_user else "n/a"))
    out.append(_line(_mark(env.has_cron), "cron", "available" if env.has_cron else "n/a"))
    out.append(_line(_mark(env.has_schtasks), "schtasks", "available" if env.has_schtasks else "n/a"))

    out.append("")
    out.append("Wake support")
    out.append(_line(_mark(env.default_wake != "none"), "chosen wake", env.default_wake))
    if env.system == "macos":
        out.append(_line(_mark(env.has_pmset), "pmset", "wake needs root; 'add' prints the command (or --arm-wake)"))
    if env.system == "linux":
        out.append(_line(_mark(env.has_rtcwake), "rtcwake", "best-effort; relies on systemd Persistent catch-up"))

    out.append("")
    out.append("Keep-awake during run")
    out.append(_line(_mark(env.keep_awake != "none"), "mechanism", env.keep_awake))

    out.append("")
    out.append("Timeout")
    out.append(_line(OK, "in-process", "enforced by claude-schedule itself (no external tool required)"))
    extras = [n for n, ok in (("timeout", env.has_gnu_timeout), ("gtimeout", env.has_gtimeout)) if ok]
    out.append(_line(OK, "also available", ", ".join(extras) or "none (not needed)"))

    out.append("")
    out.append("Privileges")
    out.append(_line(WARN if env.is_root else OK, "running as root", "yes" if env.is_root else "no (good)"))
    out.append(_line(OK, "passwordless sudo", "yes" if env.sudo_noninteractive else "no (you'll be prompted for wake)"))

    out.append("")
    out.append("Gotchas")
    for g in _gotchas(env):
        out.append(f"  {WARN} {g}")

    out.append("")
    out.append(_line(_mark(ready), "READY", "you can schedule jobs" if ready else "missing claude and/or a scheduler"))
    return out, ready


def _gotchas(env: Environment) -> list[str]:
    g: list[str] = []
    if env.system == "macos":
        g.append("Laptops: keep on AC power; lid-closed-on-AC is fine. On battery, system sleep may still occur.")
        g.append("macOS exposes ONE repeating wake slot; claude-schedule manages it across all wake jobs.")
    if env.system == "linux":
        g.append("User systemd timers cannot wake the machine; arrange BIOS/RTC wake or rely on Persistent catch-up.")
        g.append("To run while logged out: loginctl enable-linger $USER")
    if env.system == "windows":
        g.append("Enable 'Allow wake timers' in the active power plan for WakeToRun to work.")
    g.append("Unattended runs default to --permission-mode auto: Claude acts autonomously on safe steps and ABORTS "
             "on anything risky (no TTY to prompt). Use --permission-mode default for read-only, or plan to dry-run.")
    return g


def run_doctor() -> int:
    env = detect()
    lines, ready = build_report(env)
    print("\n".join(lines))
    return 0 if ready else 1
