import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.runner import run_workflow_with_metadata

_INTERVAL_RE = re.compile(r"^(?P<value>\d+)\s*(?P<unit>[smhd]|seconds?|minutes?|hours?|days?)$", re.IGNORECASE)


@dataclass(frozen=True)
class QuietHours:
    start: dt_time
    end: dt_time

    def contains(self, value: datetime) -> bool:
        current = value.timetz().replace(tzinfo=None)
        if self.start < self.end:
            return self.start <= current < self.end
        return current >= self.start or current < self.end


@dataclass(frozen=True)
class SchedulePolicy:
    timezone: ZoneInfo
    mode: str
    interval: timedelta | None = None
    cron_minutes: set[int] | None = None
    cron_hours: set[int] | None = None
    cron_days: set[int] | None = None
    cron_months: set[int] | None = None
    cron_weekdays: set[int] | None = None
    quiet_hours: QuietHours | None = None
    max_missed_runs_to_catch_up: int = 0

    @classmethod
    def from_export_config(cls, export_cfg: dict[str, Any]) -> "SchedulePolicy":
        schedule = export_cfg.get("schedule")
        if not schedule:
            raise ValueError("export.schedule is required for daemon mode")

        tz_name = export_cfg.get("timezone", "UTC")
        timezone = ZoneInfo(tz_name)

        quiet = _parse_quiet_hours(export_cfg.get("quiet_hours"))
        max_missed = int(export_cfg.get("max_missed_runs_to_catch_up", 0))

        if isinstance(schedule, dict):
            if "cron" in schedule:
                schedule = schedule["cron"]
            elif "interval" in schedule:
                schedule = schedule["interval"]
            elif "every_hours" in schedule:
                schedule = f"every {schedule['every_hours']} hours"

        if isinstance(schedule, str) and len(schedule.split()) == 5:
            mins, hours, days, months, weekdays = schedule.split()
            return cls(
                timezone=timezone,
                mode="cron",
                cron_minutes=_parse_cron_field(mins, 0, 59),
                cron_hours=_parse_cron_field(hours, 0, 23),
                cron_days=_parse_cron_field(days, 1, 31),
                cron_months=_parse_cron_field(months, 1, 12),
                cron_weekdays=_parse_cron_weekday_field(weekdays),
                quiet_hours=quiet,
                max_missed_runs_to_catch_up=max_missed,
            )

        interval = _parse_interval(schedule)
        return cls(
            timezone=timezone,
            mode="interval",
            interval=interval,
            quiet_hours=quiet,
            max_missed_runs_to_catch_up=max_missed,
        )

    def now(self) -> datetime:
        return datetime.now(self.timezone)

    def next_run_after(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=self.timezone)
        else:
            value = value.astimezone(self.timezone)

        if self.mode == "interval":
            assert self.interval is not None
            base = value + self.interval
            return self._adjust_for_quiet_hours(base)

        current = value.replace(second=0, microsecond=0) + timedelta(minutes=1)
        while True:
            if self._matches_cron(current):
                return self._adjust_for_quiet_hours(current)
            current += timedelta(minutes=1)

    def due_runs_since(self, last_planned: datetime, until: datetime) -> list[datetime]:
        occurrences: list[datetime] = []
        cursor = last_planned
        while True:
            next_run = self.next_run_after(cursor)
            if next_run > until:
                break
            occurrences.append(next_run)
            cursor = next_run
            if self.max_missed_runs_to_catch_up > 0 and len(occurrences) > self.max_missed_runs_to_catch_up:
                break
        if self.max_missed_runs_to_catch_up <= 0:
            return []
        if len(occurrences) > self.max_missed_runs_to_catch_up:
            skipped = len(occurrences) - self.max_missed_runs_to_catch_up
            logging.warning(
                "Missed runs exceed cap. skipped=%s cap=%s",
                skipped,
                self.max_missed_runs_to_catch_up,
            )
            occurrences = occurrences[-self.max_missed_runs_to_catch_up :]
        return occurrences

    def _matches_cron(self, value: datetime) -> bool:
        weekday = (value.weekday() + 1) % 7
        return (
            value.minute in (self.cron_minutes or set())
            and value.hour in (self.cron_hours or set())
            and value.day in (self.cron_days or set())
            and value.month in (self.cron_months or set())
            and weekday in (self.cron_weekdays or set())
        )

    def _adjust_for_quiet_hours(self, candidate: datetime) -> datetime:
        if not self.quiet_hours:
            return candidate
        if not self.quiet_hours.contains(candidate):
            return candidate

        next_allowed = _end_of_quiet_window(candidate, self.quiet_hours)
        logging.info(
            "Scheduled time falls in quiet hours. original=%s deferred_to=%s",
            candidate.isoformat(),
            next_allowed.isoformat(),
        )
        return self.next_run_after(next_allowed - timedelta(seconds=1))


