#!/usr/bin/env python3
"""
image_compress.py — Downsample/compress images before upload as blobs.

Target: ~100KB JPEG, max 1600px on longest dimension. Good enough to read
keypad labels and identify devices in photos, small enough to not bloat
the SQLite database over time.

Usage:
    from image_compress import compress_image

    with open("IMG_1234.heic", "rb") as f:
        compressed_bytes, info = compress_image(f.read())

    # info is a dict: {orig_size, final_size, orig_dims, final_dims, format_in, format_out}

    # Or as CLI:
    #   python3 image_compress.py input.jpg output.jpg
    #   (also supports HEIC if pillow-heif is installed)
"""
import io
import sys
from typing import Tuple, Dict, Any

MAX_DIMENSION = 1600
TARGET_MAX_BYTES = 150_000  # 150KB ceiling; we aim for 100KB but allow some headroom
JPEG_QUALITY_START = 85
JPEG_QUALITY_MIN = 55
JPEG_QUALITY_STEP = 5


def _compress_with_sips(data: bytes) -> Tuple[bytes, Dict[str, Any]]:
    """macOS fallback when Pillow is missing or can't decode (e.g. HEIC without
    pillow-heif). sips ships with macOS and reads HEIC natively."""
    import os, subprocess, tempfile
    with tempfile.TemporaryDirectory() as td:
        src, out = os.path.join(td, "in"), os.path.join(td, "out.jpg")
        with open(src, "wb") as f:
            f.write(data)
        final = b""
        for dim in (MAX_DIMENSION, 1200, 1000):
            for q in range(JPEG_QUALITY_START, JPEG_QUALITY_MIN - 1, -JPEG_QUALITY_STEP):
                subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(q),
                                "-Z", str(dim), src, "--out", out],
                               check=True, capture_output=True)
                with open(out, "rb") as f:
                    final = f.read()
                if len(final) <= TARGET_MAX_BYTES:
                    break
            if len(final) <= TARGET_MAX_BYTES:
                break
    return final, {"orig_size": len(data), "final_size": len(final),
                   "format_in": "via-sips", "format_out": "JPEG"}


def compress_image(data: bytes) -> Tuple[bytes, Dict[str, Any]]:
    """Compress image bytes to ~100KB JPEG, max 1600px. Returns (bytes, info_dict)."""
    try:
        from PIL import Image
    except ImportError:
        if sys.platform == "darwin":
            return _compress_with_sips(data)
        raise RuntimeError("Pillow required: pip install pillow")

    # HEIC support (iPhone default). Silent if not installed — JPEG/PNG still work.
    try:
        import pillow_heif  # type: ignore
        pillow_heif.register_heif_opener()
    except ImportError:
        pass

    try:
        img = Image.open(io.BytesIO(data))
    except Exception:
        if sys.platform == "darwin":
            return _compress_with_sips(data)
        raise
    orig_format = img.format or "UNKNOWN"
    orig_dims = img.size
    orig_size = len(data)

    # Normalize to RGB for JPEG output (handles RGBA, palette, etc.)
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Respect EXIF orientation so photos aren't sideways
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Downsample if needed
    if max(img.size) > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

    # Encode JPEG, dropping quality until we fit target
    quality = JPEG_QUALITY_START
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        out = buf.getvalue()
        if len(out) <= TARGET_MAX_BYTES or quality <= JPEG_QUALITY_MIN:
            break
        quality -= JPEG_QUALITY_STEP

    info = {
        "orig_size": orig_size,
        "final_size": len(out),
        "orig_dims": orig_dims,
        "final_dims": img.size,
        "format_in": orig_format,
        "format_out": "JPEG",
        "quality": quality,
    }
    return out, info


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: image_compress.py <input> <output>", file=sys.stderr)
        return 1
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    out, info = compress_image(data)
    with open(sys.argv[2], "wb") as f:
        f.write(out)
    print(
        f"{info['orig_dims']} {info['format_in']} {info['orig_size']:,}B -> "
        f"{info['final_dims']} JPEG q{info['quality']} {info['final_size']:,}B"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
