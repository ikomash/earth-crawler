import ast
from configparser import ConfigParser
from enum import Enum, IntEnum
from pathlib import Path
from typing import Union
from pydantic import BaseModel, field_validator

from paths import Paths
from utils import check_folder_existance, get_color

from __version__ import __version__


class LanguageItem:
    """Simple wrapper for a localized language entry."""

    def __init__(self, code: str, name: str, country: str):
        """Initialize a language metadata record.

        Args:
            code (str): ISO language code.
            name (str): Display name in the local language.
            country (str): Country code used for flag lookup.
        """
        self.code = code
        self.name = name
        self.country = country

    def __str__(self):
        """Return the language code as the string representation."""
        return self.code


class ObjectsLanguage(str, Enum):
    """
    Smart Enum for OSM Languages (Python 3.9+ compatible).
    """
    AR = LanguageItem('ar', 'العربية', 'eg')
    AZ = LanguageItem('az', 'Azərbaycanca', 'az')
    BA = LanguageItem('ba', 'Башҡортса', 'ru')
    BE = LanguageItem('be', 'Беларуская', 'by')
    CA = LanguageItem('ca', 'Català', 'es')
    CE = LanguageItem('ce', 'Нохчийн', 'ru')
    CS = LanguageItem('cs', 'Čeština', 'cz')
    CV = LanguageItem('cv', 'Чӑвашла', 'ru')
    DE = LanguageItem('de', 'Deutsch', 'de')
    EL = LanguageItem('el', 'Ελληνικά', 'gr')
    EN = LanguageItem('en', 'English', 'us')
    ES = LanguageItem('es', 'Español', 'es')
    FI = LanguageItem('fi', 'Suomi', 'fi')
    FR = LanguageItem('fr', 'Français', 'fr')
    HE = LanguageItem('he', 'עברית', 'il')
    HR = LanguageItem('hr', 'Hrvatski', 'hr')
    HU = LanguageItem('hu', 'Magyar', 'hu')
    HY = LanguageItem('hy', 'Հայերեն', 'am')
    IT = LanguageItem('it', 'Italiano', 'it')
    KA = LanguageItem('ka', 'Ქართული', 'ge')
    KBD = LanguageItem('kbd', 'Адыгэбзэ', 'ru')
    KV = LanguageItem('kv', 'Коми', 'ru')
    LT = LanguageItem('lt', 'Lietuvių', 'lt')
    MN = LanguageItem('mn', 'Монгол', 'mn')
    NL = LanguageItem('nl', 'Nederlands', 'nl')
    NO = LanguageItem('no', 'Norsk', 'no')
    OS = LanguageItem('os', 'Ирон', 'ge')
    PL = LanguageItem('pl', 'Polski', 'pl')
    PT = LanguageItem('pt', 'Português', 'br')
    RU = LanguageItem('ru', 'Русский', 'ru')
    UK = LanguageItem('uk', 'Українська', 'ua')
    XAL = LanguageItem('xal', 'Хальмг', 'us')
    ZH = LanguageItem('zh', '中文', 'cn')
    ZH_HANS = LanguageItem('zh-Hans', '简体中文', 'cn')
    ZH_HANT = LanguageItem('zh-Hant', '繁體中文', 'tw')

    def __new__(cls, item: LanguageItem):
        """Create an enum member from its language metadata."""
        obj = super().__new__(cls, item.code)
        obj._value_ = item.code
        obj.name_text = item.name
        obj.country = item.country
        return obj


class AppMode (IntEnum):
    """Program running mode."""
    SCRIPT = 0
    GUI = 1


class OverpassQueryMode(IntEnum):
    """Overpass query mode."""
    REGIONS = 0
    LOCATIONS = 1


class SearchType(IntEnum):
    """Search scale type."""

    label: str

    def __new__(cls, value, label):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        return obj

    WORLD = (0, "World")
    COUNTRY = (1, "Country")
    STATE = (2, "State")

    @classmethod
    def labels_list(cls):
        """Return display labels in enum order."""
        return [item.label for item in cls]


class SearchMode(IntEnum):
    """Objects search mode type."""
    REQUESTS = 0
    OSM_PYTHON_TOOLS = 1


class General(BaseModel):
    """General application preferences and directory settings."""

    open_last_directory: bool = True
    default_directory: Union[str, Path] = ""
    last_directory: Union[str, Path] = ""


