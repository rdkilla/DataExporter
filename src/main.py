import argparse

from src.logging_setup import setup_logging
from src.runner import run_workflow
from src.trainer import run_trainer


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

    return parser


def main() -> int:
    setup_logging()
    args = build_parser().parse_args()

    if args.command == "trainer":
        return run_trainer(backend=args.backend)

    if args.command == "run":
        return run_workflow(args.config)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
