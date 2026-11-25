from pathlib import Path
from shutil import copy2
import tomllib
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parent.parent
LINUX_BUILD_DIR = ROOT_DIR / "Docker" / "linux_build"
PYPROJECT_FILE = ROOT_DIR.joinpath("pyproject.toml")
VERSION_FILE = ROOT_DIR.joinpath("src", "__version__.py")
DOCKER_ENV_FILE = ROOT_DIR.joinpath(".env")
DISTROS = ("debian_12", "ubuntu_22_04")


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


def copy_docker_env(dirs: Iterable[Path]):
    """Copy Docker Compose environment file to specified directories."""
    for dir_path in dirs:
        target_file = dir_path / ".env"
        copy2(DOCKER_ENV_FILE, target_file)
