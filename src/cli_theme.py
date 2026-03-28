import os
from dataclasses import dataclass

_THEME_ENV_VAR = "DATA_EXPORTER_THEME"
_VALID_MODES = {"minimal", "standard", "vibrant"}


@dataclass(frozen=True)
class ThemeConfig:
    mode: str = "standard"


class CliTheme:
    """Semantic CLI theming with lightweight rendering helpers."""

    _PALETTES = {
        "minimal": {
            "primary": "",
            "muted": "",
            "success": "",
            "error": "",
            "accent": "",
            "reset": "",
        },
        "standard": {
            "primary": "\033[36m",  # cyan
            "muted": "\033[90m",  # bright black
            "success": "\033[32m",  # green
            "error": "\033[31m",  # red
            "accent": "\033[35m",  # magenta
            "reset": "\033[0m",
        },
        "vibrant": {
            "primary": "\033[96m",  # bright cyan
            "muted": "\033[37m",  # white
            "success": "\033[92m",  # bright green
            "error": "\033[91m",  # bright red
            "accent": "\033[95m",  # bright magenta
            "reset": "\033[0m",
        },
    }

    def __init__(self, config: ThemeConfig | None = None):
        self.config = config or ThemeConfig()
        self._palette = self._PALETTES[self.config.mode]

    def stylize(self, text: str, style: str = "primary") -> str:
        prefix = self._palette.get(style, "")
        reset = self._palette["reset"] if prefix else ""
        return f"{prefix}{text}{reset}"

    def status_pill(self, label: str, style: str = "accent") -> str:
        return self.stylize(f"[{label}]", style)

    def banner(self, title: str, subtitle: str | None = None) -> str:
        border = self.stylize("=" * max(24, len(title) + 8), "accent")
        headline = self.stylize(f"  {title}", "primary")
        if not subtitle:
            return "\n".join([border, headline, border])
        return "\n".join([border, headline, self.stylize(f"  {subtitle}", "muted"), border])

    def section(self, title: str) -> str:
        return self.stylize(f"\n-- {title} --", "accent")

    def key_value_row(self, key: str, value: object, key_style: str = "muted", value_style: str = "primary") -> str:
        return f"{self.stylize(f'{key}:', key_style)} {self.stylize(str(value), value_style)}"

    def emit(self, text: str, style: str = "primary") -> None:
        print(self.stylize(text, style))

    def emit_section(self, title: str) -> None:
        print(self.section(title))

    def emit_banner(self, title: str, subtitle: str | None = None) -> None:
        print(self.banner(title, subtitle))


def resolve_theme_mode(cli_mode: str | None = None) -> str:
    mode = (cli_mode or os.getenv(_THEME_ENV_VAR, "standard")).strip().lower()
    return mode if mode in _VALID_MODES else "standard"


def build_theme(cli_mode: str | None = None) -> CliTheme:
    return CliTheme(ThemeConfig(mode=resolve_theme_mode(cli_mode)))
