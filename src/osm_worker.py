import logging
import random
import re
import threading
import time
from typing import Any, Callable, Optional, Union

from OSMPythonTools.nominatim import Nominatim
from OSMPythonTools.overpass import Overpass
import requests
import simplekml
from shapely import wkt
from shapely.geometry import shape
import pandas as pd

# imports for data types
from geojson.geometry import Polygon as JPolygon
from shapely.geometry.base import BaseGeometry
from OSMPythonTools.element import Element as OSMElement
from OSMPythonTools.overpass import OverpassResult

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from logger import DEFAULT_LOGGER_NAME, Logger
from app_data import AppData, OverpassQueryMode, SearchMode
from paths import Paths
from utils import ValueSpec, ValueSpecEntry

# The map outline of a polygon is thinned out to roughly this many vertices
# per side of its bounding box: a country border has hundreds of thousands
# of vertices, which the map widget cannot draw without freezing the window.
# The KML file keeps the full detail.
MAP_OUTLINE_DETAIL = 2000

# Columns of every locations sheet in the Excel export, in this exact order.
# Every column is filled in locations_search(); add a column there and here.
EXCEL_COLUMNS = ["location", "place", "lon", "lat"]
# Excel limits worksheet names to 31 characters and forbids []:*?/\ in them.
EXCEL_SHEET_NAME_MAX_LEN = 31
_EXCEL_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")

# HTTP answers worth a retry: rate limiting and temporary server trouble.
# Other 4xx (e.g. 400 for a broken query) will fail the same way every time.
TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
# Fragments of error messages that point to a temporary problem. Needed
# because OSMPythonTools re-raises HTTP/network errors as a plain Exception
# that carries only a message such as 'HTTP Error 504: Gateway Timeout'.
_TRANSIENT_ERROR_HINTS = (
    "timed out", "timeout", "connection reset", "connection aborted",
    "connection refused", "remote end closed", "temporarily unavailable",
    "too many requests", "bad gateway", "service unavailable",
    "gateway", "server is probably too busy", "try again",
)
# Texts of overload pages that servers or proxies send instead of JSON.
_BUSY_PAGE_HINTS = (
    "too busy", "rate_limited", "rate limit", "too many requests",
    "bad gateway", "service unavailable", "gateway time-out",
    "gateway timeout",
)
_HTTP_STATUS_IN_TEXT = re.compile(
    r"(?:http error|status(?: code)?)\D{0,3}(\d{3})")


class RetryableOverpassError(Exception):
    """A temporary Overpass failure that is worth another attempt.

    Attributes:
        retry_after (Optional[float]): Seconds the server asked us to wait
            (Retry-After header), if any.
    """

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class OverpassRuntimeError(Exception):
    """Overpass answered, but with an error or an unusable response.

    Typically a runtime error in its 'remark' (out of memory or time) or an
    answer that is not JSON. The same query would fail again, so this is
    deliberately NOT retried.
    """


class OperationCancelled(BaseException):
    """The user cancelled the running search.

    Derives from BaseException, like ``asyncio.CancelledError``, so that the
    many ``except Exception`` blocks in the search code cannot swallow it by
    accident. It is caught where a worker slot starts (``OsmWorker``).
    """


def is_transient_error(exc: BaseException) -> bool:
    """Decide whether a failed request is worth repeating.

    Retry: dropped connections, timeouts, HTTP 429/500/502/503/504 and
    messages that say the same. Do not retry: ``TypeError`` (in this app it
    means "the server answered but there is no data"), Overpass runtime
    errors, and anything unrecognised -- a wrong query or a bug would only
    fail again and hammer the public servers.

    Args:
        exc (BaseException): The error raised by a request attempt.

    Returns:
        bool: True if the request should be retried.
    """
    if isinstance(exc, (TypeError, OverpassRuntimeError)):
        return False
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (
                RetryableOverpassError, ConnectionError, TimeoutError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError)):
            return True
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if status is None:
            status = getattr(current, "code", None)  # urllib HTTPError
        if isinstance(status, int) and status in TRANSIENT_HTTP_STATUSES:
            return True
        text = str(current).lower()
        match = _HTTP_STATUS_IN_TEXT.search(text)
        if match and int(match.group(1)) in TRANSIENT_HTTP_STATUSES:
            return True
        if any(hint in text for hint in _TRANSIENT_ERROR_HINTS):
            return True
        current = current.__cause__ or current.__context__
    return False


def call_with_retries(
        func: Callable[[], Any],
        *,
        attempts: int = 4,
        base_delay: float = 5.0,
        max_delay: float = 120.0,
        is_retryable: Callable[[BaseException], bool] = is_transient_error,
        on_retry: Optional[Callable[[int, int, float, BaseException],
                                    None]] = None,
        sleep: Optional[Callable[[float], None]] = None) -> Any:
    """Call ``func`` and repeat it after temporary failures.

    The wait doubles after every failure (base_delay, 2*base_delay, ...),
    is capped at ``max_delay`` and gets up to 25% random jitter so that
    several clients do not retry in lockstep. A ``retry_after`` attribute on
    the error (a Retry-After header) raises the wait, up to ``max_delay``.

    Args:
        func (Callable[[], Any]): Zero-argument callable performing one try.
        attempts (int): Total number of tries, including the first one.
        base_delay (float): Wait in seconds after the first failure.
        max_delay (float): Upper bound for one wait (before jitter).
        is_retryable (Callable): Predicate deciding whether to try again.
        on_retry (Optional[Callable]): Called as ``(attempt, attempts, delay,
            error)`` right before each wait, e.g. for logging.
        sleep (Optional[Callable[[float], None]]): Performs the wait. Defaults
            to ``time.sleep``; pass an interruptible wait to support cancel.

    Returns:
        Any: Whatever ``func`` returns on its first success.

    Raises:
        Exception: The last error, once it is not retryable or the attempts
            are used up.
    """
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:
            if attempt >= attempts or not is_retryable(exc):
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            retry_after = getattr(exc, "retry_after", None)
            if retry_after:
                delay = max(delay, min(float(retry_after), max_delay))
            delay += random.uniform(0, delay * 0.25)
            if on_retry:
                on_retry(attempt, attempts, delay, exc)
            (sleep or time.sleep)(delay)


