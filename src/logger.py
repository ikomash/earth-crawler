# -*- coding: utf-8 -*-
import faulthandler
import html
import logging
import os
import sys
import threading
from collections import deque
from logging import StreamHandler
from logging.handlers import RotatingFileHandler
from os import makedirs
from pathlib import Path
from typing import Union, Optional

from PyQt6.QtCore import (
    QObject, QtMsgType, Qt, pyqtSignal, qInstallMessageHandler)
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import QTextEdit, QApplication, QWidget, QPushButton, \
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSizePolicy, \
    QBoxLayout, QFrame

from paths import Paths


DEFAULT_LOGGER_NAME = 'earth_crawler_logger'


def mkdir_if_none(folder: Union[str, Path]):
    """
    Check whether the folder exists. Creates the folder if it does not exist.

    Args:
        folder (Union[str, Path]): Folder path.
    """
    if type(folder) is str:
        path = Path(folder)
    else:
        path = folder  # type: ignore
    exists = path.exists()
    if not exists:
        makedirs(folder)


# Colors of the log lines, from the most to the least severe level.
_LEVEL_COLORS = (
    (logging.CRITICAL, "darkRed"),
    (logging.ERROR, "red"),
    (logging.WARNING, "orange"),
    (logging.INFO, "green"),
)


def level_color(levelno: int) -> str:
    """Return the color of the log lines of a logging level.

    Args:
        levelno (int): Numeric logging level, for example logging.ERROR.

    Returns:
        str: Color name usable in the style of the log widget.
    """
    for level, color in _LEVEL_COLORS:
        if levelno >= level:
            return color
    return "gray"


def format_log_html(message: str, levelno: int) -> str:
    """Make a log message safe and readable for a rich text widget.

    The message is escaped: log texts and tracebacks contain things like
    '<class ...>' and '<module>', which a rich text widget would swallow as
    unknown tags. Line breaks and indentation of tracebacks are kept.

    Args:
        message (str): Formatted log message.
        levelno (int): Numeric logging level, selects the color.

    Returns:
        str: HTML for QTextEdit.append().
    """
    return (
        f"<span style='color:{level_color(levelno)}; white-space:pre-wrap;'>"
        f"{html.escape(message)}</span>"
    )


