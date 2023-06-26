import pytest
import os
import sys
# Path hack to make tests work.
sys.path.insert(1, os.path.join(sys.path[0], '..'))

from tempdata import TempData   # noqa: E402


@pytest.fixture
def Tmp() -> TempData:
    Tmp = TempData()
    return Tmp


def test_get_settings(Tmp: TempData) -> None:
    # Tmp.get_settings() not needed, because of it's call in TempData __init__
    assert Tmp.search_type in ["world", "country", "state"]
    assert Tmp.objects_language in list(Tmp.obj_lang_dict.keys())
    assert isinstance(Tmp.search_borders, (bool))
    assert isinstance(Tmp.search_locations, (bool))
    assert isinstance(Tmp.search_places_list, (list)) and \
        Tmp.search_places_list != []
    assert set(Tmp.search_places_choice).issubset(set(Tmp.search_places_list))
    assert isinstance(Tmp.polygons_to_lines, (bool))
    # assert Tmp.line_color # get_color
    assert Tmp.line_width in range(0, 30)
    assert isinstance(Tmp.export_to_kml, (bool))
    assert isinstance(Tmp.export_to_excel, (bool))
    assert Tmp.logging_level in ["NOTSET", "DEBUG", "INFO", "WARNING",
                                 "ERROR", "CRITICAL"]


def test_get_color(Tmp: TempData) -> None:
    assert Tmp.get_color("blue") == "#0000ff"   # Text value
    assert Tmp.get_color("09c") == "#0099cc"    # Short Hex value
    assert Tmp.get_color("") == "#ff0000"       # Empty value -> default: red