def _parse_retry_after(value: Any) -> Optional[float]:
    """Read a Retry-After header given in seconds; None if absent/unusable."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def assemble_rings(ways: list[list[tuple]]) -> tuple[list, list]:
    """Join way fragments end to end into closed rings.

    Fragments are matched by identical end coordinates and reversed when
    needed. Unlike a strict assembler this one never gives up on the whole
    boundary: chains that do not close are returned separately so the caller
    can skip them and keep every ring that did close.

    Args:
        ways (list[list[tuple]]): Fragments as lists of (lon, lat) points.

    Returns:
        tuple[list, list]: ``(rings, open_chains)``. A ring is a list of
            points whose first and last point are equal (at least 4 points).
    """
    fragments = [list(way) for way in ways if len(way) >= 2]
    ends: dict = {}
    for index, fragment in enumerate(fragments):
        ends.setdefault(fragment[0], []).append(index)
        if fragment[-1] != fragment[0]:
            ends.setdefault(fragment[-1], []).append(index)
    used = [False] * len(fragments)

    def take(point):
        """Pop an unused fragment that starts or ends at ``point``."""
        candidates = ends.get(point, [])
        while candidates:
            index = candidates.pop()
            if not used[index]:
                used[index] = True
                return fragments[index]
        return None

    rings: list = []
    open_chains: list = []
    for start in range(len(fragments)):
        if used[start]:
            continue
        used[start] = True
        chain = list(fragments[start])
        while chain[0] != chain[-1]:
            fragment = take(chain[-1])
            if fragment is not None:
                if fragment[0] == fragment[-1]:
                    # a separate closed way that merely touches the chain
                    if len(fragment) >= 4:
                        rings.append(fragment)
                elif fragment[0] == chain[-1]:
                    chain.extend(fragment[1:])
                else:
                    chain.extend(reversed(fragment[:-1]))
                continue
            fragment = take(chain[0])
            if fragment is not None:
                if fragment[0] == fragment[-1]:
                    if len(fragment) >= 4:
                        rings.append(fragment)
                elif fragment[-1] == chain[0]:
                    chain[:0] = fragment[:-1]
                else:
                    chain[:0] = reversed(fragment[1:])
                continue
            break
        if chain[0] == chain[-1] and len(chain) >= 4:
            rings.append(chain)
        else:
            open_chains.append(chain)
    return rings, open_chains


def relation_geometry_from_json(
        relation: dict, logger: Optional[logging.Logger] = None
) -> Optional[dict]:
    """Build a relation's boundary from an Overpass JSON element.

    Works on the output of ``out body geom``: every way member carries its
    own list of coordinates. Only outer rings are built (the app draws
    outlines, holes are not needed). Rings that cannot be closed are skipped
    with a warning instead of failing the whole relation.

    Args:
        relation (dict): One relation element of an Overpass JSON answer.
        logger (Optional[logging.Logger]): Receives warnings about problems.

    Returns:
        Optional[dict]: GeoJSON-like 'Polygon' or 'MultiPolygon' mapping, or
            None if no closed ring could be built.
    """
    ways = []
    for member in relation.get("members") or []:
        if member.get("type") != "way":
            continue
        if member.get("role", "") not in ("outer", ""):
            continue
        points = [(node["lon"], node["lat"])
                  for node in member.get("geometry") or [] if node]
        if len(points) >= 2:
            ways.append(points)

    label = f"{relation.get('type', 'relation')}/{relation.get('id')}"
    rings, open_chains = assemble_rings(ways)
    if open_chains and logger:
        logger.warning(
            "%s: %s way chain(s) could not be closed and were skipped "
            "(%s ring(s) built)", label, len(open_chains), len(rings))
    if not rings:
        if logger:
            logger.warning("%s: no closed outer ring could be built", label)
        return None
    polygons = [[[list(point) for point in ring]] for ring in rings]
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


class RawElement:
    """Element of an Overpass JSON answer.

    Offers the small part of the OSMPythonTools element API that
    EarthCrawler uses, so results of the Requests backend can be handled by
    the same code as results of OSMPythonTools.
    """

    def __init__(self, data: dict, logger: Optional[logging.Logger] = None):
        self._data = data
        self._logger = logger

    def type(self) -> Optional[str]:
        return self._data.get("type")

    def id(self) -> Optional[int]:
        return self._data.get("id")

    def tags(self) -> dict:
        return self._data.get("tags") or {}

    def tag(self, key: str) -> Optional[str]:
        return self.tags().get(key)

    def lat(self) -> Optional[float]:
        return self._data.get("lat")

    def lon(self) -> Optional[float]:
        return self._data.get("lon")

    def geometry(self) -> Optional[dict]:
        """Boundary of a relation, built by relation_geometry_from_json."""
        return relation_geometry_from_json(self._data, self._logger)

    def toJSON(self) -> dict:
        return self._data


class RawOverpassResult:
    """Overpass JSON answer with the OverpassResult methods EarthCrawler uses.
    """

    def __init__(self, data: dict, logger: Optional[logging.Logger] = None):
        self._data = data
        self._logger = logger

    def _elements(self, element_type: str) -> list:
        return [RawElement(element, self._logger)
                for element in self._data.get("elements") or []
                if element.get("type") == element_type]

    def relations(self) -> list:
        return self._elements("relation")

    def nodes(self) -> list:
        return self._elements("node")

    def toJSON(self) -> dict:
        return self._data


def parse_admin_level(value: Any) -> int:
    """Read an OSM admin_level tag value.

    Args:
        value (Any): Tag value, usually a string such as '4'.

    Returns:
        int: The level, or 0 if the tag is missing or not a plain number
            (OSM data also contains values like '4;5').
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def get_nominatim_id_from_json(
        json_data: list[dict], index: int = 0) -> str:
    """Extract an OSM type-and-ID string from Nominatim search results.

    Args:
        json_data (list[dict]): Search results returned by Nominatim.
        index (int, optional): Record index to read. Defaults to 0.

    Returns:
        str: Combined OSM type and identifier string.
    """
    return f"{json_data[index]['osm_type'][0]}{json_data[index]['osm_id']}"


