from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QGridLayout, QLabel)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QObject

from paths import Paths
from utils import IndexCounter, read_qss
from widgets.LineWidgets import QHLine
from __version__ import __version__


class InfoWindow(QDialog):
    """Application information dialog with links to project resources."""

    def __init__(self, parent: Optional[QObject] = None):
        """Initialize the information dialog.

        Args:
            parent (Optional[QObject], optional): Parent object for the dialog.
        """
        super(InfoWindow, self).__init__(parent)
        self.setWindowTitle("Info")
        self.setModal(True)
        self.setWindowIcon(QIcon(str(Paths.app_icon_path)))
        self.setStyleSheet(read_qss(Paths.stylesheet_path))
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint |
            Qt.WindowType.MSWindowsFixedSizeDialogHint
        )

        layout = QVBoxLayout()

        app_icon_label = QLabel(self)
        app_icon = QIcon(str(Paths.app_icon_path))
        app_icon_label.setPixmap(app_icon.pixmap(64, 64))
        app_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app_icon_label)

        app_info_group = QGroupBox(self)
        app_info_group.setTitle("Application info")
        app_info_layout = QGridLayout()
        app_info_group.setLayout(app_info_layout)
        app_info_row = IndexCounter()

        version_label = QLabel("Version:", self)
        app_info_layout.addWidget(version_label, app_info_row(), 0)

        version_value_label = QLabel(__version__, self)
        app_info_layout.addWidget(version_value_label, next(app_info_row), 1)

        repo_label = QLabel("Repository:", self)
        app_info_layout.addWidget(repo_label, app_info_row(), 0)
        repo_link_label = QLabel(
            '<a href=https://github.com/ikomash/earth-crawler>'
            'https://github.com/ikomash/earth-crawler</a>',
            self
        )
        repo_link_label.setOpenExternalLinks(True)
        repo_link_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        app_info_layout.addWidget(repo_link_label, next(app_info_row), 1)
        layout.addWidget(app_info_group)

        links_group = QGroupBox(self)
        links_group.setTitle("Related links")
        links_layout = QGridLayout()
        links_group.setLayout(links_layout)
        pref_row = IndexCounter()

        administrative_levels_link = QLabel(
            '<a href="https://wiki.openstreetmap.org/wiki/Tag:boundary%3Dadmin'
            'istrative#Country_specific_values_of_the_key_admin_level=*">'
            'Administrative levels</a>'
        )
        administrative_levels_link.setOpenExternalLinks(True)
        administrative_levels_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        links_layout.addWidget(administrative_levels_link, next(pref_row), 0)
        administrative_levels_link.setStatusTip(
            "Open Administrative levels table wiki page in browser")

        links_layout.addWidget(QHLine(), next(pref_row), 0)

        nominatim_link = QLabel(
            '<a href="https://nominatim.openstreetmap.org/">Nominatim</a>',
            self
        )
        nominatim_link.setOpenExternalLinks(True)
        nominatim_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        nominatim_link.setStatusTip("Open Nominatim page in browser")
        links_layout.addWidget(nominatim_link, next(pref_row), 0)

        overpass_link = QLabel(
            '<a href="https://overpass-turbo.eu/">Overpass</a>', self)
        overpass_link.setOpenExternalLinks(True)
        overpass_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        overpass_link.setStatusTip("Open Overpass page in browser")
        links_layout.addWidget(overpass_link, next(pref_row), 0)
        osm_link = QLabel(
            '<a href="https://www.openstreetmap.org/">OSM</a>', self)
        osm_link.setOpenExternalLinks(True)
        osm_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        osm_link.setStatusTip("Open OSM page in browser")
        links_layout.addWidget(osm_link, next(pref_row), 0)

        links_group.setLayout(links_layout)
        layout.addWidget(links_group)

        self.setLayout(layout)
