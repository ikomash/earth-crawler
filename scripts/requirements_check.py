from __future__ import annotations

from importlib.metadata import PackageNotFoundError, distribution
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional


log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
REQUIREMENTS_FILE = PROJECT_ROOT.parent.joinpath("requirements-build.txt")


def parse_requirements(path: Path) -> list[str]:
    """
    Read a requirements file and return a list of clean package names.

    Skips:
      - blank lines
      - comments (starting with '#')
      - inline comments (everything after ' #')
      - pip options like '-r other.txt', '--index-url ...'
      - environment markers and version specifiers (we only need the name)
    """
    if not path.exists():
        raise FileNotFoundError(f"Requirements file not found: {path}")

    packages: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if " #" in line:
            line = line.split(" #", 1)[0].strip()

        if line.startswith("-"):
            continue

        name = line.split(";", 1)[0].strip()
        for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
            if sep in name:
                name = name.split(sep, 1)[0].strip()

        if name:
            packages.append(name)

    return packages


def is_installed(package: str) -> bool:
    """True if the distribution is present in the current interpreter."""
    try:
        distribution(package)  # Lookup by distribution name (pip name)
        return True
    except PackageNotFoundError:
        return False


def install(package: str) -> None:
    """Install a single package using the current interpreter's pip."""
    log.info("  -> installing '%s' ...", package)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", package]
    )


def ensure_dependencies(
    requirements_file: Optional[Path] = None,
) -> bool:
    """
    Check every requirement and install the missing ones.

    Uses the module-level logger. The caller is responsible for
    configuring logging (handlers, level, format).

    Args:
        requirements_file (Optional[Path]):
            Path to requirements file. Defaults to requirements-build.txt.

    Returns:
        True if everything is installed (or was installed successfully),
        False if the requirements file is missing or empty.
    """
    path = requirements_file or REQUIREMENTS_FILE

    try:
        packages = parse_requirements(path)
    except FileNotFoundError as e:
        log.warning("%s", e)
        return False

    if not packages:
        log.warning("No dependencies found in %s.", path.name)
        return False

    log.info(
        "Checking %d dependencies from %s...",
        len(packages),
        path.name,
    )

    missing: list[str] = []
    for pkg in packages:
        if is_installed(pkg):
            log.info("[ok]      %s", pkg)
        else:
            log.info("[missing] %s", pkg)
            missing.append(pkg)

    if not missing:
        log.info("All dependencies are already installed. Nothing to do.")
        return True

    log.info("Installing %d missing package(s)...", len(missing))
    for pkg in missing:
        install(pkg)

    log.info("Done. All dependencies are installed.")
    return True


if __name__ == "__main__":
    # Standalone use: configure a minimal console logger.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ensure_dependencies()
