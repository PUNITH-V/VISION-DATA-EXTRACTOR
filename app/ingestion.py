
import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.schemas import VisionExtractionReport
from embeddings.embedder import TextEmbedder
from vector_stores.chroma_store import ChromaStore


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CHROMA_DIR = PROJECT_ROOT / "chroma_data"


def report_to_document(report: VisionExtractionReport) -> str:
    """Convert a validated report into text suitable for semantic search."""
    parts = [
        f"Image description: {report.image_description}",
        "Extracted data:",
    ]

    for item in report.extracted_data:
        parts.append(f"{item.label}: {item.value}")

    return "\n".join(parts)


def ingest_reports(
    output_dir: Path = OUTPUT_DIR,
    persist_directory: Path = CHROMA_DIR,
) -> dict[str, int]:
    """Validate, embed, and persist every valid JSON report."""
    embedder = TextEmbedder()
    store = ChromaStore(persist_directory=str(persist_directory))

    summary = {
        "discovered": 0,
        "ingested": 0,
        "skipped": 0,
        "failed": 0,
    }

    report_paths = sorted(
        output_dir.glob("*_report.json"),
        key=lambda path: path.name.casefold(),
    )
    summary["discovered"] = len(report_paths)

    for report_path in report_paths:
        try:
            raw_data = json.loads(
                report_path.read_text(encoding="utf-8")
            )
            report = VisionExtractionReport.model_validate(raw_data)

            document = report_to_document(report)

            if not document.strip():
                raise ValueError("Report produced empty searchable text.")

            embedding = embedder.embed_text(document)

            metadata = {
                "image_filename": report_path.name.removesuffix("_report.json"),
                "confidence": report.confidence,
                "report_filename": report_path.name,
            }

            store.upsert_report(
                report_id=report_path.name,
                document=document,
                embedding=embedding,
                metadata=metadata,
            )

            summary["ingested"] += 1
            logger.info("Indexed report: %s", report_path.name)

        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            summary["skipped"] += 1
            logger.warning(
                "Skipping invalid report %s: %s",
                report_path.name,
                exc,
            )

        except Exception:
            summary["failed"] += 1
            logger.exception(
                "Failed to ingest report: %s",
                report_path.name,
            )

    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    results = ingest_reports()

    print("\nIngestion summary")
    print("-----------------")
    for key, value in results.items():
        print(f"{key.capitalize()}: {value}")
