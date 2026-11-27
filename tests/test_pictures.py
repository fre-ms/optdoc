"""A picture stays a picture: optdoc handed a JPEG gives a JPEG, handed a HEIC a HEIC, and
so on, prepared from the picture's own pixels; one that no plan changes comes back byte
for byte; what the picture says of itself stays, with the orientation upright and without
the embedded preview; the same picture and document give the same bytes."""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

import pytest

from optdoc import cleanup, output, pictures
from optdoc.cli import main
from optdoc.errors import OptdocError
from optdoc.project import Options, Project, load_config
from tests.synthetic import camera_photo

pytestmark = pytest.mark.skipif(not cleanup.available(), reason="needs OpenCV")
FORMATS = {"jpg": "JPEG", "png": "PNG", "heic": "HEIF", "tiff": "TIFF", "webp": "WEBP",
           "bmp": "BMP"}


def _photo(report: Path) -> object:
    """An invented photo of the report's first page, at a slant on a dark desk (BGR)."""
    return camera_photo(report, pitch=18, yaw=6, roll=2, fill=0.85, size=(1200, 1600),
                        dpi=150)[0]


def _saved(image: object, path: Path, **options: object) -> Path:
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    Image.fromarray(image[:, :, ::-1].copy()).save(path, **options)  # type: ignore[index]
    return path


def _exif(thumbnail: bytes, orientation: int = 1) -> bytes:
    """EXIF as a phone writes it (big-endian): a make, the orientation, the picture's
    width among the details, a place, and an embedded preview in a directory of its own."""
    def entry(tag: int, kind: int, count: int, value: bytes) -> bytes:
        return struct.pack(">HHI4s", tag, kind, count, value)

    make = b"Beispielfon\0"
    main_at = 8
    make_at = main_at + 2 + 4 * 12 + 4
    details_at = make_at + len(make)
    place_at = details_at + 2 + 12 + 4
    latitude_at = place_at + 2 + 2 * 12 + 4
    preview_at = latitude_at + 24
    data_at = preview_at + 2 + 2 * 12 + 4
    out = b"MM\0\x2a" + struct.pack(">I", main_at) + struct.pack(">H", 4)
    out += entry(0x010F, 2, len(make), struct.pack(">I", make_at))
    out += entry(0x0112, 3, 1, struct.pack(">HH", orientation, 0))
    out += entry(0x8769, 4, 1, struct.pack(">I", details_at))
    out += entry(0x8825, 4, 1, struct.pack(">I", place_at))
    out += struct.pack(">I", preview_at) + make
    out += struct.pack(">H", 1) + entry(0xA002, 4, 1, struct.pack(">I", 1200)) + b"\0" * 4
    out += struct.pack(">H", 2) + entry(1, 2, 2, b"N\0\0\0")
    out += entry(2, 5, 3, struct.pack(">I", latitude_at)) + b"\0" * 4
    out += struct.pack(">IIIIII", 48, 1, 8, 1, 0, 1)
    out += struct.pack(">H", 2) + entry(0x0201, 4, 1, struct.pack(">I", data_at))
    out += entry(0x0202, 4, 1, struct.pack(">I", len(thumbnail))) + b"\0" * 4
    return b"Exif\0\0" + out + thumbnail


def _prepared(source: Path, folder: Path, options: Options | None = None,
              config: dict | None = None) -> dict[str, Path]:
    project = Project.open(source, options, config)
    try:
        prepared = project.build()
        try:
            return output.write(prepared, folder)
        finally:
            prepared.close()
    finally:
        project.close()


@pytest.mark.parametrize("ending", list(FORMATS))
def test_a_picture_comes_back_in_its_own_type(tmp_path: Path, report: Path,
                                              ending: str) -> None:
    """The photographed sheet is found and unwarped, and what is written is a picture of
    the type that came, in the picture's own resolution, with the configuration document
    beside it; from both, the same bytes again."""
    from PIL import Image

    photo = _saved(_photo(report), tmp_path / f"foto.{ending}")
    first = _prepared(photo, tmp_path / "a")
    assert {p.name for p in (tmp_path / "a").iterdir()} == {f"foto.{ending}",
                                                            "foto.optdoc.json"}
    assert first["document"].name == f"foto.{ending}"
    with Image.open(first["document"]) as out:
        assert out.format == FORMATS[ending]
        # the sheet filled 85 % of the photo: the result is that sheet, not a rendering
        assert 900 < out.size[0] < 1200 and 1250 < out.size[1] < 1600
        assert out.size[1] / out.size[0] == pytest.approx(2 ** 0.5, rel=0.03)  # A4
        corner = out.convert("RGB").getpixel((12, 12))
        assert min(corner) > 215  # paper, not the dark desk
    config = load_config(first["config"])
    assert config["version"] == 3 and config["input"]["suffix"] == f".{ending}"
    assert config["pages"][0]["plan"]["unwarp"] is True
    assert "paper" not in config["options"]
    again = _prepared(photo, tmp_path / "b", config=config)
    for key in ("document", "config"):
        assert first[key].read_bytes() == again[key].read_bytes(), key


