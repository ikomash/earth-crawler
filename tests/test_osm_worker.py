import logging
from unittest.mock import MagicMock, create_autospec

import pytest
import simplekml
from shapely.geometry import MultiPolygon, Polygon

import osm_worker as ow
from osm_worker import (
    EarthCrawler,
    OsmWorker,
    OverpassQueryMode,
    SearchMode,
    get_nominatim_id_from_json,
)
from utils import ValueSpecEntry

# Value the code under test produces for app_data.kml.line_color == "#ff0000"
LINE_COLOR = simplekml.Color.hex("ff0000")
SQUARE = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]


def kml_xml(kml):
    """Serialized KML of a whole document."""
    return kml.kml()


# Fixtures
@pytest.fixture
def app_data():
    """A MagicMock standing in for a fully configured AppData instance."""
    ad = MagicMock()
    ad.kml.line_color = "#ff0000"
    ad.kml.line_width = 3
    ad.kml.polygons_to_lines = False
    ad.search.objects_language = "en"
    ad.search.search_borders = True
    ad.search.search_locations = True
    ad.search.search_places_choice = ["city", "town"]
    ad.export.export_to_excel = False
    ad.export.export_to_kml = False
    ad.requests.requests_type = SearchMode.OSM_PYTHON_TOOLS
    ad.error_found = 0
    return ad


@pytest.fixture
def crawler(monkeypatch, app_data):
    """An EarthCrawler with the Nominatim/Overpass clients mocked out."""
    monkeypatch.setattr(ow, "Nominatim", MagicMock())
    monkeypatch.setattr(ow, "Overpass", MagicMock())
    c = EarthCrawler(
        app_data,
        on_progress=MagicMock(),
        on_total_progress=MagicMock(),
        on_export=MagicMock(),
        on_point=MagicMock(),
        on_polygon=MagicMock(),
        on_finish=MagicMock(),
    )
    # Overwrite with fresh, easily-configurable mocks for use in tests.
    c.nominatim = MagicMock()
    c.overpass = MagicMock()
    return c


# get_nominatim_id_from_json
def test_get_nominatim_id_from_json_default_index():
    data = [{"osm_type": "relation", "osm_id": 12345}]
    assert get_nominatim_id_from_json(data) == "r12345"


def test_get_nominatim_id_from_json_custom_index():
    data = [
        {"osm_type": "relation", "osm_id": 1},
        {"osm_type": "way", "osm_id": 2},
    ]
    assert get_nominatim_id_from_json(data, index=1) == "w2"


# EarthCrawler.__init__
def test_init_uses_provided_callbacks(crawler, app_data):
    assert crawler.app_data is app_data
    crawler._on_progress(1, "x")
    crawler._on_progress.assert_called_once_with(1, "x")


def test_init_defaults_callbacks_to_noop(monkeypatch, app_data):
    monkeypatch.setattr(ow, "Nominatim", MagicMock())
    monkeypatch.setattr(ow, "Overpass", MagicMock())
    c = EarthCrawler(app_data)
    # Should not raise even though no callbacks were supplied.
    c._on_progress(1, "x")
    c._on_total_progress(5)
    c._on_export([0, "KML"])
    c._on_point(1.0, 2.0, "name")
    c._on_polygon([(1, 2)], "name")
    c._on_finish()


# get_osm_element_name
def test_get_osm_element_name_prefers_localized_name():
    element = MagicMock()
    element.tag.side_effect = lambda key: {"name:ru": "Москва"}.get(key)
    assert EarthCrawler.get_osm_element_name(element, "ru") == "Москва"


def test_get_osm_element_name_falls_back_to_default_name():
    element = MagicMock()
    element.tag.side_effect = lambda key: {"name": "Moscow"}.get(key)
    assert EarthCrawler.get_osm_element_name(element, "ru") == "Moscow"


def test_get_osm_element_name_falls_back_to_unnamed():
    element = MagicMock()
    element.tag.return_value = None
    assert EarthCrawler.get_osm_element_name(
        element, "ru") == "Unnamed object"