def run_daemon(config_path: str, state_path: str = "state/run_history.json") -> int:
    from src.config_io import load_json

    cfg = load_json(config_path)
    export_cfg = cfg.get("export", {})
    policy = SchedulePolicy.from_export_config(export_cfg)

    history = _load_history(state_path)
    now = policy.now()
    last_planned = _last_planned_time(history, policy.timezone)

    if last_planned is not None:
        missed_runs = policy.due_runs_since(last_planned=last_planned, until=now)
        if missed_runs:
            logging.info("Catch-up scan found %s missed run(s)", len(missed_runs))
        for missed in missed_runs:
            logging.info("Executing catch-up run for planned_time=%s", missed.isoformat())
            _execute_and_persist(config_path, state_path, planned_time=missed, catch_up=True)

    while True:
        current = policy.now()
        next_run = policy.next_run_after(current)
        sleep_seconds = max(0.0, (next_run - current).total_seconds())
        logging.info(
            "Scheduler decision: now=%s next_run=%s sleep_seconds=%.2f",
            current.isoformat(),
            next_run.isoformat(),
            sleep_seconds,
        )

        _sleep_until(next_run, policy)
        _execute_and_persist(config_path, state_path, planned_time=next_run, catch_up=False)


def _execute_and_persist(config_path: str, state_path: str, planned_time: datetime, catch_up: bool) -> None:
    started_at = datetime.now(UTC)
    result = run_workflow_with_metadata(config_path)
    completed_at = datetime.now(UTC)

    record = {
        "planned_time": planned_time.isoformat(),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "success": bool(result.get("success", False)),
        "output_file": result.get("output_file"),
        "exit_code": result.get("exit_code", 1),
        "catch_up": catch_up,
    }
    _append_history(state_path, record)
    logging.info(
        "Run recorded: planned_time=%s success=%s catch_up=%s output=%s",
        record["planned_time"],
        record["success"],
        record["catch_up"],
        record["output_file"],
    )


def _sleep_until(target: datetime, policy: SchedulePolicy) -> None:
    while True:
        now = policy.now()
        seconds = (target - now).total_seconds()
        if seconds <= 0:
            return
        time.sleep(min(seconds, 30))


def _load_history(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, dict):
        return payload.get("runs", [])
    if isinstance(payload, list):
        return payload
    return []


def _append_history(path: str, record: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    history = _load_history(path)
    history.append(record)
    with p.open("w", encoding="utf-8") as file:
        json.dump({"runs": history}, file, indent=2)


def _last_planned_time(history: list[dict[str, Any]], timezone: ZoneInfo) -> datetime | None:
    for item in reversed(history):
        planned = item.get("planned_time")
        if not planned:
            continue
        parsed = datetime.fromisoformat(planned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone)
        return parsed.astimezone(timezone)
    return None


def _parse_interval(value: Any) -> timedelta:
    if isinstance(value, (int, float)):
        return timedelta(seconds=float(value))

    if not isinstance(value, str):
        raise ValueError("Unsupported schedule format. Use cron expression or interval string.")

    normalized = value.strip().lower()
    if normalized.startswith("every "):
        normalized = normalized[len("every ") :]

    match = _INTERVAL_RE.match(normalized)
    if not match:
        raise ValueError(f"Invalid interval schedule: {value}")

    amount = int(match.group("value"))
    unit = match.group("unit").lower()

    if unit.startswith("s"):
        return timedelta(seconds=amount)
    if unit.startswith("m"):
        return timedelta(minutes=amount)
    if unit.startswith("h"):
        return timedelta(hours=amount)
    return timedelta(days=amount)


def _parse_time(value: str) -> dt_time:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format '{value}', expected HH:MM")
    return dt_time(hour=int(parts[0]), minute=int(parts[1]))


def _parse_quiet_hours(value: Any) -> QuietHours | None:
    if value is None:
        return None

    if isinstance(value, str) and "-" in value:
        start_raw, end_raw = [part.strip() for part in value.split("-", maxsplit=1)]
        return QuietHours(start=_parse_time(start_raw), end=_parse_time(end_raw))

    if isinstance(value, dict):
        start_raw = value.get("start")
        end_raw = value.get("end")
        if start_raw and end_raw:
            return QuietHours(start=_parse_time(start_raw), end=_parse_time(end_raw))

    raise ValueError("quiet_hours must be omitted, a string 'HH:MM-HH:MM', or {start, end}.")


def _parse_cron_field(field: str, minimum: int, maximum: int) -> set[int]:
    field = field.strip()
    if field == "*":
        return set(range(minimum, maximum + 1))

    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            range_part, step_part = part.split("/", maxsplit=1)
            step = int(step_part)
            if range_part == "*":
                start, end = minimum, maximum
            elif "-" in range_part:
                start_raw, end_raw = range_part.split("-", maxsplit=1)
                start, end = int(start_raw), int(end_raw)
            else:
                start = int(range_part)
                end = maximum
            for value in range(start, end + 1, step):
                if minimum <= value <= maximum:
                    values.add(value)
            continue

        if "-" in part:
            start_raw, end_raw = part.split("-", maxsplit=1)
            values.update(range(int(start_raw), int(end_raw) + 1))
            continue

        values.add(int(part))

    return {value for value in values if minimum <= value <= maximum}


def _parse_cron_weekday_field(field: str) -> set[int]:
    values = _parse_cron_field(field, 0, 7)
    normalized: set[int] = set()
    for value in values:
        if value == 7:
            normalized.add(0)
        else:
            normalized.add(value)
    return normalized


def _end_of_quiet_window(current: datetime, quiet: QuietHours) -> datetime:
    date_part = current.date()
    start_dt = datetime.combine(date_part, quiet.start, tzinfo=current.tzinfo)
    end_dt = datetime.combine(date_part, quiet.end, tzinfo=current.tzinfo)

    if quiet.start < quiet.end:
        if current < end_dt:
            return end_dt
        return end_dt + timedelta(days=1)

    if current >= start_dt:
        return end_dt + timedelta(days=1)
    return end_dt
