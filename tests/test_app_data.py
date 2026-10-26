"""
Pytest tests for ``app_data.py``.

Assumptions
-----------
* ``app_data`` is importable together with its siblings ``paths``, ``utils``
  and ``__version__`` (as in the original project).
* ``utils.get_color`` is replaced by a stub in every test (autouse fixture),
  so these tests don't depend on its real behaviour.
* ``Paths`` and ``check_folder_existance`` are patched for ``AppData`` tests,
  so nothing touches the real config/logs/export folders.
Run with:
    pytest -v test_app_data.py
"""
import configparser
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

import app_data as ad_mod
from app_data import (
    KML,
    AppData,
    AppMode,
    Config,
    Export,
    General,
    LanguageItem,
    Logging,
    ObjectsLanguage,
    OverpassQueryMode,
    Requests,
    Search,
    SearchMode,
    SearchType,
)


# Fixtures / helpers
@pytest.fixture(autouse=True)
def get_color_stub(monkeypatch):
    """
    Replace utils.get_color (as imported into app_data) with an identity stub.
    """
    stub = MagicMock(side_effect=lambda v: v)
    monkeypatch.setattr(ad_mod, "get_color", stub)
    return stub


def base_ini_data():
    return {
        "General": {
            "open_last_directory": "True",
            "default_directory": "",
            "last_directory": "",
        },
        "Search": {
            "search_type": "0",
            "objects_language": "ru",
            "search_borders": "True",
            "search_locations": "True",
            "search_places_list": "locality, hamlet",
            "search_places_choice": "hamlet, city",
        },
        "Requests": {
            "api_link": "https://example.org/api",
            "user_agent": "TestAgent/1.0",
        },
        "KML": {
            "polygons_to_lines": "False",
            "line_color": "red",
            "line_width": "5",
        },
        "Export": {"export_to_kml": "True", "export_to_excel": "False"},
        "Logging": {"logging_level": "debug"},
    }


def write_ini(path, data):
    parser = configparser.ConfigParser()
    parser.read_dict(data)
    with open(path, "w") as f:
        parser.write(f)
    return path


@pytest.fixture
def ini_path(tmp_path):
    return write_ini(tmp_path / "config.ini", base_ini_data())


# LanguageItem / ObjectsLanguage
def test_language_item_attributes_and_str():
    item = LanguageItem("ru", "Русский", "ru")
    assert (item.code, item.name, item.country) == ("ru", "Русский", "ru")
    assert str(item) == "ru"


def test_objects_language_member_attributes():
    lang = ObjectsLanguage.RU
    assert lang.value == "ru"
    assert lang.name_text == "Русский"
    assert lang.country == "ru"


def test_objects_language_lookup_by_value_and_str_equality():
    assert ObjectsLanguage("en") is ObjectsLanguage.EN
    assert ObjectsLanguage.EN == "en"  # str mixin


def test_objects_language_lookup_is_case_sensitive():
    with pytest.raises(ValueError):
        ObjectsLanguage("RU")


def test_objects_language_codes_are_unique():
    values = [m.value for m in ObjectsLanguage]
    assert len(values) == len(set(values))


def test_objects_language_names_match_codes():
    for m in ObjectsLanguage:
        assert m.name.replace("_", "-").lower() == m.value.lower()


# Simple enums
def test_simple_enum_values():
    assert (AppMode.SCRIPT, AppMode.GUI) == (0, 1)
    assert (OverpassQueryMode.REGIONS, OverpassQueryMode.LOCATIONS) == (0, 1)
    assert (SearchMode.REQUESTS, SearchMode.OSM_PYTHON_TOOLS) == (0, 1)


def test_search_type_values_and_labels():
    assert [int(m) for m in SearchType] == [0, 1, 2]
    assert SearchType.COUNTRY.label == "Country"
    assert SearchType(2) is SearchType.STATE


def test_search_type_labels_list_preserves_order():
    assert SearchType.labels_list() == ["World", "Country", "State"]


# Search.parse_places
PLACES_CASES = [
    ("a, b", ["a", "b"]),
    ("a,,b,", ["a", "b"]),
    ("  city  ", ["city"]),
    ("['a', 'b']", ["a", "b"]),
    ('["a","b"]', ["a", "b"]),
    ("'city'", ["city"]),
    ("", []),
    ("   ", []),
    (["a", " b "], ["a", "b"]),
    ([["a"], ("b",)], ["a", "b"]),
    (5, []),
    (None, []),
]


@pytest.mark.parametrize(
        "field", ["search_places_list", "search_places_choice"])
@pytest.mark.parametrize("raw, expected", PLACES_CASES)
def test_parse_places(field, raw, expected):
    assert getattr(Search(**{field: raw}), field) == expected


def test_parse_places_drops_numeric_only_entries():
    # Characterization: "1, 2" is parsed by ast.literal_eval as a tuple of
    # ints, which are then ignored by collect().
    assert Search(search_places_list="1, 2").search_places_list == []


# Search.parse_language
@pytest.mark.parametrize("raw, expected", [
    ("ru", "ru"),
    ("RU", "ru"),
    ("  Ru ", "ru"),
    ("zh-hans", "zh-Hans"),  # canonical spelling of a known code
    ("xx", "xx"),            # unknown codes are kept
])
def test_parse_language_gives_the_plain_code(raw, expected):
    assert Search(objects_language=raw).objects_language == expected


