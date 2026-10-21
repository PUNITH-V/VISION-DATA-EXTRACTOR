
import pytest

from app.image_discovery import discover_images


def test_discovers_only_top_level_supported_images(tmp_path):
    (tmp_path / "chart.png").write_bytes(b"placeholder")
    (tmp_path / "photo.JPG").write_bytes(b"placeholder")
    (tmp_path / "notes.txt").write_text("not an image")

    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.png").write_bytes(b"placeholder")

    images = discover_images(tmp_path)

    assert [path.name for path in images] == [
        "chart.png",
        "photo.JPG",
    ]


def test_returns_empty_list_when_no_images_exist(tmp_path):
    (tmp_path / "notes.txt").write_text("nothing to process")

    assert discover_images(tmp_path) == []


def test_rejects_a_missing_directory(tmp_path):
    missing_dir = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        discover_images(missing_dir)
