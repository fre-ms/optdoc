"""The models optdoc can use, each measured against the rules it adds to before it was
listed.  None is needed: every step works without, and a model that does not lie in the
folder given (``--models``) is done without.  How they are listed, fetched and found:
:mod:`doccor.models`.
"""

from __future__ import annotations

from pathlib import Path

from doccor import models
from doccor.models import Model

ORIENTATION = Model(
    name="page-orientation",
    file="pp-lcnet-x1-0-doc-ori.onnx",
    # the upstream's own ONNX file, at the commit that was measured
    url="https://huggingface.co/PaddlePaddle/PP-LCNet_x1_0_doc_ori_onnx/resolve/"
        "7330ab7039123e46af2dc03154b9969aa412c61d/inference.onnx",
    sha256="af9a0a4f317ff0709ce752067807f819cb15d883f8ecad89f28df1c6ee2d9c92",
    size=6_788_069,
    licence="Apache-2.0",
    source="https://huggingface.co/PaddlePaddle/PP-LCNet_x1_0_doc_ori_onnx",
    does={"en": "tells which way up a page stands, upside down too, without reading it "
                "(PaddleOCR's PP-LCNet_x1_0_doc_ori)",
          "de": "erkennt, wie herum eine Seite steht, auch auf dem Kopf, ohne sie zu lesen "
                "(PP-LCNet_x1_0_doc_ori von PaddleOCR)"},
)

CATALOGUE: tuple[Model, ...] = (ORIENTATION,)


def orientation(folder: Path | None) -> Path | None:
    """The orientation model's file in a models folder, where it lies there."""
    return models.present(ORIENTATION, folder)