# configure_kml_obj
def test_configure_kml_obj_applies_style(crawler, app_data):
    kml = simplekml.Kml()
    kml_obj = kml.newlinestring(name="Line", coords=[(0, 0), (1, 1)])

    result = crawler.configure_kml_obj(kml_obj)

    assert result is kml_obj
    xml = kml_xml(kml)
    assert f"<color>{LINE_COLOR}</color>" in xml
    assert "<width>3</width>" in xml


# add_kml_object
def test_add_kml_object_polygon_only(crawler, app_data):
    app_data.kml.polygons_to_lines = False
    kml = simplekml.Kml()

    crawler.add_kml_object(kml, SQUARE, "Obj", ["Polygon"])

    xml = kml_xml(kml)
    assert xml.count("<Polygon") == 1
    assert xml.count("<LineString") == 0
    assert "<name>Obj</name>" in xml
    assert "<fill>0</fill>" in xml  # polygons are drawn unfilled
    assert f"<color>{LINE_COLOR}</color>" in xml
    assert "<width>3</width>" in xml


def test_add_kml_object_line_only(crawler, app_data):
    app_data.kml.polygons_to_lines = False
    kml = simplekml.Kml()

    crawler.add_kml_object(kml, SQUARE, "Obj", ["Line"])

    xml = kml_xml(kml)
    assert xml.count("<Polygon") == 0
    assert xml.count("<LineString") == 1
    assert "<name>Obj</name>" in xml
    assert f"<color>{LINE_COLOR}</color>" in xml


def test_add_kml_object_polygons_forced_to_lines(crawler, app_data):
    app_data.kml.polygons_to_lines = True
    kml = simplekml.Kml()

    crawler.add_kml_object(kml, SQUARE, "Obj", ["Polygon"])

    xml = kml_xml(kml)
    # polygons_to_lines=True disables the polygon branch...
    assert xml.count("<Polygon") == 0
    # ...and forces the line branch regardless of obj_types.
    assert xml.count("<LineString") == 1


# choose_name_from_tag
def test_choose_name_from_tag_prefers_localized(crawler, app_data):
    app_data.search.objects_language = "ru"
    tags = {"name:ru": "Рига", "name": "Riga"}
    assert crawler.choose_name_from_tag(tags) == "Рига"


def test_choose_name_from_tag_falls_back_to_default(crawler, app_data):
    app_data.search.objects_language = "ru"
    tags = {"name": "Riga"}
    assert crawler.choose_name_from_tag(tags) == "Riga"


def test_choose_name_from_tag_falls_back_to_unnamed(crawler, app_data):
    app_data.search.objects_language = "ru"
    assert crawler.choose_name_from_tag({}) == "Unnamed object"


# process_loaded_wkt
def test_process_loaded_wkt_single_polygon(crawler):
    kml = simplekml.Kml()
    # Asymmetric coordinates so lon/lat swapping is actually verifiable.
    poly = Polygon([(0, 10), (5, 10), (5, 20), (0, 20)])

    crawler.process_loaded_wkt(kml, poly, "Region")

    xml = kml_xml(kml)
    assert xml.count("<Polygon") == 1
    assert "<name>Region</name>" in xml

    crawler._on_polygon.assert_called_once()
    coords_arg, name_arg = crawler._on_polygon.call_args[0]
    assert name_arg == "Region"
    # on_polygon receives (lat, lon) pairs, swapped from (lon, lat).
    assert coords_arg[0] == (10, 0)


def test_process_loaded_wkt_multi_polygon(crawler):
    kml = simplekml.Kml()
    p1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    p2 = Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])
    multi = MultiPolygon([p1, p2])

    crawler.process_loaded_wkt(kml, multi, "Region")

    xml = kml_xml(kml)
    # One folder holding two separately named polygons.
    assert xml.count("<Folder") == 1
    assert "<name>Region</name>" in xml
    assert xml.count("<Polygon") == 2
    assert "<name>Region_1</name>" in xml
    assert "<name>Region_2</name>" in xml

    assert crawler._on_polygon.call_count == 2
    sub_names = [c.args[1] for c in crawler._on_polygon.call_args_list]
    assert sub_names == ["Region_1", "Region_2"]


