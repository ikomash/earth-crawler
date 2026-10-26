"""
Modified pyqt6 widget from
https://gis.stackexchange.com/questions/350148/qcombobox-multiple-selection-pyqt5  # noqa: E501
"""
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import QComboBox, QStyledItemDelegate
from PyQt6.QtGui import QStandardItem, QFontMetrics


class CheckableComboBox(QComboBox):
    """Combo box with checkable items and a compact summary text."""

    class Delegate(QStyledItemDelegate):
        """Delegate that keeps checkable items at a compact height."""

        def sizeHint(self, option, index):
            """Return a consistent item size for the delegate.

            Args:
                option: The paint option for the item.
                index: The model index for the item.

            Returns:
                QSize: Preferred item size.
            """
            size = super().sizeHint(option, index)
            size.setHeight(20)
            return size

    def __init__(self, *args, **kwargs):
        """Initialize the checkable combo box."""
        super().__init__(*args, **kwargs)

        # Make the combo editable to set a custom text, but readonly
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)

        # Use custom delegate
        self.setItemDelegate(CheckableComboBox.Delegate())

        # Update the text when an item is toggled
        self.model().dataChanged.connect(self.updateText)

        # Hide and show popup when clicking the line edit
        self.lineEdit().installEventFilter(self)
        self.closeOnLineEditClick = False

        # Prevent popup from closing when clicking on an item
        self.view().viewport().installEventFilter(self)

    def resizeEvent(self, event):
        """Refresh the displayed text when the widget is resized."""
        self.updateText()
        super().resizeEvent(event)

    def eventFilter(self, object, event):
        """Handle clicks inside the line edit and popup viewport.

        Args:
            object: The object receiving the event.
            event: The Qt event instance.

        Returns:
            bool: True if the event was handled internally.
        """

        if object == self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonRelease:
                if self.closeOnLineEditClick:
                    self.hidePopup()
                else:
                    self.showPopup()
                return True
            return False

        if object == self.view().viewport():
            if event.type() == QEvent.Type.MouseButtonRelease:
                index = self.view().indexAt(event.pos())
                item = self.model().item(index.row())

                if item.checkState() == Qt.CheckState.Checked:
                    item.setCheckState(Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked)
                return True
        return False

    def showPopup(self):
        """Open the popup and prepare it for the next line-edit click."""
        super().showPopup()
        self.closeOnLineEditClick = True

    def hidePopup(self):
        """Hide the popup and refresh the summary text."""
        super().hidePopup()
        # Used to prevent immediate reopening when clicking on the lineEdit
        self.startTimer(100)
        # Refresh the display text when closing
        self.updateText()

    def timerEvent(self, event):
        """Reset the line-edit click state after the popup closes."""
        self.killTimer(event.timerId())
        self.closeOnLineEditClick = False

    def updateText(self):
        """Build the summary text from the checked items."""
        texts = []
        for i in range(self.model().rowCount()):
            if self.model().item(i).checkState() == Qt.CheckState.Checked:
                texts.append(self.model().item(i).text())
        text = ", ".join(texts)

        # Compute elided text (with "...")
        metrics = QFontMetrics(self.lineEdit().font())
        elidedText = metrics.elidedText(
            text, Qt.TextElideMode.ElideRight, self.lineEdit().width())
        self.lineEdit().setText(elidedText)

    def addItem(self, text, data=None, is_checked=False):
        """Add one checkable item to the combo box.

        Args:
            text: Label displayed in the item.
            data: Optional user data stored with the item.
            is_checked (bool, optional): Whether the item starts checked.
        """
        item = QStandardItem()
        item.setText(text)
        if data is None:
            item.setData(text)
        else:
            item.setData(data)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        if is_checked:
            item.setData(
                Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        else:
            item.setData(
                Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        self.model().appendRow(item)

    def addItems(self, texts, datalist=None, check_list=None):
        """Add a list of items and optionally pre-check selected ones.

        Args:
            texts: Collection of item labels.
            datalist: Optional list of user data values.
            check_list: Optional list of labels that should start checked.
        """
        for i, text in enumerate(texts):
            try:
                data = datalist[i]
            except (TypeError, IndexError):
                data = None
            if isinstance(check_list, list):
                if text in check_list:
                    self.addItem(text, data, is_checked=True)
                    continue
            self.addItem(text, data, is_checked=False)

    def currentData(self):
        """Return the selected items' stored data values."""
        res = []
        for i in range(self.model().rowCount()):
            if self.model().item(i).checkState() == Qt.CheckState.Checked:
                res.append(self.model().item(i).data())
        return res
