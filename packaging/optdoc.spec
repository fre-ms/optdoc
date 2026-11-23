# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification: optdoc as one executable file, to ship beside an
application (a Tauri sidecar, for medorello).

Build it with ``packaging/build.py``, which names the file after the target platform
and tries it out.  Everything travels inside: Python, PyMuPDF, OpenCV, ONNX Runtime,
RapidOCR with its models, pillow-heif.  Nothing is downloaded at run time.

Environment: ``OPTDOC_BINARY_NAME`` (the file's name), ``OPTDOC_CODESIGN_IDENTITY`` (a
Developer ID for macOS; without it the build is signed ad hoc), ``OPTDOC_ONEDIR`` (a
folder of that name, with the program ``optdoc`` in it, instead of one file).
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH).parent  # noqa: F821 (given by PyInstaller)
identity = os.environ.get("OPTDOC_CODESIGN_IDENTITY") or None

datas, binaries, hiddenimports = [], [], []
for package in ("rapidocr", "onnxruntime", "pymupdf"):  # rapidocr: its models and settings
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
binaries += collect_dynamic_libs("pillow_heif")
hiddenimports += collect_submodules("optdoc")
hiddenimports += ["pillow_heif", "PIL.Image", "PIL.ImageFilter", "PIL.ImageOps", "cv2",
                  "shapely", "pyclipper", "omegaconf", "colorlog", "yaml"]
# RapidOCR's other inference engines and what optdoc never uses
excludes = ["torch", "paddle", "openvino", "tensorrt", "MNN", "tkinter", "matplotlib",
            "IPython", "jupyter", "notebook", "pytest", "PySide6", "PyQt5", "PyQt6"]

a = Analysis(  # noqa: F821
    [str(root / "packaging" / "start.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[str(root / "packaging" / "rth_offline.py")],
    excludes=excludes,
    noarchive=False,
)
# ONNX Runtime's C library is for other languages; the Python module carries its own copy
# (it neither links nor loads the library), and the file is 35 MB unpacked at every start.
# collect_all and the library's hook both bring it, as binary and as data.
a.binaries = [e for e in a.binaries if not Path(e[0]).name.startswith("libonnxruntime")]
a.datas = [e for e in a.datas if not Path(e[0]).name.startswith("libonnxruntime")]
pyz = PYZ(a.pure)  # noqa: F821
name = os.environ.get("OPTDOC_BINARY_NAME", "optdoc")
signing = {"codesign_identity": identity,
           "entitlements_file": str(root / "packaging" / "entitlements.plist") if identity
           else None}
if os.environ.get("OPTDOC_ONEDIR"):  # a folder: nothing unpacked at start, see docs/sidecar.md
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="optdoc", debug=False,  # noqa: F821
              strip=False, upx=False, console=True, **signing)
    COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=name)  # noqa: F821
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=name, debug=False,  # noqa: F821
              strip=False, upx=False, console=True, runtime_tmpdir=None, **signing)