def test_process_loaded_wkt_unknown_type_logs_error(crawler, caplog):
    kml = simplekml.Kml()
    with caplog.at_level(logging.ERROR):
        crawler.process_loaded_wkt(kml, object(), "Region")
    assert "Unknown geometry type" in caplog.text
    xml = kml_xml(kml)
    assert "<Polygon" not in xml
    assert "<Folder" not in xml
    crawler._on_polygon.assert_not_called()


# _is_kml_empty
# NOTE: the method logs ``self.kml_doc`` (not its argument), so the crawler's
# kml_doc attribute has to be set even though a document is passed in.
def test_is_kml_empty_true_for_fresh_document(crawler):
    crawler.kml_doc = simplekml.Kml()
    assert crawler._is_kml_empty(crawler.kml_doc) is True


def test_is_kml_empty_false_after_adding_geometry(crawler):
    crawler.kml_doc = simplekml.Kml()
    crawler.kml_doc.newlinestring(name="x", coords=[(0, 0), (1, 1)])
    assert crawler._is_kml_empty(crawler.kml_doc) is False


# save_kml / save_excel
def test_save_kml_skips_empty_document(monkeypatch, crawler, caplog):
    crawler.kml_doc = simplekml.Kml()
    save_spy = MagicMock()
    monkeypatch.setattr(crawler.kml_doc, "save", save_spy)

    with caplog.at_level(logging.WARNING):
        crawler.save_kml("Area")

    save_spy.assert_not_called()
    assert "empty" in caplog.text.lower()


def test_save_kml_saves_polygons_suffix(monkeypatch, crawler, app_data):
    app_data.kml.polygons_to_lines = False
    crawler.kml_doc = simplekml.Kml()
    crawler.add_kml_object(crawler.kml_doc, SQUARE, "Obj", ["Polygon"])
    save_spy = MagicMock()
    monkeypatch.setattr(crawler.kml_doc, "save", save_spy)

    crawler.save_kml("Area")

    (path,), _ = save_spy.call_args
    assert "(polygons)" in path
    assert "Area" in path


def test_save_kml_saves_lines_suffix(monkeypatch, crawler, app_data):
    app_data.kml.polygons_to_lines = True
    crawler.kml_doc = simplekml.Kml()
    crawler.add_kml_object(crawler.kml_doc, SQUARE, "Obj", ["Polygon"])
    save_spy = MagicMock()
    monkeypatch.setattr(crawler.kml_doc, "save", save_spy)

    crawler.save_kml("Area")

    (path,), _ = save_spy.call_args
    assert "(lines)" in path


# prepare_overpass_query
def test_prepare_overpass_query_regions(monkeypatch, crawler, app_data):
    fake_area = MagicMock()
    fake_area.areaId.return_value = 3600000001
    monkeypatch.setattr(
        ow.OSMElement, "fromId", MagicMock(return_value=fake_area))
    fake_levels = MagicMock()
    fake_levels.format.return_value = "4|6"
    monkeypatch.setattr(
        ow.ValueSpec, "apply_extra_value", MagicMock(return_value=fake_levels))

    object_request = MagicMock()
    object_request.explicit = True
    search_data = {
        "nominatim_id": "r1",
        "object_request": object_request,
        "admin_level": 6,
    }

    query = crawler.prepare_overpass_query(
        search_data, OverpassQueryMode.REGIONS)

    assert "area(3600000001)->.country;" in query
    assert '"admin_level"~"^(4|6)$"' in query


def test_prepare_overpass_query_locations(monkeypatch, crawler, app_data):
    fake_area = MagicMock()
    fake_area.areaId.return_value = 3600000002
    monkeypatch.setattr(
        ow.OSMElement, "fromId", MagicMock(return_value=fake_area))
    app_data.search.search_places_choice = ["city", "town"]

    search_data = {"nominatim_id": "r2"}
    query = crawler.prepare_overpass_query(
        search_data, OverpassQueryMode.LOCATIONS)

    assert "area(3600000002)->.searchArea;" in query
    assert '"place"~"city|town"' in query


