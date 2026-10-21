
import pytest
from pydantic import ValidationError

from app.schemas import VisionExtractionReport


def test_valid_report():
    data = {
        "image_description": "A GitHub logo",
        "extracted_data": [
            {"label": "Text", "value": "GitHub"}
        ],
        "confidence": "High",
    }

    report = VisionExtractionReport.model_validate(data)

    assert report.confidence == "High"
    assert report.extracted_data[0].value == "GitHub"


def test_invalid_confidence():
    data = {
        "image_description": "A GitHub logo",
        "extracted_data": [],
        "confidence": "Extremely High",
    }

    with pytest.raises(ValidationError):
        VisionExtractionReport.model_validate(data)


def test_missing_nested_value():
    data = {
        "image_description": "A GitHub logo",
        "extracted_data": [{"label": "Text"}],
        "confidence": "High",
    }

    with pytest.raises(ValidationError):
        VisionExtractionReport.model_validate(data)
