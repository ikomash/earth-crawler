# General imports
import logging
import math
import os
import subprocess
import sys
from queue import Queue
from typing import Optional

# QT related imports
from PyQt6.QtCore import (
    QObject, QSize, Qt, QThread, QTimer, pyqtSignal, pyqtSlot)
from PyQt6.QtWidgets import (
    QMainWindow, QMenuBar, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QLineEdit, QProgressBar, QLabel, QComboBox, QSpinBox, QColorDialog,
    QSizePolicy, QGroupBox, QTabWidget, QListWidgetItem, QListWidget, QCheckBox
)
from PyQt6.QtGui import QCloseEvent, QColor, QIcon
from pyqtwaitingspinner import WaitingSpinner, SpinnerParameters

from info_window import InfoWindow
from osm_worker import OsmWorker
from logger import DEFAULT_LOGGER_NAME, LogSwitchebleWidget, Logger
from paths import Paths
from app_data import AppData, AppMode, ObjectsLanguage, SearchType
from minimap import MplMinimap
from settings_window import SettingsWindow
from widgets.FoliumMapWidget import MapWidget
from widgets.CheckableComboBoxWidget import CheckableComboBox
from utils import read_qss, UiUpdateBuffer, ValueSpec
from widgets.HelpDialogWidget import HelpDialog
from widgets.SearchResultsWidget import SearchResultsWidget
from widgets.LineWidgets import QVLine