class Search(BaseModel):
    """Search scope, language, and place-type preferences."""

    search_type: Union[SearchType, int] = SearchType.WORLD
    objects_language: str = "ru"
    search_borders: bool = True
    search_locations: bool = True
    search_places_list: list[str] = [
        "locality", "isolated_dwelling", "hamlet", "village", "town", "city"]
    search_places_choice: list[str] = [
        "isolated_dwelling", "hamlet", "village", "town", "city"]

    @field_validator(
        "search_places_list", "search_places_choice", mode="before")
    @classmethod
    def parse_places(cls, v):
        """Normalize configured place types into a flat list.

        Args:
            v: A comma-separated string, a serialized list, or a sequence.

        Returns:
            list[str]: Non-empty place-type values.
        """
        def collect(value):
            if isinstance(value, (list, tuple)):
                return [place for item in value for place in collect(item)]

            if not isinstance(value, str):
                return []

            text = value.strip()

            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                parsed = None

            if isinstance(parsed, (list, tuple)):
                return collect(parsed)

            if isinstance(parsed, str) and parsed != text:
                return collect(parsed)

            return [x.strip() for x in text.split(",") if x.strip()]

        return collect(v)

    @field_validator("objects_language", mode="before")
    @classmethod
    def parse_language(cls, v):
        """Normalize a language to its plain code string, for example 'ru'.

        The code is what OSM tags ('name:ru') and the Nominatim
        'accept-language' parameter need. An ObjectsLanguage member is
        converted to its code, because ``str(ObjectsLanguage.RU)`` would give
        'ObjectsLanguage.RU'. A known code is matched ignoring case and
        returned in its canonical spelling ('zh-hans' -> 'zh-Hans'). Unknown
        codes are kept as they are, OSM knows many more languages.

        Args:
            v: Raw language value from config or user input.

        Returns:
            str: Language code, or the original value if it is not a string.
        """
        if isinstance(v, ObjectsLanguage):
            return v.value
        if isinstance(v, str):
            code = v.strip()
            for lang in ObjectsLanguage:
                if lang.value.lower() == code.lower():
                    return lang.value
            return code
        return v


class Requests(BaseModel):
    """Overpass API endpoint and request identity settings."""
    requests_type: int = SearchMode.REQUESTS.value
    api_link: str = "https://overpass-api.de/api/interpreter"
    user_agent: str = f"EarthCrawlerApp/{__version__} "\
        "(https://github.com/ikomash/earth-crawler)"


class KML(BaseModel):
    """KML geometry styling preferences."""
    polygons_to_lines: bool = False
    line_color: str = "red"
    line_width: int = 3

    @field_validator("line_color", mode="before")
    @classmethod
    def parse_color(cls, v):
        """Normalize the configured color to a valid HEX value.

        Args:
            v: Raw color value from the configuration.

        Returns:
            str: Normalized color string.
        """
        if isinstance(v, str):
            return get_color(v)
        return v


class Export(BaseModel):
    """Enabled export formats."""

    export_to_kml: bool = True
    export_to_excel: bool = False


class Logging(BaseModel):
    """Logging configuration."""

    logging_level: str = "Warning"

    @field_validator("logging_level", mode="before")
    @classmethod
    def parse_logging_level(cls, v):
        """Normalize string logging levels to uppercase.

        Args:
            v: Raw logging level from configuration.

        Returns:
            str: Uppercase logging level, or the original non-string value.
        """
        if isinstance(v, str):
            return v.upper()
        return v


class Config(ConfigParser):
    """ Configuration class. Reads and writes config.ini file. """

    def __init__(self, cfg_path: Path):
        """Initialize Config.

        Args:
            cfg_path (Path): Path to configuration file.
        """
        super(Config, self).__init__()
        self.cfg_path = cfg_path
        self.read_cfg()

    def read_cfg(self):
        """Load settings from the config file and initialize the models.

        This method reads the INI configuration, builds the nested data
        models, and prepares the state used by the application.
        """
        self.read(self.cfg_path)
        self.general = General(**self["General"])
        self.search = Search(**self["Search"])
        self.requests = Requests(**self["Requests"])
        self.kml = KML(**self["KML"])
        self.export = Export(**self["Export"])
        self.logging = Logging(**self["Logging"])

    def write_cfg(self):
        """Write data to the configuration file."""
        dump = {}
        dump["General"] = self.general.model_dump()
        dump["Search"] = self.search.model_dump()
        for key in ("search_places_list", "search_places_choice"):
            dump["Search"][key] = ", ".join(dump["Search"][key])
        dump["Requests"] = self.requests.model_dump()
        dump["KML"] = self.kml.model_dump()
        dump["Export"] = self.export.model_dump()
        dump["Logging"] = self.logging.model_dump()
        self.read_dict(dump)
        with open(self.cfg_path, 'w') as configfile:
            self.write(configfile)


class AppData(Config):
    """Operative data and settings storage.
    """

    def __init__(self, mode: AppMode = AppMode.SCRIPT):
        """
        Initializes temporary parameters and loads configurations
        from 'config.ini'.

        Args:
            mode (AppMode, optional):
                Running program mode. Defaults to AppMode.SCRIPT.
        """
        # Load configuration
        super().__init__(Paths.config_path)
        self.mode = mode
        self.search_mode = SearchMode.REQUESTS
        self.error_found = 0

        self.check_necessary_folders()

    def check_necessary_folders(self):
        """
        Checks whether important folders exist or not (creates if missing).
        """
        check_folder_existance(Paths.logs_folder)
        check_folder_existance(Paths.export_folder)