class QtLogHandler(StreamHandler, QObject):
    """
    Logging stream handler.
    Sends Qt signals with formatted messages to the LogWidget.
    QObject is used for Qt signal routing.
    """
    message = pyqtSignal(str)  # type: ignore

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the Qt-aware logging handler.

        Args:
            parent (Optional[QWidget], optional):
                PyQt parent object. Defaults to None.
        """
        StreamHandler.__init__(self)
        QObject.__init__(self, parent)

    def emit(self, record: logging.LogRecord):
        """Forward a formatted log record to the Qt signal channel.

        Args:
            record (logging.LogRecord): Log record emitted by the logger.
        """
        log_msg = self.format(record)  # applies formatter if set.

        # The color comes from the level of the record, not from searching
        # the text for words like "INFO", and the text is escaped.
        text = format_log_html(log_msg, record.levelno)

        self.message.emit(text)  # emit signal with colored text

        self.flush()  # clear buffer


class LogWidget(QTextEdit):
    """Qt logging widget based on QTextEdit and StreamHandler.
    Supports text size control. While the display is stopped the messages
    are kept and shown when it is started again.
    """

    # Most messages kept while the display is stopped.
    HELD_MESSAGES_LIMIT = 10000

    def __init__(
            self,
            handler: QtLogHandler,
            logger_name: str,
            parent: Optional[QWidget] = None):
        """
        Create a LogWidget instance.

        Args:
            handler (QtLogHandler): Handler that emits formatted messages.
            logger_name (str): Logger name to search for.
            parent (Optional[QWidget], optional):
                PyQt parent object. Defaults to None.
        """
        QTextEdit.__init__(self, parent)
        self.setReadOnly(True)

        self.handler = handler
        self.logger = logging.getLogger(logger_name)

        self.default_font_size = 11
        self.min_font_size = 8
        self.max_font_size = 18
        self.font_size_step = 1

        self._paused = False
        self._held: deque = deque(maxlen=self.HELD_MESSAGES_LIMIT)

        self._set_font_size(self.default_font_size)
        self._setup_shortcuts()
        self.handler.message.connect(self.__updateText)  # type:ignore

    def _setup_shortcuts(self):
        """
        Sets keyboard shortcuts for changing the log text size.
        """
        self.increase_font_shortcut = QShortcut(QKeySequence("Ctrl+="), self)
        self.increase_font_shortcut.activated.connect(
            self.increase_font_size)  # type:ignore

        self.decrease_font_shortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        self.decrease_font_shortcut.activated.connect(
            self.decrease_font_size)  # type:ignore

        self.reset_font_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        self.reset_font_shortcut.activated.connect(
            self.reset_font_size)  # type:ignore
        self.setToolTip(
            'For font size control, use "Ctrl+=/"Ctrl+-"/"Ctrl+0" or '
            'scroll mouse wheel while holding "Ctrl" key.'
        )

    def _set_font_size(self, size: int):
        """Set the logger font size.

        Args:
            size (int): Font size in points.
        """
        document = self.document()
        if document is not None:
            current_font = document.defaultFont()
            current_font.setPointSize(size)
            document.setDefaultFont(current_font)

    def increase_font_size(self):
        """Increase the font size by one step (+)."""
        document = self.document()
        if document is not None:
            current_font = document.defaultFont()
        current_size = current_font.pointSize()
        new_size = min(current_size + self.font_size_step, self.max_font_size)
        if new_size != current_size:
            self._set_font_size(new_size)

    def decrease_font_size(self):
        """Decrease the font size by one step."""
        document = self.document()
        if document is not None:
            current_font = document.defaultFont()
        current_size = current_font.pointSize()
        new_size = max(current_size - self.font_size_step, self.min_font_size)
        if new_size != current_size:
            self._set_font_size(new_size)

    def reset_font_size(self):
        """Reset the default font size."""
        self._set_font_size(self.default_font_size)

    def __scrollDown(self):
        """Scroll the QTextEdit widget down."""
        scroll_bar = self.verticalScrollBar()
        end_text = scroll_bar.maximum()
        scroll_bar.setValue(end_text)

    def __updateText(self, msg: str):
        """
        Append a log message to the QTextEdit widget.

        Args:
            msg (str): Text to append.
        """
        if self._paused:
            self._held.append(msg)
            return
        self.append(msg)
        self.__scrollDown()

    def stop(self):
        """Stop the log display. Messages are kept until start()."""
        self._paused = True

    def start(self):
        """Resume the log display and show the messages held meanwhile."""
        self._paused = False
        while self._held:
            self.append(self._held.popleft())
        self.__scrollDown()


class Logger:
    """Configure application loggers and their output handlers."""

    # Log files rotate at this size and this many old files are kept. The old
    # 100 KB x 4 was used up within one big search.
    LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
    LOG_FILE_BACKUPS = 5

    def __init__(
            self, caller: str = __name__, log_file: Optional[Path] = None):
        """
        General logging handler class.

        Args:
            caller (str, optional): Who calls the logger. Defaults to __name__.
            log_file (Optional[Path], optional):
                Path to log file. Defaults to None.
        """
        self.gui_stream_handler: Optional[QtLogHandler] = None
        self.file_handler: Optional[RotatingFileHandler] = None
        self.stream_handler: Optional[StreamHandler] = None
        self.logger: Optional[logging.Logger] = None
        self.caller = caller
        self.log_file = log_file

        _log_format = "%(asctime)s - [%(levelname)s] - %(name)s - " \
                      "(%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"
        self.formatter = logging.Formatter(_log_format)

        self.set_logger(caller)
        self.set_handlers()
        self.capture_library_logs()

    @staticmethod
    def log_level_from_text(log_level_name: str) -> int:
        """
        Converts a logging level name to its numeric logging level.

        Args:
            log_level_name (str):
                Log level name supported by the logging module.

        Returns:
            int: Log level integer equivalent.
        """
        levels_dict = {"NOTSET": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30,
                       "ERROR": 40, "CRITICAL": 50}
        if log_level_name.upper() in levels_dict:
            log_level = levels_dict[log_level_name]
        else:
            log_level = levels_dict["DEBUG"]
        return log_level

    def set_logger(
            self,
            name: str = __name__,
            log_level_name: str = "DEBUG"
    ):
        """
        Create and configure the logger.

        Args:
            name (str, optional):
                Logger's name. Defaults to __name__.
            log_level_name (str, optional):
                Logger log level name ("NOTSET", "DEBUG", "INFO", "WARNING",
                "ERROR", "CRITICAL"). Defaults to "DEBUG".
        """
        log_level = self.log_level_from_text(log_level_name)
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level)

    def set_handlers(self):
        """Set up handlers for the logger."""
        if self.logger is not None and len(self.logger.handlers) == 0:
            self.set_stream_handler()
            self.set_file_handler()

    def capture_library_logs(self):
        """Also write warnings and errors that libraries log themselves.

        OSMPythonTools, urllib3 and others log to their own loggers, which are
        not part of the application logger, so their messages were lost. The
        handlers are therefore attached to the root logger too, at level
        WARNING so that library noise stays out, and the application logger
        stops passing its records on to avoid writing them twice. Python
        warnings are routed into the log as well.
        """
        if self.logger is None:
            return
        root = logging.getLogger()
        root.setLevel(logging.WARNING)
        attached = False
        for handler in (self.stream_handler, self.file_handler):
            if handler is not None:
                attached = True
                if handler not in root.handlers:
                    root.addHandler(handler)
        if attached:
            self.logger.propagate = False
        logging.captureWarnings(True)

    def set_stream_handler(self, log_level_name: str = "DEBUG"):
        """
        Set up the logger's stream handler.

        Args:
            log_level_name (str, optional): Logging level. Defaults to "DEBUG".
        """
        if self.logger:
            self.stream_handler = StreamHandler()
            self.stream_handler.setFormatter(self.formatter)
            stream_log_level = self.log_level_from_text(log_level_name)
            self.stream_handler.setLevel(stream_log_level)
            self.logger.addHandler(self.stream_handler)

    def set_file_handler(self, log_level_name: str = "DEBUG"):
        """
        Set up the logger's file handler.

        Args:
            log_level_name (str, optional): Logging level. Defaults to "DEBUG".
        """
        if self.logger:
            if self.log_file is not None:
                file_path = self.log_file
            else:
                file_path = Path(__file__).parent.resolve().joinpath(
                    "logs").joinpath(f"{self.caller}.log")
            parent_folder = file_path.parent
            if parent_folder != Path("."):
                mkdir_if_none(parent_folder)
            self.file_handler = RotatingFileHandler(
                file_path, maxBytes=self.LOG_FILE_MAX_BYTES,
                backupCount=self.LOG_FILE_BACKUPS, encoding='utf-8')
            file_log_level = self.log_level_from_text(log_level_name)
            self.file_handler.setLevel(file_log_level)
            self.file_handler.setFormatter(self.formatter)
            self.logger.addHandler(self.file_handler)

    def set_qt_signal_handler(
            self, log_level_name: str = "DEBUG") -> Optional[QtLogHandler]:
        """Attach a Qt-aware log handler for GUI display.

        Args:
            log_level_name (str, optional): Logging level. Defaults to "DEBUG".

        Returns:
            Optional[QtLogHandler]: The configured Qt log handler, if created.
        """
        if self.logger:
            self.gui_stream_handler = QtLogHandler()
            self.gui_stream_handler.setLevel(log_level_name)
            self.gui_stream_handler.setFormatter(self.formatter)
            self.logger.addHandler(self.gui_stream_handler)
            return self.gui_stream_handler
        else:
            return None


class LogSwitcher(QWidget):
    """Widget with buttons and a combobox for log control."""

    log_hidden = pyqtSignal(bool)

    def __init__(
            self,
            logs_widget: LogWidget,
            parent: Optional[QWidget] = None,
            hide_buttons: bool = True):
        """Initialize LogSwitcher.

        Args:
            logs_widget (LogWidget): Switchable log widget.
            parent (Optional[QWidget], optional):
                Parent Qt object. Defaults to None.
            hide_buttons (bool, optional):
                Hide buttons together with the log widget. Defaults to True.
        """
        super(LogSwitcher, self).__init__(parent)

        self.logs_widget = logs_widget
        self.logs_widget.setProperty("cssClass", "logs_widget")
        self.logs_widget.setObjectName("logs_widget")
        self.logger = self.logs_widget.logger
        self.hide_buttons = hide_buttons

        self.display_log = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # log settings container
        self.log_box = QFrame(self)  # QGroupBox(self)
        self.log_box.setFrameShape(QFrame.Shape.StyledPanel)
        self.log_box.setObjectName("log_box")
        log_box_layout = QVBoxLayout()
        log_box_layout.addStretch(1)
        self.log_box.setLayout(log_box_layout)
        self.log_box.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        self.title = QLabel("Log settings")
        self.title.setObjectName("log_title")
        self.title.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        log_box_layout.addWidget(self.title)

        # log control buttons
        self.clear_log_button = QPushButton("Clear", self)
        self.clear_log_button.setToolTip('Clear log entries')
        self.clear_log_button.setProperty('cssClass', 'hideable_btn')
        self.clear_log_button.setIcon(QIcon(str(Paths.delete_bin_icon_path)))
        self.clear_log_button.clicked.connect(self.clear_logs)  # type: ignore
        log_box_layout.addWidget(self.clear_log_button)
        self.stop_log_display_button = QPushButton("Stop", self)
        self.stop_log_display_button.setToolTip(
            'Stop log updates')
        self.stop_log_display_button.setProperty('cssClass', 'hideable_btn')
        self.stop_log_display_button.setIcon(QIcon(str(Paths.pause_icon_path)))
        self.stop_log_display_button.clicked.connect(
            self.disable_log_display)  # type: ignore
        log_box_layout.addWidget(self.stop_log_display_button)

        # logging filter container
        self.severity_box = QGroupBox(self)
        self.severity_box.setObjectName('severity_box')
        self.severity_box.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        severity_layout = QHBoxLayout(self.severity_box)
        severity_layout.setContentsMargins(0, 0, 0, 0)
        self.severity_box.setLayout(severity_layout)
        self.severity_label = QLabel("Filter:", self.severity_box)
        self.severity_label.setObjectName("log_level_title")
        self.severity_label.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        log_box_layout.setSpacing(4)
        severity_layout.setSpacing(0)

        severity_layout.addWidget(self.severity_label)
        # combobox with logging levels
        self.severity_combobox = QComboBox(self.severity_box)
        self.severity_combobox.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.severity_combobox.setObjectName("log_combobox")
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            self.severity_combobox.addItem(
                QIcon(str(Paths.icons_folder.joinpath(
                    f"{level.lower()}.svg"))),
                level
            )
        self.severity_combobox.setCurrentText("INFO")
        self.severity_combobox.currentTextChanged.connect(
            self.change_log_level)  # type: ignore
        severity_layout.addWidget(self.severity_combobox)
        log_box_layout.addWidget(self.severity_box)
        log_box_layout.addStretch(1)

        layout.addWidget(self.log_box)

    def clear_logs(self):
        """Clear the log."""
        self.logs_widget.clear()

    def change_log_level(self):
        """Update the active logger level from the selected combo-box value."""
        selected_level = self.severity_combobox.currentText().upper()
        numeric_level = getattr(logging, selected_level, None)
        if isinstance(numeric_level, int):
            self.logger.setLevel(numeric_level)

    def disable_log_display(self):
        """Pause log updates."""
        self.display_log = not self.display_log
        if not self.display_log:
            self.logs_widget.stop()
            self.stop_log_display_button.setText("Resume")
            self.stop_log_display_button.setToolTip(
                'Resume log updates')
            self.stop_log_display_button.setIcon(
                QIcon(str(Paths.play_icon_path)))
        else:
            self.logs_widget.start()
            self.stop_log_display_button.setText("Stop")
            self.stop_log_display_button.setToolTip(
                'Stop log updates')
            self.stop_log_display_button.setIcon(
                QIcon(str(Paths.pause_icon_path)))


class LogSwitchebleWidget(QWidget):
    """Log widget with support for switching the logging level."""

    def __init__(
            self,
            parent=None,
            logger_name=DEFAULT_LOGGER_NAME,
            horizontal: bool = True):
        """Create the log display and its control panel.

        Args:
            parent (QWidget, optional): Parent widget.
            logger_name (str, optional): Logger displayed by this widget.
            horizontal (bool, optional): Place controls beside the log when
                true, or below it when false.
        """
        super(LogSwitchebleWidget, self).__init__(parent)

        self.gui_stream_handler = QtLogHandler()
        _log_format = "[%(asctime)s][%(levelname)s][%(thread)d]:\t %(message)s"
        formatter = logging.Formatter(_log_format)
        self.gui_stream_handler.setFormatter(formatter)
        self.gui_stream_handler.setLevel(logging.DEBUG)
        self.logger = logging.getLogger(logger_name)
        self.logger.addHandler(self.gui_stream_handler)
        root = logging.getLogger()
        if not self.logger.propagate and self.logger is not root:
            # records of libraries go to the root logger, see
            # Logger.capture_library_logs()
            root.addHandler(self.gui_stream_handler)

        layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight
            if horizontal else QBoxLayout.Direction.TopToBottom
        )
        self.setLayout(layout)

        self.logs_widget = LogWidget(
            self.gui_stream_handler, logger_name, self)
        layout.addWidget(self.logs_widget)

        self.log_swithcer = LogSwitcher(
            self.logs_widget, self)
        # log_swithcer.setMinimumHeight(275)
        layout.addWidget(self.log_swithcer)

        self.log_swithcer.change_log_level()

    def set_horizontal(self, horizontal: bool):
        """Switch the layout orientation of the log widget.

        Args:
            horizontal (bool): Whether the widget should be laid out
                horizontally.
        """
        direction = (
            QBoxLayout.Direction.LeftToRight
            if horizontal
            else QBoxLayout.Direction.TopToBottom
        )
        if horizontal:
            self.log_swithcer.log_box.setSizePolicy(
                QSizePolicy.Minimum, QSizePolicy.Preferred)
        else:
            self.log_swithcer.log_box.setSizePolicy(
                QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout = self.layout()
        if isinstance(layout, QBoxLayout):
            layout.setDirection(direction)

    def get_logger(self) -> logging.Logger:
        """Return the Logger object."""
        return self.logger

    def closeEvent(self, event):
        """Clean up Qt log handlers when the widget is closed.

        Args:
            event: Close event emitted by the widget.
        """
        for logger in (self.logger, logging.getLogger()):
            for handler in logger.handlers[:]:
                if isinstance(handler, QtLogHandler):
                    logger.removeHandler(handler)
                    handler.deleteLater()
        event.accept()


# Qt message types and the logging levels they correspond to.
_QT_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}

# Kept at module level: faulthandler needs the file to stay open, and the
# Qt message handler has to stay alive.
_crash_file = None
_qt_logger: Optional[logging.Logger] = None


def _log_qt_message(msg_type, context, message):
    """Qt message handler: write Qt's own messages into the log."""
    if _qt_logger is not None:
        _qt_logger.log(_QT_LEVELS.get(msg_type, logging.WARNING),
                       "Qt: %s", message)


