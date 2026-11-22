"""optdoc: makes photographed and scanned documents legible.

Finds and straightens the page, evens out light and noise, upscales, reads the text
(RapidOCR, Tesseract) with word boxes, gives it structure (paragraphs, lists, tables)
and lays it back onto the page as an invisible text layer.  Everything runs locally.

The modules:

- :mod:`optdoc.laden`: open PDFs and images (HEIC too), images placed on a paper size;
- :mod:`optdoc.aufbereitung`: the clean-up steps and their automatic suggestion;
- :mod:`optdoc.ocr`: the OCR engines and the page text they produce;
- :mod:`optdoc.textebene`: the page text with a box for every character;
- :mod:`optdoc.gliederung`: lines, paragraphs, headings, lists and tables as Markdown;
- :mod:`optdoc.textabgleich`: a corrected text laid back onto the OCR boxes;
- :mod:`optdoc.einstellungen`: the settings of the OCR layer.
"""

__version__ = "0.0.1"
