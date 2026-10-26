from typing import Optional
import requests

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtCore import Qt

from paths import Paths


class SearchResultsWidget(QWidget):
    """Display one OSM search result in the results list."""

    def __init__(self, data: dict, index: int,
                 parent: Optional[QWidget] = None):
        """Initialize the result widget.

        Args:
            data (dict): Single Nominatim result record.
            index (int): Row position in the list widget.
            parent (Optional[QWidget], optional): Parent widget.
        """
        super(SearchResultsWidget, self).__init__(parent)
        h_layout = QHBoxLayout()
        sub_v_layout = QVBoxLayout()
        name_label = QLabel(f"Name: {data['display_name']}")
        name_label.setWordWrap(True)
        sub_v_layout.addWidget(name_label)

        types_label_text = f"Nominatim ID: {data['nominatim_id']}, " \
            f"OSM type: {data['osm_type']}, Class: {data['class']}, " \
            f"Type: {data['type']}"
        admin_level = data.get('admin_level', False)
        if admin_level:
            types_label_text += f", Administrative level: {admin_level}"

        types_label = QLabel(types_label_text)
        types_label.setWordWrap(True)
        sub_v_layout.addWidget(types_label)

        image = QImage()
        icon = QLabel()
        if 'icon' in data.keys():
            image.loadFromData(requests.get(data['icon']).content)
            icon.setPixmap(QPixmap(image))
        else:
            icon.setPixmap(
                QIcon(str(Paths.fill_circle_icon_path)).pixmap(24, 24))
        h_layout.addWidget(icon)

        map_v_layout = QVBoxLayout()
        map_icon = QLabel()
        map_icon.setPixmap(
            QIcon(str(Paths.tmp_folder.joinpath(
                f"minimap_{index}.png"))).pixmap(150, 150))
        lat_label = QLabel(f"Lat: {data['lat']}")
        lat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lon_label = QLabel(f"Lon: {data['lon']}")
        lon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        map_v_layout.addWidget(map_icon)
        map_v_layout.addWidget(lat_label)
        map_v_layout.addWidget(lon_label)

        sub_v_layout.setSpacing(0)
        sub_v_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addLayout(sub_v_layout, 4)
        h_layout.addLayout(map_v_layout, 0)
        self.setLayout(h_layout)
