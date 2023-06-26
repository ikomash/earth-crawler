import pytest
import os
import sys
# Path hack to make tests work.
sys.path.insert(1, os.path.join(sys.path[0], '..'))

from tempdata import TempData   # noqa: E402
from earth_crawler import EarthCrawler  # noqa: E402


@pytest.fixture
def Tmp() -> TempData:
    Tmp = TempData()
    return Tmp


@pytest.fixture
def Crawler(Tmp) -> EarthCrawler:
    Crawler = EarthCrawler(Tmp)
    return Crawler


def test_admin_level_try_list_creator(Crawler: EarthCrawler) -> None:
    assert Crawler.admin_level_try_list_creator(
        6, [4, 5, 6, 7, 8, 9, 10, 3]) == [6, 4, 5, 7, 8, 9, 10, 3]


def test_search_line_proccessing(Crawler: EarthCrawler, Tmp: TempData) -> None:
    Tmp.search_line = "USA=5; China=6; Russia=4"
    test_list = Crawler.search_line_proccessing()
    assert test_list == [("USA", 5), ("China", 6), ("Russia", 4)]


def test_choose_name_from_tag(Crawler: EarthCrawler, Tmp: TempData) -> None:
    tags = {
        "name": "Int_name", "name:en": "En_name", "name:de": "De_name",
        "name:ru": "Ru_name"}
    Tmp.objects_language = "de"
    res = Crawler.choose_name_from_tag(tags)
    assert res == "De_name"
    Tmp.objects_language = ""
    res = Crawler.choose_name_from_tag(tags)
    assert res == "Int_name"
