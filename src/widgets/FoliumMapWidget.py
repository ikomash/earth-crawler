import logging
import shutil
import tempfile
import weakref
from collections import deque
from pathlib import Path
from typing import Any, Optional

import folium
from folium.plugins import MarkerCluster
from PyQt6.QtCore import QUrl, pyqtSlot
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from utils import format_size


class MapWidget(QWidget):
    """Widget for rendering a Folium-based map inside Qt.

    add_point() and add_polygon() only collect the objects. The map page is
    built and shown by fit_to_results() (at the end of a search), clear() and
    refresh().

    Two problems of building the page after every added object:
        * It costs O(n^2): the whole page is rendered again for each of n
          objects, which froze the window for large searches.
        * QWebEngineView.setHtml() cannot show content larger than 2 MB. Once
          the page grew past that, new versions were silently not shown and
          the map kept an old, incomplete picture. The page is therefore
          written to a file and loaded from there, which has no such limit.

    Attributes:
        max_points (int): Most markers drawn on the map. A page with a marker
            per hamlet of a whole country would be too heavy for the browser.
            Further points are counted and mentioned in the log; KML and
            Excel exports are not affected.
        cluster_threshold (int): From this many markers on they are grouped
            into clusters, otherwise they are drawn one by one.
    """

    max_points = 20000
    cluster_threshold = 300

    def __init__(
            self,
            parent: Optional[QWidget] = None,
            location=(0, 0),
            zoom_start=0,
            tiles="OpenStreetMap",
            logger: Optional[logging.Logger] = None,
            **kwargs):
        """Initialize the map widget.

        Args:
            parent (Optional[QWidget], optional): Parent widget.
            location (tuple, optional): Initial map center coordinates.
            zoom_start (int, optional): Initial zoom level.
            tiles (str, optional): Tile provider name.
            logger (Optional[logging.Logger], optional): Receives the
                widget's messages. Defaults to the logger of this module.
            **kwargs: Additional keyword arguments forwarded to ``folium.Map``.
        """
        super().__init__(parent)
        self.logger = logger if logger is not None \
            else logging.getLogger(__name__)

        self.web_view = QWebEngineView()
        # the page is a local file that loads Leaflet and the tiles from the
        # internet
        self.web_view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_view)

        self._temp_dir = tempfile.mkdtemp(prefix="earth_crawler_map_")
        self._cleanup = weakref.finalize(
            self, shutil.rmtree, self._temp_dir, True)
        self._page_files: deque = deque()
        self._page_counter = 0

        self._polygons: list[tuple[list, str]] = []
        self._points: list[tuple[float, float, str]] = []
        self._dropped_points = 0
        self._bounds: Optional[tuple[float, float, float, float]] = None
        self._map_kwargs: dict = {}

        self.update_base_map_parameters(
            initial=True,
            refresh_map=True,
            location=location,
            zoom_start=zoom_start,
            tiles=tiles,
            **kwargs
        )

    def update_base_map_parameters(
            self,
            initial: bool = False,
            refresh_map: bool = True,
            location: Optional[tuple] = None,
            zoom_start: Optional[int] = None,
            tiles: Optional[str] = None,
            **kwargs):
        """Update base map settings and optionally recreate the map.

        Args:
            initial (bool, optional):
                Initialize stored defaults. Defaults to False.
            refresh_map (bool, optional):
                Drop all objects and show an empty map. Defaults to True.
            location (Optional[tuple], optional): Map center coordinates.
            zoom_start (Optional[int], optional): Initial zoom level.
            tiles (Optional[str], optional): Folium tile layer name.
            **kwargs: Additional keyword arguments forwarded to ``folium.Map``.
        """
        if initial:
            self.base_location = location if location else (0, 0)
            self.base_zoom = zoom_start if zoom_start else 1
            self.base_tiles = tiles if tiles else "OpenStreetMap"
        else:
            if location is not None:
                self.base_location = location
            if zoom_start is not None:
                self.base_zoom = zoom_start
            if tiles is not None:
                self.base_tiles = tiles
        if initial or kwargs:
            self._map_kwargs = kwargs

        if refresh_map:
            self._reset_objects()
            self._render()

    def _reset_objects(self):
        """Forget all collected objects."""
        self._polygons = []
        self._points = []
        self._dropped_points = 0
        self._bounds = None

    def _render(
            self,
            location: Any = None,
            zoom: Optional[int] = None,
            tiles: Optional[str] = None,
            fit: bool = False):
        """Build the Folium map from the collected objects and show it.

        Args:
            location (Any, optional): Map center. Defaults to the base one.
            zoom (Optional[int], optional): Zoom level. Defaults to the base.
            tiles (Optional[str], optional): Tile layer. Defaults to the base.
            fit (bool, optional): Zoom to all collected objects.
        """
        options = {"prefer_canvas": True, **self._map_kwargs}
        self.map = folium.Map(
            location=location if location is not None
            else self.base_location,
            zoom_start=zoom if zoom is not None else self.base_zoom,
            tiles=tiles if tiles is not None else self.base_tiles,
            **options
        )

        for coordinates, popup in self._polygons:
            folium.Polygon(locations=coordinates, popup=popup).add_to(self.map)

        if self._points:
            target = self.map
            if len(self._points) > self.cluster_threshold:
                target = MarkerCluster().add_to(self.map)
            for latitude, longitude, popup in self._points:
                folium.Marker(
                    [latitude, longitude], popup=popup).add_to(target)
        if self._dropped_points:
            self.logger.warning(
                f"The map shows the first {len(self._points)} of "
                f"{len(self._points) + self._dropped_points} points; the "
                "KML and Excel files contain all of them")

        if fit and self._bounds is not None:
            south, west, north, east = self._bounds
            self.map.fit_bounds(
                [[south, west], [north, east]],
                padding=(24, 24),
                max_zoom=12,
            )

        html = self.map.get_root().render()
        self._show_html(html)
        self.logger.info(
            f"Map page: {format_size(len(html))}, "
            f"{len(self._polygons)} polygons, {len(self._points)} points")

    def _show_html(self, html: str):
        """Show a page in the web view, loading it from a file.

        Every page gets its own file name, so the web view cannot mistake it
        for the page it already shows. Only the two newest files are kept.

        Args:
            html (str): The complete page.
        """
        self._page_counter += 1
        path = Path(self._temp_dir) / f"map_{self._page_counter}.html"
        path.write_text(html, encoding="utf-8")
        self._page_files.append(path)
        while len(self._page_files) > 2:
            self._page_files.popleft().unlink(missing_ok=True)
        self.web_view.load(QUrl.fromLocalFile(str(path)))

    def _extend_bounds(self, coordinates: list[tuple[float, float]]):
        """Expand the stored bounds to include the supplied coordinates."""
        if not coordinates:
            return

        latitudes = [coordinate[0] for coordinate in coordinates]
        longitudes = [coordinate[1] for coordinate in coordinates]
        south = min(latitudes)
        west = min(longitudes)
        north = max(latitudes)
        east = max(longitudes)

        if self._bounds is not None:
            old_south, old_west, old_north, old_east = self._bounds
            south = min(south, old_south)
            west = min(west, old_west)
            north = max(north, old_north)
            east = max(east, old_east)

        self._bounds = (south, west, north, east)

    def refresh(self):
        """Show the collected objects without changing the map view."""
        self._render()

    @pyqtSlot()
    def fit_to_results(self):
        """Show all collected objects and zoom to them.

        Call it when processing has completed: this builds the page, which
        takes a moment for a large result.
        """
        if self._bounds is None:
            return

        self._render(fit=True)

    @pyqtSlot(float, float, str)
    def add_point(self, latitude, longitude, popup=""):
        """Add a marker to the map. It appears after the next render.

        Args:
            latitude (float): Marker latitude.
            longitude (float): Marker longitude.
            popup (str, optional): Marker popup text. Defaults to an empty
                string.
        """
        if len(self._points) >= self.max_points:
            self._dropped_points += 1
            return
        self._points.append((latitude, longitude, popup))
        self._extend_bounds([(latitude, longitude)])

    @pyqtSlot(object, str)
    def add_polygon(self, coordinates, popup=""):
        """Add a polygon to the map. It appears after the next render.

        Args:
            coordinates (list): Polygon coordinates as latitude/longitude
                pairs.
            popup (str, optional): Polygon popup text. Defaults to an empty
                string.
        """
        self._polygons.append((coordinates, popup))
        self._extend_bounds(coordinates)

    @pyqtSlot()
    def clear(self):
        """Remove all objects from the map."""
        self._reset_objects()
        self._render(location=[0, 0], zoom=2, tiles="OpenStreetMap")
