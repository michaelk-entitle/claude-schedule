"""Job specification: parsing, validation, and the serialized JobSpec model.

A JobSpec fully describes one scheduled Claude Code job. It is serialized to
``<config>/jobs/<name>.json`` and read back by the runner at fire time, so it
stores only JSON-friendly, already-resolved (absolute) values.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from pathlib import Path

# Day handling -------------------------------------------------------------
# Canonical day index: 0..6 == Monday..Sunday (matches datetime.weekday()).
# Letters use the classic timetable notation the user supplied: MTWRFSU.
DAY_LETTERS = "MTWRFSU"  # M=Mon T=Tue W=Wed R=Thu F=Fri S=Sat U=Sun
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_LETTER_TO_IDX = {c: i for i, c in enumerate(DAY_LETTERS)}
_DAY_ALIASES = {
    "daily": "MTWRFSU",
    "everyday": "MTWRFSU",
    "all": "MTWRFSU",
    "weekdays": "MTWRF",
    "weekday": "MTWRF",
    "weekends": "SU",
    "weekend": "SU",
}

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DURATION_RE = re.compile(r"(\d+)([smhd])")
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")


def parse_days(spec: str) -> tuple[int, ...]:
    """Parse 'MTWRFSU' letters or an alias (daily/weekdays/weekends) into day indices."""
    raw = spec.strip().lower()
    letters = _DAY_ALIASES[raw] if raw in _DAY_ALIASES else spec.strip().upper()
    if not letters:
        raise ValueError("no days given")
    idx: set[int] = set()
    for ch in letters:
        if ch not in _LETTER_TO_IDX:
            raise ValueError(
                f"invalid day {ch!r}; use letters MTWRFSU "
                "(M=Mon T=Tue W=Wed R=Thu F=Fri S=Sat U=Sun) "
                "or an alias: daily, weekdays, weekends"
            )
        idx.add(_LETTER_TO_IDX[ch])
    return tuple(sorted(idx))


def format_days(days: tuple[int, ...]) -> str:
    return "".join(DAY_LETTERS[i] for i in sorted(days))


def parse_time(spec: str) -> tuple[int, int]:
    """Parse 24-hour HH:MM into (hour, minute)."""
    m = _TIME_RE.match(spec.strip())
    if not m:
        raise ValueError(f"invalid time {spec!r}; expected 24-hour HH:MM (e.g. 09:00 or 23:30)")
    return int(m.group(1)), int(m.group(2))


def parse_duration(spec: str) -> int:
    """Parse a duration like '30m', '90s', '1h30m', '2h' into seconds. 0/none -> 0."""
    raw = spec.strip().lower()
    if raw in ("", "0", "none", "off", "never"):
        return 0
    matches = _DURATION_RE.findall(raw)
    # The matched tokens must reconstruct the whole string (no stray characters).
    if not matches or "".join(f"{n}{u}" for n, u in matches) != raw:
        raise ValueError(
            f"invalid duration {spec!r}; use number+unit s/m/h/d, optionally combined "
            "(e.g. 30m, 90s, 1h30m, 2h). Use 0 for none."
        )
    return sum(int(n) * _DURATION_UNITS[u] for n, u in matches)


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "none"
    parts: list[str] = []
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
    return "".join(parts)


@dataclass
class JobSpec:
    """One scheduled Claude Code job. All paths are absolute and pre-resolved."""

    name: str
    hour: int
    minute: int
    days: tuple[int, ...]
    claude_path: str

    # what claude runs
    prompt: str | None = None
    prompt_file: str | None = None
    repo: str | None = None
    model: str | None = None
    permission_mode: str = "auto"  # autonomous by default: auto-approves safe actions, aborts on risky ones
    allowed_tools: str | None = None
    bare: bool = False
    output_format: str | None = None
    extra_args: list[str] = field(default_factory=list)

    # how it runs
    timeout_seconds: int = 1800
    env_file: str | None = None
    log_path: str = ""
    node_bin_dir: str | None = None

    # scheduling + wake
    backend: str = ""
    wake: bool = True
    wake_before_seconds: int = 60

    created_at: str = ""

    @property
    def time_str(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"

    def wake_time(self) -> tuple[int, int]:
        """Clock time to wake the machine: job time minus wake_before, clamped to 00:00."""
        total = self.hour * 60 + self.minute - self.wake_before_seconds // 60
        total = max(total, 0)
        return total // 60, total % 60

    def schedule_summary(self) -> str:
        return f"{format_days(self.days)} at {self.time_str}"

    def validate(self) -> None:
        errors: list[str] = []
        if not NAME_RE.match(self.name or ""):
            errors.append(f"name {self.name!r} must be 1-64 chars of letters/digits/._- starting with alnum")
        if not (0 <= self.hour <= 23 and 0 <= self.minute <= 59):
            errors.append("time out of range")
        if not self.days:
            errors.append("at least one day required")
        if bool(self.prompt) == bool(self.prompt_file):
            errors.append("provide exactly one of --prompt or --prompt-file")
        if self.prompt_file and not Path(self.prompt_file).is_file():
            errors.append(f"prompt file not found: {self.prompt_file}")
        if self.repo and not Path(self.repo).is_dir():
            errors.append(f"repo directory not found: {self.repo}")
        if self.env_file and not Path(self.env_file).is_file():
            errors.append(f"env file not found: {self.env_file}")
        if not self.claude_path or not Path(self.claude_path).exists():
            errors.append(f"claude binary not found: {self.claude_path!r} (set it with --claude)")
        if self.timeout_seconds < 0:
            errors.append("timeout must be >= 0")
        if self.permission_mode and self.permission_mode not in PERMISSION_MODES:
            errors.append(f"--permission-mode must be one of {list(PERMISSION_MODES)}")
        if errors:
            raise ValueError("; ".join(errors))

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["days"] = list(self.days)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> JobSpec:
        d = dict(d)
        d["days"] = tuple(d.get("days", ()))
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})
