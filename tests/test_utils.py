"""Tests for utils.py. The real webcolors is used, nothing is stubbed."""
import pytest

from utils import (
    IndexCounter,
    ValueSpec,
    ValueSpecDefault,
    ValueSpecEntry,
    check_folder_existance,
    get_color,
    normalize_value,
    read_qss,
    validate_str_dir,
)


@pytest.mark.parametrize("raw, expected", [
    ("red", "#ff0000"),
    ("Blue", "#0000ff"),
    ("green", "#008000"),
    ("#FF0000", "#ff0000"),
    ("ff0000", "#ff0000"),
    ("#f00", "#ff0000"),
    ("  blue  ", "#0000ff"),
    (" #00F ", "#0000ff"),
])
def test_get_color_accepts_names_and_hex_codes(raw, expected):
    assert get_color(raw) == expected


@pytest.mark.parametrize("raw", ["nonsense", "", "   ", "#12", "#gggggg"])
def test_get_color_falls_back_to_red_and_logs(raw, caplog):
    assert get_color(raw) == "#ff0000"
    assert "set incorrectly" in caplog.text


def test_get_color_does_not_log_for_valid_colors(caplog):
    get_color("blue")
    get_color("#abc")
    assert caplog.text == ""


@pytest.mark.parametrize("as_text", [False, True])
def test_check_folder_existance_creates_nested_folders(tmp_path, as_text):
    folder = tmp_path / "a" / "b" / "c"
    check_folder_existance(str(folder) if as_text else folder)
    assert folder.is_dir()


def test_check_folder_existance_keeps_an_existing_folder(tmp_path):
    (tmp_path / "note.txt").write_text("keep me")
    check_folder_existance(tmp_path)
    check_folder_existance(tmp_path)
    assert (tmp_path / "note.txt").read_text() == "keep me"


@pytest.mark.parametrize("empty", ["", "   "])
def test_validate_str_dir_empty_path_gives_the_fallback(tmp_path, empty):
    fallback = tmp_path / "fallback"
    assert validate_str_dir(empty, fallback) == fallback
    assert fallback.is_dir()


def test_validate_str_dir_keeps_an_existing_directory(tmp_path):
    existing = tmp_path / "data"
    existing.mkdir()
    fallback = tmp_path / "fallback"

    assert validate_str_dir(str(existing), fallback) == existing.resolve()
    assert not fallback.exists()


def test_validate_str_dir_missing_directory_gives_the_fallback(tmp_path):
    fallback = tmp_path / "fallback"
    result = validate_str_dir(str(tmp_path / "missing"), fallback)
    assert result == fallback
    assert fallback.is_dir()


def test_validate_str_dir_a_file_is_not_a_directory(tmp_path):
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    fallback = tmp_path / "fallback"

    assert validate_str_dir(str(a_file), fallback) == fallback


@pytest.mark.parametrize("as_text", [False, True])
def test_read_qss_returns_the_file_content(tmp_path, as_text):
    qss = tmp_path / "style.qss"
    qss.write_text("QWidget { color: red; }\n")
    assert read_qss(str(qss) if as_text else qss) == \
        "QWidget { color: red; }\n"


def test_read_qss_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_qss(tmp_path / "missing.qss")


def test_read_qss_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_qss(tmp_path)


@pytest.mark.parametrize("value, kwargs, expected", [
    (None, {}, []),
    ("tcp, udp", {"converter": str.upper}, ["TCP", "UDP"]),
    ("1883, 8883", {"converter": int}, [1883, 8883]),
    (["value1", "value2"], {"converter": str}, ["value1", "value2"]),
    (("a", " b "), {}, ["a", "b"]),
    ("single", {}, ["single"]),
    ("a,,b, ,", {}, ["a", "b"]),
    ("", {}, []),
    (5, {}, ["5"]),
    (5, {"converter": int}, [5]),
    ("a;b", {"separator": ";"}, ["a", "b"]),
    ("a, b", {"separator": None}, ["a, b"]),
    (["a", "", "  "], {}, ["a"]),
    (" a , b ", {"strip": False}, [" a ", " b "]),
])
def test_normalize_value(value, kwargs, expected):
    assert normalize_value(value, **kwargs) == expected


