from __future__ import annotations

from pathlib import Path, PureWindowsPath

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


class PathSafetyError(ValueError):
    """Raised when a configured path violates write safety constraints."""



def resolve_base_dir(base_dir: str | Path | None = None) -> Path:
    candidate = Path(base_dir) if base_dir is not None else Path.cwd()
    return candidate.expanduser().resolve()



def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False



def _contains_device_segments(raw_path: str) -> bool:
    normalized = raw_path.strip()
    if normalized.startswith("\\\\.\\") or normalized.startswith("\\\\?\\"):
        return True
    if normalized.startswith("/dev/"):
        return True

    for part in PureWindowsPath(normalized).parts:
        cleaned = part.rstrip(" .").upper()
        if cleaned in _WINDOWS_RESERVED_NAMES:
            return True
    return False



def _reject_symlink_traversal(path: Path, base_dir: Path) -> None:
    if path.exists() and path.is_symlink():
        raise PathSafetyError(f"Write target cannot be a symlink: '{path}'.")

    current = path.parent
    while _is_relative_to(current, base_dir):
        if current.exists() and current.is_symlink():
            raise PathSafetyError(f"Write target traverses symlinked parent directory: '{current}'.")
        if current == base_dir:
            break
        current = current.parent



def resolve_write_path(
    path: str | Path,
    *,
    base_dir: str | Path | None = None,
    reject_symlink_traversal: bool = True,
) -> Path:
    raw = str(path).strip()
    if not raw:
        raise PathSafetyError("Output path must be a non-empty string.")
    if _contains_device_segments(raw):
        raise PathSafetyError(f"Device paths are not allowed for output: '{path}'.")

    approved_base = resolve_base_dir(base_dir)
    source_path = Path(raw).expanduser()
    if not source_path.is_absolute():
        source_path = approved_base / source_path

    resolved_path = source_path.resolve(strict=False)
    if not _is_relative_to(resolved_path, approved_base):
        raise PathSafetyError(
            f"Resolved output path '{resolved_path}' escapes approved base directory '{approved_base}'."
        )

    if reject_symlink_traversal:
        _reject_symlink_traversal(resolved_path, approved_base)

    return resolved_path
