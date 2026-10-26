from enum import IntEnum
import hashlib
from pathlib import Path
from typing import Optional
from langcodes import Language
import requests
import logging

from app_data import ObjectsLanguage
from paths import Paths


class FileNames(IntEnum):
    """Modes for saving downloaded files."""
    COUNTRY = 0
    LANGUAGE = 1


class SkipModes(IntEnum):
    """Modes for skipping existing files."""
    OVERWRITE = 0
    SKIP = 1
    CHECKSUM = 2


def file_hash(filepath: Path) -> str:
    """
    Calculate MD5 hash for a file.

    Args:
        filepath (Path): Path to the file.

    Returns:
        str: MD5 hash of the file.
    """
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def compare_file_with_bytes(
    filepath: Path,
    compare_content: bytes
) -> bool:
    """
    Compares a local file with the given content.

    Args:
        filepath (Path): Path to the local file.
        compare_content (bytes): Content to compare with.

    Returns:
        bool: True if files are identical, False if different or file does
        not exist
    """
    if not filepath.exists():
        return False

    remote_hash = hashlib.md5(compare_content).hexdigest()
    local_hash = file_hash(filepath)
    return remote_hash == local_hash


def download_flag(
        language_code: str,
        output_folder: Path,
        file_names: FileNames = FileNames.LANGUAGE,
        found_languages: Optional[set[str]] = None,
        found_countries: Optional[set[str]] = None,
        skip_mode: SkipModes = SkipModes.SKIP
) -> tuple[str, str]:
    """
    Download an SVG flag by ISO country code and save it to the specified
    folder.

    Args:
        language_code (str): ISO language code (e.g., "en" for English).
        output_folder (Path): Path to the folder where the flag will be saved.
        file_names (FileNames):
            Enum value indicating whether to save the file under the language
            name or country code.
        found_languages (set[str], optional):
            Set of already found language codes.
        found_countries (set[str], optional):
            Set of already found country codes.
        skip_mode (SkipModes, optional):
            Enum value indicating how to handle existing files.
            Defaults to SkipModes.SKIP.

    Returns:
        tuple[str, str]: A tuple containing the original language code and the
            country code.
    """
    # Cleaning up the language code
    lang_original = language_code.strip()

    try:
        # .maximize() is required for langcodes to fill the territory field
        lang_obj = Language.get(lang_original).maximize()
        territory = lang_obj.territory
        # Convert to lower case since CDN does not accept 'US' or 'CN'
        country_code_final = \
            territory.lower() if territory else lang_original.lower()
    except Exception:
        country_code_final = lang_original.lower()

    # Create a folder if it does not exist
    if not output_folder.exists():
        output_folder.mkdir(parents=True, exist_ok=True)
        logging.info(f"Folder created: {output_folder}")

    # Save the file under the original language name (example: zh-hans.svg),
    if file_names == FileNames.LANGUAGE:
        if found_languages and lang_original in found_languages:
            logging.info(
                f"Flag for language '{lang_original}' already downloaded. "
                "Skip!"
            )
            return lang_original, country_code_final
        file_path = output_folder.joinpath(f"{lang_original.lower()}.svg")
    else:
        if found_countries and country_code_final in found_countries:
            logging.info(
                f"Flag for country '{country_code_final}' already downloaded. "
                "Skip!"
            )
            return lang_original, country_code_final
        file_path = output_folder.joinpath(f"{country_code_final}.svg")

    file_exists = file_path.exists()
    if skip_mode == SkipModes.SKIP and file_exists:
        logging.info(
            f"Flag for '{lang_original}' already exists. Skip!"
        )
        return lang_original, country_code_final

    # Create a link to the SVG and the path to the local file
    url = f"https://flagicons.lipis.dev/flags/4x3/{country_code_final}.svg"

    try:
        # Download the file
        response = requests.get(url, timeout=10)

        # If the response code is 200 (OK), save the file
        if response.status_code == 200:
            if file_exists and skip_mode == SkipModes.CHECKSUM:
                compare_result = compare_file_with_bytes(
                    file_path, response.content)
                if compare_result:
                    logging.info(
                        f"Flag for '{lang_original}' already exists and is "
                        "identical. Skip!"
                    )
                    return lang_original, country_code_final

            with open(file_path, "wb") as file:
                file.write(response.content)
            logging.info(
                f"Downloaded successfully: {file_path} "
                f"(Mapped '{lang_original}' -> '{country_code_final}')"
            )
        elif response.status_code == 404:
            logging.error(
                f"Error 404: Country code '{country_code_final}' "
                f"(for language '{lang_original}') not found."
            )
        else:
            logging.error(
                f"Failed to download. Status: {response.status_code}")

    except requests.exceptions.RequestException as e:
        logging.error(
            f"Network error while downloading {country_code_final}: {e}")
    finally:
        return lang_original, country_code_final


