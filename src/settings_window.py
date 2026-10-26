from typing import Optional

from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QGroupBox,
    QGridLayout, QLabel, QLineEdit, QSizePolicy)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QObject

from app_data import AppData, SearchMode
from paths import Paths
from utils import IndexCounter, read_qss


class SettingsWindow(QDialog):
    """Application settings window."""

    def __init__(self, app_data: AppData, parent: Optional[QObject] = None):
        """Initialize the settings dialog.

        Args:
            app_data (AppData): Application configuration and runtime data.
            parent (Optional[QObject], optional): Parent widget for the dialog.
        """
        super(SettingsWindow, self).__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.app_data = app_data
        self.setWindowIcon(QIcon(str(Paths.app_icon_path)))
        self.setStyleSheet(read_qss(Paths.stylesheet_path))
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint |
            Qt.WindowType.MSWindowsFixedSizeDialogHint
        )

        layout = QVBoxLayout()

        requests_group = QGroupBox(self)
        requests_group.setTitle("Requests")
        requests_layout = QGridLayout()
        requests_group.setLayout(requests_layout)
        pref_row = IndexCounter()

        requests_type_label = QLabel("Requests type", self)
        requests_layout.addWidget(requests_type_label, pref_row(), 0)
        self.requests_type_combobox = QComboBox(self)
        self.requests_type_combobox.addItems(
            [mode.name for mode in SearchMode])
        self.requests_type_combobox.setCurrentIndex(
            self.app_data.requests.requests_type)
        requests_layout.addWidget(
            self.requests_type_combobox, next(pref_row), 1)

        api_link_label = QLabel(
            "API link", self)
        requests_layout.addWidget(api_link_label, pref_row(), 0)
        self.api_link_edit = QLineEdit(self)
        self.api_link_edit.setMinimumWidth(500)
        self.api_link_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.api_link_edit.setText(self.app_data.requests.api_link)
        self.api_link_edit.setCursorMoveStyle(
            Qt.CursorMoveStyle.LogicalMoveStyle)
        requests_layout.addWidget(
            self.api_link_edit, next(pref_row), 1)

        user_agent_label = QLabel("User agent", self)
        requests_layout.addWidget(user_agent_label, pref_row(), 0)
        self.user_agent_edit = QLineEdit(self)
        self.user_agent_edit.setMinimumWidth(500)
        self.user_agent_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.user_agent_edit.setText(self.app_data.requests.user_agent)
        self.user_agent_edit.setCursorMoveStyle(
            Qt.CursorMoveStyle.LogicalMoveStyle)
        requests_layout.addWidget(
            self.user_agent_edit, next(pref_row), 1)

        requests_layout.setColumnStretch(1, 1)
        layout.addWidget(requests_group)

        # Apply / Cancel buttons
        apply_layout = QHBoxLayout()
        settings_accept_button = QPushButton("Apply", self)
        settings_accept_button.setIcon(
            QIcon(str(Paths.confirm_icon_path)))
        settings_accept_button.clicked.connect(self.confirm_config)
        apply_layout.addWidget(settings_accept_button)
        settings_reject_button = QPushButton("Cancel", self)
        settings_reject_button.setIcon(
            QIcon(str(Paths.cancel_icon_path)))
        settings_reject_button.clicked.connect(self.close)  # type: ignore
        apply_layout.addWidget(settings_reject_button)
        layout.addLayout(apply_layout)

        self.setLayout(layout)

    def confirm_config(self):
        """Save the edited request settings and close the dialog."""
        # Requests
        self.app_data.requests.api_link = self.api_link_edit.text()
        self.app_data.requests.user_agent = self.user_agent_edit.text()
        self.app_data.requests.requests_type = \
            self.requests_type_combobox.currentIndex()
        self.app_data.write_cfg()
        # self.config_changed.emit()
        self.close()
