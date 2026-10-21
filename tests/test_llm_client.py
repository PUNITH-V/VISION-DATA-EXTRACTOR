
from unittest.mock import MagicMock, patch

import pytest

from app.llm_client import LLMClient, LLMClientError


def test_status_message_is_not_returned_as_an_answer():
    client = LLMClient(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
    )

    fake_response = MagicMock()
    fake_response.model = "test-model"
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = "User Safety: safe"

    with patch.object(
        client.client.chat.completions,
        "create",
        return_value=fake_response,
    ) as mock_create:
        with pytest.raises(LLMClientError, match="status message"):
            client.generate(
                system_prompt="You are a helpful assistant.",
                user_prompt="Describe the image.",
            )

    mock_create.assert_called_once()
