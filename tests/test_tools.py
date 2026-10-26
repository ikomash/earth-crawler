import pytest

from tools import (
    FileNames,
    SkipModes,
    compare_file_with_bytes,
    download_flag,
    file_hash,
)


def test_file_hash_and_compare_file_with_bytes(tmp_path):
    path = tmp_path / "data.bin"
    content = b"same-data"
    path.write_bytes(content)

    assert file_hash(path) == file_hash(path)
    assert compare_file_with_bytes(path, content)
    assert not compare_file_with_bytes(path, b"different")
    assert not compare_file_with_bytes(tmp_path / "missing", content)


def test_download_flag_uses_local_file_when_skip_mode_is_skip(
        tmp_path, monkeypatch):
    path = tmp_path / "de.svg"
    path.write_bytes(b"cached")
    monkeypatch.setattr(
        "tools.requests.get",
        lambda *args, **kwargs: pytest.fail("network called")
    )

    language, country = download_flag(
        "de", tmp_path, file_names=FileNames.LANGUAGE,
        skip_mode=SkipModes.SKIP,
    )

    assert (language, country) == ("de", "de")
    assert path.read_bytes() == b"cached"


def test_download_flag_writes_successful_response(tmp_path, monkeypatch):
    class Response:
        status_code = 200
        content = b"<svg />"

    monkeypatch.setattr(
        "tools.requests.get", lambda *args, **kwargs: Response())

    language, country = download_flag(
        "en", tmp_path, file_names=FileNames.COUNTRY,
        skip_mode=SkipModes.OVERWRITE,
    )

    assert (language, country) == ("en", "us")
    assert (tmp_path / "us.svg").read_bytes() == b"<svg />"


def test_download_flag_returns_for_not_found_without_writing(
        tmp_path, monkeypatch):
    class Response:
        status_code = 404

    monkeypatch.setattr(
        "tools.requests.get", lambda *args, **kwargs: Response()
    )

    download_flag("zz", tmp_path, skip_mode=SkipModes.OVERWRITE)

    assert list(tmp_path.iterdir()) == []
