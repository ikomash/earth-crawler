
import logging
import subprocess
import argparse

from prepare_release import get_project_data
from project_data_manager import LINUX_BUILD_DIR, DISTROS, ROOT_DIR


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_linux(distro: str = "debian_12") -> None:
    """
    Build the Linux application using Docker Compose.

    Args:
        distro(str, optional):
            The Linux distribution to build for. Must be one of 'debian_12' or
            'ubuntu_22_04'. Defaults to 'debian_12'.

    """
    distro = distro.lower()
    if distro not in DISTROS:
        raise ValueError(f"Unsupported distro: {distro}")

    compose_file = LINUX_BUILD_DIR / distro.capitalize() / "compose.yaml"
    name, version = get_project_data()

    logger.info("Project: %s", name)
    logger.info("Version: %s", version)
    logger.info("Distro: %s", distro)
    logger.info("Building Linux application...")

    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "build",
        ],
        cwd=ROOT_DIR,
        check=True,
    )

    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "run",
            "--rm",
            "earth-crawler-build",
        ],
        cwd=ROOT_DIR,
        check=True,
    )

    logger.info(
        "Linux build completed: builds/%s/linux/",
        version.replace(".", "_"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Linux app in Docker.")
    parser.add_argument(
        "--distro",
        choices=(*DISTROS, "all"),
        default="all",
    )
    args = parser.parse_args()

    for d in (DISTROS if args.distro == "all" else (args.distro,)):
        build_linux(d)