# overpass_request
def test_overpass_request_osmpythontools(crawler):
    crawler.overpass.query.return_value = "RESULT"
    result = crawler.overpass_request("QUERY", SearchMode.OSM_PYTHON_TOOLS)
    crawler.overpass.query.assert_called_once_with("QUERY", timeout=60)
    assert result == "RESULT"


# regions_search
def test_regions_search_processes_valid_geometry(monkeypatch, crawler):
    region_data = MagicMock()
    region_data.wkt.return_value = (
        "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")
    spy = MagicMock()
    monkeypatch.setattr(crawler, "process_loaded_wkt", spy)
    kml_doc = MagicMock()

    crawler.regions_search(region_data, kml_doc, "Region")

    spy.assert_called_once()
    args = spy.call_args[0]
    assert args[0] is kml_doc
    assert args[2] == "Region"
    assert hasattr(args[1], "geom_type")


def test_regions_search_warns_on_unsupported_geometry(
        monkeypatch, crawler, caplog):
    region_data = MagicMock()
    region_data.wkt.return_value = "irrelevant"
    monkeypatch.setattr(ow.wkt, "loads", MagicMock(return_value=object()))
    spy = MagicMock()
    monkeypatch.setattr(crawler, "process_loaded_wkt", spy)

    with caplog.at_level(logging.WARNING):
        crawler.regions_search(region_data, MagicMock(), "Region")

    spy.assert_not_called()
    assert "no supported geometry type" in caplog.text.lower()


def test_regions_search_multipolygon_end_to_end(crawler):
    """Real WKT -> real shapely -> real KML, no internal spies."""
    crawler.kml_doc = simplekml.Kml()
    region_data = MagicMock()
    region_data.wkt.return_value = (
        "MULTIPOLYGON(((0 0, 1 0, 1 1, 0 1, 0 0)),"
        "((2 2, 3 2, 3 3, 2 3, 2 2)))")

    crawler.regions_search(region_data, crawler.kml_doc, "Region")

    xml = kml_xml(crawler.kml_doc)
    assert xml.count("<Polygon") == 2
    assert "<name>Region_1</name>" in xml
    assert "<name>Region_2</name>" in xml
    assert crawler._on_polygon.call_count == 2
    assert crawler._is_kml_empty(crawler.kml_doc) is False


# locations_search
def _make_point(lat, lon, name):
    p = MagicMock()
    p.lat.return_value = lat
    p.lon.return_value = lon
    p.tags.return_value = {"name": name}
    p.tag.side_effect = lambda key: {"name": name}.get(key)
    return p


def test_locations_search_adds_points(crawler, app_data):
    points = MagicMock()
    points.nodes.return_value = [
        _make_point(56.95, 24.10, "Riga"),
        _make_point(56.50, 21.01, "Liepaja"),
    ]
    kml = simplekml.Kml()

    next_idx = crawler.locations_search(points, kml)

    assert next_idx == 2
    xml = kml_xml(kml)
    assert xml.count("<Point") == 2
    assert "<name>Riga</name>" in xml
    assert "<name>Liepaja</name>" in xml
    assert crawler._on_point.call_count == 2
    crawler._on_point.assert_any_call(56.95, 24.10, "Riga")


def test_locations_search_handles_unnamed_point(crawler, app_data):
    points = MagicMock()
    points.nodes.return_value = [_make_point(1.0, 2.0, "X")]
    # A KeyError can't be provoked with a real Kml, so use an autospec'd
    # one: it still rejects wrong method names and signatures.
    kml_doc = create_autospec(simplekml.Kml, instance=True)
    kml_doc.newpoint.side_effect = KeyError("location")

    next_idx = crawler.locations_search(points, kml_doc)

    assert next_idx == 1
    crawler._on_progress.assert_called_once_with(0, "Unnamed location")
    crawler._on_point.assert_not_called()


