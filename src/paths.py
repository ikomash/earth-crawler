from pathlib import Path
from dataclasses import dataclass


@dataclass
class Paths:
    """Contains paths used in this project."""
    this_folder = Path(__file__).parent.resolve()
    parent_folder = this_folder.parent.resolve()

    assets_folder = parent_folder.joinpath("assets")
    default_export_folder = parent_folder.joinpath("exports")
    icons_folder = assets_folder.joinpath("icons")
    flags_folder = assets_folder.joinpath("flags")
    fill_circle_icon_path = icons_folder.joinpath("fill_circle.svg")
    links_icon_path = icons_folder.joinpath("links.svg")
    color_picker_icon_path = icons_folder.joinpath("color_picker.svg")
    app_icon_path = assets_folder.joinpath("app_icon.ico")
    play_icon_path = icons_folder.joinpath("play.svg")
    pause_icon_path = icons_folder.joinpath("pause.svg")
    delete_bin_icon_path = icons_folder.joinpath("delete_bin.svg")
    info_icon_path = icons_folder.joinpath("info.svg")
    info_light_icon_path = icons_folder.joinpath("info_light.svg")
    map_location_pin_icon_path = icons_folder.joinpath("map_location_pin.svg")
    list_icon_path = icons_folder.joinpath("list.svg")
    settings_icon_path = icons_folder.joinpath("settings.svg")
    search_icon_path = icons_folder.joinpath("search.svg")
    down_arrow_path = icons_folder.joinpath("down_arrow.svg")
    open_folder_icon = icons_folder.joinpath("open_folder.svg")
    confirm_icon_path = icons_folder.joinpath("confirm.svg")
    cancel_icon_path = icons_folder.joinpath("cancel.svg")
    help_icon_path = icons_folder.joinpath("help.svg")

    configs_folder = parent_folder.joinpath("configs")
    config_path = configs_folder.joinpath("config.ini")

    export_folder = parent_folder.joinpath("export")

    logs_folder = parent_folder.joinpath("logs")
    log_file_path = logs_folder.joinpath("earth_crawler.log")

    style_folder = parent_folder.joinpath("style")
    stylesheet_path = style_folder.joinpath("stylesheet.qss")

    tmp_folder = parent_folder.joinpath("tmp")

    help_path = parent_folder.joinpath("README.md")
