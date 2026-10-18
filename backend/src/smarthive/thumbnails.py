"""Resized JPEG copies of stored images, cached next to the originals under `thumbs/<width>/`."""

import os
from pathlib import Path

from PIL import Image, ImageOps

WIDTHS = (160, 320, 640)


def thumbnail(root: Path, rel: str, width: int) -> Path:
    """Path of the `width`-wide copy of the image at `rel`; made on first use. Never upscales."""
    target = root / "thumbs" / str(width) / Path(rel).name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(root / rel) as src:
            im = ImageOps.exif_transpose(src)
            im.thumbnail((width, width * 10))  # constrain the width only; keeps the aspect ratio
            tmp = target.with_suffix(f".{os.getpid()}.tmp")
            im.convert("RGB").save(tmp, "JPEG", quality=80)
        os.replace(tmp, target)
    return target