def test_locations_search_respects_progress_start(crawler, app_data):
    points = MagicMock()
    points.nodes.return_value = [_make_point(1.0, 2.0, "X")]
    next_idx = crawler.locations_search(
        points, simplekml.Kml(), progress_start=10)
    assert next_idx == 11


# details_search
def test_details_search_both_enabled(monkeypatch, crawler, app_data):
    app_data.search.search_borders = True
    app_data.search.search_locations = True
    region = MagicMock()
    region.tag.side_effect = lambda key: {"name": "Region"}.get(key)

    regions_req_spy = MagicMock(return_value="REGION_DATA")
    regions_search_spy = MagicMock()
    locations_req_spy = MagicMock(return_value="POINTS")
    locations_search_spy = MagicMock()
    monkeypatch.setattr(crawler, "regions_overpass_request", regions_req_spy)
    monkeypatch.setattr(crawler, "regions_search", regions_search_spy)
    monkeypatch.setattr(
        crawler, "locations_overpass_request", locations_req_spy)
    monkeypatch.setattr(crawler, "locations_search", locations_search_spy)

    crawler.details_search(region, MagicMock())

    regions_req_spy.assert_called_once_with(region)
    regions_search_spy.assert_called_once()
    locations_req_spy.assert_called_once_with(region)
    locations_search_spy.assert_called_once()


def test_details_search_only_locations(monkeypatch, crawler, app_data):
    app_data.search.search_borders = False
    app_data.search.search_locations = True
    region = MagicMock()
    region.tag.side_effect = lambda key: {"name": "Region"}.get(key)

    regions_req_spy = MagicMock()
    locations_req_spy = MagicMock(return_value="POINTS")
    locations_search_spy = MagicMock()
    monkeypatch.setattr(crawler, "regions_overpass_request", regions_req_spy)
    monkeypatch.setattr(
        crawler, "locations_overpass_request", locations_req_spy)
    monkeypatch.setattr(crawler, "locations_search", locations_search_spy)

    crawler.details_search(region, MagicMock())

    regions_req_spy.assert_not_called()
    locations_req_spy.assert_called_once()


# first_nominatim_search
def test_first_nominatim_search_world(crawler, app_data):
    single_obj_req = MagicMock()
    single_obj_req.name = "Moscow"
    osm_data = MagicMock()
    osm_data.address.return_value = {}
    osm_data.toJSON.return_value = [
        {
            "osm_type": "relation",
            "osm_id": 1,
            "licence": "ODbL",
            "extratags": {"admin_level": "4", "other": "x"},
        }
    ]
    crawler.nominatim.query.return_value = osm_data

    result = crawler.first_nominatim_search(single_obj_req, "world")

    _, kwargs = crawler.nominatim.query.call_args
    assert "featureType" not in kwargs.get("params", {})
    assert result[0]["nominatim_id"] == "r1"
    assert result[0]["object_request"] is single_obj_req
    assert "licence" not in result[0]
    assert result[0]["admin_level"] == 4
    assert "admin_level" not in result[0]["extratags"]
    assert result[0]["extratags"]["other"] == "x"


def test_first_nominatim_search_with_feature_type(crawler, app_data):
    single_obj_req = MagicMock()
    single_obj_req.name = "Riga"
    osm_data = MagicMock()
    osm_data.address.return_value = {}
    osm_data.toJSON.return_value = [
        {"osm_type": "node", "osm_id": 2, "extratags": {}}
    ]
    crawler.nominatim.query.return_value = osm_data

    crawler.first_nominatim_search(single_obj_req, "city")

    _, kwargs = crawler.nominatim.query.call_args
    assert kwargs["params"]["featureType"] == "city"


def test_first_nominatim_search_missing_admin_level_defaults_to_zero(
        crawler, app_data):
    single_obj_req = MagicMock()
    single_obj_req.name = "Riga"
    osm_data = MagicMock()
    osm_data.address.return_value = {}
    osm_data.toJSON.return_value = [
        {"osm_type": "node", "osm_id": 3, "extratags": {}}
    ]
    crawler.nominatim.query.return_value = osm_data

    result = crawler.first_nominatim_search(single_obj_req, "world")

    assert result[0]["admin_level"] == 0


