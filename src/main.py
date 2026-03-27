import argparse

from src.logging_setup import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valve Export Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    trainer_parser = subparsers.add_parser("trainer", help="Run interactive trainer")
    trainer_parser.add_argument(
        "--backend",
        default="win32",
        choices=["win32", "uia"],
        help="pywinauto backend",
    )

    run_parser = subparsers.add_parser("run", help="Run saved workflow")
    run_parser.add_argument(
        "--config",
        required=True,
        help="Path to workflow config JSON",
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

    if args.command == "trainer":
        from src.trainer import run_trainer

        return run_trainer(backend=args.backend)

    if args.command == "run":
        from src.runner import run_workflow

        return run_workflow(args.config)

    if args.command == "check":
        from src.runner import check_workflow

        return check_workflow(args.config, resolve_selectors=args.resolve_selectors)

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
