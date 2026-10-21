
import chromadb


class ChromaStore:
    """Persist report documents and their embeddings in ChromaDB."""

    def __init__(
        self,
        persist_directory: str = "chroma_data",
        collection_name: str = "vision_reports",
    ) -> None:
        self.client = chromadb.PersistentClient(path=persist_directory)

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_report(
        self,
        report_id: str,
        document: str,
        embedding: list[float],
        metadata: dict,
    ) -> None:
        """Insert a report or update it if its ID already exists."""
        self.collection.upsert(
            ids=[report_id],
            documents=[document],
            embeddings=[embedding],
            metadatas=[metadata],
        )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 3,
        where: dict | None = None,
    ) -> dict:
        """
        Retrieve the most semantically similar reports.

        Args:
            query_embedding: The query vector.
            top_k: Maximum number of results to return.
            where: Optional ChromaDB metadata filter, e.g.
                   ``{"user_id": "abc123"}``.  Pass this for every
                   user-facing query to enforce data isolation.
        """
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")

        if self.collection.count() == 0:
            return {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }

        query_kwargs: dict = dict(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        if where is not None:
            query_kwargs["where"] = where

        results = self.collection.query(**query_kwargs)

        return results

    def count(self) -> int:
        """Return the number of stored reports."""
        return self.collection.count()

    def delete_report(self, report_id: str) -> None:
        """Delete a report by its stored ID."""
        self.collection.delete(ids=[report_id])