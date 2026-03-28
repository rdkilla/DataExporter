import logging
import platform
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence


logger = logging.getLogger(__name__)


def _run_command(command: Sequence[str]) -> int:
    logger.info("Running packaging command: %s", " ".join(shlex.quote(part) for part in command))
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError:
        logger.error("Unable to run packaging command. Is Python available on PATH?")
        return 1

    if completed.returncode != 0:
        logger.error("Packaging command failed with exit code %s", completed.returncode)
        return completed.returncode
    return 0


def build_executable(
    executable_name: str,
    one_file: bool = True,
    dist_dir: str = "dist",
    work_dir: str = "build",
    spec_dir: str = ".",
    clean: bool = True,
    extra_pyinstaller_args: Sequence[str] | None = None,
) -> int:
    if platform.system().lower() != "windows":
        logger.warning(
            "You are building on %s. For best Windows 7 compatibility, build on a Windows host that matches your target architecture.",
            platform.system(),
        )

    entrypoint = Path(__file__).with_name("main.py")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        executable_name,
        "--distpath",
        dist_dir,
        "--workpath",
        work_dir,
        "--specpath",
        spec_dir,
    ]

    if clean:
        command.append("--clean")
    if one_file:
        command.append("--onefile")

    command.append(str(entrypoint))

    if extra_pyinstaller_args:
        command.extend(extra_pyinstaller_args)

    exit_code = _run_command(command)
    if exit_code == 0:
        if one_file:
            exe_suffix = ".exe" if platform.system().lower() == "windows" else ""
            output_name = f"{executable_name}{exe_suffix}"
            output_path = Path(dist_dir) / output_name
            logger.info("Packaging complete (onefile). Expected output: %s", output_path)
            logger.info("Next step: run or distribute this single executable.")
        else:
            output_path = Path(dist_dir) / executable_name
            logger.info("Packaging complete (onedir). Expected output folder: %s", output_path)
            logger.info("Next step: run the executable found inside this folder with its bundled dependencies.")

        if output_path.exists():
            logger.info("Verified packaged artifact exists at: %s", output_path)
        else:
            logger.warning("Expected packaged artifact not found at: %s", output_path)
    return exit_code