def install_exception_logging(
        logger: logging.Logger, crash_log: Optional[Path] = None):
    """Write errors that normally vanish into the log.

    Without this, an exception that nobody catches, in a Qt slot or in a
    thread, is only printed to stderr. A windowed (--noconsole) build has no
    stderr, so such errors were lost, and PyQt6 even aborts the application
    on an exception in a slot, which looked like a crash without a reason.

    What gets logged:
        * uncaught exceptions of the main thread (and PyQt6 no longer aborts)
        * uncaught exceptions of other threads
        * exceptions that Python can only report as "unraisable"
        * Qt's own warnings and errors, for example from the web engine
        * hard crashes of the interpreter (stack dump into ``crash_log``)

    Args:
        logger (logging.Logger): Receives the messages.
        crash_log (Optional[Path], optional): File for the stack dump of a
            hard crash and of dump_threads_later(). Defaults to None.
    """
    global _crash_file, _qt_logger

    # A windowed build has no standard streams. Libraries that write to them
    # directly would fail with "'NoneType' object has no attribute 'write'".
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))

    def log_uncaught(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback))

    def log_thread_exception(args):
        if args.exc_type is SystemExit:
            return
        thread_name = args.thread.name if args.thread else "unknown"
        logger.error(
            f"Uncaught exception in thread {thread_name}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    def log_unraisable(unraisable):
        logger.error(
            "Unraisable exception: %s (%r)",
            unraisable.err_msg or "", unraisable.object,
            exc_info=(unraisable.exc_type, unraisable.exc_value,
                      unraisable.exc_traceback))

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread_exception
    sys.unraisablehook = log_unraisable

    _qt_logger = logger
    qInstallMessageHandler(_log_qt_message)

    if crash_log is not None and _crash_file is None:
        mkdir_if_none(crash_log.parent)
        _crash_file = open(crash_log, "a", encoding="utf-8")
        faulthandler.enable(file=_crash_file, all_threads=True)


def dump_threads_later(seconds: float):
    """Write the stack of every thread into the crash log after a delay.

    Arm it when closing the application: if the process is still alive after
    the delay, the dump shows what keeps it alive. It does nothing when
    install_exception_logging() was given no crash log.

    Args:
        seconds (float): Delay before the dump.
    """
    if _crash_file is not None:
        faulthandler.dump_traceback_later(
            seconds, repeat=False, file=_crash_file)


def test_run():
    """Test function for the Qt logger."""
    Log = Logger(Path(__file__).name)
    logger = Log.logger

    gui_stream_handler = QtLogHandler()
    gui_stream_handler.setFormatter(Log.formatter)
    gui_stream_handler.setLevel(logging.WARNING)
    logger.addHandler(gui_stream_handler)

    # Test app start
    app = QApplication(sys.argv)
    w = LogWidget(gui_stream_handler, Path(__file__).name)
    w.show()

    # Log display test messages
    logger.debug("Debug")
    logger.info("Info")
    logger.warning("Warning")
    logger.error("Error")
    logger.critical("Critical")

    sys.exit(app.exec_())


if __name__ == "__main__":
    test_run()
