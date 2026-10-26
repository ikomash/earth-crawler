# Prepare project files for a release according to data foundin pyproject.toml.

import logging
from pathlib import Path
import tomllib

from build_with_pyinstaller import prepared_build


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
PYPROJECT_FILE = ROOT_DIR.joinpath("pyproject.toml")
VERSION_FILE = ROOT_DIR.joinpath("src", "__version__.py")
DOCKER_ENV_FILE = ROOT_DIR.joinpath(".env")


def get_project_data() -> tuple[str, str]:
    """Read project name and version from pyproject.toml.
    Returns:
        tuple[str, str]: Project name and version.
    """
    with PYPROJECT_FILE.open("rb") as file:
        config = tomllib.load(file)

    try:
        name = config["project"]["name"]
    except KeyError as error:
        raise RuntimeError(
            "Project name is not defined in pyproject.toml"
        ) from error

    try:
        version = config["project"]["version"]
    except KeyError as error:
        raise RuntimeError(
            "Project version is not defined in pyproject.toml"
        ) from error

    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(
            "Project version in pyproject.toml must be a non-empty string"
        )

    return name, version


def write_version_file(version: str):
    """Write project version to __version__.py."""
    VERSION_FILE.write_text(
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )


def write_docker_env(version: str):
    """Write Docker Compose environment file."""
    DOCKER_ENV_FILE.write_text(
        f"VERSION={version}\n",
        encoding="utf-8",
    )


def prepare_release_minimal() -> tuple[str, str]:
    """
    Prepare project for release (minimal, no build).

    Returns:
        tuple[str, str]: Project name and version.
    """
    name, version = get_project_data()

    logger.info("Project name: %s", name)
    logger.info("Project version: %s", version)

    write_version_file(version)
    logger.info("Writing: %s", VERSION_FILE)

    write_docker_env(version)
    logger.info("Writing: %s", DOCKER_ENV_FILE)

    logger.info("Release metadata preparation completed.")
    logger.info("Docker image: %s:%s", name, version)
    return name, version


def prepare_release_full():
    """Prepare project for release (with build)."""
    name, version = prepare_release_minimal()
    prepared_build(name, "windows")
    prepared_build(name, "linux")


if __name__ == "__main__":
    # prepare_release_minimal()
    prepare_release_full()
