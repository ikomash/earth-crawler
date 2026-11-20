# Prepare project files for a release according to data foundin pyproject.toml.

import logging

from build_with_pyinstaller import prepared_build
from project_data_manager import (
    get_project_data,
    write_version_file,
    write_docker_env,
    copy_docker_env,
    VERSION_FILE,
    DOCKER_ENV_FILE,
    LINUX_BUILD_DIR,
    DISTROS,
)


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


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

    copy_docker_env(
        (LINUX_BUILD_DIR / d for d in DISTROS))

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
