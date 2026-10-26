from PyQt6.QtWidgets import QFrame


class QHLine(QFrame):
    """Horizontal separator line widget."""

    def __init__(self):
        """Initialize the horizontal line widget."""
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)


class QVLine(QFrame):
    """Vertical separator line widget."""

    def __init__(self):
        """Initialize the vertical line widget."""
        super(QVLine, self).__init__()
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
