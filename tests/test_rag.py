
from unittest.mock import MagicMock, patch

import pytest

import app.rag as rag
from app.llm_client import LLMClientError


def test_empty_question_is_rejected():
    with pytest.raises(ValueError, match="Question cannot be empty"):
        rag.answer_question("   ")


def test_invalid_top_k_is_rejected():
    with pytest.raises(ValueError, match="top_k must be at least 1"):
        rag.answer_question("What is in the image?", top_k=0)


def test_empty_database_returns_helpful_message():
    fake_store = MagicMock()
    fake_store.count.return_value = 0

    with (
        patch.object(rag, "ChromaStore", return_value=fake_store),
        patch.object(rag, "TextEmbedder") as mock_embedder,
        patch.object(rag, "LLMClient") as mock_llm,
    ):
        result = rag.answer_question("What is in the image?")

    assert "No reports are indexed yet" in result
    mock_embedder.assert_not_called()
    mock_llm.assert_not_called()


def test_successful_rag_query_uses_retrieved_evidence():
    fake_store = MagicMock()
    fake_store.count.return_value = 2
    fake_store.search.return_value = {
        "ids": [["spiderman profile_report.json"]],
        "documents": [
            [
                "Image description: Spider-Man illustration. "
                "Extracted data: pink bow."
            ]
        ],
        "metadatas": [
            [
                {
                    "image_filename": "spiderman profile",
                    "confidence": "High",
                }
            ]
        ],
        "distances": [[0.25]],
    }

    fake_embedder = MagicMock()
    fake_embedder.embed_text.return_value = [0.1, 0.2, 0.3]

    fake_llm = MagicMock()
    fake_llm.generate.return_value = (
        "The Spider-Man image contains a pink bow. "
        "Source: spiderman profile_report.json"
    )

    with (
        patch.object(rag, "ChromaStore", return_value=fake_store),
        patch.object(rag, "TextEmbedder", return_value=fake_embedder),
        patch.object(rag, "LLMClient", return_value=fake_llm),
    ):
        answer = rag.answer_question("Which image contains a pink bow?")

    assert "pink bow" in answer
    assert "spiderman profile_report.json" in answer

    fake_embedder.embed_text.assert_called_once_with(
        "Which image contains a pink bow?"
    )
    fake_store.search.assert_called_once_with(
        query_embedding=[0.1, 0.2, 0.3],
        top_k=3,
    )

    # Confirm the language model received the retrieved report as evidence.
    _, user_prompt = fake_llm.generate.call_args.args
    assert "spiderman profile_report.json" in user_prompt
    assert "pink bow" in user_prompt
    assert "Spider-Man illustration" in user_prompt


def test_generation_error_is_propagated():
    fake_store = MagicMock()
    fake_store.count.return_value = 1
    fake_store.search.return_value = {
        "ids": [["github1_report.json"]],
        "documents": [["Image description: GitHub logo. Text: GitHub."]],
        "metadatas": [
            [{"image_filename": "github1", "confidence": "High"}]
        ],
        "distances": [[0.2]],
    }

    fake_embedder = MagicMock()
    fake_embedder.embed_text.return_value = [0.1, 0.2, 0.3]

    fake_llm = MagicMock()
    fake_llm.generate.side_effect = LLMClientError(
        "The text-generation request timed out."
    )

    with (
        patch.object(rag, "ChromaStore", return_value=fake_store),
        patch.object(rag, "TextEmbedder", return_value=fake_embedder),
        patch.object(rag, "LLMClient", return_value=fake_llm),
    ):
        with pytest.raises(LLMClientError, match="timed out"):
            rag.answer_question("What text appears in the logo?")
