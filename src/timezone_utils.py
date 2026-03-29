from datetime import timezone, tzinfo
from zoneinfo import ZoneInfo

_UTC_ALIASES = {"UTC", "ETC/UTC", "ETC/GMT", "GMT", "Z", "ZULU"}


def resolve_timezone(name: str) -> tzinfo:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Timezone must be a non-empty string.")

    tz_name = name.strip()
    if tz_name.upper() in _UTC_ALIASES:
        return timezone.utc

    try:
        return ZoneInfo(tz_name)
    except Exception as exc:  # pragma: no cover - defensive conversion
        raise ValueError(f"No time zone found with key {tz_name}") from exc