class EarthCrawler:
    """
    Uses OSM APIs (Nominatim, Overpass) to get requested regions borders as
    well as various lacalities (cities, towns, villages,etc.) and export them
    to related formats like KML.
    """

    # Retry policy for requests to Overpass and Nominatim, see
    # call_with_retries(). With the defaults a failing request is tried 4
    # times with waits of about 5, 10 and 20 seconds in between.
    retry_attempts = 4
    retry_base_delay = 5.0
    retry_max_delay = 120.0

    def __init__(
            self,
            app_data: AppData,
            on_progress: Any = None,
            on_total_progress: Any = None,
            on_export: Any = None,
            on_point: Any = None,
            on_polygon: Any = None,
            on_finish: Any = None,
            on_status: Any = None):
        """Initialize OSM clients and optional event callbacks.

        Args:
            app_data (AppData): Application settings and various data.
            on_progress (Any, optional): Callback for indexed progress events.
            on_total_progress (Any, optional): Callback for total work count.
            on_export (Any, optional): Callback for export-state events.
            on_point (Any, optional): Callback for map point additions.
            on_polygon (Any, optional): Callback for map polygon additions.
            on_finish (Any, optional): Callback invoked when a search ends.
            on_status (Any, optional): Callback for short status texts such
                as "Requesting borders from the server...".
        """
        self.app_data = app_data
        self.logger = logging.getLogger(DEFAULT_LOGGER_NAME)

        # Initiate search engines
        self.nominatim = Nominatim()
        self.overpass = Overpass()

        # Excel export is collected here (sheet name -> DataFrame) while the
        # search runs and written to disk in one go by save_excel().
        self._excel_sheets: dict[str, pd.DataFrame] = {}

        # Set from another thread (the GUI) by cancel() to stop the search.
        self._cancel_event = threading.Event()

        self._on_progress = on_progress or (lambda *a, **kw: None)
        self._on_total_progress = on_total_progress or (lambda *a, **kw: None)
        self._on_export = on_export or (lambda *a, **kw: None)
        self._on_point = on_point or (lambda *a, **kw: None)
        self._on_polygon = on_polygon or (lambda *a, **kw: None)
        self._on_finish = on_finish or (lambda *a, **kw: None)
        self._on_status = on_status or (lambda *a, **kw: None)

    def cancel(self):
        """Ask the running search to stop as soon as possible.

        Safe to call from any thread. The search raises OperationCancelled at
        its next checkpoint: while waiting for a server, while pausing before
        a retry, and between processed regions and locations.
        """
        self._cancel_event.set()

    def reset_cancel(self):
        """Forget a previous cancel() so that a new search can run."""
        self._cancel_event.clear()

    def _raise_if_cancelled(self):
        """Checkpoint: stop the search if cancel() was called."""
        if self._cancel_event.is_set():
            raise OperationCancelled()

    def _interruptible_sleep(self, seconds: float):
        """Wait like time.sleep, but wake up immediately on cancel()."""
        if self._cancel_event.wait(seconds):
            raise OperationCancelled()

    def _run_cancellable(self, func: Callable[[], Any]) -> Any:
        """Run a blocking call so that cancel() does not have to wait for it.

        A running HTTP request cannot be interrupted from outside, so it runs
        in a helper thread while this thread watches the cancel flag. After a
        cancel the helper thread is abandoned: it finishes (or times out) in
        the background and its result is dropped.

        Args:
            func (Callable[[], Any]): Zero-argument blocking callable.

        Returns:
            Any: Whatever ``func`` returns.

        Raises:
            OperationCancelled: If cancel() was called before it finished.
        """
        self._raise_if_cancelled()
        outcome: dict = {}
        done = threading.Event()

        def target():
            try:
                outcome["value"] = func()
            except BaseException as exc:  # handed over to the caller
                outcome["error"] = exc
            finally:
                done.set()

        threading.Thread(
            target=target, daemon=True, name="OsmRequest").start()
        while not done.wait(0.2):
            if self._cancel_event.is_set():
                raise OperationCancelled()
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]

    def _with_retries(self, func: Callable[[], Any], what: str) -> Any:
        """Run one server request, repeating it after temporary failures.

        The request can be cancelled, see cancel().

        Args:
            func (Callable[[], Any]): Zero-argument callable doing the request.
            what (str): Short description used in the log messages.

        Returns:
            Any: The result of the first successful call.
        """
        def log_retry(attempt, attempts, delay, exc):
            self.logger.warning(
                "%s failed (attempt %s of %s): %s. Retrying in %.0f s",
                what, attempt, attempts, exc, delay)
            self._on_status(
                f"Server problem, retry {attempt + 1} of {attempts} "
                f"in {delay:.0f} s")

        return call_with_retries(
            lambda: self._run_cancellable(func),
            attempts=self.retry_attempts,
            base_delay=self.retry_base_delay,
            max_delay=self.retry_max_delay,
            on_retry=log_retry,
            sleep=self._interruptible_sleep)

    def _nominatim_query(self, *args, **kwargs) -> Any:
        """Query Nominatim, repeating the request after temporary failures."""
        return self._with_retries(
            lambda: self.nominatim.query(*args, **kwargs), "Nominatim query")

    @staticmethod
    def get_osm_element_name(element: Any, language_code: str) -> str:
        """Choose a localized name for an OSM element with a stable fallback.

        Args:
            element (Any): OSM element that provides ``tag``, ``type``, and
                ``id`` methods.
            language_code (str): Language code used for the localized name tag.

        Returns:
            str: Localized name, default name, or 'Unnamed object'.
        """
        localized_name = element.tag(f"name:{language_code}")
        if localized_name:
            return localized_name

        default_name = element.tag("name")
        if default_name:
            return default_name

        return "Unnamed object"

    def configure_kml_obj(self, kml_obj: simplekml.Folder) -> simplekml.Folder:
        """Apply the configured line color and width to a KML object.

        Args:
            kml_obj (simplekml.Folder): Base KML folder or feature to style.

        Returns:
            simplekml.Folder: Styled KML object.
        """
        kml_obj.style.linestyle.color = simplekml.Color.hex(
            self.app_data.kml.line_color[1:])
        kml_obj.style.linestyle.width = self.app_data.kml.line_width
        return kml_obj

    def add_kml_object(
            self, kml_level: simplekml.Folder, coords: list,
            obj_name: str, obj_types: list):
        """Add a geometry object to the target KML folder.

        Args:
            kml_level (simplekml.Folder): Folder that receives the geometry.
            coords (list): Coordinate pairs describing the shape.
            obj_name (str): Name used in the generated KML object.
            obj_types (list): Geometry types such as "Polygon" or "Line".
        """
        if 'Polygon' in obj_types and \
                self.app_data.kml.polygons_to_lines is False:
            kml_obj = kml_level.newpolygon(
                name=f"{obj_name}", outerboundaryis=coords)
            kml_obj.polystyle.fill = 0
            self.configure_kml_obj(kml_obj)
        if 'Line' in obj_types or self.app_data.kml.polygons_to_lines is True:
            kml_obj = kml_level.newlinestring(
                name=f"{obj_name}", coords=coords)
            self.configure_kml_obj(kml_obj)

    def choose_name_from_tag(self, tags: dict) -> str:
        """Choose a localized or default name from an OSM tag mapping.

        Args:
            tags (dict): Raw OSM tags returned for the object.

        Returns:
            str: Localized name, default name, or an unnamed-object fallback.
        """
        cur_lang_tag = f"name:{self.app_data.search.objects_language}"
        return tags.get(cur_lang_tag) or tags.get("name") or "Unnamed object"

    def process_loaded_wkt(
            self,
            kml_doc: simplekml.Folder,
            loaded_wkt: Union[JPolygon, BaseGeometry],
            object_name: str):
        """Convert a WKT (well-known text) geometry into KML polygons or lines.

        Polygon and MultiPolygon geometries are supported (outer boundaries
        only). A geojson Polygon object is converted to a shapely geometry
        first.

        Args:
            kml_doc (simplekml.Folder): Destination KML folder.
            loaded_wkt (Union[JPolygon, BaseGeometry]): Geometry returned by
                the Nominatim API or built from an Overpass relation.
            object_name (str): Name assigned to the region geometry.
        """
        if isinstance(loaded_wkt, JPolygon):
            # geojson objects are plain dicts, shapely can build from them
            loaded_wkt = shape(loaded_wkt)
        if not isinstance(loaded_wkt, BaseGeometry):
            self.logger.error(
                f"Unknown geometry type: {type(loaded_wkt)}")
            return
        gtype = loaded_wkt.geom_type
        if gtype == 'MultiPolygon':
            polygons = list(loaded_wkt.geoms)
            multi_poly_folder = kml_doc.newfolder(name=object_name)
            for i, poly in enumerate(polygons):
                coords = list(poly.exterior.coords)
                i_obj_name = f"{object_name}_{i+1}"
                self.add_kml_object(
                    multi_poly_folder, coords, i_obj_name, ['Polygon'])
                self._on_polygon(self._map_outline(poly), i_obj_name)
        elif gtype == 'Polygon':
            coords = list(loaded_wkt.exterior.coords)
            self.add_kml_object(
                kml_doc,
                coords,
                object_name,
                ['Polygon']
            )
            self._on_polygon(self._map_outline(loaded_wkt), object_name)
        else:
            self.logger.error(f"Unsupported geometry type: {gtype}")

    @staticmethod
    def _map_outline(polygon: Any) -> list[tuple[float, float]]:
        """Outer ring of a polygon as (lat, lon) pairs for the map widget.

        The ring is simplified with a tolerance relative to the polygon's own
        size (see MAP_OUTLINE_DETAIL), so a small region keeps its detail and
        a country shrinks from hundreds of thousands of vertices to a few
        thousand. The polygon itself is not changed.

        Args:
            polygon (Any): A shapely Polygon.

        Returns:
            list[tuple[float, float]]: The ring as (lat, lon) pairs.
        """
        min_x, min_y, max_x, max_y = polygon.bounds
        tolerance = max(max_x - min_x, max_y - min_y) / MAP_OUTLINE_DETAIL
        outline = polygon
        if tolerance > 0:
            simple = polygon.simplify(tolerance, preserve_topology=True)
            if simple.geom_type == "Polygon" and not simple.is_empty:
                outline = simple
        return [(lat, lon) for lon, lat in outline.exterior.coords]

    def _is_kml_empty(self, kml_doc: simplekml.Kml) -> bool:
        """Check whether the current KML document contains any features.

        Args:
            kml_doc (simplekml.Kml): KML document to inspect.

        Returns:
            bool: True if the document is empty, otherwise False.
        """
        self.logger.debug(
            f"self.kml_doc.allcontainers: {self.kml_doc.allcontainers}")
        self.logger.debug(
            f"self.kml_doc.allfeatures: {self.kml_doc.allfeatures}")
        self.logger.debug(
            f"self.kml_doc.allgeometries: {self.kml_doc.allgeometries}")
        if not kml_doc.allcontainers and \
           not kml_doc.allfeatures and \
           not kml_doc.allgeometries:
            return True
        return False

    def save_kml(self, obj_name: str):
        """Save the current KML document for the processed object.

        Args:
            obj_name (str): Base name used for the exported file.
        """
        if not self._is_kml_empty(self.kml_doc):
            if self.app_data.kml.polygons_to_lines:
                sub_name = "(lines)"
            else:
                sub_name = "(polygons)"
            kml_file_name = f"{obj_name} {sub_name}"
            self.kml_doc.save(f".\\export\\{kml_file_name}.kml")
            self.logger.info(f"KML file saved as {kml_file_name}")
        else:
            self.logger.warning("KML file is empty. Nothing to save.")

    @staticmethod
    def make_sheet_name(name: Optional[str]) -> str:
        """Turn an arbitrary name into a valid Excel worksheet name.

        Invalid characters are replaced with underscores, apostrophes at the
        edges are dropped, and the result is cut to 31 characters. An empty
        result falls back to 'Locations'.

        Args:
            name (Optional[str]): Desired sheet name, usually a region name.

        Returns:
            str: Name that Excel accepts.
        """
        cleaned = _EXCEL_INVALID_SHEET_CHARS.sub("_", str(name or ""))
        cleaned = cleaned.strip().strip("'").strip()
        return cleaned[:EXCEL_SHEET_NAME_MAX_LEN] or "Locations"

    def _unique_sheet_name(self, name: Optional[str]) -> str:
        """Return a valid sheet name not yet used in the collected export.

        Excel compares sheet names case-insensitively, so 'Riga' and 'RIGA'
        clash. A clash gets a numeric suffix: 'Riga', 'Riga (2)', ...

        Args:
            name (Optional[str]): Desired sheet name.

        Returns:
            str: Valid and unique sheet name.
        """
        base = self.make_sheet_name(name)
        taken = {existing.lower() for existing in self._excel_sheets}
        candidate = base
        counter = 2
        while candidate.lower() in taken:
            suffix = f" ({counter})"
            candidate = base[:EXCEL_SHEET_NAME_MAX_LEN - len(suffix)] + suffix
            counter += 1
        return candidate

    def _add_excel_sheet(self, sheet_name: Optional[str], rows: list[dict]):
        """Store one sheet of locations for the later Excel export.

        Args:
            sheet_name (Optional[str]): Desired sheet name (region name).
            rows (list[dict]): One dict per location with EXCEL_COLUMNS keys.
        """
        if not rows:
            self.logger.debug(
                "No locations for sheet '%s', sheet skipped", sheet_name)
            return
        name = self._unique_sheet_name(sheet_name)
        self._excel_sheets[name] = pd.DataFrame(rows, columns=EXCEL_COLUMNS)
        self.logger.debug(
            "Excel sheet '%s' prepared with %s locations", name, len(rows))

    def save_excel(self, obj_name: str):
        """Write all collected location sheets to '<obj_name>.xlsx'.

        The file is created in the export folder. Nothing is written when no
        sheet has been collected.

        Args:
            obj_name (str): Base name used for the exported file.
        """
        if not self._excel_sheets:
            self.logger.warning("Excel export is empty. Nothing to save.")
            return
        file_path = Paths.export_folder.joinpath(f"{obj_name}.xlsx")
        with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
            for sheet_name, df in self._excel_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        self.logger.info(
            f"Excel file saved as {obj_name}.xlsx "
            f"({len(self._excel_sheets)} sheets)")

    def prepare_overpass_query(
            self, search_data: dict, mode: OverpassQueryMode) -> str:
        """Build an Overpass query from the search context.

        Args:
            search_data (dict): Search metadata and Nominatim result payload.
            mode (OverpassQueryMode): The mode for the Overpass query.

        Returns:
            str: Prepared Overpass query string.
        """
        area = OSMElement.fromId(search_data["nominatim_id"])
        areaId = area.areaId()
        if mode == OverpassQueryMode.REGIONS:
            object_request = search_data["object_request"]
            levels_obj = ValueSpec.apply_extra_value(
                object_request,
                search_data["admin_level"],
                object_request.explicit
            )
            levels = levels_obj.format()  # search_data["admin_level"]
            query = f'area({areaId})->.country; '\
                'relation["boundary"="administrative"]' \
                f'["admin_level"~"^({levels})$"]'\
                '(area.country); out body geom;'
        elif mode == OverpassQueryMode.LOCATIONS:
            places = "|".join(self.app_data.search.search_places_choice)
            query = f'area({areaId})->.searchArea;' \
                f'(node["place"~"{places}"](area.searchArea););' \
                'out geom;'
        self.logger.info("Query: %s", str(query))
        return query

    def overpass_request(
            self,
            query: str,
            search_mode: SearchMode = SearchMode.OSM_PYTHON_TOOLS) -> Any:
        """Execute an Overpass query using the selected backend.

        Args:
            query (str): Overpass QL query to execute.
            search_mode (SearchMode, optional): Backend to use. Defaults to
                ``SearchMode.OSMPYTHONTOOLS``.

        Returns:
            Any: Result returned by the selected backend. Temporary server
                errors are retried first, see ``call_with_retries``.
        """
        if search_mode == SearchMode.OSM_PYTHON_TOOLS:
            result = self._with_retries(
                lambda: self.overpass.query(query, timeout=60),
                "Overpass query")
        elif search_mode == SearchMode.REQUESTS:
            # overpass_raw_request() retries on its own
            # raw JSON -> same relations()/nodes() API as OSMPythonTools
            result = RawOverpassResult(
                self.overpass_raw_request(
                    query, self.app_data.requests.api_link),
                self.logger)
        return result

    def regions_overpass_request(self, region: OSMElement) -> Any:
        """Fetch the named region's WKT geometry from Nominatim.

        Args:
            region (OSMElement): Region element returned by Overpass.

        Returns:
            Any: Nominatim response containing the region geometry.
        """
        region_data = self._nominatim_query(
            f"{region.type()}/{region.id()}",
            zoom=4, lookup=True, wkt=True)
        return region_data

    def regions_search(
            self, region_data: Any, kml_doc: simplekml.Folder,
            region_name: str):
        """Search and render the polygon geometry for a region.

        Args:
            region_data (Any): Nominatim response containing WKT geometry.
            kml_doc (simplekml.Folder): Destination KML folder.
            region_name (str): Name assigned to the region geometry.
        """
        loaded_wkt = wkt.loads(region_data.wkt())
        if hasattr(loaded_wkt, 'geom_type'):
            self.process_loaded_wkt(kml_doc, loaded_wkt, region_name)
        else:
            self.logger.warning(
                "Region geometry has no supported geometry type")

    def locations_overpass_request(self, region: OSMElement) -> Any:
        """Fetch place nodes contained by a region.

        Args:
            region (OSMElement): Region element returned by Nominatim.

        Returns:
            Any: Overpass result containing matching place nodes.

        """
        # TODO: Needs testing
        search_data = {"nominatim_id": f"{region.type()[0]}{region.id()}"}
        query = self.prepare_overpass_query(
            search_data, OverpassQueryMode.LOCATIONS)

        points = self.overpass_request(
            query, SearchMode(self.app_data.requests.requests_type))
        return points

    def locations_search(
            self,
            points: Any,
            kml_doc: simplekml.Folder,
            progress_start: Optional[int] = None,
            sheet_name: Optional[str] = None) -> int:
        """Add place nodes to KML and the map, and optionally export a sheet.

        Each location becomes one Excel row with the EXCEL_COLUMNS fields:
        its (localized) name, its OSM 'place' type, longitude and latitude.

        Args:
            points (Any): Overpass result containing place nodes.
            kml_doc (simplekml.Folder): Destination KML folder.
            progress_start (Optional[int]): Initial zero-based progress index.
                Defaults to zero when omitted.
            sheet_name (Optional[str]): Excel sheet for these locations,
                normally the region name. Made valid and unique
                automatically; defaults to 'Locations'.

        Returns:
            int: Next zero-based progress index after the processed nodes.
        """
        current_object_num = progress_start or 0
        # keys_list = self.app_data.search.search_places_choice + \
        #     ["county", "state", "region", "country"]
        dict_list = []
        for p in points.nodes():
            self._raise_if_cancelled()
            self.logger.debug(
                "Location found at %.6f, %.6f with tags: %s",
                p.lat(), p.lon(), p.tags()
            )
            # nom_result = self.nominatim.query(
            #     f"{p.type()}/{p.id()}", zoom=10, lookup=True,
            #     params={
            #         'accept-language':
            #             str(self.app_data.search.objects_language),
            #     }
            # )
            # adr = nom_result.address()
            adr_mod = {}
            # for x in keys_list:
            #     try:
            #         loc = adr[x]
            #         if x in self.app_data.search.search_places_choice:
            #             adr_mod["location"] = loc

            #         else:
            #             adr_mod[x] = loc
            #     except Exception:
            #         continue
            adr_mod["location"] = self.get_osm_element_name(
                p, str(self.app_data.search.objects_language))
            adr_mod["place"] = p.tag("place")
            adr_mod["lon"] = p.lon()
            adr_mod["lat"] = p.lat()
            try:
                kml_doc.newpoint(
                    name=adr_mod["location"], coords=[(p.lon(), p.lat())])
            except KeyError:
                self.logger.warning(
                    "Location without a name was skipped: %.6f, %.6f",
                    p.lat(), p.lon())
                self._on_progress(current_object_num, "Unnamed location")
                current_object_num += 1
                continue
            self.logger.debug(
                "Location added: %s", adr_mod["location"])
            self._on_point(
                float(p.lat()),
                float(p.lon()),
                adr_mod["location"],
            )
            dict_list.append(adr_mod)
            self._on_progress(current_object_num, adr_mod["location"])
            current_object_num += 1
        if self.app_data.export.export_to_excel:
            self._add_excel_sheet(sheet_name, dict_list)
        return current_object_num

    def details_search(self, region: OSMElement, kml_doc: simplekml.Folder):
        """Search the region's border geometry and place nodes.

        Args:
            region (OSMElement): Region whose border and places are searched.
            kml_doc (simplekml.Folder): Destination KML folder.
        """
        region_name = self.get_osm_element_name(
            region, str(self.app_data.search.objects_language)
        )
        if self.app_data.search.search_borders:
            region_data = self.regions_overpass_request(region)
            self.regions_search(region_data, kml_doc, region_name)

        self._raise_if_cancelled()
        if self.app_data.search.search_locations:
            points = self.locations_overpass_request(region)
            self.locations_search(points, kml_doc, sheet_name=region_name)

    def first_nominatim_search(
            self,
            single_obj_req: ValueSpecEntry,
            search_type: str) -> list[dict]:
        """Search Nominatim for the requested object and return its raw data.

        Args:
            single_obj_req (ValueSpecEntry): Object specification entry.
            search_type (str): Search scope type such as world, country, or
                state.

        Returns:
            list[dict]: List of Nominatim results as dictionaries.
        """
        self.kml_doc = simplekml.Kml()
        self._excel_sheets = {}
        self._on_status(f"Searching for {single_obj_req.name}...")
        params = {
            'accept-language': str(
                self.app_data.search.objects_language),
            'extratags': 1,
        }  # language=self.app_data.search.objects_language

        if search_type == "world" or search_type == "":
            osm_data = self._nominatim_query(
                single_obj_req.name,
                params=params
            )
        else:
            params['featureType'] = str(search_type)
            osm_data = self._nominatim_query(
                single_obj_req.name, params=params
            )

        self.logger.debug(
            "Nominatim result address: %s for search type: %s",
            osm_data.address(), search_type
        )

        json: list = osm_data.toJSON()

        for i, res in enumerate(json):
            # Add new attribute to results dictionary for future use
            res["nominatim_id"] = \
                get_nominatim_id_from_json(json, i)
            res["object_request"] = single_obj_req
            # Remove an excessive attribute from results dictionary
            res.pop("licence", None)
            # "extratags" is null for objects without extra tags
            extra = res.get("extratags") or {}
            res["extratags"] = extra
            res["admin_level"] = parse_admin_level(
                extra.pop("admin_level", None))
        return json

    def overpass_raw_request(
            self,
            query: str,
            api_url: str = "https://overpass-api.de/api/interpreter",
            user_agent: str = (
                "MyOSMTools/1.0 "
                "(https://github.com/yourname/MyOSMTools)"
            )) -> Any:
        """
        Sends a raw Overpass query and returns the result in JSON format.

        Overpass answers in XML unless the query starts with ``[out:json]``;
        that setting is added here when the query has no settings of its own.

        Temporary failures (HTTP 429/500/502/503/504, timeouts, dropped
        connections, a "server busy" page) are retried with growing pauses,
        honouring the Retry-After header. Other errors (for example HTTP 400
        for a broken query, an Overpass runtime error such as out of memory,
        or an answer that is not JSON) are not retried; the beginning of the
        unexpected answer is put into the error message.

        Args:
            query (str): Overpass query string
            api_url (str, optional): The Overpass API URL to use.
            user_agent (str, optional): The User-Agent header for the request.

        Returns:
            Any: Result of the Overpass query in JSON format.

        Raises:
            Exception: If the request finally failed. An empty list used to
                be returned instead, which callers mistook for a result.
        """
        # url = "https://overpass-api.de/api/interpreter"
        # url = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
        # url = "https://overpass.private.coffee/api/interpreter"

        # EarthCrawlerApp/2.0.0 (https://github.com/ikomash/earth-crawler)
        headers = {
            "User-Agent": user_agent,
            "Content-Type":
                "application/x-www-form-urlencoded; charset=UTF-8"
        }

        # OSMPythonTools adds this itself, a plain request has to do it
        if not query.lstrip().startswith("["):
            query = f"[out:json];{query}"

        def post_once() -> Any:
            response = requests.post(
                api_url, data={'data': query}, headers=headers, timeout=600)
            if response.status_code in TRANSIENT_HTTP_STATUSES:
                raise RetryableOverpassError(
                    f"HTTP {response.status_code} from {api_url}",
                    retry_after=_parse_retry_after(
                        response.headers.get("Retry-After")))
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as e:
                snippet = " ".join(str(response.text)[:200].split())
                if any(hint in snippet.lower()
                       for hint in _BUSY_PAGE_HINTS):
                    raise RetryableOverpassError(
                        f"Overpass looks busy, answer is not JSON: "
                        f"{snippet}") from e
                raise OverpassRuntimeError(
                    f"Overpass answer is not JSON: {snippet}") from e
            remark = data.get("remark") if isinstance(data, dict) else None
            if isinstance(remark, str) and "runtime error" in remark.lower():
                raise OverpassRuntimeError(remark)
            return data

        return self._with_retries(post_once, "Overpass request")

    def overpass_short_search(self, search_data: dict) -> OverpassResult:
        """Try admin levels and return the first valid Overpass result.

        Args:
            search_data (dict): One selected Nominatim result with query
                metadata.

        Returns:
            Optional[OverpassResult]: Matching regions, or None if the query
                fails for all attempted levels.
        """
        regions: Any = None
        object_request = search_data["object_request"]
        levels_obj = ValueSpec.apply_extra_value(
            object_request,
            search_data["admin_level"],
            object_request.explicit,
        )

        for i in levels_obj.levels:
            try:
                query = self.prepare_overpass_query(
                    search_data, OverpassQueryMode.REGIONS)
                regions = self.overpass_request(
                    query, SearchMode.OSM_PYTHON_TOOLS)
                self.logger.info("Overpass query: %s", query)
                break
            except TypeError:
                self.logger.warning(f"No administrative level {i} found")
                continue
        return regions

    def _region_geometry(self, region: Any) -> Optional[dict]:
        """Get a region's boundary as a GeoJSON-like mapping.

        OSMPythonTools refuses to build some complex boundaries ("cannot
        close ring"). Then the boundary is assembled from the element's raw
        JSON by relation_geometry_from_json(), which skips only the broken
        chains and keeps every ring that closes. Elements of the Requests
        backend always use that assembler.

        Args:
            region (Any): Relation element (OSMPythonTools or RawElement).

        Returns:
            Optional[dict]: Polygon/MultiPolygon mapping, or None.
        """
        try:
            return region.geometry()
        except AttributeError as e:
            self.logger.warning("Region geometry is unavailable: %s", e)
            return None
        except Exception as e:
            self.logger.warning(
                f"Geometry error: {e}. Trying own boundary assembly")
        to_json = getattr(region, "toJSON", None)
        if not callable(to_json):
            return None
        try:
            return relation_geometry_from_json(to_json(), self.logger)
        except Exception as e:
            self.logger.error(f"Own boundary assembly failed: {e}")
            return None

    def overpass_full_search(self, search_data: dict) -> OverpassResult:
        """Search administrative borders for the selected object in full mode.

        Args:
            search_data (dict): Search metadata and result set from Nominatim.

        Returns:
            OverpassResult: Regions found for the target object.
        """
        self.logger.debug(
            "Overpass full object search using this data: %s",
            str(search_data)
        )

        failed_requests = 0
        borders_num = 0
        borders = None
        if self.app_data.search.search_borders:
            self._on_status("Requesting borders from the server...")
            try:
                borders_query = self.prepare_overpass_query(
                    search_data, OverpassQueryMode.REGIONS)
                self.logger.debug("Borders query: %s", str(borders_query))
                borders = self.overpass_request(
                    borders_query,
                    SearchMode(self.app_data.requests.requests_type)
                )
                # res = self.overpass_raw_request(ext_query)
                # 'params' is unused in source lib but required
                # borders = OverpassResult(res, borders_query, None)
            except TypeError as e:
                self.logger.error(f"No administrative objects found {e}")
                borders = None
            except Exception as e:
                self.logger.error(f"Overpass borders full search failed: {e}")
                borders = None
                failed_requests += 1
            if borders:
                rel = borders.relations()
                if rel:
                    borders_num = len(borders.relations())
                else:
                    borders_num = 0
                self.logger.debug(f"Borders found: {borders_num}")

        locations_num = 0
        locations = None
        if self.app_data.search.search_locations:
            self._on_status("Requesting locations from the server...")
            try:
                places_query = self.prepare_overpass_query(
                    search_data, OverpassQueryMode.LOCATIONS)
                self.logger.debug("Places query: %s", str(places_query))
                locations = self.overpass_request(
                    places_query,
                    SearchMode(self.app_data.requests.requests_type)
                )
            except TypeError as e:
                self.logger.error(f"No locations found {e}")
                locations = None
            except Exception as e:
                self.logger.error(
                    f"Overpass locations full search failed: {e}")
                locations = None
                failed_requests += 1
            if locations:
                nodes = locations.nodes()
                if nodes:
                    locations_num = len(locations.nodes())
                else:
                    locations_num = 0
                self.logger.debug(f"Found locations: {locations_num}")

        total_objects_num = locations_num + borders_num
        if self._on_total_progress:
            self._on_total_progress(total_objects_num)
        current_object_num = 0

        if borders is not None and borders.relations() is not None:
            for region in borders.relations():
                self._raise_if_cancelled()
                cur_folder = self.kml_doc
                region_name = self.get_osm_element_name(
                    region, str(self.app_data.search.objects_language)
                )
                geometry = self._region_geometry(region)
                if geometry:
                    geom = shape(geometry)
                    self.process_loaded_wkt(cur_folder, geom, region_name)
                self._on_progress(current_object_num, region_name)
                current_object_num += 1

        found_nodes = locations.nodes() if locations is not None else None
        if found_nodes:
            current_object_num = self.locations_search(
                locations, self.kml_doc, current_object_num,
                sheet_name=search_data["object_request"].name)
        elif self.app_data.search.search_locations:
            self.logger.warning("No locations found")

        try:
            if self.app_data.export.export_to_excel and \
                    self.app_data.search.search_locations:
                self.save_excel(search_data["object_request"].name)
        except Exception as e:
            self.logger.error(f"Excel export error {e}")
        try:
            if self.app_data.export.export_to_kml:
                self.save_kml(search_data["object_request"].name)
        except Exception as e:
            self.logger.error(f"KML export error {e}")
        finally:
            if failed_requests:
                self._on_status("Finished with errors, see the log")
            self._on_finish()

    def second_nominatim_search(
            self, overpass_regions: OverpassResult):
        """Build border and point data for each Overpass region result.

        Args:
            overpass_regions (OverpassResult): Regions returned by Overpass.
        """
        try:
            for i, region in enumerate(overpass_regions.relations()):
                self._raise_if_cancelled()
                if self.app_data.search.search_borders and \
                        self.app_data.search.search_locations:
                    cur_folder = self.kml_doc.newfolder(
                        name=self.choose_name_from_tag(region.tags()))
                else:
                    cur_folder = self.kml_doc
                # TODO: Add progress signals for points and borders
                self.details_search(region, cur_folder)
        except TypeError:
            self.logger.error("No administrative levels found")
            self.app_data.error_found = 1

    # NOTE: Old logic
    def request_and_process_data(self, search_line: str):
        """Run the full search pipeline for the provided request string.

        Args:
            search_line (str): Objects and admin levels in the format
                "object1=admin_level1; object2=admin_level2;...".
        """
        search_list = ValueSpec.search_line_processing(search_line)
        for single_obj_req in search_list:
            search_data = self.first_nominatim_search(
                single_obj_req, self.app_data.search.search_type.name.lower())
            overp_regions = self.overpass_short_search(search_data[0])
            self.second_nominatim_search(overp_regions)
            if self.app_data.error_found == 0:
                if self.app_data.export.export_to_excel:
                    self.save_excel(single_obj_req.name)
                if self.app_data.export.export_to_kml:
                    self.save_kml(single_obj_req.name)
            else:
                self.app_data.error_found = 0