def test_normalize_value_passes_converter_errors_through():
    with pytest.raises(ValueError):
        normalize_value("1, x", int)


def test_value_spec_defaults():
    assert (ValueSpecDefault.MIN, ValueSpecDefault.MAX) == (2, 11)
    assert ValueSpecDefault.VALUE == 4


def test_entry_defaults_and_helpers():
    entry = ValueSpecEntry(name="Riga", levels=[3, 4, 5])

    assert entry.default_level == 4
    assert entry.explicit is False
    assert entry.is_default() is True
    assert entry.format() == "3|4|5"
    assert entry.format(sep=",") == "3,4,5"


def test_entry_is_not_default_when_explicit():
    assert ValueSpecEntry("A", [4], explicit=True).is_default() is False


@pytest.mark.parametrize("spec, expected", [
    ("5", [5]),
    (" 5 ", [5]),
    ("[3,6]", [3, 4, 5, 6]),
    ("[ 3 , 6 ]", [3, 4, 5, 6]),
    ("[3,]", list(range(3, 12))),
    ("[,9]", list(range(2, 10))),
    ("[,]", list(range(2, 12))),
    ("[6,3]", [3, 4, 5, 6]),
    ("(3,6)", [3, 6]),
    ("(6,3,3)", [3, 6]),
])
def test_parse_spec(spec, expected):
    assert ValueSpec.parse_spec(spec) == expected


def test_parse_spec_uses_the_given_bounds():
    assert ValueSpec.parse_spec("[3,]", default_max=5) == [3, 4, 5]
    assert ValueSpec.parse_spec("[,4]", default_min=1) == [1, 2, 3, 4]
    assert ValueSpec.parse_spec("[,]", default_max=4, default_min=3) == [3, 4]


@pytest.mark.parametrize("spec, message", [
    ("[1,2,3]", "must contain 2 values"),
    ("[1]", "must contain 2 values"),
    ("abc", "not an integer"),
    ("", "not an integer"),
    ("[3,6", "not an integer"),
    ("[a,5]", "Invalid start"),
    ("[1,b]", "Invalid end"),
    ("()", "Empty value list"),
    ("(1,x)", "Invalid value"),
])
def test_parse_spec_rejects_malformed_input(spec, message):
    with pytest.raises(ValueError, match=message):
        ValueSpec.parse_spec(spec)


def test_parse_line_builds_an_explicit_entry():
    entry = ValueSpec.parse_line("Latvia=[3,5]")

    assert entry.name == "Latvia"
    assert entry.levels == [3, 4, 5]
    assert entry.explicit is True
    assert entry.default_level == 4


def test_parse_line_strips_name_and_value_and_keeps_the_defaults():
    entry = ValueSpec.parse_line(
        "  Riga  =  5 ", default_max=9, default_min=3, default_value=6)

    assert (entry.name, entry.levels) == ("Riga", [5])
    assert (entry.default_max, entry.default_min) == (9, 3)
    assert entry.default_level == 6


@pytest.mark.parametrize("line, message", [
    ("Latvia", "Expected 'Name=value'"),
    ("=5", "Missing object name"),
    ("  =5", "Missing object name"),
    ("Latvia=", "not an integer"),
    ("Latvia=5=6", "not an integer"),
])
def test_parse_line_rejects_malformed_lines(line, message):
    with pytest.raises(ValueError, match=message):
        ValueSpec.parse_line(line)


def test_search_line_mixes_explicit_and_default_entries():
    entries = ValueSpec.search_line_processing(
        "Latvia; Estonia=5; ; Lithuania=[3,]")

    assert [e.name for e in entries] == ["Latvia", "Estonia", "Lithuania"]
    assert [e.levels for e in entries] == [
        [4], [5], list(range(3, 12))]
    assert [e.explicit for e in entries] == [False, True, True]


