# QT related imports
from PyQt6.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton,\
     QVBoxLayout, QHBoxLayout, QWidget, QCheckBox, QLineEdit, QProgressBar,\
     QLabel, QComboBox, QSpinBox, QColorDialog, QSizePolicy, QFrame,\
     QGroupBox, QToolBar, QTabWidget, QListWidgetItem, QListWidget
from PyQt6.QtGui import QColor, QIcon, QPixmap, QAction, QImage
from widgets.CheckableComboBoxWidget import CheckableComboBox
from waitingspinnerwidget import QtWaitingSpinner
import webbrowser

# Python related imports
import sys
import os
import time
import requests
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt

from typing import Union
from earth_crawler import EarthCrawler
from tempdata import TempData

# Hack for taskbar icon work
try:
    from ctypes import windll  # Only exists on Windows.
    myappid = 'com.demonkik.earthcrawler.1.0'
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass


def pause():  # ! remove
    os.system('pause')


class PB_Thread(QThread):
    """Creates thread to work with OSM APIs.
    """
    # Initializing signals
    _PB_Thread_obj_signal = pyqtSignal(int)
    _PB_Thread_sub_obj_signal = pyqtSignal(int)
    json_update_signal = pyqtSignal(int)
    export_visuals_signal = pyqtSignal(list)
    processing_stages_signal = pyqtSignal(int)
    return_to_initial_state_signal = pyqtSignal()

    def __init__(self, OsmWorker: EarthCrawler, Tmp: TempData) -> None:
        """Accepts required class instances.

        Args:
            OsmWorker (EarthCrawler): OSM worker class instance
            Tmp (TempData): Operative data and settings storage instance
        """
        super(PB_Thread, self).__init__()
        self.OsmWorker = OsmWorker
        self.Tmp = Tmp

    def __del__(self):
        self.wait()

    def run(self) -> None:
        """Runs OSM search functions.
        """
        search_list = self.OsmWorker.search_line_proccessing()
        self.Tmp.obj_number = len(search_list)

        for i, single_obj_req in enumerate(search_list):
            # self.Tmp.current_obj = i
            # First Nominatim search
            try:
                osm_area_id = self.OsmWorker.first_nominatim_search(
                    single_obj_req)
                if self.Tmp.choose_from_results:
                    self.Tmp.process_paused = True
                    print(self.Tmp.current_search_json)
                    self.json_update_signal.emit(0)
                    while self.Tmp.process_paused:
                        time.sleep(0)
                    osm_area_id = self.Tmp.current_search_json[
                        self.Tmp.current_search_chosen_index]["nominatim_id"]
                    self.Tmp.current_obj_name = self.Tmp.current_search_json[
                        self.Tmp.current_search_chosen_index]["display_name"]
                else:
                    self.Tmp.current_obj_name = self.Tmp.current_search_json[
                        0]["display_name"]
                # moved lower for object name display
                self.Tmp.processing_choises_num = [
                    self.Tmp.search_borders,
                    self.Tmp.search_locations].count(True)
                self._PB_Thread_obj_signal.emit(i)
            except Exception:
                self.Tmp.logger_object.error("First Nominatim search error")
                self.Tmp.logger_object.exception("Exception")

            # Overpass search
            try:
                overp_regions = self.OsmWorker.overpass_search(
                    osm_area_id, single_obj_req)
            except Exception:
                self.Tmp.logger_object.error("Overpass search error")
                self.Tmp.logger_object.exception("Exception")
                # self.return_to_initial_state_signal.emit()
                continue

            # Second Nominatim search
            try:
                self.OsmWorker.second_nominatim_search(overp_regions)
            except Exception:
                self.Tmp.logger_object.error("Second Nominatim search error")
                self.Tmp.logger_object.exception("Exception")
                # self.return_to_initial_state_signal.emit()
                continue

            # Export section
            if self.Tmp.error_found == 0:
                # Excel export
                try:
                    if self.Tmp.export_to_excel and self.Tmp.search_locations:
                        self.export_visuals_signal.emit([0, "Excel"])
                        self.OsmWorker.save_excel(single_obj_req[0])
                        self.export_visuals_signal.emit([1, "Excel"])
                except Exception:
                    self.Tmp.logger_object.error("Excel export error")
                    self.Tmp.logger_object.exception("Exception")

                # KML export
                try:
                    if self.Tmp.export_to_kml:
                        self.export_visuals_signal.emit([0, "KML"])
                        self.OsmWorker.save_kml(single_obj_req[0])
                        self.export_visuals_signal.emit([1, "KML"])
                except Exception:
                    self.Tmp.logger_object.error("KML export error")
                    self.Tmp.logger_object.exception("Exception")
            else:
                self.Tmp.error_found = 0
        self.export_visuals_signal.emit([2, "KML"])  # ??
        self.return_to_initial_state_signal.emit()