def script_sequence(search_line: str):
    """Execute the crawler flow without launching the GUI.

    Args:
        search_line (str): Objects and admin levels in the format
            "object1=admin_level1; object2=admin_level2;...".
    """
    app_data = AppData()
    logger = Logger(app_data.logging.logging_level).logger
    try:
        Converter = EarthCrawler(app_data)
        Converter.request_and_process_data(search_line)
    except Exception as e:
        if logger:
            logger.exception(f"UncaughtException: {e}")
            logger.warning("Ending script due too uncaught exception")


class OsmWorker(QObject):
    """ Class to run OSM data gathering in a separate thread with GUI. """

    sub_obj_signal = pyqtSignal(int, str)
    total_sub_obj_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    export_visuals_signal = pyqtSignal(list)
    return_to_initial_state_signal = pyqtSignal()

    add_point = pyqtSignal(float, float, str)
    # object, not list: a list would be converted to Qt types vertex by
    # vertex on both sides, which is slow for big polygons
    add_polygon = pyqtSignal(object, str)

    update_results = pyqtSignal(list)
    object_processed = pyqtSignal()
    finish = pyqtSignal()

    def __init__(self, app_data: AppData):
        """Initialize the worker that performs the OSM data collection.

        Args:
            app_data (AppData): Application data class instance.
        """
        super(OsmWorker, self).__init__()
        self.logger = logging.getLogger(DEFAULT_LOGGER_NAME)
        self.app_data = app_data
        self.crawler = EarthCrawler(
            app_data,
            self.sub_obj_signal.emit,
            self.total_sub_obj_signal.emit,
            self.export_visuals_signal.emit,
            self.add_point.emit,
            self.add_polygon.emit,
            self.finish.emit,
            self.status_signal.emit
        )

        self.finish.connect(self.finish_processing)

        # True while a slot below is running in the worker thread
        self._busy = False

    # def __del__(self):
    #     self.wait()

    def cancel(self):
        """Stop the running search or processing, if there is one.

        Call it directly from the GUI thread, not through a signal: the
        worker thread is busy inside the running slot and would not deliver a
        queued signal until that slot has finished. The slot ends without
        emitting any signals; the GUI resets its own state when it cancels.
        Does nothing while the worker is idle, so a cancel can never hit the
        next search by accident.
        """
        if self._busy:
            self.logger.info("Cancelling the running search")
            self.crawler.cancel()

    def _finish_operation(self):
        """Mark the worker idle and drop a cancel request that was consumed."""
        self._busy = False
        self.crawler.reset_cancel()

    @pyqtSlot(object)
    def search_objects(self, single_obj_req: ValueSpecEntry):
        """Run the initial Nominatim search for a single requested object.

        Args:
            single_obj_req (ValueSpecEntry): Object specification entry.
        """
        self._busy = True
        try:
            search_data = \
                self.crawler.first_nominatim_search(
                    single_obj_req,
                    self.app_data.search.search_type.name.lower()
                )
            self.update_results.emit(search_data)
        except OperationCancelled:
            self.logger.info("Search cancelled")
        except Exception as e:
            self.logger.error(f"First Nominatim search error {e}")
        finally:
            self._finish_operation()

    @pyqtSlot(dict)
    def process_object(self, search_data: dict):
        """Process one initial search result through Overpass and export steps.

        A cancel() ends the processing silently: no export, and no
        object_processed signal that would make the GUI start the next one.

        Args:
            search_data (dict): Data returned by the initial Nominatim search.
        """
        self._busy = True
        try:
            self._process_object(search_data)
        except OperationCancelled:
            self.logger.info("Processing cancelled")
        finally:
            self._finish_operation()

    def _process_object(self, search_data: dict):
        """Do the work of process_object(); may raise OperationCancelled."""
        if self.app_data.search_mode == SearchMode.REQUESTS:
            # Overpass search
            try:
                overp_regions = self.crawler.overpass_full_search(search_data)
                self.object_processed.emit()
                return
            except Exception as e:
                self.logger.error(f"Overpass search error {e}")
                # self.return_to_initial_state_signal.emit()
                self.object_processed.emit()
                return
        else:
            try:
                overp_regions = self.crawler.overpass_short_search(search_data)
            except Exception as e:
                self.logger.error(f"Overpass search error {e}")
                # self.return_to_initial_state_signal.emit()
                self.object_processed.emit()
                return

        self.logger.debug(
            "Overpass result count: %s",
            len(overp_regions.relations()))

        # Second Nominatim search
        try:
            self.crawler.second_nominatim_search(overp_regions)
        except Exception as e:
            self.logger.error(f"Second Nominatim search error {e}")
            # self.return_to_initial_state_signal.emit()
            self.object_processed.emit()
            return

        # Export section
        if self.app_data.error_found == 0:
            # Excel export
            try:
                if self.app_data.export.export_to_excel and \
                        self.app_data.search.search_locations:
                    self.export_visuals_signal.emit([0, "Excel"])
                    self.crawler.save_excel(search_data["object_request"][0])
                    self.export_visuals_signal.emit([1, "Excel"])
            except Exception as e:
                self.logger.error(f"Excel export error {e}")

            # KML export
            try:
                if self.app_data.export.export_to_kml:
                    self.export_visuals_signal.emit([0, "KML"])
                    self.crawler.save_kml(search_data["object_request"][0])
                    self.export_visuals_signal.emit([1, "KML"])
            except Exception as e:
                self.logger.error(f"KML export error {e}")
        else:
            self.app_data.error_found = 0
        self.object_processed.emit()

    def finish_processing(self):
        """Finalize the processing workflow and reset the GUI state."""
        self.export_visuals_signal.emit([2, "KML"])  # ??
        self.return_to_initial_state_signal.emit()


if __name__ == "__main__":
    script_sequence("Riga")
    # nominatim = Nominatim()
    # osm_data = nominatim.query(
    #     "riga", params={'accept-language': 'ru', '2': 'riga'})
    # print(osm_data.toJSON())
