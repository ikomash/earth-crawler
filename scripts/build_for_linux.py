
import logging
import subprocess
from pathlib import Path

from prepare_release import get_project_data


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT_DIR / "docker" / "linux_build" / "compose.yaml"


def build_linux() -> None:
    """Build the Linux application using Docker Compose."""
    name, version = get_project_data()

    logger.info("Project: %s", name)
    logger.info("Version: %s", version)
    logger.info("Building Linux application...")

    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
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
            str(COMPOSE_FILE),
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
    build_linux()