class SearchResultWidget(QWidget):
    """Widget showing first OSM search results.
    """
    def __init__(self, data: dict, index: int,
                 parent: Union[QWidget, None] = None) -> None:
        """
        Args:
            data (dict): Single row data dictionary
            index (int): List widget row number
            parent (Union[QWidget, None], optional):
                QT related, parent object. Defaults to None.
        """
        super(SearchResultWidget, self).__init__(parent)
        h_layout = QHBoxLayout()
        sub_v_layout = QVBoxLayout()
        print(data)
        # js['place_id'], js['osm_type'], js['lat'], js['lon'],
        # js['display_name'], js['class'], js['type'], js['icon']
        name_label = QLabel(f"Name: {data['display_name']}")
        name_label.setWordWrap(True)
        sub_v_layout.addWidget(name_label)

        types_label = QLabel(
            f"Nominatim ID: {data['nominatim_id']}, "
            f"OSM type: {data['osm_type']}, "
            f"Class: {data['class']}, "
            f"Type: {data['type']}"
            )
        types_label.setWordWrap(True)
        sub_v_layout.addWidget(types_label)

        image = QImage()
        icon = QLabel()
        if 'icon' in data.keys():
            image.loadFromData(requests.get(data['icon']).content)
            icon.setPixmap(QPixmap(image))
        else:
            icon.setPixmap(QIcon(
                ".//Images//icons//fill_circle.svg").pixmap(24, 24))
        h_layout.addWidget(icon)

        map_v_layout = QVBoxLayout()
        map_icon = QLabel()
        map_icon.setPixmap(
            QIcon(f'.//tmp//minimap_{index}.png').pixmap(150, 150))
        lat_label = QLabel(f"Lat: {data['lat']}")
        lat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # lat_label.setWordWrap(True)
        lon_label = QLabel(f"Lon: {data['lon']}")
        lon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # lon_label.setWordWrap(True)
        map_v_layout.addWidget(map_icon)
        map_v_layout.addWidget(lat_label)
        map_v_layout.addWidget(lon_label)

        sub_v_layout.setSpacing(0)
        sub_v_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addLayout(sub_v_layout, 4)
        h_layout.addLayout(map_v_layout, 0)
        self.setLayout(h_layout)


class MplMinimap():
    """Creates minimap image.
    """
    def __init__(self) -> None:
        """Creates Matplotlib basemap.
        """
        # create new figure, axes instances.
        fig = plt.figure(figsize=(1, 1), frameon=False)
        self.ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
        for facet in ['top', 'bottom', 'left', 'right']:
            self.ax.spines[facet].set_linewidth(0.3)
        # setup mercator map projection.
        self.m = Basemap()
        self.m.drawcoastlines(linewidth=0.3)
        self.m.fillcontinents()
        self.sc = None

    def set_point(self, lat: float, lon: float, index: int) -> None:
        """Adds point to created basemap

        Args:
            lat (float): Point latitude
            lon (float): Point longitude
            index (int): List widget row number
        """
        if self.sc is not None:
            self.sc.remove()
        self.sc = self.m.scatter(
            lon, lat, marker='o', c='r', edgecolors="b",
            linewidths=0.5, s=6, zorder=5
            )
        plt.savefig(f'.//tmp//minimap_{index}.png', dpi=200)