def test_a_picture_no_plan_changes_is_written_as_it_came(tmp_path: Path, report: Path) -> None:
    from PIL import Image

    exif = Image.Exif()
    exif[0x0112] = 6
    photo = _saved(_photo(report), tmp_path / "foto.jpg", quality=80, exif=exif.tobytes())
    written = _prepared(photo, tmp_path / "out", Options(clean_up=False))
    assert written["document"].read_bytes() == photo.read_bytes()  # byte for byte
    assert load_config(written["config"])["pages"][0]["plan"] is None
    with pytest.raises(OptdocError) as caught:  # it would replace the picture itself
        _prepared(photo, tmp_path)
    assert caught.value.kind == "same-as-source"


def test_what_the_picture_says_of_itself_stays(tmp_path: Path, report: Path) -> None:
    """The camera, the place and the details stay; the orientation is upright (the
    prepared picture is); the embedded preview, which would show the picture as it came,
    is gone; the sizes named are those of the prepared picture."""
    from PIL import ExifTags, Image

    small = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 0, 0)).save(small, "JPEG")
    preview = small.getvalue()
    import cv2

    held = cv2.rotate(_photo(report), cv2.ROTATE_90_COUNTERCLOCKWISE)  # as the sensor lay
    photo = _saved(held, tmp_path / "foto.jpg", quality=85, exif=_exif(preview, orientation=6),
                   dpi=(72, 72))
    assert preview in photo.read_bytes()
    with Image.open(photo) as before:
        assert before.size == (1600, 1200) and before.getexif()[0x0112] == 6
    written = _prepared(photo, tmp_path / "out")
    data = written["document"].read_bytes()
    assert preview not in data
    with Image.open(written["document"]) as after:
        said = after.getexif()
        assert after.size[0] < after.size[1]  # upright: a portrait
        assert said[0x0112] == 1 and said[0x010F] == "Beispielfon"
        assert dict(said.get_ifd(ExifTags.IFD.GPSInfo)) == {1: "N", 2: (48.0, 8.0, 0.0)}
        assert said.get_ifd(ExifTags.IFD.Exif)[0xA002] == after.size[0]
        assert not said.get_ifd(ExifTags.IFD.IFD1)


def test_a_scanners_tiff_keeps_what_it_says(tmp_path: Path, report: Path) -> None:
    """A TIFF's main directory says how the picture is stored and what it is: the second
    stays (make, software, date, resolution), the first is the new picture's."""
    from PIL import Image

    said = {271: "Beispielscan", 305: "Scan 1.0", 306: "2026:03:12 10:00:00"}
    scan = _saved(_photo(report), tmp_path / "scan.tiff", tiffinfo=said, dpi=(300, 300),
                  compression="tiff_lzw")
    written = _prepared(scan, tmp_path / "out")
    with Image.open(written["document"]) as after:
        assert {tag: after.tag_v2[tag] for tag in said} == said
        assert after.info["dpi"] == (300, 300) and after.tag_v2[256] == after.size[0]
        assert after.tag_v2[259] == 5  # compressed without loss
    pages = tmp_path / "zwei.tiff"
    first = Image.fromarray(_photo(report)[:, :, ::-1].copy())  # type: ignore[index]
    first.save(pages, save_all=True, append_images=[Image.new("RGB", (400, 600), (250,) * 3)])
    assert pictures.count(pages) == 2
    project = Project.open(pages)
    try:
        project.set_plan(1, None)  # the second stays as it came
        prepared = project.build()
        both = output.write(prepared, tmp_path / "both")
        assert prepared.cleaned_up == [0]
    finally:
        project.close()
    with Image.open(both["document"]) as after:  # one prepared, one as it came: one file
        assert after.n_frames == 2 and after.size[0] < 1200
        after.seek(1)
        assert after.size == (400, 600)


def test_a_picture_on_the_command_line(tmp_path: Path, report: Path,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    """``run`` on a picture answers with the picture it wrote; the sheet of paper is no
    setting of optdoc's any more."""
    photo = _saved(_photo(report), tmp_path / "foto.jpg")
    assert main(["run", str(photo), "--out", str(tmp_path / "out")]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["document"] == str(tmp_path / "out" / "foto.jpg")
    assert answer["pages"] == 1 and answer["cleaned_up"] == [1] == answer["unwarped"]
    assert main(["run", str(photo), "--out", str(tmp_path / "again"), "--config",
                 answer["config"]]) == 0
    again = json.loads(capsys.readouterr().out)
    assert Path(again["document"]).read_bytes() == Path(answer["document"]).read_bytes()
    assert main(["run", str(photo), "--paper", "a4"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "usage"
