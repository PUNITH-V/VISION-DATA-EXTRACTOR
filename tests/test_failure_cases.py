import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import app.main as main
from app.schemas import VisionExtractionReport


VALID_RESPONSE = json.dumps(
    {
        "image_description": "A GitHub logo.",
        "extracted_data": [
            {"label": "Company Name", "value": "GitHub"}
        ],
        "confidence": "High",
    }
)


@pytest.fixture
def setup_processing(tmp_path, monkeypatch):
    """Prepare a temporary input image and output directory."""

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"

    input_dir.mkdir()
    output_dir.mkdir()

    image_path = input_dir / "github.jpeg"
    image_path.write_bytes(b"test image placeholder")

    monkeypatch.setattr(main, "OUTPUT_DIR", output_dir)

    # Keep tests independent of Pillow and actual image files.
    monkeypatch.setattr(
        main,
        "load_image",
        lambda path: {
            "image_base64": "dGVzdA==",
            "mime_type": "image/jpeg",
        },
    )

    client = Mock()
    client.analyze_image.return_value = VALID_RESPONSE

    return image_path, output_dir, client


def test_valid_response_is_saved(setup_processing):
    image_path, output_dir, client = setup_processing

    report_path = main.process_image(image_path, client)

    assert report_path.exists()

    saved_data = json.loads(report_path.read_text(encoding="utf-8"))
    report = VisionExtractionReport.model_validate(saved_data)

    assert report.confidence == "High"
    assert report.extracted_data[0].value == "GitHub"
    client.analyze_image.assert_called_once()


@pytest.mark.parametrize(
    "bad_response",
    [
        "",
        "User Safety: safe",
        "This is not JSON",
        '{"image_description": "Missing fields"}',
        json.dumps(
            {
                "image_description": "Test image",
                "extracted_data": [],
                "confidence": "Very High",
            }
        ),
        "```json\nnot valid JSON\n```",
        "[]",
    ],
)
def test_invalid_response_is_rejected_and_not_saved(
    setup_processing,
    bad_response,
):
    image_path, output_dir, client = setup_processing
    client.analyze_image.return_value = bad_response

    with pytest.raises(ValueError):
        main.process_image(image_path, client)

    assert not (output_dir / "github_report.json").exists()
    assert not (output_dir / "github_report.json.tmp").exists()


def test_invalid_response_does_not_overwrite_existing_report(
    setup_processing,
):
    image_path, output_dir, client = setup_processing

    report_path = output_dir / "github_report.json"
    original_content = '{"original": "keep this report"}'
    report_path.write_text(original_content, encoding="utf-8")

    client.analyze_image.return_value = "User Safety: safe"

    with pytest.raises(FileExistsError):
        main.process_image(image_path, client)

    # Existing reports are skipped by default.
    assert report_path.read_text(encoding="utf-8") == original_content
    client.analyze_image.assert_not_called()


def test_overwrite_preserves_existing_report_on_invalid_response(
    setup_processing,
):
    image_path, output_dir, client = setup_processing

    report_path = output_dir / "github_report.json"
    original_content = '{"original": "keep this report"}'
    report_path.write_text(original_content, encoding="utf-8")

    client.analyze_image.return_value = "User Safety: safe"

    with pytest.raises(ValueError):
        main.process_image(image_path, client, overwrite=True)

    assert report_path.read_text(encoding="utf-8") == original_content
    assert not (output_dir / "github_report.json.tmp").exists()


def test_api_error_does_not_create_report(setup_processing):
    image_path, output_dir, client = setup_processing

    from app.vision_client import VisionClientError

    client.analyze_image.side_effect = VisionClientError(
        "Rate limit or model quota reached."
    )

    with pytest.raises(VisionClientError):
        main.process_image(image_path, client)

    assert not (output_dir / "github_report.json").exists()
    assert not (output_dir / "github_report.json.tmp").exists()