"""Image processing for vision input (OpenAI-compatible format)."""

import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_MEDIA_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}

MAX_IMAGE_SIZE_MB = 20


def encode_image_for_openai(image_bytes: bytes, mime_type: str) -> Optional[dict]:
    """Encode raw image bytes into an OpenAI-compatible image_url content block.

    Returns the content block dict ready to insert into a messages payload,
    or None if the image is invalid.
    """
    if not image_bytes:
        return None

    size_mb = len(image_bytes) / (1024 * 1024)
    if size_mb > MAX_IMAGE_SIZE_MB:
        logger.warning(f"Image too large ({size_mb:.1f} MB), max is {MAX_IMAGE_SIZE_MB} MB")
        return None

    canonical_mime = SUPPORTED_MEDIA_TYPES.get(mime_type.lower(), "image/jpeg")
    if canonical_mime == "image/jpeg" and mime_type.lower() not in SUPPORTED_MEDIA_TYPES:
        logger.debug(f"Unknown mime type '{mime_type}', defaulting to image/jpeg")

    encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:{canonical_mime};base64,{encoded}",
        },
    }


def detect_mime_from_bytes(image_bytes: bytes) -> str:
    """Detect image MIME type from file magic bytes."""
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # default
