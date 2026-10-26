
import argparse
from pathlib import Path
from shutil import copytree, rmtree
import logging
import sys
from typing import Literal, Optional

from PyInstaller.__main__ import run as run_installer


Platform = Literal["windows", "linux"]


def pyinstaller_build(
        app_name: str,
        platform: Platform = "windows",
        upx_folder_name: Optional[str] = None,
        rm_build: bool = True,
        move_dist: bool = True,
        rm_spec: bool = True,
        source_file: Optional[Path] = None,
        icon_name: Optional[str] = None) -> None:
    """Build a standalone application with PyInstaller.

    Args:
        app_name: Executable name without extension.
        platform: Target platform. Must match the OS running PyInstaller.
        upx_folder_name: Optional UPX directory inside scripts/upx/.
        rm_build: Remove temporary build files after a successful build.
        move_dist: Move the application into the final platform directory.
        rm_spec: Remove the generated PyInstaller spec file.
        source_file: Source script relative to src/. Defaults to app_name.py.
        icon_name: Windows icon in assets/. Defaults to app_name.ico.
    """
    if platform not in ("windows", "linux"):
        raise ValueError(f"Unsupported platform: {platform}")

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )
    logger = logging.getLogger(__name__)

    scripts_folder = Path(__file__).resolve().parent
    project_folder = scripts_folder.parent

    sys.path.insert(0, str(project_folder))
    sys.path.insert(0, str(project_folder / "src"))

    from scripts.requirements_check import ensure_dependencies
    from __version__ import __version__

    version = __version__.replace(".", "_")
    version_folder = project_folder / "builds" / version
    platform_folder = version_folder / platform

    # Temporary files are kept separate from the final application.
    temp_folder = version_folder / f".{platform}_build"
    dist_folder = temp_folder / "dist"
    build_folder = temp_folder / "build"
    spec_folder = temp_folder / "spec"

    source_folder = project_folder / "src"
    app_file = source_file or Path(f"{app_name}.py")
    app_path = source_folder / app_file

    requirements_file = project_folder / "requirements-build.txt"
    upx_folder = scripts_folder / "upx"

    if not app_path.is_file():
        raise FileNotFoundError(f"Source file not found: {app_path}")

    ensure_dependencies(requirements_file)

    # Clear only temporary files; never delete the previous release here.
    if temp_folder.exists():
        rmtree(temp_folder)

    temp_folder.mkdir(parents=True)

    args = [
        str(app_path),
        f"--name={app_name}",
        "--noconfirm",
        "--clean",
        f"--distpath={dist_folder}",
        f"--workpath={build_folder}",
        f"--specpath={spec_folder}",
        "--hidden-import=mpl_toolkits.basemap",
        "--collect-data=mpl_toolkits.basemap_data",
        "--hidden-import=OSMPythonTools",
        "--collect-data=OSMPythonTools",
        "--exclude-module=PyQt5",
        "--exclude-module=tkinter",
        "--exclude-module=unittest",
    ]

    if platform == "windows":
        args.extend(["--noconsole"])

        icon_file = project_folder / "assets" / (
            icon_name or f"{app_name}.ico"
        )
        if icon_file.is_file():
            args.append(f"--icon={icon_file}")

        if upx_folder_name:
            upx_path = upx_folder / upx_folder_name
            if not upx_path.is_dir():
                raise FileNotFoundError(f"UPX directory not found: {upx_path}")
            args.append(f"--upx-dir={upx_path}")

    try:
        run_installer(args)

        dist_app_folder = dist_folder / app_name
        if not dist_app_folder.is_dir():
            raise FileNotFoundError(
                f"PyInstaller output not found: {dist_app_folder}"
            )

        # Copy resources alongside the executable.
        for folder_name in (
                "assets", "configs", "fonts", "modules", "style"):
            src = project_folder / folder_name
            if src.is_dir():
                copytree(
                    src,
                    dist_app_folder / folder_name,
                    dirs_exist_ok=True
                )

        if move_dist:
            platform_folder.mkdir(parents=True, exist_ok=True)
            final_folder = platform_folder / app_name
            old_folder = platform_folder / f".{app_name}.old"

            # Keep the previous build until the new one is ready.
            if old_folder.exists():
                rmtree(old_folder)

            if final_folder.exists():
                final_folder.rename(old_folder)

            try:
                dist_app_folder.rename(final_folder)
            except Exception:
                if old_folder.exists() and not final_folder.exists():
                    old_folder.rename(final_folder)
                raise

            if old_folder.exists():
                rmtree(old_folder)

            logger.info("Build completed: %s", final_folder)
        else:
            logger.info("Build completed: %s", dist_app_folder)

        if rm_spec and spec_folder.exists():
            rmtree(spec_folder)

        if rm_build and build_folder.exists():
            rmtree(build_folder)

        # Remove the temporary directory if it is now empty.
        if temp_folder.exists():
            try:
                temp_folder.rmdir()
            except OSError:
                pass

    except Exception:
        logger.exception("Application build failed")
        raise


def prepared_build(
        name: str = "earth_crawler",
        platform: Platform = "windows") -> None:
    """Prepare platform-specific options and build the application."""
    upx_folder_name = (
        "upx-5.2.1-win64" if platform == "windows" else None
    )

    pyinstaller_build(
        app_name=name,
        platform=platform,
        upx_folder_name=upx_folder_name,
        rm_build=True,
        move_dist=True,
        rm_spec=True,
        icon_name="app_icon.ico",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build the application with PyInstaller."
    )
    parser.add_argument(
        "--platform",
        choices=("windows", "linux"),
        default="windows",
        help="Target platform (default: windows).",
    )
    args = parser.parse_args()

    prepared_build(platform=args.platform)