# overpass_raw_request
def test_overpass_raw_request_success(monkeypatch, crawler):
    fake_response = MagicMock()
    fake_response.json.return_value = {"elements": []}
    post_spy = MagicMock(return_value=fake_response)
    monkeypatch.setattr(ow.requests, "post", post_spy)

    result = crawler.overpass_raw_request(
        "MY QUERY", "https://api.example/interpreter")

    assert result == {"elements": []}
    fake_response.raise_for_status.assert_called_once()
    _, kwargs = post_spy.call_args
    assert kwargs["data"] == {"data": "[out:json];MY QUERY"}
    assert kwargs["timeout"] == 600


# overpass_short_search
def short_search_data():
    """Search data as first_nominatim_search produces it.

    object_request is a ValueSpecEntry: overpass_short_search reads its
    ``explicit`` flag and ``levels``. Two levels, so a retry has somewhere to
    go.
    """
    entry = ValueSpecEntry("Area", [6, 8], explicit=True)
    return {"object_request": entry, "nominatim_id": "r1",
            "admin_level": 8}


def test_overpass_short_search_succeeds_first_try(monkeypatch, crawler):
    search_data = short_search_data()
    prepare_spy = MagicMock(return_value="Q")
    request_spy = MagicMock(return_value="RESULT")
    monkeypatch.setattr(crawler, "prepare_overpass_query", prepare_spy)
    monkeypatch.setattr(crawler, "overpass_request", request_spy)

    result = crawler.overpass_short_search(search_data)

    assert result == "RESULT"
    prepare_spy.assert_called_once_with(
        search_data, OverpassQueryMode.REGIONS)
    request_spy.assert_called_once_with("Q", SearchMode.OSM_PYTHON_TOOLS)


def test_overpass_short_search_retries_on_type_error(monkeypatch, crawler):
    search_data = short_search_data()
    monkeypatch.setattr(crawler, "prepare_overpass_query",
                        MagicMock(return_value="Q"))
    monkeypatch.setattr(
        crawler, "overpass_request",
        MagicMock(side_effect=[TypeError, "RESULT2"]))

    result = crawler.overpass_short_search(search_data)

    assert result == "RESULT2"


def test_overpass_short_search_returns_none_if_all_levels_fail(
        monkeypatch, crawler):
    search_data = short_search_data()
    monkeypatch.setattr(crawler, "prepare_overpass_query",
                        MagicMock(return_value="Q"))
    monkeypatch.setattr(
        crawler, "overpass_request", MagicMock(side_effect=TypeError))

    result = crawler.overpass_short_search(search_data)

    assert result is None


def test_overpass_full_search_borders_type_error_is_handled(
        monkeypatch, crawler, app_data, caplog):
    app_data.search.search_borders = True
    app_data.search.search_locations = False
    crawler.kml_doc = MagicMock()
    monkeypatch.setattr(crawler, "prepare_overpass_query",
                        MagicMock(return_value="Q"))
    monkeypatch.setattr(
        crawler, "overpass_request", MagicMock(side_effect=TypeError))

    object_request = MagicMock()
    object_request.name = "Area"
    search_data = {
        "nominatim_id": "r1", "object_request": object_request,
        "admin_level": 6,
    }

    crawler.overpass_full_search(search_data)

    # The request was made and its TypeError ("no data") was handled.
    crawler.overpass_request.assert_called_once()
    assert "No administrative objects found" in caplog.text
    crawler._on_total_progress.assert_called_once_with(0)
    crawler._on_finish.assert_called_once()


