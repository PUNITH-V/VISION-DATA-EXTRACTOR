
from sentence_transformers import SentenceTransformer


class TextEmbedder:
    """Convert text into numerical vectors using a local embedding model."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Convert multiple text strings into embedding vectors."""
        if not texts:
            return []

        if any(not text.strip() for text in texts):
            raise ValueError("Text inputs must not contain empty strings.")

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return embeddings.tolist()

    def embed_text(self, text: str) -> list[float]:
        """Convert one text string into a single embedding vector."""
        return self.embed_texts([text])[0]
