from pathlib import Path

SUPPORTED_IMAGE_SUFFIXES = {".jpg",".jpeg", ".png"}

def discover_images(input_dir: Path) -> list[Path]:
    """return supported image candidates directly inside input_dir."""
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"not a directory: {input_dir}")
    images = [
        path 
        for path in input_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES

    ] 
    return sorted(images, key=lambda path: path.name.lower())


