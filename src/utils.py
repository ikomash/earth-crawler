from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import IntEnum
import logging
from pathlib import Path
import time
from typing import Any, Callable, Optional, Union, Iterable
from webcolors import name_to_hex, normalize_hex


def read_qss(file_path: Union[str, Path]) -> str:
    """
    Reads qss styles from a file.

    Args:
        file_path (Union[str, Path]): Path to the qss file.

    Returns:
        str: String suitable for pyQt's .setStyleSheet().
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError
    return file_path.read_text(encoding="utf-8")


def check_folder_existance(folder: Union[str, Path]):
    """
    Checks whether folder exists or not. If not - creates new one.

    Args:
        folder (Union[str, Path]): Folder path.
    """
    if isinstance(folder, str):
        folder = Path(folder)
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)


def get_color(color_str: str) -> str:
    """
    Converts CSS3 color name or normalizes HEX color code to
    format accepted by QT.

    Args:
        color_str (str): String with HEX color code or CSS3 color name

    Returns:
        str: Normalized HEX color code string
    """
    color_value = color_str.strip()
    hex_candidate = color_value
    if not hex_candidate.startswith("#"):
        hex_candidate = f"#{hex_candidate}"

    try:
        normal_hex = normalize_hex(hex_candidate).lower()
        return normal_hex
    except ValueError:
        pass
    try:
        normal_hex = name_to_hex(color_value).lower()
        return normal_hex
    except ValueError:
        logging.exception(
            "Parameter 'line_color' from 'config.ini' set incorrectly, "
            "using default 'red' (#ff0000) value instead"
        )
        return "#ff0000"


def validate_str_dir(path_str: str, alt_path: Path) -> Path:
    """Validate a directory path and fall back to a safe alternative if needed.

    Args:
        path_str (str): Path string to validate.
        alt_path (Path): Fallback directory to use when the input is empty or
            invalid.

    Returns:
        Path: Existing directory path to use.
    """
    is_empty = not path_str.strip()

    if is_empty:
        alt_path.mkdir(parents=True, exist_ok=True)
        return alt_path

    path = Path(path_str).resolve()
    if path.exists() and path.is_dir():
        return path

    alt_path.mkdir(parents=True, exist_ok=True)
    return alt_path


def format_size(bytes_size: int, binary: bool = True) -> str:
    """Format a size in bytes into a human-readable string with units.

    Args:
        bytes_size (int): Size in bytes to format.
        binary (bool, optional):
            Whether to use binary (1024) or decimal (1000) units.
            Defaults to True.

    Raises:
        ValueError: If the size is negative.

    Returns:
        str: Formatted size string.
    """
    if int(bytes_size) < 0:
        raise ValueError("Size cannot be negative")

    factor = 1024 if binary else 1000
    # Units of measurement
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

    size = float(bytes_size)
    unit_index = 0

    # Divide by factor, while the number is greater than the base factor
    while size >= factor and unit_index < len(units) - 1:
        size /= factor
        unit_index += 1

    # Format the string: .2f ensures exactly 2 decimal places
    return f"{size:.2f} {units[unit_index]}"


def normalize_value(
    value: Any,
    converter: Optional[Callable[[str], Any]] = None,
    strip: bool = True,
    separator: Optional[str] = ","
) -> list[Any]:
    """
    Converts a value to a list of normalized elements.

    Args:
        value (Any): Value or list of values.
        converter (Optional[Callable[[str], Any]], optional):
            Function for converting a string to the target type.
            If None, returns the string without conversion. Defaults to None.
        strip (bool, optional):
            Whether to strip whitespace from the string. Defaults to True.
        separator (Optional[str], optional):
            Delimiter used to split string values. If None, strings are not
            split. Defaults to ",".

    Returns:
        list[Any]: List of normalized elements.

    Example:
        >>> normalize_value("tcp, udp", lambda x: x.upper())
        ['TCP', 'UDP']

        >>> normalize_value("1883, 8883", int)
        [1883, 8883]

        >>> normalize_value(["value1", "value2"], str)
        ['value1', 'value2']
    """
    if value is None:
        return []

    # If already a list or tuple
    if isinstance(value, (list, tuple)):
        items = value
    # If it's a string with separators
    elif separator and isinstance(value, str) and separator in value:
        items = [
            v.strip() if strip else v for v in value.split(separator)
            if v.strip()
        ]
    else:
        items = [value]

    result = []
    for item in items:
        item_str = str(item)
        if strip:
            item_str = item_str.strip()
        if not item_str:
            continue

        if converter:
            result.append(converter(item_str))
        else:
            result.append(item_str)  # type: ignore

    return result


class ValueSpecDefault(IntEnum):
    MAX = 11
    MIN = 2
    VALUE = 4


@dataclass
class ValueSpecEntry:
    """Parsed search entry with its administrative levels and metadata.

    Attributes:
        name (str): Object name to search.
        levels (list[int]): Sorted list of unique administrative levels.
        default_level (int): Default level, applied when no explicit value
            was given in the source string.
        default_max (int): Upper bound used when parsing an open-ended
            range like "[3,]".
        default_min (int): Lower bound used when parsing an open-ended
            range like "[,9]".
        explicit (bool): True if the source string specified an explicit
            value (any of "5", "[3,6]", "[,9]", "(1,4)"); False if the
            level came from `default_level` only.
    """

    name: str
    levels: list[int]
    default_level: int = ValueSpecDefault.VALUE
    default_max: int = ValueSpecDefault.MAX
    default_min: int = ValueSpecDefault.MIN
    explicit: bool = False

    def is_default(self) -> bool:
        """Return True if the entry only carries the default level.

        Returns:
            bool: True when the source string had no explicit value,
                so levels is exactly [default_level].
        """
        return not self.explicit

    def format(self, sep: str = "|") -> str:
        """Format levels as a separator-delimited string.

        Args:
            sep (str): Separator between values. Defaults to "|".

        Returns:
            str: Joined levels, e.g. "3|4|5|6".
        """
        return sep.join(map(str, self.levels))


class ValueSpec:
    """Parser and formatter for compact numeric value specifications.

    Supported formats:
        "5"        -> single value
        "[3,6]"    -> inclusive range 3..6
        "[3,]"     -> range 3..default_max (inclusive)
        "[,9]"     -> range default_min..9 (inclusive)
        "[,]"      -> range default_min..default_max (inclusive)
        "(3,6)"    -> explicit list of values
    """

    @staticmethod
    def parse_spec(
        spec: str,
        default_max: int = ValueSpecEntry.default_max,
        default_min: int = ValueSpecEntry.default_min,
    ) -> list[int]:
        """Parse a value specification into a sorted list of unique ints.

        Args:
            spec (str):
                Value specification, e.g. "5", "[3,6]", "[3,]", "[,9]",
                "(3,6)".
            default_max (int):
                Upper bound used when the end of a range is omitted.
                Defaults to 11.
            default_min (int):
                Lower bound used when the start of a range is omitted.
                Defaults to 1.

        Returns:
            list[int]: Sorted list of unique integers.

        Raises:
            ValueError: If the specification is malformed or empty.
        """
        spec = spec.strip()

        if spec.startswith("[") and spec.endswith("]"):
            return ValueSpec._parse_range(spec, default_max, default_min)

        if spec.startswith("(") and spec.endswith(")"):
            return ValueSpec._parse_list(spec)

        return [ValueSpec._to_int(spec, spec, "value")]

    @staticmethod
    def parse_line(
        line: str,
        default_max: int = ValueSpecEntry.default_max,
        default_min: int = ValueSpecEntry.default_min,
        default_value: int = ValueSpecEntry.default_level,
    ) -> ValueSpecEntry:
        """Parse a 'Name=value' line into a ValueSpecEntry.

        Args:
            line (str): Source line in the form "Name=value".
            default_max (int): Upper bound for "[x,]". Defaults to 11.
            default_min (int): Lower bound for "[,y]". Defaults to 1.
            default_value (int): Default level used when the entry has
                no explicit value. Defaults to 4.

        Returns:
            ValueSpecEntry: Parsed entry with name, levels and metadata.

        Raises:
            ValueError: If the line has no '=', no name before it, or the
                value is malformed.
        """
        if "=" not in line:
            raise ValueError(f"Expected 'Name=value' format: {line!r}")
        name, _, value = line.partition("=")
        name = name.strip()
        if not name:
            raise ValueError(f"Missing object name before '=': {line!r}")
        levels = ValueSpec.parse_spec(value.strip(), default_max, default_min)
        return ValueSpecEntry(
            name=name,
            levels=levels,
            default_level=default_value,
            default_max=default_max,
            default_min=default_min,
            explicit=True,
        )

    @staticmethod
    def search_line_processing(
        search_line: str,
        default_value: int = ValueSpecEntry.default_level,
        default_max: int = ValueSpecEntry.default_max,
        default_min: int = ValueSpecEntry.default_min,
    ) -> list[ValueSpecEntry]:
        """Split a search string into a list of ValueSpecEntry objects.

        The input string contains object names and their administrative levels
        in the format "object1=value1; object2=value2; ...". Each value can be
        a single int, an inclusive range "[a,b]", an open range "[a,]",
        "[,b]", "[,]", or an explicit list "(a,b,c)". Objects without '='
        get only the default level and are marked as not explicit.

        Args:
            search_line (str):
                String with objects and their levels in format
                "object1=admin_level1; object2=admin_level2;...".
            default_value (int, optional):
                Default level used when not specified. Defaults to 4.
            default_max (int, optional):
                Upper bound when a range end is omitted. Defaults to 11.
            default_min (int, optional):
                Lower bound when a range start is omitted. Defaults to 1.

        Returns:
            list[ValueSpecEntry]: Parsed entries in source order.
        """
        result: list[ValueSpecEntry] = []
        for loc in search_line.split(";"):
            strp = loc.strip()
            if strp == "":
                continue

            if "=" in strp:
                result.append(
                    ValueSpec.parse_line(
                        strp, default_max, default_min, default_value
                    )
                )
            else:
                result.append(
                    ValueSpecEntry(
                        name=strp,
                        levels=[default_value],
                        default_level=default_value,
                        default_max=default_max,
                        default_min=default_min,
                        explicit=False,
                    )
                )

        return result

    @staticmethod
    def format_values(values: Iterable[int], sep: str = "|") -> str:
        """Join numeric values into a separator-delimited string.

        Args:
            values (Iterable[int]): Values to join.
            sep (str): Separator. Defaults to "|".

        Returns:
            str: Joined string, e.g. "3|4|5|6".
        """
        return sep.join(map(str, values))

    @staticmethod
    def apply_extra_value(
        entry: ValueSpecEntry,
        extra: int,
        replace_default: bool = True,
    ) -> ValueSpecEntry:
        """Insert `extra` at the front of entry.levels, or replace default.

        If the entry was not explicit (its levels came from `default_level`
        only) and `replace_default` is True, `extra` replaces the default
        level. Otherwise `extra` is prepended and the resulting list is
        sorted with duplicates removed.

        Args:
            entry (ValueSpecEntry): Entry to modify.
            extra (int): Value to insert or use as replacement.
            replace_default (bool): When True, replace default-only level
                with `extra` instead of prepending. Defaults to True.

        Returns:
            ValueSpecEntry: New entry with updated levels or the original entry
                if the extra value is out of bounds. The input entry is not
                mutated.
        """
        if extra < entry.default_min or extra > entry.default_max:
            return entry
        if entry.is_default() and replace_default:
            new_levels = [extra]
        else:
            new_levels = sorted({extra, *entry.levels})

        return ValueSpecEntry(
            name=entry.name,
            levels=new_levels,
            default_level=entry.default_level,
            default_max=entry.default_max,
            default_min=entry.default_min,
            explicit=True,
        )

    @staticmethod
    def _parse_range(
        spec: str,
        default_max: int = ValueSpecEntry.default_max,
        default_min: int = ValueSpecEntry.default_min,
    ) -> list[int]:
        """Parse an inclusive range spec like '[3,6]', '[3,]', '[,9]', '[,]'.

        Args:
            spec (str): Bracket-wrapped range specification.
            default_max (int): Upper bound when the end is omitted.
                Defaults to 11.
            default_min (int): Lower bound when the start is omitted.
                Defaults to 1.

        Returns:
            list[int]: Sorted list of unique integers in the inclusive range.

        Raises:
            ValueError: If the spec does not contain exactly two parts
                or a bound is not an integer.
        """
        body = spec[1:-1]
        parts = [p.strip() for p in body.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Range must contain 2 values: {spec!r}")

        start_s, end_s = parts
        start = (
            ValueSpec._to_int(start_s, spec, "start")
            if start_s
            else default_min
        )
        end = (
            ValueSpec._to_int(end_s, spec, "end") if end_s else default_max
        )
        if start > end:
            start, end = end, start

        return list(range(start, end + 1))

    @staticmethod
    def _parse_list(spec: str) -> list[int]:
        """Parse an explicit list spec like '(3,6,9)'.

        Args:
            spec (str): Parenthesis-wrapped comma-separated list.

        Returns:
            list[int]: Sorted list of unique integers.

        Raises:
            ValueError: If the list is empty after parsing or contains
                a non-integer value.
        """
        body = spec[1:-1]
        parts = [p.strip() for p in body.split(",") if p.strip()]
        if not parts:
            raise ValueError(f"Empty value list: {spec!r}")
        return sorted({ValueSpec._to_int(p, spec, "value") for p in parts})

    @staticmethod
    def _to_int(token: str, spec: str, part: str) -> int:
        """Convert a token to int, wrapping errors with context.

        Args:
            token (str): Raw token to convert, e.g. "3".
            spec (str): Original specification, used in the error message.
            part (str): Human-readable name of the part being parsed,
                e.g. "start", "end", "value".

        Returns:
            int: Parsed integer.

        Raises:
            ValueError: If the token is not a valid integer.
        """
        try:
            return int(token)
        except ValueError:
            raise ValueError(
                f"Invalid {part} in spec {spec!r}: {token!r} is not an integer"
            ) from None


class IndexCounter:
    """
    Iterator utility for managing sequential index values,
    such as rows or columns.

    Supports both iteration (`next(row)`) and calling the instance as a
    function (`row()`) to get the current index. You can also reset the
    counter or skip a specified number of steps.

    Example:
        row = IndexCounter()
        layout.addWidget(QLabel("Label"), next(row), 0)
        layout.addWidget(QLineEdit(), row(), 1)
    """

    def __init__(self, start: int = 0):
        """
        Initializes the index counter.

        Args:
            start (int): Initial index. Defaults to 0.
        """
        self._index = start

    def __next__(self):
        """
        Returns the current index and increments the counter.

        Returns:
            int: Index before incrementing.
        """
        value = self._index
        self._index += 1
        return value

    def __call__(self):
        """
        Allows calling the instance as a function to get the current index.

        Returns:
            int: Current index.
        """
        return self._index

    def skip(self, count: int = 1):
        """
        Skips a specified number of indices.

        Args:
            count (int): Number of indices to skip. Defaults to 1.
        """
        self._index += count

    def reset(self, value: int = 0):
        """
        Resets the counter to the specified value.

        Args:
            value (int): New starting value. Defaults to 0.
        """
        self._index = value


class UiUpdateBuffer:
    """Collects GUI updates that arrive faster than the GUI can draw them.

    A worker thread can send thousands of points and progress steps per
    second. Drawing each one in its own slot keeps the GUI thread so busy
    that the window stops reacting. This buffer sits between the slots and
    the widgets: the slots only store updates, and a timer applies them in
    short portions, so the event loop gets time for the user's clicks.

    Two kinds of updates are kept apart:
        items: things that must all be applied, in order (map points).
        values: state where only the newest one matters (progress value,
            label text). A newer value replaces an older one with the same
            key.

    Not thread safe: use it from the GUI thread only, which is where Qt runs
    the slots.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        """
        Args:
            clock (Callable[[], float]): Time source in seconds. Replaceable
                for tests.
        """
        self._clock = clock
        self._items: deque = deque()
        self._values: dict[str, Any] = {}

    def add_item(self, item: Any):
        """Queue an item that must be applied later, in order."""
        self._items.append(item)

    def set_value(self, key: str, value: Any):
        """Remember the newest value for ``key``, replacing an older one."""
        self._values[key] = value

    def discard_value(self, key: str):
        """Forget a pending value, for example because it became stale."""
        self._values.pop(key, None)

    def pop_values(self) -> dict[str, Any]:
        """Return all pending values and forget them."""
        values, self._values = self._values, {}
        return values

    def drain(
            self, apply_item: Callable[[Any], None],
            budget: float = 0.015) -> bool:
        """Apply queued items until the time budget is used up.

        At least one item is applied per call, so a slow item can never stop
        the queue from advancing.

        Args:
            apply_item (Callable[[Any], None]): Draws one item.
            budget (float): Seconds this call may take, apart from the last
                item, which is always finished.

        Returns:
            bool: True if no items are left.
        """
        end = self._clock() + budget
        while self._items:
            apply_item(self._items.popleft())
            if self._clock() >= end:
                break
        return not self._items

    def has_items(self) -> bool:
        """Return True if queued items are waiting."""
        return bool(self._items)

    def has_work(self) -> bool:
        """Return True if items or values are waiting."""
        return bool(self._items or self._values)

    def clear_items(self):
        """Drop all queued items, for example when the map is cleared."""
        self._items.clear()

    def clear(self):
        """Drop everything, for example when the search is cancelled."""
        self._items.clear()
        self._values.clear()