def test_search_line_uses_the_given_defaults():
    entries = ValueSpec.search_line_processing(
        "A; B=[3,]", default_value=6, default_max=5, default_min=1)

    assert entries[0].levels == [6]
    assert entries[0].default_level == 6
    assert entries[1].levels == [3, 4, 5]
    assert entries[1].default_max == 5


@pytest.mark.parametrize("line", ["", "   ", ";;", " ; ; "])
def test_search_line_without_entries_is_empty(line):
    assert ValueSpec.search_line_processing(line) == []


def test_search_line_ignores_a_trailing_semicolon():
    assert len(ValueSpec.search_line_processing("A=5;")) == 1


@pytest.mark.parametrize("line", ["A=[1,2,3]", "A=x", "=5", "A; B=("])
def test_search_line_reports_malformed_entries(line):
    with pytest.raises(ValueError):
        ValueSpec.search_line_processing(line)


def test_format_values():
    assert ValueSpec.format_values([3, 4, 5]) == "3|4|5"
    assert ValueSpec.format_values(iter([1, 2]), sep=",") == "1,2"
    assert ValueSpec.format_values([]) == ""


def default_entry():
    return ValueSpecEntry(name="Riga", levels=[4], explicit=False)


def test_apply_extra_value_replaces_a_default_level():
    entry = default_entry()

    result = ValueSpec.apply_extra_value(entry, 6)

    assert result.levels == [6]
    assert result.explicit is True
    assert result.name == "Riga"


def test_apply_extra_value_can_keep_the_default_level():
    result = ValueSpec.apply_extra_value(
        default_entry(), 6, replace_default=False)

    assert result.levels == [4, 6]
    assert result.explicit is True


def test_apply_extra_value_adds_to_an_explicit_entry():
    entry = ValueSpecEntry("Riga", [3, 5], explicit=True)

    result = ValueSpec.apply_extra_value(entry, 4)

    assert result.levels == [3, 4, 5]


def test_apply_extra_value_does_not_duplicate_levels():
    entry = ValueSpecEntry("Riga", [3, 5], explicit=True)
    assert ValueSpec.apply_extra_value(entry, 5).levels == [3, 5]


@pytest.mark.parametrize("extra", [1, 12, 0, 100])
def test_apply_extra_value_ignores_out_of_bounds_values(extra):
    entry = default_entry()
    assert ValueSpec.apply_extra_value(entry, extra) is entry


@pytest.mark.parametrize("extra", [2, 11])
def test_apply_extra_value_bounds_are_inclusive(extra):
    result = ValueSpec.apply_extra_value(default_entry(), extra)
    assert result.levels == [extra]


def test_apply_extra_value_does_not_mutate_its_input():
    entry = ValueSpecEntry("Riga", [3, 5], explicit=True)

    ValueSpec.apply_extra_value(entry, 4)

    assert entry.levels == [3, 5]
    assert entry.explicit is True


def test_apply_extra_value_keeps_the_entry_settings():
    entry = ValueSpecEntry(
        "Riga", [4], default_level=6, default_max=9, default_min=3)

    result = ValueSpec.apply_extra_value(entry, 5)

    assert (result.default_level, result.default_max, result.default_min) \
        == (6, 9, 3)


def test_index_counter_next_returns_then_increments():
    row = IndexCounter()
    assert [next(row), next(row), next(row)] == [0, 1, 2]


def test_index_counter_call_reads_without_incrementing():
    row = IndexCounter(5)
    assert row() == 5
    assert row() == 5
    assert next(row) == 5
    assert row() == 6


def test_index_counter_skip_and_reset():
    row = IndexCounter()
    next(row)
    row.skip()
    assert row() == 2
    row.skip(3)
    assert row() == 5
    row.reset()
    assert row() == 0
    row.reset(10)
    assert next(row) == 10


def test_index_counter_layout_usage_pattern():
    row = IndexCounter()
    placed = [(next(row), 0), (row(), 1)]
    assert placed == [(0, 0), (1, 1)]
