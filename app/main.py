import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from config.settings import API_KEY, BASE_URL, MODEL
from app.image_discovery import discover_images
from app.image_loader import load_image
from app.schemas import VisionExtractionReport
from app.vision_client import VisionClient, VisionClientError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"

PROMPT = """
Analyze the supplied image and extract information that is visibly
supported by the image.

Return exactly one JSON object with these fields:
{
  "image_description": "Brief description of the image",
  "extracted_data": [
    {
      "label": "Name of an extracted item",
      "value": "Its corresponding value"
    }
  ],
  "confidence": "High"
}

Requirements:
- confidence must be exactly "High", "Medium", or "Low".
- Use valid JSON with double quotes around keys and string values.
- Do not include Markdown fences or text outside the JSON object.
- Do not invent details that cannot be supported by the image.
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract structured data from images."
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        type=Path,
        help="Optional image path. Omit to process all images in input/.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing reports after successful processing.",
    )
    return parser.parse_args(argv)


def create_vision_client() -> VisionClient:
    return VisionClient(
        api_key=API_KEY,
        base_url=BASE_URL,
        model=MODEL,
    )


def get_report_path(image_path: Path) -> Path:
    return OUTPUT_DIR / f"{image_path.stem}_report.json"


def parse_model_response(response: str) -> VisionExtractionReport:
    """Parse model text and validate it against our report schema."""

    if not response or not response.strip():
        raise ValueError("The model returned an empty response.")

    text = response.strip()

    # Explicitly reject known non-JSON safety/status responses.
    if text.lower().startswith("user safety:"):
        raise ValueError(
            "The model returned a safety/status message instead of JSON. "
            "No report was saved."
        )

    # Allow a model to wrap JSON in Markdown fences.
    if text.startswith("```"):
        lines = text.splitlines()

        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise ValueError("The model returned an incomplete Markdown fence.")

        text = "\n".join(lines[1:-1]).strip()

        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        preview = text[:120].replace("\n", " ")
        raise ValueError(
            f"The model did not return valid JSON. "
            f"Response begins: {preview!r}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("The model response must be a JSON object.")

    try:
        return VisionExtractionReport.model_validate(data)
    except ValidationError as exc:
        raise ValueError(
            f"The model response failed schema validation: {exc}"
        ) from exc


def save_report(
    report: VisionExtractionReport,
    report_path: Path,
) -> None:
    """Write a complete validated report without partial final files."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report_json = report.model_dump_json(indent=2) + "\n"
    temp_path = report_path.with_name(report_path.name + ".tmp")

    try:
        temp_path.write_text(report_json, encoding="utf-8")
        temp_path.replace(report_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def process_image(
    image_path: Path,
    vision_client: VisionClient,
    overwrite: bool = False,
) -> Path:
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if not image_path.is_file():
        raise ValueError(f"Path is not a file: {image_path}")

    report_path = get_report_path(image_path)

    if report_path.exists() and not overwrite:
        raise FileExistsError(f"Report already exists: {report_path}")

    # Validate the image before making an API call.
    image_data = load_image(str(image_path))

    # API errors are converted into clear VisionClientError messages.
    response = vision_client.analyze_image(
        image_base64=image_data["image_base64"],
        mime_type=image_data["mime_type"],
        prompt=PROMPT,
    )

    print(f"\nRaw response for {image_path.name}:")
    print(repr(response[:500]))

    # Parsing and validation must succeed before saving.
    report = parse_model_response(response)

    save_report(report, report_path)
    return report_path


def main() -> None:
    args = parse_args()
    vision_client = create_vision_client()

    if args.image_path is not None:
        image_path = args.image_path

        if not image_path.is_absolute():
            image_path = PROJECT_ROOT / image_path

        try:
            report_path = process_image(
                image_path,
                vision_client,
                overwrite=args.overwrite,
            )
            print(f"\nSuccess: {image_path} -> {report_path}")

        except FileExistsError as exc:
            print(f"\nSkipped: {exc}")

        except Exception as exc:
            print(f"\nFailed: {image_path.name}: {exc}")

        return

    try:
        images = discover_images(INPUT_DIR)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"Cannot discover input images: {exc}")
        return

    if not images:
        print(f"No supported images found in: {INPUT_DIR}")
        return

    succeeded = 0
    skipped = 0
    failed = 0

    for image_path in images:
        try:
            report_path = process_image(
                image_path,
                vision_client,
                overwrite=args.overwrite,
            )
            succeeded += 1
            print(f"Success: {image_path.name} -> {report_path.name}")

        except FileExistsError as exc:
            skipped += 1
            print(f"Skipped: {image_path.name}: {exc}")

        except Exception as exc:
            failed += 1
            print(f"Failed: {image_path.name}: {exc}")

    print("\n========== BATCH SUMMARY ==========")
    print(f"Total images: {len(images)}")
    print(f"Succeeded:   {succeeded}")
    print(f"Skipped:     {skipped}")
    print(f"Failed:      {failed}")
    print("===================================")


if __name__ == "__main__":
    main()