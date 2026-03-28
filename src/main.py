import argparse
import sys

from src.cli_theme import build_theme
from src.logging_setup import setup_logging


TOOL_NAME = "Valve Export Tool"


def _is_interactive() -> bool:
    return sys.stdout.isatty() and sys.stdin.isatty()


def _color(text: str, code: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def _print_startup_banner(command: str) -> None:
    if not _is_interactive():
        return

    mode = command.upper()
    print(f"{_color(TOOL_NAME, '1;36', enabled=True)} · mode: {mode}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valve Export Tool")
    parser.add_argument(
        "--theme",
        choices=["minimal", "standard", "vibrant"],
        default=None,
        help="CLI theme mode (or set DATA_EXPORTER_THEME)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    trainer_parser = subparsers.add_parser("trainer", help="Run interactive trainer")
    trainer_parser.add_argument(
        "--backend",
        default="win32",
        choices=["win32", "uia"],
        help="pywinauto backend",
    )
    trainer_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output in trainer mode",
    )

    run_parser = subparsers.add_parser("run", help="Run saved workflow")
    run_parser.add_argument(
        "--config",
        required=True,
        help="Path to workflow config JSON",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate workflow control resolution without performing UI actions",
    )
    run_parser.add_argument(
        "--path-base-dir",
        default=None,
        help="Approved base directory for workflow output writes (default: config file directory)",
    )

    daemon_parser = subparsers.add_parser("daemon", help="Run scheduled daemon")
    daemon_parser.add_argument(
        "--config",
        required=True,
        help="Path to workflow config JSON",
    )
    daemon_parser.add_argument(
        "--state-file",
        default="state/run_history.json",
        help="Path to scheduler state history JSON",
    )
    daemon_parser.add_argument(
        "--path-base-dir",
        default=None,
        help="Approved base directory for workflow output writes (default: config file directory)",
    )

    check_parser = subparsers.add_parser("check", help="Validate workflow config")
    check_parser.add_argument(
        "--config",
        required=True,
        help="Path to workflow config JSON",
    )
    check_parser.add_argument(
        "--resolve-selectors",
        action="store_true",
        help="Try to resolve window/control selectors without performing actions",
    )
    check_parser.add_argument(
        "--path-base-dir",
        default=None,
        help="Approved base directory for output path validation (default: config file directory)",
    )

    init_parser = subparsers.add_parser("init", help="Generate a starter workflow config")
    init_parser.add_argument(
        "--config",
        required=True,
        help="Path where starter workflow config JSON will be written",
    )
    init_parser.add_argument(
        "--backend",
        default="win32",
        choices=["win32", "uia"],
        help="pywinauto backend for generated config",
    )
    init_parser.add_argument(
        "--output-dir",
        default="exports",
        help="Default export output directory",
    )
    init_parser.add_argument(
        "--schedule",
        default="every 6 hours",
        help="Default export schedule (cron or interval form)",
    )
    init_parser.add_argument(
        "--timezone",
        default="UTC",
        help="Default IANA timezone for schedule interpretation",
    )

    package_parser = subparsers.add_parser("package", help="Build a standalone executable with PyInstaller")
    package_parser.add_argument(
        "--name",
        default="valve-export-tool",
        help="Executable name (without extension)",
    )
    package_parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build a folder-based executable instead of a single-file executable",
    )
    package_parser.add_argument(
        "--dist-dir",
        default="dist",
        help="Output folder for final artifacts",
    )
    package_parser.add_argument(
        "--work-dir",
        default="build",
        help="Temporary build working directory",
    )
    package_parser.add_argument(
        "--spec-dir",
        default=".",
        help="Directory for generated .spec file",
    )
    package_parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not clean PyInstaller cache before building",
    )
    package_parser.add_argument(
        "--pyinstaller-arg",
        action="append",
        default=[],
        help="Extra raw argument passed to PyInstaller (can be repeated)",
    )

    return parser


def main() -> int:
    setup_logging()
    args = build_parser().parse_args()
    _print_startup_banner(args.command)

    if args.command == "trainer":
        from src.trainer import run_trainer

        return run_trainer(backend=args.backend, no_color=args.no_color)

    if args.command == "run":
        from src.runner import run_workflow

        return run_workflow(args.config, dry_run=args.dry_run, path_base_dir=args.path_base_dir)

    if args.command == "daemon":
        from src.scheduler import run_daemon

        return run_daemon(args.config, state_path=args.state_file, path_base_dir=args.path_base_dir)

    if args.command == "check":
        from src.runner import check_workflow

        return check_workflow(
            args.config,
            resolve_selectors=args.resolve_selectors,
            path_base_dir=args.path_base_dir,
        )

    if args.command == "init":
        from src.init_config import init_config

        return init_config(
            config_path=args.config,
            backend=args.backend,
            output_dir=args.output_dir,
            schedule=args.schedule,
            timezone=args.timezone,
        )

    if args.command == "package":
        from src.builder import build_executable

        return build_executable(
            executable_name=args.name,
            one_file=not args.onedir,
            dist_dir=args.dist_dir,
            work_dir=args.work_dir,
            spec_dir=args.spec_dir,
            clean=not args.no_clean,
            extra_pyinstaller_args=args.pyinstaller_arg,
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
