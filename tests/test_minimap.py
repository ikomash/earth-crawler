from unittest.mock import MagicMock

import minimap


def test_set_point_creates_tmp_folder_and_saves_image(
        tmp_path, monkeypatch):
    output_folder = tmp_path / "tmp"
    savefig = MagicMock()
    monkeypatch.setattr(minimap.Paths, "tmp_folder", output_folder)
    monkeypatch.setattr(minimap.plt, "savefig", savefig)

    widget = minimap.MplMinimap.__new__(minimap.MplMinimap)
    widget.m = MagicMock()
    widget.sc = None

    widget.set_point(40.0, 20.0, 0)

    assert output_folder.is_dir()
    savefig.assert_called_once_with(
        str(output_folder / "minimap_0.png"), dpi=200)
