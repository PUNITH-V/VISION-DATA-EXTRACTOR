
from pathlib import Path

from app.main import parse_args


def test_image_path_is_optional():
    args = parse_args([])

    assert args.image_path is None


def test_accepts_a_single_image_path():
    args = parse_args(["input/chart.png"])

    assert args.image_path == Path("input/chart.png")
