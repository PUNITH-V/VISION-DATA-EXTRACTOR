
import argparse
from pathlib import Path

from embeddings.embedder import TextEmbedder
from vector_stores.chroma_store import ChromaStore


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = PROJECT_ROOT / "chroma_data"


def search_reports(query: str, top_k: int = 3) -> dict:
    """Find vision reports semantically similar to a text query."""
    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    store = ChromaStore(persist_directory=str(CHROMA_DIR))

    if store.count() == 0:
        return {
            "ids": [],
            "documents": [],
            "metadatas": [],
            "distances": [],
        }

    embedder = TextEmbedder()
    query_embedding = embedder.embed_text(query)

    return store.search(
        query_embedding=query_embedding,
        top_k=top_k,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search indexed vision reports using natural language."
    )
    parser.add_argument(
        "query",
        help="The question or concept to search for.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Maximum number of reports to retrieve (default: 3).",
    )

    args = parser.parse_args()

    try:
        results = search_reports(args.query, args.top_k)
    except Exception as exc:
        parser.exit(1, f"Search failed: {exc}\n")

    if not results["ids"]:
        print("No indexed reports found. Run the ingestion pipeline first.")
        return

    print(f"\nQuery: {args.query}")
    print("=" * 60)

    for rank, report_id in enumerate(results["ids"][0], start=1):
        document = results["documents"][0][rank - 1]
        metadata = results["metadatas"][0][rank - 1]
        distance = results["distances"][0][rank - 1]

        print(f"\nResult {rank}")
        print(f"Report: {report_id}")
        print(f"Image: {metadata.get('image_filename', 'Unknown')}")
        print(f"Confidence: {metadata.get('confidence', 'Unknown')}")
        print(f"Cosine distance: {distance:.4f}")
        print(f"Content:\n{document}")


if __name__ == "__main__":
    main()
