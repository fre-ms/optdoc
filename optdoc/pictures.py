"""A picture stays a picture: reading its pixels, and writing it again in the type it
came in.

docrepro forces no file type.  optdoc handed a JPEG gives a JPEG, handed a HEIC gives a
HEIC, and so for PNG, TIFF, WebP, BMP, GIF and PNM; turning a picture into a PDF is
typdoc's step.

**A picture no plan changes is written as it came, byte for byte.**  One that was
prepared is encoded again in its type: a JPEG, a HEIC and a WebP at quality 92 with full
colour resolution, the others without loss.

**What the picture says of itself stays**, as the user decided (27 November 2026): the
camera, the moment, the place, the colour profile.  Two things change with the pixels and
are set right: the orientation is "upright" now (the prepared picture is), and the small
preview a camera embeds is left out, since it would still show the picture as it came.
The sizes the picture names are those of the prepared one.

The same picture and the same plan give the same bytes on the same version of optdoc and
its libraries (measured for HEIC as well, whose encoder is the largest of them).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from optdoc.errors import OptdocError

QUALITY = 92  # of a picture written with loss (JPEG, HEIC, WebP)
_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".tif": "TIFF", ".tiff": "TIFF",
            ".heic": "HEIF", ".heif": "HEIF", ".webp": "WEBP", ".bmp": "BMP", ".gif": "GIF",
            ".pnm": "PPM"}
_ORIENTATION, _WIDTH, _HEIGHT = 0x0112, 0x0100, 0x0101
_PIXEL_X, _PIXEL_Y = 0xA002, 0xA003
# what a TIFF says of itself in its main directory (the rest there is how it is stored):
# document and page name, description, make, model, software, date, artist, computer,
# copyright
_TIFF_SAYS = (269, 285, 270, 271, 272, 305, 306, 315, 316, 33432)


def _pillow() -> Any:
    """Pillow's Image module, with HEIC and HEIF where pillow-heif is installed."""
    from PIL import Image

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:  # HEIC files then fail to open: "no-heic" was said on loading
        pass
    return Image


def _opened(path: Path) -> Any:
    try:
        return _pillow().open(path)
    except Exception as e:  # Pillow words its failures with the file's name
        raise OptdocError("unreadable") from e


def count(path: Path) -> int:
    """How many pictures the file holds (a TIFF may hold several)."""
    with _opened(path) as image:
        return int(getattr(image, "n_frames", 1))


def pixels(path: Path, n: int = 0) -> Any:
    """Picture ``n`` of the file as a BGR NumPy image, upright as its EXIF orientation
    says: the pixels as they came, not a rendering of them."""
    import numpy as np
    from PIL import ImageOps

    with _opened(path) as image:
        image.seek(n)
        upright = ImageOps.exif_transpose(image)
        if upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info:
            rgba = upright.convert("RGBA")
            white = _pillow().new("RGBA", rgba.size, (255, 255, 255, 255))
            upright = _pillow().alpha_composite(white, rgba)
        rgb = np.asarray(upright.convert("RGB"))
    return rgb[:, :, ::-1].copy()


def _described(image: Any, size: tuple[int, int], format_: str) -> dict[str, Any]:
    """What the picture says of itself, to be written with the prepared one: its EXIF with
    the orientation upright, the sizes of the prepared picture and without the embedded
    preview; its colour profile, its XMP packet and its resolution where it has them.
    For a TIFF, whose main directory also says how the picture is stored, only what it
    says of itself is taken from there ("says"), and "details" tells whether it has more
    in directories of its own (EXIF, GPS), which only an uncompressed TIFF can carry."""
    from PIL import ExifTags

    kept: dict[str, Any] = {}
    exif = image.getexif()
    details = exif.get_ifd(ExifTags.IFD.Exif)  # loaded, so that they are written again
    place = exif.get_ifd(ExifTags.IFD.GPSInfo)
    for tag, value in ((_PIXEL_X, size[0]), (_PIXEL_Y, size[1])):
        if tag in details:
            details[tag] = value
    if format_ == "TIFF":
        own = _pillow().Exif()
        for tag in _TIFF_SAYS:
            if tag in exif:
                own[tag] = exif[tag]
        kept["says"] = {tag: own[tag] for tag in own}
        if details or place:
            own.get_ifd(ExifTags.IFD.Exif).update(details)
            own.get_ifd(ExifTags.IFD.GPSInfo).update(place)
            kept["exif"], kept["details"] = own.tobytes(), True
    elif len(exif) or details or place:
        exif[_ORIENTATION] = 1
        for tag, value in ((_WIDTH, size[0]), (_HEIGHT, size[1])):
            if tag in exif:
                exif[tag] = value
        # the directory of the embedded preview (IFD1) is never read, so it is not written
        kept["exif"] = exif.tobytes()
    for key in ("icc_profile", "xmp", "dpi"):
        if image.info.get(key):
            kept[key] = image.info[key]
    return kept


def _picture(array: Any) -> Any:
    """A NumPy image (BGR, or grey) as a Pillow picture."""
    image = _pillow()
    return image.fromarray(array if array.ndim == 2 else array[:, :, ::-1].copy())


def _settings(format_: str, kept: dict[str, Any]) -> dict[str, Any]:
    """How a picture of that format is written, and what of ``kept`` the format takes."""
    takes = {"JPEG": ("exif", "icc_profile", "xmp", "dpi"), "PNG": ("exif", "icc_profile", "dpi"),
             "TIFF": ("icc_profile", "dpi"), "HEIF": ("exif", "icc_profile", "xmp"),
             "WEBP": ("exif", "icc_profile", "xmp"), "BMP": ("dpi",), "GIF": (), "PPM": ()}
    settings: dict[str, Any] = {key: kept[key] for key in takes[format_] if key in kept}
    if format_ == "JPEG":
        settings.update(quality=QUALITY, subsampling=0, optimize=False)
    elif format_ in ("HEIF", "WEBP"):
        settings.update(quality=QUALITY)
    elif format_ == "TIFF" and kept.get("details"):
        # directories of its own (EXIF, GPS) go only into a TIFF written without compression
        settings.update(compression="raw", exif=kept["exif"])
    elif format_ == "TIFF":
        settings.update(compression="tiff_lzw", tiffinfo=dict(kept.get("says", {})))
    return settings


def written(path: Path, prepared: list[Any | None]) -> bytes:
    """The picture file again, in the type it came in: ``prepared`` holds for every
    picture in it the prepared pixels (a NumPy image), or None where it stays as it came.
    Where none was prepared, these are the file's own bytes."""
    data = path.read_bytes()
    if all(page is None for page in prepared):
        return data
    from PIL import ImageOps

    format_ = _FORMATS[path.suffix.lower()]
    try:
        with _opened(path) as source:
            frames = []
            kept: dict[str, Any] = {}
            for n, page in enumerate(prepared):
                source.seek(n)
                # a picture left as it came is upright as well, as the file then says it is
                frame = _picture(page) if page is not None else ImageOps.exif_transpose(source)
                if n == 0:
                    kept = _described(source, frame.size, format_)
                frames.append(frame)
            out = io.BytesIO()
            settings = _settings(format_, kept)
            if len(frames) > 1:
                settings.update(save_all=True, append_images=frames[1:])
            frames[0].save(out, format=format_, **settings)
            return out.getvalue()
    except OptdocError:
        raise
    except Exception as e:
        raise OptdocError("clean-up-failed") from e