def download_flags(
        language_codes: list[str],
        output_folder: Path,
        file_names: FileNames = FileNames.LANGUAGE,
        skip_mode: SkipModes = SkipModes.SKIP,
        generate_enum: bool = True
):
    """Download multiple SVG flag files for the given language codes.

    Args:
        language_codes (list[str]): ISO language codes to resolve.
        output_folder (Path): Folder where the downloaded flags will be saved.
        file_names (FileNames): Naming scheme for the saved files.
        skip_mode (SkipModes, optional): Behavior for existing files.
        generate_enum (bool, optional): Whether to print generated enum code.
    """
    found_languages = set()
    found_countries = set()
    enum_lines = []

    for code in language_codes:
        try:
            language_code, country_code = download_flag(
                code,
                output_folder,
                file_names,
                found_languages,
                found_countries,
                skip_mode
            )
            found_languages.add(language_code)
            found_countries.add(country_code)
            lang_name = next(
                (
                    language.name_text
                    for language in ObjectsLanguage
                    if language.value == code.upper()
                ),
                "Unknown",
            )
            if generate_enum:
                enum_key = code.replace("-", "_").upper()
                enum_lines.append(
                    f"    {enum_key} = LanguageItem('{code}', '{lang_name}', "
                    f"'{country_code}')"
                )
        except Exception as e:
            logging.error(f"Error downloading flag for {code}: {e}")

    if generate_enum:
        # Create an isolated logger to output the generated code without
        # timestamps
        codegen_logger = logging.getLogger("codegen")
        codegen_logger.propagate = False

        if codegen_logger.hasHandlers():
            codegen_logger.handlers.clear()

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        codegen_logger.addHandler(console_handler)
        codegen_logger.setLevel(logging.INFO)

        # Output the generated Enum code through the logger
        codegen_logger.info(
            "\n" + "=" * 20 + " GENERATED ENUM CODE FOR PYTHON 3.9+ "
            + "=" * 20
        )
        codegen_logger.info("from enum import Enum\n")
        codegen_logger.info("class LanguageItem:")
        codegen_logger.info(
            "    def __init__(self, code: str, name: str, country: str):")
        codegen_logger.info("        self.code = code")
        codegen_logger.info("        self.name = name")
        codegen_logger.info("        self.country = country\n")
        codegen_logger.info("    def __str__(self):")
        codegen_logger.info("        return self.code\n\n")
        codegen_logger.info("class ObjectsLanguage(str, Enum):")
        codegen_logger.info('    """')
        codegen_logger.info(
            '    Smart Enum for OSM Languages (Python 3.9+ compatible).')
        codegen_logger.info('    """')

        codegen_logger.info("\n".join(enum_lines))

        codegen_logger.info("\n    def __new__(cls, item: LanguageItem):")
        codegen_logger.info("        obj = super().__new__(cls, item.code)")
        codegen_logger.info("        obj._value_ = item.code")
        codegen_logger.info("        obj.name_text = item.name")
        codegen_logger.info("        obj.country = item.country")
        codegen_logger.info("        return obj")
        codegen_logger.info("=" * 80 + "\n")


if __name__ == "__main__":
    # Setting up logging for console output
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s][%(levelname)s][%(thread)d]:\t %(message)s'
    )

    languages = [language.value.code for language in ObjectsLanguage]
    download_flags(languages, output_folder=Paths.flags_folder,
                   file_names=FileNames.COUNTRY, skip_mode=SkipModes.SKIP)