class QHLine(QFrame):
    """Horizontal separation line.
    """
    def __init__(self) -> None:
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)


class QVLine(QFrame):
    """Vertical separation line.
    """
    def __init__(self):
        super(QVLine, self).__init__()
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)


# Style sheet for progress bar
StyleSheet = '''
            #GreenProgressBar {
                min-height: 15px;
                max-height: 15px;
                border-radius: 6px;
                text-align: center;
            }
            #GreenProgressBar::chunk {
                border-radius: 2px;
                background-color: #009688;
            }
            '''


class MainWindow(QMainWindow):
    """Composes all elements together
    """
    def __init__(self) -> None:
        """Creates GUI main elements
        """
        super().__init__()
        self.Tmp = TempData(mode="gui")
        # Main window setup
        self.setWindowTitle("Earth Crawler")
        # self.setFixedSize(QSize(450, 350))
        # self.setMaximumSize(QSize(600, 500))
        self.setMinimumSize(QSize(500, 400))

        # Toolbar setup
        left_spacer = QWidget()
        left_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(12, 12))
        toolbar.setMovable(False)
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        nom_act = QAction(QIcon(
            ".\\images\\Icons\\links.svg"),
            "Administrative levels", self
            )
        nom_act.triggered.connect(
            lambda: webbrowser.open(  # type: ignore
                'https://wiki.openstreetmap.org/wiki/Tag:boundary%'
                '3Dadministrative#admin_level=*_Country_specific_values'
                )
            )
        nom_act.setStatusTip(
            "Open Administrative levels table wiki page in browser")
        toolbar.addAction(nom_act)
        toolbar.addWidget(left_spacer)
        nom_act = QAction(
            QIcon(".\\images\\Icons\\links.svg"), "Nominatim", self)
        nom_act.triggered.connect(
            lambda: webbrowser.open(  # type: ignore
                'https://nominatim.openstreetmap.org/'))
        nom_act.setStatusTip("Open Nominatim page in browser")
        toolbar.addAction(nom_act)
        nom_act = QAction(
            QIcon(".\\images\\Icons\\links.svg"), "Overpass", self)
        nom_act.triggered.connect(
            lambda: webbrowser.open(  # type: ignore
                'https://overpass-turbo.eu/'))
        nom_act.setStatusTip("Open Overpass page in browser")
        toolbar.addAction(nom_act)
        nom_act = QAction(QIcon(".\\images\\Icons\\links.svg"), "OSM", self)
        nom_act.triggered.connect(
            lambda: webbrowser.open(  # type: ignore
                'https://www.openstreetmap.org/'))
        nom_act.setStatusTip("Open OSM page in browser")
        toolbar.addAction(nom_act)
        self.addToolBar(toolbar)

        # Main Layout
        v_layout = QVBoxLayout()

        # Search config combobox
        self.search_type_combobox = QComboBox()
        search_types_list = ["World", "Country", "State"]
        # self.search_type_combobox.addItems(search_types_list)
        for index, item in enumerate(search_types_list):
            self.search_type_combobox.addItem(item)
            self.search_type_combobox.setItemIcon(
                index, QIcon(f".//Images//icons//{item.lower()}.svg"))

        self.search_type_combobox.currentIndexChanged.connect(
            lambda x: self.Tmp.__setattr__(
                "search_type", search_types_list[x].lower())
            )
        # Region input line
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(
            "Country, region or their list separated by ;")
        self.line_edit.returnPressed.connect(self.return_pressed)
        # Region input acception button
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.return_pressed)
        self.cancel_button = QPushButton("Cancel")
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

        # Label with spinner indicating current proccessing object
        h_progress_indicator_layout = QHBoxLayout()
        self.spinner = QtWaitingSpinner(self, False, False)
        self.spinner.setRoundness(90.0)
        self.spinner.setMinimumTrailOpacity(3.14)
        self.spinner.setTrailFadePercentage(70.0)
        self.spinner.setNumberOfLines(12)
        self.spinner.setLineLength(6)
        self.spinner.setLineWidth(1)
        self.spinner.setInnerRadius(2)
        self.spinner.setRevolutionsPerSecond(1.5)
        # spinner.setColor(QColor(81, 4, 71))

        self.current_sub_object_name_label = QLabel()
        h_progress_indicator_layout.addWidget(self.spinner)
        h_progress_indicator_layout.addWidget(
            self.current_sub_object_name_label)
        v_layout.addLayout(h_progress_indicator_layout)
        # v_layout.addStretch()

        # Objects settings tab layout
        obj_settings_v_layoyt = QVBoxLayout()

        self.choose_from_results_checkbox = QCheckBox("Choose from results")
        self.choose_from_results_checkbox.setChecked(
            self.Tmp.choose_from_results)
        self.choose_from_results_checkbox.stateChanged.connect(
            lambda state: self.Tmp.__setattr__("choose_from_results", state))
        obj_settings_v_layoyt.addWidget(self.choose_from_results_checkbox)

        # Combobox locations search
        self.search_locations_groupbox = QGroupBox("Search locations")
        locations_search_groupbox_v_layout = QVBoxLayout()
        self.search_locations_groupbox.setLayout(
            locations_search_groupbox_v_layout)
        self.search_locations_groupbox.setCheckable(True)
        self.search_locations_groupbox.setChecked(self.Tmp.search_locations)
        self.search_locations_groupbox.clicked.connect(
            lambda state: self.Tmp.__setattr__("search_locations", state))
        self.points_search_list_combobox = CheckableComboBox()
        self.points_search_list_combobox.addItems(
            self.Tmp.search_places_list,
            check_list=self.Tmp.search_places_choice
            )
        locations_search_groupbox_v_layout.addWidget(
            self.points_search_list_combobox)
        obj_settings_v_layoyt.addWidget(self.search_locations_groupbox)
        # self.currentData()

        # Search borders
        self.search_borders_groupbox = QGroupBox("Search borders")
        search_borders_groupbox_v_layout = QVBoxLayout()
        self.search_borders_groupbox.setLayout(
            search_borders_groupbox_v_layout)
        self.search_borders_groupbox.setCheckable(True)
        self.search_borders_groupbox.setChecked(self.Tmp.search_borders)
        self.search_borders_groupbox.clicked.connect(
            lambda state: self.Tmp.__setattr__("search_borders", state))
        # Checkbox transforming polygons into lines
        self.checkbox_polygons_to_lines = QCheckBox(
            "Draw lines instead of polygons")
        self.checkbox_polygons_to_lines.setChecked(self.Tmp.polygons_to_lines)
        self.checkbox_polygons_to_lines.stateChanged.connect(
            lambda state: self.Tmp.__setattr__("checkbox_poly_to_lines", state)
            )

        # Line width
        h_line_width_and_color_layout = QHBoxLayout()

        self.line_width_label = QLabel()
        self.line_width_label.setText("Line width:")
        self.line_width_spin_box = QSpinBox()
        self.line_width_spin_box.setValue(self.Tmp.line_width)
        self.line_width_spin_box.valueChanged.connect(
            lambda val: self.Tmp.__setattr__("line_width", val))
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
            QIcon(".//Images//icons//color_picker.svg"))
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
            f"background-color:{self.Tmp.line_color}; border: 1px solid black")

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
        self.checkbox_export_to_kml.setChecked(self.Tmp.export_to_kml)
        self.checkbox_export_to_kml.stateChanged.connect(
            lambda x: self.Tmp.__setattr__("export_to_kml", x))
        self.checkbox_export_to_excel = QCheckBox("Excel")
        self.checkbox_export_to_excel.setChecked(self.Tmp.export_to_excel)
        self.checkbox_export_to_excel.stateChanged.connect(
            lambda x: self.Tmp.__setattr__("export_to_excel", x))
        h_exports_layout.addWidget(export_to_label)
        h_exports_layout.addWidget(self.checkbox_export_to_kml)
        h_exports_layout.addWidget(self.checkbox_export_to_excel, 1)
        obj_settings_v_layoyt.addLayout(h_exports_layout)

        # Combobox object language chooser with label
        self.obj_lang_combobox_label = QLabel()
        self.obj_lang_combobox_label.setText("Choose objects language:")
        self.obj_lang_combobox = QComboBox()

        for index, key in enumerate(self.Tmp.obj_lang_dict):
            self.obj_lang_combobox.addItem(self.Tmp.obj_lang_dict[key])
            self.obj_lang_combobox.setItemIcon(
                index, QIcon(f".//Images//flags//{key}.svg"))
            self.Tmp.obj_lang_combo_list.append(key)
            if key == self.Tmp.objects_language:
                self.obj_lang_combobox.setCurrentIndex(index)
        self.obj_lang_combobox.currentIndexChanged.connect(
            lambda x: self.Tmp.__setattr__(
                "objects_language", self.Tmp.obj_lang_combo_list[x]))

        # HLayout for object language combobox and it's label
        h_obj_lang_combobox_layout = QHBoxLayout()
        h_obj_lang_combobox_layout.addWidget(self.obj_lang_combobox_label)
        h_obj_lang_combobox_layout.addWidget(self.obj_lang_combobox, 2)
        h_obj_lang_combobox_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        obj_settings_v_layoyt.addLayout(h_obj_lang_combobox_layout)

        # Search results tab
        self.search_list_widget = QListWidget()

        # label2 = QLabel("Widget in Tab 2.")
        tabwidget = QTabWidget()
        tab_widget_tab_1 = QWidget()
        tab_widget_tab_1.setLayout(obj_settings_v_layoyt)
        tabwidget.addTab(tab_widget_tab_1, "Search settings")
        tabwidget.addTab(self.search_list_widget, "Search results")
        # self.update_search_results()
        v_layout.addWidget(tabwidget)

        widget = QWidget()
        widget.setLayout(v_layout)
        self.setCentralWidget(widget)

    # Progress bar functions
    def pb_top_thread_signal_accept(self, index: int) -> None:
        """Top progress bar signals processing

        Args:
            index (int): Current stage
        """
        self.current_object_name_label.setText(
            self.Tmp.current_obj_name)
        i = int(index) + 1
        if i == 1:
            self.pr_bar_top.setMaximum(self.Tmp.obj_number)
            self.pr_bar_top.setFormat("%v/%m (%p %)")
        self.pr_bar_top.setValue(i)

    def pb_bottom_thread_signal_accept(self, index: int) -> None:
        """Bottom progress bar signals processing

        Args:
            index (int): Current stage
        """
        i = int(index) + 1
        if i == 1:
            self.pr_bar_bottom.setMaximum(self.Tmp.sub_obj_number)
            self.pr_bar_bottom.setFormat("%v/%m (%p %)")
        self.current_sub_object_name_label.setText(
            self.Tmp.current_sub_obj_name)
        self.pr_bar_bottom.setValue(i)
        print(i, "/", self.Tmp.sub_obj_number)

    def export_visuals(self, state: int, export_type: str = "end") -> None:
        """Sends export state messages

        Args:
            state (int): State number (0,1,2)
            export_type (str, optional): Export type (KML or Excel).
                                         Defaults to "end".
        """
        if state == 0:
            self.current_sub_object_name_label.setText(
                f"Saving {export_type} file")
        if state == 1:
            self.current_sub_object_name_label.setText(
                f"{export_type} file saved")
        if state == 2:
            self.spinner.stop()
            self.search_button.setEnabled(True)

    def processing_stage_indicator(self, stage_number: int) -> None:
        self.current_object_name_label.setText(
            "Stage "
            f"{self.Tmp.current_stage_num} of "
            f"{self.Tmp.processing_choises_num}"
            f" - {self.Tmp.stages_list[stage_number]}: "
            f"({self.Tmp.current_area_obj + 1} / "
            f"{self.Tmp.current_area_obj_number}) "
            f"{self.Tmp.current_obj_name} - "
            f"{self.Tmp.current_area_obj_name}"
            )

    def return_pressed(self) -> None:
        """Search button sequence. Starts OSM search thread
        """
        print("Return pressed!")
        if self.line_edit.text() != "":
            print(self.line_edit.text())
            print("Search type choosen:", self.Tmp.search_type)
            print(self.points_search_list_combobox.currentData())
            print("Groupboxes: ",
                  [self.Tmp.search_borders, self.Tmp.search_locations])
            print("Spinboxes: ", [self.Tmp.line_width])
            self.Tmp.search_line = self.line_edit.text()
            self.Tmp.search_places_choice = \
                self.points_search_list_combobox.currentData()
            OsmWorker = EarthCrawler(self.Tmp)
            # Worker tread creation
            self.Pb_thread = PB_Thread(
                OsmWorker, self.Tmp)
            self.Tmp.current_thread = self.Pb_thread
            self.cancel_button

            # Signals connection
            self.Pb_thread._PB_Thread_sub_obj_signal.connect(
                self.pb_bottom_thread_signal_accept)
            self.Pb_thread._PB_Thread_obj_signal.connect(
                self.pb_top_thread_signal_accept)
            self.Pb_thread.json_update_signal.connect(
                self.update_search_results)
            self.Pb_thread.export_visuals_signal.connect(self.export_visuals)
            self.Pb_thread.processing_stages_signal.connect(
                self.processing_stage_indicator)
            self.Pb_thread.return_to_initial_state_signal.connect(
                self.cancel_button_stop_thread)

            self.Pb_thread.start()
            # self.search_button.setEnabled(False)
            self.search_button.clicked.disconnect(self.return_pressed)
            self.search_button.clicked.connect(self.search_results_choise)
            self.cancel_button.setEnabled(True)
            self.cancel_button.clicked.connect(self.cancel_button_stop_thread)
            self.spinner.start()

    def cancel_button_stop_thread(self) -> None:
        """Stops OSM search thread
        """
        self.Pb_thread.terminate()
        self.search_button.clicked.connect(self.return_pressed)
        self.search_list_widget.clear()
        self.spinner.stop()
        self.cancel_button.setEnabled(False)

    def pick_line_color(self) -> None:
        """Line color picker dialog
        """
        col_dialog = QColorDialog(QColor(self.Tmp.line_color))
        col = col_dialog.getColor(QColor(self.Tmp.line_color))
        if col.isValid():
            self.Tmp.line_color = col.name()
            self.line_current_color.setStyleSheet(
                f"background-color:{self.Tmp.line_color}; "
                f"border: 1px solid black")

    def update_search_results(self) -> None:
        """Updates search results page
        """
        MMap = MplMinimap()
        for i, res in enumerate(self.Tmp.current_search_json):
            MMap.set_point(float(res['lat']), float(res['lon']), i)
            self.Tmp.current_search_json[i]["nominatim_id"] = \
                f"{self.Tmp.current_search_json[i]['osm_type'][0]}" \
                f"{self.Tmp.current_search_json[i]['osm_id']}"
            item = QListWidgetItem()
            item_widget = SearchResultWidget(res, i)
            item.setData(Qt.ItemDataRole.UserRole, res)
            item.setSizeHint(QSize(350, 150))  # item_widget.sizeHint()
            self.search_list_widget.addItem(item)
            self.search_list_widget.setItemWidget(item, item_widget)

    def search_results_choise(self) -> None:
        """Confirms search result choise
        """
        self.Tmp.current_search_chosen_index = \
            self.search_list_widget.currentRow()
        self.Tmp.process_paused = False


def run_app() -> None:
    """Application start function.
    """
    app = QApplication(sys.argv)
    app.setStyleSheet(StyleSheet)
    app.setWindowIcon(QIcon('.//images//app-icon.png'))
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    run_app()