# second_nominatim_search
def test_second_nominatim_search_iterates_regions(
        monkeypatch, crawler, app_data):
    app_data.search.search_borders = True
    app_data.search.search_locations = True
    app_data.export.export_to_excel = False
    crawler.kml_doc = simplekml.Kml()
    region1, region2 = MagicMock(), MagicMock()
    region1.tags.return_value = {"name": "R1"}
    region2.tags.return_value = {"name": "R2"}
    overpass_regions = MagicMock()
    overpass_regions.relations.return_value = [region1, region2]
    details_spy = MagicMock()
    monkeypatch.setattr(crawler, "details_search", details_spy)

    crawler.second_nominatim_search(overpass_regions)

    assert details_spy.call_count == 2
    assert app_data.error_found == 0
    # With borders AND locations enabled, each region gets its own folder.
    xml = kml_xml(crawler.kml_doc)
    assert xml.count("<Folder") == 2
    assert "<name>R1</name>" in xml
    assert "<name>R2</name>" in xml


def test_second_nominatim_search_handles_type_error(crawler, app_data):
    overpass_regions = MagicMock()
    overpass_regions.relations.side_effect = TypeError
    crawler.second_nominatim_search(overpass_regions)
    assert app_data.error_found == 1


# script_sequence
def test_script_sequence_logs_uncaught_exceptions(monkeypatch):
    fake_app_data = MagicMock()
    fake_logger = MagicMock()
    monkeypatch.setattr(ow, "AppData", MagicMock(return_value=fake_app_data))
    monkeypatch.setattr(
        ow, "Logger", MagicMock(return_value=MagicMock(logger=fake_logger)))
    fake_crawler_cls = MagicMock()
    fake_crawler_instance = fake_crawler_cls.return_value
    fake_crawler_instance.request_and_process_data.side_effect = \
        RuntimeError("boom")
    monkeypatch.setattr(ow, "EarthCrawler", fake_crawler_cls)

    ow.script_sequence("Russia")

    fake_crawler_instance.request_and_process_data.assert_called_once_with(
        "Russia")
    fake_logger.exception.assert_called_once()


# OsmWorker (PyQt6) -- lighter coverage, flagged as potentially environment
# sensitive per the discussion above.
@pytest.fixture(scope="session")
def qapp():
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PyQt6 is required for OsmWorker tests")
    return QApplication.instance() or QApplication([])


@pytest.fixture
def worker(qapp, monkeypatch, app_data):
    fake_crawler = MagicMock()
    monkeypatch.setattr(ow, "EarthCrawler",
                        MagicMock(return_value=fake_crawler))
    w = OsmWorker(app_data)
    w.crawler = fake_crawler
    return w


def test_osm_worker_search_objects_emits_results(worker):
    received = []
    worker.update_results.connect(lambda data: received.append(data))
    worker.crawler.first_nominatim_search.return_value = [
        {"nominatim_id": "r1"}]

    worker.search_objects(MagicMock())

    worker.crawler.first_nominatim_search.assert_called_once()
    assert received == [[{"nominatim_id": "r1"}]]


def test_osm_worker_search_objects_logs_on_exception(worker, caplog):
    worker.crawler.first_nominatim_search.side_effect = RuntimeError("boom")
    with caplog.at_level(logging.ERROR):
        worker.search_objects(MagicMock())
    assert "First Nominatim search error" in caplog.text


def test_osm_worker_process_object_requests_mode(worker, app_data):
    app_data.search_mode = SearchMode.REQUESTS
    finished = []
    worker.object_processed.connect(lambda: finished.append(True))

    worker.process_object({"object_request": MagicMock()})

    worker.crawler.overpass_full_search.assert_called_once()
    assert finished == [True]


def test_osm_worker_process_object_short_search_mode(worker, app_data):
    app_data.search_mode = SearchMode.OSM_PYTHON_TOOLS
    app_data.export.export_to_excel = False
    app_data.export.export_to_kml = False
    worker.crawler.overpass_short_search.return_value = MagicMock(
        relations=MagicMock(return_value=[]))
    finished = []
    worker.object_processed.connect(lambda: finished.append(True))

    worker.process_object({"object_request": MagicMock()})

    worker.crawler.overpass_short_search.assert_called_once()
    worker.crawler.second_nominatim_search.assert_called_once()
    assert finished == [True]


def test_osm_worker_finish_processing_emits_reset(worker):
    emitted = []
    worker.return_to_initial_state_signal.connect(lambda: emitted.append(True))
    worker.finish_processing()
    assert emitted == [True]
