# Build the Docker image for the project.
import subprocess

from project_data_manager import get_project_data


if __name__ == "__main__":
    name, version = get_project_data()

    subprocess.run([
        "docker",
        "build",
        "-t",
        f"{name}:{version}",
        ".",
    ], check=True)
