import configparser
from typing import Any
import logger
from webcolors import name_to_hex, normalize_hex


class TempData():
    """Operative data and settings storage.
    """
    def __init__(self, mode: str = "script") -> None:
        """
        Initializes temporary parameters and loads configurations
        from 'config.ini'.

        Args:
            mode (str, optional): Running program mode. Defaults to "script".
        """
        self.mode = mode.lower()
        self.config = configparser.RawConfigParser(
            inline_comment_prefixes=("#"))
        self.config.read("config.ini")

        # Pulls from config
        self.search_type = "world"
        self.search_locations = True
        self.search_places_list = ["locality", "isolated_dwelling", "hamlet",
                                   "village", "town", "city"]  # GUI only
        self.search_places_choice = ["isolated_dwelling", "hamlet", "village",
                                     "town", "city"]
        self.search_borders = True
        self.polygons_to_lines = False
        self.line_width = 3
        self.line_color = "#ff0000"
        self.export_to_kml = True
        self.export_to_excel = True
        self.objects_language = "ru"
        self.obj_lang_dict = {'en': 'English', 'ru': 'Русский',
                              'de': 'Deutsch', 'fr': 'French', 'it': 'Italian'}
        self.obj_lang_combo_list: list[str] = []
        self.stages_list = ["Regions search", "Locations search", "Export",
                            "Finished"]
        self.choose_from_results = True  # GUI only

        # Proccess specific
        self.current_thread = Any
        # self.current_stage = 0
        self.current_stage_num = 0
        self.processing_choises_num = 0
        # Top progress bar variables
        self.obj_number = 0
        self.current_obj_name = ""  # can be pulled directly pulled from json
        # self.current_obj = 0  not needed, comes from signal

        self.current_area_obj_number = 0
        self.current_area_obj = 0
        self.current_area_obj_name = ""
        self.current_sub_obj_name = ""
        self.sub_obj_number = 0
        self.current_sub_obj = 0
        self.current_search_json: list[Any] = []  # Complex list
        self.current_search_chosen_index = 0
        self.error_found = 0
        self.logging_level = "DEBUG"
        self.search_line = "Russia"  # "Russia"

        # self.search_mode = 0
        self.process_paused = True  # GUI only

        self.get_settings()
        self.set_logger()

    @property
    def current_obj(self):
        return self._current_obj

    @current_obj.setter
    def current_obj(self, value: int):
        self._current_obj = value
        if self.mode == "gui":
            self.current_thread._PB_Thread_sub_obj_signal.emit(  # type: ignore
                                value)

    @property
    def current_stage(self):
        return self._current_stage

    @current_stage.setter
    def current_stage(self, index: int):
        self._current_stage = index
        if self.mode == "gui":
            self.current_thread.processing_stages_signal.emit(  # type: ignore
                                index)

    def get_settings(self) -> None:
        """
        Loads settings from config.ini and converts them
        into certain data types.
        """
        # [Search]
        self.search_type = str(self.config["Search"]["search_type"])
        self.objects_language = str(self.config["Search"]["objects_language"])
        self.search_borders = self.config["Search"].\
            getboolean("search_borders")
        self.search_locations = self.config["Search"].getboolean(
            "search_locations")
        self.search_places_list = list(map(
            str.strip, self.config["Search"]["search_places_list"].split(',')
            ))
        self.search_places_choice = list(map(
            str.strip, self.config["Search"]["search_places_choice"].split(',')
            ))

        # [KML]
        self.polygons_to_lines = self.config["KML"].getboolean(
            "polygons_to_lines")
        self.line_color = self.get_color(str(self.config["KML"]["line_color"]))
        self.line_width = int(self.config["KML"]["line_width"])

        # [Export]
        self.export_to_kml = self.config["Export"].getboolean("export_to_kml")
        self.export_to_excel = self.config["Export"].getboolean(
            "export_to_excel")
        # [Logging]
        self.logging_level = self.config["Logging"]["logging_level"].upper()

    def set_logger(self) -> None:
        """Creates logger instance as self.logger_object.
        """
        print(self.logging_level)
        self.logger_object = logger.set_logger(
            log_level_name=self.logging_level)

    def get_color(self, color_str: str) -> str:
        """
        Converts CSS3 color name or normalizes HEX color code to
        format accepted by QT.

        Args:
            color_str (str): String with HEX color code or CSS3 color name

        Returns:
            str: Normalized HEX color code string
        """
        try:
            normal_hex = normalize_hex(f"#{color_str}").lower()
            return normal_hex
        except ValueError:
            pass
        try:
            normal_hex = name_to_hex(color_str).lower()
            return normal_hex
        except ValueError:
            print("Parameter 'line_color' from 'config.ini' set incorrectly, "
                  "using default 'red' (#ff0000) value instead")
            return "#ff0000"