class MainWidget(QWidget):
    """ Composes all elements together. """
    from_queue = pyqtSignal(object)
    second_search_signal = pyqtSignal(dict)

    def __init__(self, parent: Optional[QObject] = None):
        """Initialize the main widget.

        Args:
            parent (Optional): parent object for the widget.
        """
        super(MainWidget, self).__init__(parent)
        # Logger setup
        self.logger = logging.getLogger(DEFAULT_LOGGER_NAME)

        # AppData setup
        self.app_data = AppData(mode=AppMode.GUI)

        self.processing_available = False  # Flag for processing availability
        self._search_batch_active = False
        self.current_queue = Queue()
        self._map_has_results = False
        self._map_cleared_for_batch = False

        # The worker can send thousands of points and progress steps per
        # second. The slots only store them in this buffer, and the timer
        # applies them in short portions so the window keeps reacting.
        self._ui_buffer = UiUpdateBuffer()
        self._accept_updates = True  # False after Cancel, see the slots
        self._fit_map_when_drained = False
        self._map_stats = {"point": 0, "polygon": 0, "vertices": 0}
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(30)
        self._ui_timer.timeout.connect(self._flush_ui_updates)

        # Main Layout
        v_layout = QVBoxLayout()

        self.menu_bar = QMenuBar(self)

        file_menu = self.menu_bar.addMenu("&File")
        self.open_export_dir_action = file_menu.addAction(
            "Open export directory")
        self.open_export_dir_action.setIcon(QIcon(str(Paths.open_folder_icon)))
        self.open_export_dir_action.triggered.connect(
            self.open_export_directory)
        self.settings_action = file_menu.addAction("&Settings")
        self.settings_action.setIcon(QIcon(str(Paths.settings_icon_path)))
        self.settings_action.triggered.connect(self._settings_popup)

        help_menu = self.menu_bar.addMenu("&Help")
        self.info_action = help_menu.addAction("&Info")
        self.info_action.setIcon(QIcon(str(Paths.info_icon_path)))
        self.info_action.triggered.connect(self._info_popup)
        self.help_action = help_menu.addAction("&Help")
        self.help_action.setIcon(QIcon(str(Paths.help_icon_path)))
        self.help_action.triggered.connect(self._show_help)

        v_layout.setMenuBar(self.menu_bar)

        # Search config combobox
        self.search_type_combobox = QComboBox()
        search_types_list = SearchType.labels_list()
        for index, item in enumerate(search_types_list):
            self.search_type_combobox.addItem(item)
            self.search_type_combobox.setItemIcon(
                index,
                QIcon(str(Paths.icons_folder.joinpath(f"{item.lower()}.svg")))
            )

        self.search_type_combobox.currentIndexChanged.connect(
            lambda x: self.app_data.search.__setattr__(
                "search_type", SearchType(x)))
        # Region input line
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(
            "Country, region or their list separated by ;")
        self.line_edit.returnPressed.connect(self.return_pressed)
        # Region input acception button
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("searchButton")
        self._search_icon = QIcon(str(Paths.search_icon_path))
        self._processing_icon = QIcon(str(Paths.play_icon_path))
        self.search_button.setIcon(self._search_icon)
        self.search_button.clicked.connect(self.return_pressed)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        # HLayout for region input and it's button
        h_text_inp_layout = QHBoxLayout()
        h_text_inp_layout.addWidget(self.search_type_combobox)
        h_text_inp_layout.addWidget(self.line_edit)
        h_text_inp_layout.addWidget(self.search_button)
        h_text_inp_layout.addWidget(self.cancel_button)
        v_layout.addLayout(h_text_inp_layout)

        # Current object name label
        self.current_object_name_label = QLabel()
        v_layout.addWidget(self.current_object_name_label)

        # Top progress bar
        self.pr_bar_top = QProgressBar(self)
        self.pr_bar_top.setObjectName("GreenProgressBar")
        self.pr_bar_top.setValue(0)
        self.pr_bar_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_layout.addWidget(self.pr_bar_top)
        # bottom progress bar
        self.pr_bar_bottom = QProgressBar(self)
        self.pr_bar_bottom.setObjectName("GreenProgressBar")
        self.pr_bar_bottom.setValue(0)
        self.pr_bar_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_layout.addWidget(self.pr_bar_bottom)

        # Current processing status
        h_progress_indicator_layout = QHBoxLayout()
        spinner_params = SpinnerParameters(
            90.0,
            70.0,
            12,
            6,
            1,
            2,
            math.pi / 2,
            None,
            math.pi,
            center_on_parent=False,
            disable_parent_when_spinning=False)  # QColor(81, 4, 71)
        self.spinner = WaitingSpinner(self, spinner_params)  # False, False

        self.current_sub_object_name_label = QLabel()
        h_progress_indicator_layout.addWidget(self.spinner)
        h_progress_indicator_layout.addWidget(
            self.current_sub_object_name_label)
        v_layout.addLayout(h_progress_indicator_layout)
        # Objects settings tab layout
        obj_settings_v_layoyt = QVBoxLayout()

        self.choose_from_results_checkbox = QCheckBox("Choose from results")
        self.choose_from_results_checkbox.setToolTip(
            "If enabled, the application will allow you to choose from the "
            "search results instead of processing the first found object."
        )
        self.choose_from_results_checkbox.setChecked(True)
        obj_settings_v_layoyt.addWidget(self.choose_from_results_checkbox)

        # Combobox locations search
        self.search_locations_groupbox = QGroupBox("Search locations")
        locations_search_groupbox_v_layout = QVBoxLayout()
        self.search_locations_groupbox.setLayout(
            locations_search_groupbox_v_layout)
        self.search_locations_groupbox.setCheckable(True)
        self.search_locations_groupbox.setChecked(
            self.app_data.search.search_locations)
        self.search_locations_groupbox.clicked.connect(
            lambda state: self.app_data.search.__setattr__(
                "search_locations", state))
        self.points_search_list_combobox = CheckableComboBox()
        self.points_search_list_combobox.addItems(
            self.app_data.search.search_places_list,
            check_list=self.app_data.search.search_places_choice
        )
        locations_search_groupbox_v_layout.addWidget(
            self.points_search_list_combobox)
        obj_settings_v_layoyt.addWidget(self.search_locations_groupbox)

        # Search borders
        self.search_borders_groupbox = QGroupBox("Search borders")
        search_borders_groupbox_v_layout = QVBoxLayout()
        self.search_borders_groupbox.setLayout(
            search_borders_groupbox_v_layout)
        self.search_borders_groupbox.setCheckable(True)
        self.search_borders_groupbox.setChecked(
            self.app_data.search.search_borders)
        self.search_borders_groupbox.clicked.connect(
            lambda state: self.app_data.search.__setattr__(
                "search_borders", state))
        # Checkbox transforming polygons into lines
        self.checkbox_polygons_to_lines = QCheckBox(
            "Draw lines instead of polygons")
        self.checkbox_polygons_to_lines.setChecked(
            self.app_data.kml.polygons_to_lines)
        self.checkbox_polygons_to_lines.stateChanged.connect(
            lambda state: self.app_data.kml.__setattr__(
                "polygons_to_lines", state)
        )

        # Line width
        h_line_width_and_color_layout = QHBoxLayout()

        self.line_width_label = QLabel()
        self.line_width_label.setText("Line width:")
        self.line_width_spin_box = QSpinBox()
        self.line_width_spin_box.setValue(self.app_data.kml.line_width)
        self.line_width_spin_box.valueChanged.connect(
            lambda val: self.app_data.kml.__setattr__("line_width", val))
        h_line_width_layout = QHBoxLayout()
        h_line_width_layout.addWidget(self.line_width_label)
        h_line_width_layout.addWidget(self.line_width_spin_box)
        h_line_width_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        h_line_width_and_color_layout.addLayout(h_line_width_layout)

        h_line_width_and_color_layout.addWidget(QVLine())

        # Color picker
        self.line_color_label = QLabel()
        self.line_color_label.setText("Line color:")
        self.color_picker_button = QPushButton()
        self.color_picker_button.setIcon(
            QIcon(str(Paths.color_picker_icon_path)))
        self.color_picker_button.setStyleSheet("border: 0px")
        # Fixing color picker button size
        sizePolicy = QSizePolicy()
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        self.color_picker_button.setSizePolicy(sizePolicy)
        self.color_picker_button.clicked.connect(self.pick_line_color)

        self.line_current_color = QWidget()
        self.line_current_color.setFixedSize(30, 20)
        self.line_current_color.setStyleSheet(
            f"background-color:{self.app_data.kml.line_color}; "
            "border: 1px solid black"
        )

        h_line_color_layout = QHBoxLayout()
        h_line_color_layout.addWidget(self.line_color_label)
        h_line_color_layout.addWidget(self.line_current_color)
        h_line_color_layout.addWidget(self.color_picker_button)
        h_line_color_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        h_line_width_and_color_layout.addLayout(h_line_color_layout)
        h_line_width_and_color_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        search_borders_groupbox_v_layout.addWidget(
            self.checkbox_polygons_to_lines)
        search_borders_groupbox_v_layout.addLayout(
            h_line_width_and_color_layout)
        obj_settings_v_layoyt.addWidget(self.search_borders_groupbox)

        # Exports section
        h_exports_layout = QHBoxLayout()
        export_to_label = QLabel("Export to:")
        self.checkbox_export_to_kml = QCheckBox("KML")
        self.checkbox_export_to_kml.setChecked(
            self.app_data.export.export_to_kml)
        self.checkbox_export_to_kml.stateChanged.connect(
            lambda x: self.app_data.export.__setattr__("export_to_kml", x))
        self.checkbox_export_to_excel = QCheckBox("Excel")
        self.checkbox_export_to_excel.setChecked(
            self.app_data.export.export_to_excel)
        self.checkbox_export_to_excel.stateChanged.connect(
            lambda x: self.app_data.export.__setattr__("export_to_excel", x))
        h_exports_layout.addWidget(export_to_label)
        h_exports_layout.addWidget(self.checkbox_export_to_kml)
        h_exports_layout.addWidget(self.checkbox_export_to_excel, 1)
        obj_settings_v_layoyt.addLayout(h_exports_layout)

        # Combobox object language chooser with label
        self.obj_lang_combobox_label = QLabel()
        self.obj_lang_combobox_label.setText("Choose objects language:")
        self.obj_lang_combobox = QComboBox()

        languages = list(ObjectsLanguage)  # same order as the combobox
        for index, lang in enumerate(languages):
            self.obj_lang_combobox.addItem(lang.name_text)
            self.obj_lang_combobox.setItemIcon(
                index, QIcon(str(Paths.flags_folder.joinpath(
                    f"{lang.country}.svg")))
            )
            if lang.value == self.app_data.search.objects_language:
                self.obj_lang_combobox.setCurrentIndex(index)
        # Store the plain code ('ru'). str(ObjectsLanguage.RU) would be
        # 'ObjectsLanguage.RU', which breaks the OSM name tags and Nominatim.
        self.obj_lang_combobox.currentIndexChanged.connect(
            lambda x: self.app_data.search.__setattr__(
                "objects_language", languages[x].value))

        # HLayout for object language combobox and it's label
        h_obj_lang_combobox_layout = QHBoxLayout()
        h_obj_lang_combobox_layout.addWidget(self.obj_lang_combobox_label)
        h_obj_lang_combobox_layout.addWidget(self.obj_lang_combobox, 2)
        h_obj_lang_combobox_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        obj_settings_v_layoyt.addLayout(h_obj_lang_combobox_layout)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabBar().setExpanding(True)
        export_settings_tab = QWidget()
        export_settings_tab.setLayout(obj_settings_v_layoyt)
        export_settings_icon = QIcon(str(Paths.settings_icon_path))
        self.tab_widget.addTab(
            export_settings_tab, export_settings_icon, "Search settings")
        self.search_list_widget = QListWidget()
        search_results_icon = QIcon(str(Paths.list_icon_path))
        self.tab_widget.addTab(
            self.search_list_widget, search_results_icon, "Search results")
        self.log_widget = LogSwitchebleWidget(
            self, DEFAULT_LOGGER_NAME, True)
        log_icon = QIcon(str(Paths.info_light_icon_path))
        self.tab_widget.addTab(self.log_widget, log_icon, "Log")
        self.map_widget = MapWidget(self, logger=self.logger)
        map_icon = QIcon(str(Paths.map_location_pin_icon_path))
        self.tab_widget.addTab(self.map_widget, map_icon, "Map")
        v_layout.addWidget(self.tab_widget)

        # Worker thread setup
        self.osm_thread = QThread(self)
        self.osm_thread.setObjectName("OsmWorkerThread")
        self.osm_worker = OsmWorker(self.app_data)
        self.osm_worker.moveToThread(self.osm_thread)
        self.osm_thread.finished.connect(self.osm_worker.deleteLater)
        self.osm_thread.finished.connect(self.osm_thread.deleteLater)

        # Signals connection
        self.osm_worker.sub_obj_signal.connect(
            self.bottom_progress_bar_update)
        # A bound slot of this widget runs in the GUI thread. A lambda would
        # run in the worker thread, which must not touch widgets.
        self.osm_worker.total_sub_obj_signal.connect(
            self.bottom_progress_bar_set_total)
        self.osm_worker.update_results.connect(
            self.process_search_results)
        self.osm_worker.export_visuals_signal.connect(self.export_visuals)
        self.osm_worker.status_signal.connect(self.status_update)
        self.osm_worker.return_to_initial_state_signal.connect(
            self.worker_return_to_initial_state)
        self.cancel_button.clicked.connect(self.cancel_button_pressed)
        self.from_queue.connect(self.osm_worker.search_objects)
        self.second_search_signal.connect(self.osm_worker.process_object)
        self.osm_worker.object_processed.connect(self.check_queue)

        self.osm_worker.add_point.connect(self.add_point_to_map)
        self.osm_worker.add_polygon.connect(self.add_polygon_to_map)

        self.osm_thread.start()

        self.setLayout(v_layout)

    def _settings_popup(self):
        """Open the settings dialog."""
        self.settings_window = SettingsWindow(self.app_data, self)
        self.settings_window.show()

    def _info_popup(self):
        """Show the information window."""
        self.info_window = InfoWindow(self)
        self.info_window.show()

    def _show_help(self):
        """Show the help dialog."""
        help_dialog = HelpDialog(Paths.help_path, Paths.assets_folder, self)
        help_dialog.show()

    def open_export_directory(self):
        """Open the export folder in the system file manager."""
        export_dir = Paths.export_folder
        export_dir.mkdir(parents=True, exist_ok=True)

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(export_dir))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(export_dir)], check=False)
            else:
                subprocess.run(["xdg-open", str(export_dir)], check=False)
        except Exception as exc:
            self.logger.exception(f"Unable to open export directory: {exc}")

    def closeEvent(self, event):
        """Stop the worker thread before closing the widget."""
        self._ui_timer.stop()
        if hasattr(self, "osm_thread") and self.osm_thread.isRunning():
            self.cancel_button_pressed()
            self.osm_thread.quit()
            if not self.osm_thread.wait(500):
                self.logger.warning(
                    "OsmWorkerThread did not stop in time; terminating it."
                )
                self.osm_thread.terminate()
                self.osm_thread.wait()
        super().closeEvent(event)

    # Progress bar updates
    @pyqtSlot(int)
    def top_progress_bar_update(self, index: int):
        """Update the top progress bar for the current object stage.

        Args:
            index (int): Current stage index.
        """
        i = int(index)
        if i == 0:
            self.pr_bar_top.setFormat("%v/%m (%p %)")
        self.pr_bar_top.setValue(i)

    def _kick_ui_timer(self):
        """Make sure the timer that applies buffered updates is running."""
        if not self._ui_timer.isActive():
            self._ui_timer.start()

    def _flush_ui_updates(self):
        """Apply buffered updates: newest values first, then some map items.

        Runs from the timer. Every call is short, so between two calls the
        event loop can handle clicks and repaint the window.
        """
        values = self._ui_buffer.pop_values()
        if "bar" in values:
            self._apply_bottom_progress(values["bar"])
        if "label" in values:
            self.current_sub_object_name_label.setText(values["label"])
        drained = self._ui_buffer.drain(self._apply_map_item)
        if drained and not self._ui_buffer.has_work():
            self._ui_timer.stop()
            if self._fit_map_when_drained:
                self._fit_map_now()

    def _apply_bottom_progress(self, value: int):
        """Show a progress value in the bottom bar.

        Args:
            value (int): Number of finished sub-objects.
        """
        if value > self.pr_bar_bottom.maximum():
            # No total was announced (e.g. the older search flow). Grow the
            # range: QProgressBar silently ignores values beyond its maximum.
            self.pr_bar_bottom.setMaximum(value)
        if not self.pr_bar_bottom.format():
            self.pr_bar_bottom.setFormat("%v/%m (%p %)")
        self.pr_bar_bottom.setValue(value)

    def _apply_map_item(self, item: tuple):
        """Draw one buffered map item.

        Args:
            item (tuple): ('point', lat, lon, popup) or
                ('polygon', coordinates, popup).
        """
        kind, *args = item
        try:
            if kind == "point":
                self.map_widget.add_point(*args)
            else:
                self.map_widget.add_polygon(*args)
                self._map_stats["vertices"] += len(args[0])
        except Exception:
            # one bad item must not stop the rest of the queue
            self.logger.exception(
                f"The map widget failed to draw a {kind}: {args[-1]!r}")
            return
        self._map_stats[kind] += 1

    def _fit_map_now(self):
        """Zoom the map to everything that was drawn."""
        self._fit_map_when_drained = False
        stats = self._map_stats
        self.logger.info(
            f"Handed to the map widget: {stats['polygon']} polygons "
            f"({stats['vertices']} vertices), {stats['point']} points")
        if self._map_has_results:
            self.map_widget.fit_to_results()

    def _reset_bottom_progress(self):
        """Empty the bottom bar until the next object's total is known.

        The range is 0..1, never 0..0: a QProgressBar with an empty range
        shows an endless "busy" animation without any numbers.
        """
        self._ui_buffer.discard_value("bar")
        self.pr_bar_bottom.setRange(0, 1)
        self.pr_bar_bottom.setValue(0)
        self.pr_bar_bottom.setFormat("")

    @pyqtSlot(int)
    def bottom_progress_bar_set_total(self, total: int):
        """Set up the bottom bar for the announced number of sub-objects.

        Args:
            total (int): Number of borders and locations about to be
                processed. Zero means nothing was found (or the server
                requests failed).
        """
        self._ui_buffer.discard_value("bar")
        if total > 0:
            self.pr_bar_bottom.setRange(0, total)
            self.pr_bar_bottom.setValue(0)
            self.pr_bar_bottom.setFormat("%v/%m (%p %)")
        else:
            # setMaximum(0) would start the endless "busy" animation
            self.pr_bar_bottom.setRange(0, 1)
            self.pr_bar_bottom.setValue(0)
            self.pr_bar_bottom.setFormat("0/0")

    @pyqtSlot(int, str)
    def bottom_progress_bar_update(self, index: int, object_name: str):
        """Update the bottom progress bar and label for the current sub-object.

        Args:
            index (int): Current sub-object stage index.
            object_name (str): Name of the current sub-object.
        """
        if not self._accept_updates:
            return
        self._ui_buffer.set_value("bar", int(index) + 1)
        self._ui_buffer.set_value("label", object_name)
        self._kick_ui_timer()

    @pyqtSlot(list)
    def export_visuals(self, event: list):
        """Update the UI message from an export-state signal payload.

        Args:
            event (list): Two-item payload containing the state code and
                export format, for example `[0, "KML"]`.
        """
        state, export_type = event
        if state == 0:
            self._ui_buffer.set_value("label", f"Saving {export_type} file")
            self._kick_ui_timer()
        if state == 1:
            self._ui_buffer.set_value("label", f"{export_type} file saved")
            self._kick_ui_timer()
        if state == 2:
            self.spinner.stop()
            self.search_button.setEnabled(True)

    def clear_queue(self):
        """Clear the queued search requests."""
        with self.current_queue.mutex:
            self.current_queue.queue.clear()

    @pyqtSlot(str)
    def status_update(self, text: str):
        """Show a status text of the worker, for example a retry notice.

        The text is replaced as soon as the progress of the next sub-object
        or export message arrives.

        Args:
            text (str): Short status text.
        """
        if not self._accept_updates:
            return
        self._ui_buffer.set_value("label", text)
        self._kick_ui_timer()

    def change_processing_button(self):
        """Switch the search button between search and process modes and icons.
        """
        if self.processing_available:
            self.search_button.setText("Process")
            self.search_button.setIcon(self._processing_icon)
        else:
            self.search_button.setText("Search")
            self.search_button.setIcon(self._search_icon)

    @pyqtSlot(float, float, str)
    def add_point_to_map(self, latitude: float, longitude: float, popup: str):
        """Queue a point for the map and record that this search found data.

        The point is drawn a little later by the timer, see _ui_buffer.
        """
        if not self._accept_updates:
            return
        self._ui_buffer.add_item(("point", latitude, longitude, popup))
        self._map_has_results = True
        self._kick_ui_timer()

    @pyqtSlot(object, str)
    def add_polygon_to_map(self, coordinates: list, popup: str):
        """Queue a polygon for the map and record that this search found data.

        The polygon is drawn a little later by the timer, see _ui_buffer.
        """
        if not self._accept_updates:
            return
        self._ui_buffer.add_item(("polygon", coordinates, popup))
        self._map_has_results = True
        self._kick_ui_timer()

    def multiple_search(self, search_line: str):
        """Split a search request into individual items and enqueue them.

        Args:
            search_line (str): Search request containing one or more objects.
        """
        try:
            search_list = ValueSpec.search_line_processing(search_line)
        except ValueError as e:
            self.logger.error(
                f"Error processing search line - wrong format: {e}")
            self.tab_widget.setCurrentIndex(2)  # switch to log tab
            return False

        self.pr_bar_top.setMaximum(len(search_list))
        self.top_progress_bar_update(0)
        for single_obj_req in search_list:
            self.current_queue.put(single_obj_req)
        return True

    def first_search(self):
        """Run the first search stage for the next queued object."""
        if self.current_queue.empty():
            return

        self.search_list_widget.clear()
        single_obj_req = self.current_queue.get_nowait()
        self.current_object_name_label.setText(single_obj_req.name)
        self.from_queue.emit(single_obj_req)
        self.cancel_button.setEnabled(True)
        self._ui_buffer.discard_value("label")
        self.current_sub_object_name_label.setText("")
        self.spinner.start()

    def second_search(self):
        """
        Start a search using the item selected from the result list.
        The selected object is sent to the worker for processing.
        """
        current_row = self.search_list_widget.currentRow()

        # If nothing is selected
        if current_row < 0:
            self.logger.warning(f"No search result selected: {current_row}")
            return

        self.logger.info(f"Search result choosen: {current_row}")
        current_data: dict = self.search_list_widget.currentItem().data(
            Qt.ItemDataRole.UserRole)
        if not self._map_cleared_for_batch:
            self._ui_buffer.clear_items()
            self._map_stats = {"point": 0, "polygon": 0, "vertices": 0}
            self.map_widget.clear()
            self._map_cleared_for_batch = True
        self._reset_bottom_progress()
        self.second_search_signal.emit(current_data)
        self.processing_available = False
        self.change_processing_button()       # update to "Search"
        self.search_button.setEnabled(False)  # block until completion
        self.tab_widget.setCurrentIndex(2)  # switch to log tab
        self.spinner.start()
        self.cancel_button.setEnabled(True)

    def check_queue(self):
        """
        Continue or finish processing based on the current work queue.
        Emits the next queue item or finalizes the workflow when the queue is
        empty.
        """
        if not self._search_batch_active:
            return

        if self.current_queue.empty():
            # The entire queue is completed, return to the result selection
            self._search_batch_active = False
            self._fit_map_when_drained = True
            if not self._ui_buffer.has_items():
                self._fit_map_now()
            self.tab_widget.setCurrentWidget(
                self.map_widget if self._map_has_results else self.log_widget)
            self.processing_available = False
            self.change_processing_button()
            self.spinner.stop()
            self.cancel_button.setEnabled(False)
            self.search_button.setEnabled(True)
            # Signal to indicate that the processing of all objects is complete
            self.osm_worker.finish.emit()
        else:
            self.first_search()
        self.top_progress_bar_update(self.pr_bar_top.value() + 1)

    def return_pressed(self):
        """
        Handle the search action triggered by the user input or button.
        Runs the first or second search flow depending on the current state.
        """
        self.logger.debug("Return pressed!")
        if self.processing_available:
            self.second_search()
            return

        if self._search_batch_active:
            return

        search_line = self.line_edit.text().strip()
        if not search_line:
            return

        self._map_has_results = False
        self._map_cleared_for_batch = False
        self._fit_map_when_drained = False
        self._accept_updates = True
        self.logger.info(
            "Starting search. Search type: "
            f"{SearchType(self.app_data.search.search_type).name}; "
            f"Search line: {search_line}"
        )
        self.logger.debug(
            "Points search list: "
            f"{self.points_search_list_combobox.currentData()}"
        )
        self.logger.debug(
            "Groupboxes: "
            f"{[self.app_data.search.search_borders,
                self.app_data.search.search_locations]}"
        )
        self.search_list_widget.clear()
        if not self.multiple_search(search_line):
            return

        self._search_batch_active = True
        self.first_search()

    def cancel_button_pressed(self):
        """
        Stop the active search or processing workflow.
        Resets the UI state and disables the processing controls.
        """
        self.clear_queue()
        self._search_batch_active = False
        # Direct call on purpose: the worker thread is busy inside a running
        # slot, so a queued signal would only arrive after that slot ended.
        self.osm_worker.cancel()
        # signals the worker sent before it noticed the cancel may still be
        # on their way here, they belong to the cancelled search
        self._accept_updates = False
        self._ui_timer.stop()
        self._ui_buffer.clear()
        self._fit_map_when_drained = False
        self._reset_processing_controls()
        self._reset_bottom_progress()
        self.current_sub_object_name_label.setText("Cancelled")

    def worker_return_to_initial_state(self):
        """Reset processing controls without cancelling queued searches."""
        self._reset_processing_controls()

    def _reset_processing_controls(self):
        self.search_list_widget.clear()
        self.processing_available = False
        self.change_processing_button()
        self.spinner.stop()
        self.cancel_button.setEnabled(False)
        self.search_button.setEnabled(True)
        self.current_object_name_label.setText("")
        # self.pr_bar_top.reset()
        # self.pr_bar_bottom.reset()

    def pick_line_color(self):
        """Open a color dialog to select the line color."""
        col_dialog = QColorDialog(QColor(self.app_data.kml.line_color))
        col = col_dialog.getColor(QColor(self.app_data.kml.line_color))
        if col.isValid():
            self.app_data.kml.line_color = col.name()
            self.line_current_color.setStyleSheet(
                f"background-color:{self.app_data.kml.line_color}; "
                f"border: 1px solid black")

    def update_search_results(self, search_data: list):
        """Populate the search results list with discovered objects.

        Args:
            search_data (list): List of search results returned by the worker.
        """
        MMap = MplMinimap()
        for i, res in enumerate(search_data):
            # Add point to minimap
            MMap.set_point(float(res['lat']), float(res['lon']), i)

            # Add new item to search results list widget
            item = QListWidgetItem()
            item_widget = SearchResultsWidget(res, i)
            item.setData(Qt.ItemDataRole.UserRole, res)
            item.setSizeHint(QSize(350, 150))  # item_widget.sizeHint()
            self.search_list_widget.addItem(item)
            self.search_list_widget.setItemWidget(item, item_widget)

    @pyqtSlot(list)
    def process_search_results(self, search_data: list):
        """Process the result payload from the search worker.

        Args:
            search_data (list): List of Nominatim search results.
        """
        if not self._search_batch_active:
            return

        self.update_search_results(search_data)

        if len(search_data) > 0:
            self.processing_available = True
            if not self.choose_from_results_checkbox.isChecked():
                self.search_list_widget.setCurrentRow(0)
                self.search_list_widget.setDisabled(True)
                self.second_search()
                self.search_list_widget.setDisabled(False)
            else:
                self.tab_widget.setCurrentIndex(1)
                self.change_processing_button()
        else:
            self.logger.info("No search results found for the current request")
            self.check_queue()


class MainWindow(QMainWindow):
    """Main window of the application. Contains MainWidget and toolbar."""

    def __init__(self):
        """Initialize the main application window."""
        super(QMainWindow, self).__init__()
        self.setWindowTitle("Earth Crawler")
        self.setMinimumSize(QSize(500, 400))
        self.setWindowIcon(QIcon(str(Paths.app_icon_path)))
        self.setStyleSheet(read_qss(Paths.stylesheet_path))

        # Logger setup
        self.logger = Logger(DEFAULT_LOGGER_NAME, Paths.log_file_path).logger

        # Load configuration
        # self._config = Config(Paths.config_path)

        left_spacer = QWidget()
        left_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.main_widget = MainWidget()
        self.setCentralWidget(self.main_widget)

        self.show()

    def closeEvent(self, event: QCloseEvent):
        """Handle the window close event.

        Args:
            event (QCloseEvent): Close event emitted when the window is closed.
        """
        self.main_widget.close()
        super().closeEvent(event)


if __name__ == "__main__":
    pass
