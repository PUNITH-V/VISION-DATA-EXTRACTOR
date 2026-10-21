
from vector_stores.chroma_store import ChromaStore


def test_chroma_store_insert_search_and_update(tmp_path):
    store = ChromaStore(
        persist_directory=str(tmp_path / "chroma_test"),
        collection_name="test_reports",
    )

    store.upsert_report(
        report_id="github1.jpeg",
        document="GitHub logo with the text GitHub",
        embedding=[1.0, 0.0, 0.0],
        metadata={
            "image_filename": "github1.jpeg",
            "confidence": "High",
        },
    )

    assert store.count() == 1

    results = store.search(
        query_embedding=[0.9, 0.1, 0.0],
        top_k=3,
    )

    assert results["ids"] == [["github1.jpeg"]]
    assert results["documents"][0][0] == (
        "GitHub logo with the text GitHub"
    )

    # Upserting the same ID should update, not duplicate.
    store.upsert_report(
        report_id="github1.jpeg",
        document="Updated GitHub logo description",
        embedding=[1.0, 0.0, 0.0],
        metadata={
            "image_filename": "github1.jpeg",
            "confidence": "Medium",
        },
    )

    assert store.count() == 1

    updated = store.search(
        query_embedding=[1.0, 0.0, 0.0],
        top_k=1,
    )

    assert updated["documents"][0][0] == (
        "Updated GitHub logo description"
    )
    assert updated["metadatas"][0][0]["confidence"] == "Medium"