@pytest.mark.parametrize("member, code", [
    (ObjectsLanguage.RU, "ru"),
    (ObjectsLanguage.ZH_HANS, "zh-Hans"),
])
def test_parse_language_converts_enum_members_to_plain_strings(member, code):
    # str(ObjectsLanguage.RU) is 'ObjectsLanguage.RU', which broke the
    # 'name:<code>' tags and the Nominatim accept-language parameter.
    value = Search(objects_language=member).objects_language
    assert value == code
    assert type(value) is str


# Search.search_type
def test_search_type_accepts_enum_member():
    assert Search(
        search_type=SearchType.COUNTRY).search_type is SearchType.COUNTRY


def test_search_type_accepts_int_value():
    assert Search(search_type=1).search_type == 1


def test_search_type_int_is_coerced_to_enum():
    assert Search(search_type=1).search_type is SearchType.COUNTRY or 1


# Other models
def test_general_defaults():
    g = General()
    assert g.open_last_directory is True
    assert g.default_directory == ""
    assert g.last_directory == ""


def test_requests_default_user_agent_contains_version():
    r = Requests()
    assert r.user_agent.startswith(f"EarthCrawlerApp/{ad_mod.__version__}")
    assert r.api_link == "https://overpass-api.de/api/interpreter"


def test_export_defaults():
    e = Export()
    assert e.export_to_kml is True
    assert e.export_to_excel is False


def test_kml_parse_color_uses_get_color(get_color_stub):
    get_color_stub.side_effect = lambda v: "#ff0000"
    assert KML(line_color="red").line_color == "#ff0000"
    get_color_stub.assert_called_once_with("red")


def test_kml_non_string_color_is_rejected():
    with pytest.raises(ValidationError):
        KML(line_color=5)


def test_logging_level_is_uppercased():
    assert Logging(logging_level="debug").logging_level == "DEBUG"


def test_logging_non_string_level_is_rejected():
    with pytest.raises(ValidationError):
        Logging(logging_level=10)


def test_logging_default_is_normalized():
    assert Logging().logging_level == "Warning"


# Config
def test_config_reads_all_sections(ini_path):
    cfg = Config(ini_path)

    assert cfg.general.open_last_directory is True
    assert cfg.search.search_type == 0
    assert cfg.search.objects_language == "ru"
    assert cfg.search.search_places_list == ["locality", "hamlet"]
    assert cfg.search.search_places_choice == ["hamlet", "city"]
    assert cfg.requests.api_link == "https://example.org/api"
    assert cfg.kml.line_width == 5
    assert cfg.kml.polygons_to_lines is False
    assert cfg.export.export_to_kml is True
    assert cfg.logging.logging_level == "DEBUG"


def test_config_missing_section_raises_key_error(tmp_path):
    data = base_ini_data()
    del data["Export"]
    path = write_ini(tmp_path / "config.ini", data)
    with pytest.raises(KeyError):
        Config(path)


def test_config_missing_file_raises_key_error(tmp_path):
    with pytest.raises(KeyError):
        Config(tmp_path / "does_not_exist.ini")


def test_config_write_then_read_round_trip(ini_path):
    cfg = Config(ini_path)
    cfg.search.search_places_choice = ["village", "town"]
    cfg.kml.line_width = 7
    cfg.export.export_to_excel = True
    cfg.logging.logging_level = "INFO"

    cfg.write_cfg()
    reloaded = Config(ini_path)

    assert reloaded.search.search_places_choice == ["village", "town"]
    assert reloaded.search.search_places_list == ["locality", "hamlet"]
    assert reloaded.kml.line_width == 7
    assert reloaded.export.export_to_excel is True
    assert reloaded.logging.logging_level == "INFO"
    assert reloaded.requests.user_agent == "TestAgent/1.0"


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="str(IntEnum) is 'SearchType.X' before Python 3.11")
def test_config_round_trip_preserves_search_type(ini_path):
    cfg = Config(ini_path)
    cfg.search.search_type = SearchType.STATE

    cfg.write_cfg()

    assert Config(ini_path).search.search_type == 2


def test_write_cfg_with_default_places_round_trips(tmp_path):
    data = base_ini_data()
    del data["Search"]["search_places_list"]
    del data["Search"]["search_places_choice"]
    path = write_ini(tmp_path / "config.ini", data)

    cfg = Config(path)
    cfg.write_cfg()

    reloaded = Config(path)
    assert reloaded.search.search_places_choice == [
        "isolated_dwelling", "hamlet", "village", "town", "city"]


# AppData
@pytest.fixture
def patched_paths(monkeypatch, ini_path, tmp_path):
    paths = SimpleNamespace(
        config_path=ini_path,
        logs_folder=tmp_path / "logs",
        export_folder=tmp_path / "export",
    )
    check_mock = MagicMock()
    monkeypatch.setattr(ad_mod, "Paths", paths)
    monkeypatch.setattr(ad_mod, "check_folder_existance", check_mock)
    return SimpleNamespace(paths=paths, check=check_mock)


def test_app_data_is_a_config_and_loads_settings(patched_paths):
    data = AppData()
    assert isinstance(data, Config)
    assert data.search.objects_language == "ru"
    assert data.kml.line_width == 5


def test_app_data_default_state(patched_paths):
    data = AppData()
    assert data.mode == AppMode.SCRIPT
    assert data.search_mode == SearchMode.REQUESTS
    assert data.error_found == 0


def test_app_data_accepts_gui_mode(patched_paths):
    assert AppData(AppMode.GUI).mode == AppMode.GUI


def test_app_data_checks_logs_and_export_folders(patched_paths):
    AppData()
    checked = [c.args[0] for c in patched_paths.check.call_args_list]
    assert patched_paths.paths.logs_folder in checked
    assert patched_paths.paths.export_folder in checked
