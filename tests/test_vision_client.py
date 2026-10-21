from unittest.mock import Mock

import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from app.vision_client import VisionClient, VisionClientError


@pytest.fixture
def client():
    instance = VisionClient(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test/vision-model",
    )

    # Replace the real API method with a mock.
    instance.client.chat.completions.create = Mock()

    return instance


def test_empty_image_is_rejected_before_api_call(client):
    with pytest.raises(ValueError, match="Base64 data"):
        client.analyze_image("", "image/jpeg", "Describe this image.")

    client.client.chat.completions.create.assert_not_called()


def test_unsupported_mime_type_is_rejected(client):
    with pytest.raises(ValueError, match="Unsupported image MIME type"):
        client.analyze_image("dGVzdA==", "image/gif", "Describe this image.")

    client.client.chat.completions.create.assert_not_called()


def test_empty_model_content_is_rejected(client):
    message = Mock()
    message.content = "   "
    message.refusal = None

    choice = Mock()
    choice.message = message
    choice.finish_reason = "stop"

    response = Mock()
    response.choices = [choice]
    response.model = "test/vision-model"

    client.client.chat.completions.create.return_value = response

    with pytest.raises(VisionClientError, match="empty or non-text"):
        client.analyze_image("dGVzdA==", "image/jpeg", "Describe this image.")


def test_authentication_error_has_clear_message(client):
    client.client.chat.completions.create.side_effect = AuthenticationError(
        message="Unauthorized",
        response=Mock(status_code=401, headers={}),
        body={"error": "Unauthorized"},
    )

    with pytest.raises(VisionClientError, match="Authentication failed"):
        client.analyze_image("dGVzdA==", "image/jpeg", "Describe this image.")


def test_rate_limit_error_has_clear_message(client):
    client.client.chat.completions.create.side_effect = RateLimitError(
        message="Rate limited",
        response=Mock(status_code=429, headers={}),
        body={"error": "Rate limited"},
    )

    with pytest.raises(VisionClientError, match="Rate limit"):
        client.analyze_image("dGVzdA==", "image/jpeg", "Describe this image.")


def test_timeout_error_has_clear_message(client):
    client.client.chat.completions.create.side_effect = APITimeoutError(
        request=Mock()
    )

    with pytest.raises(VisionClientError, match="timed out"):
        client.analyze_image("dGVzdA==", "image/jpeg", "Describe this image.")


def test_connection_error_has_clear_message(client):
    client.client.chat.completions.create.side_effect = APIConnectionError(
        request=Mock()
    )

    with pytest.raises(VisionClientError, match="Could not connect"):
        client.analyze_image("dGVzdA==", "image/jpeg", "Describe this image.")