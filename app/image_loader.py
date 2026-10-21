import base64
from pathlib import Path

from PIL import Image, UnidentifiedImageError

SUPPORTED_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG" : "image/png",

}

def load_image(image_path: str) -> dict:
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    try:
        with Image.open(path) as image:
            image_format = image.format

            if image_format not in SUPPORTED_FORMATS:
                raise ValueError(
                    f"Unsupported image format: {image_format}"
                )
            image.verify()
        with Image.open(path) as image:
            image.load()

    except UnidentifiedImageError as exc: 
        raise ValueError(
            f"File is not a recongnized image:{path}"
            ) from exc

    image_bytes  = path.read_bytes()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    return {
        "image_base64": image_base64,
        "mime_type" : SUPPORTED_FORMATS[image_format]
        }


"""print("MIME type:", image_data["mime_type"])
print("Base64 type:", type(image_data["image_base64"]))
print("Base64 length:", len(image_data["image_base64"]))"""
