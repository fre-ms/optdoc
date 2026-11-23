"""optdoc: makes photographed and scanned documents legible.

Finds and straightens the page, evens out light and noise, upscales, reads the text
(RapidOCR, Tesseract) with word boxes, gives it structure (paragraphs, lists, tables)
and lays it back onto the page as an invisible text layer.  Everything runs locally.

The modules:

- :mod:`optdoc.loading`: open PDFs and images (HEIC too), images placed on a paper size;
- :mod:`optdoc.cleanup`: the clean-up steps and their automatic suggestion;
- :mod:`optdoc.ocr`: the OCR engines and the page text they produce;
- :mod:`optdoc.pagetext`: the page text with a box for every character;
- :mod:`optdoc.structure`: lines, paragraphs, headings, lists and tables as Markdown;
- :mod:`optdoc.alignment`: a corrected text laid back onto the OCR boxes;
- :mod:`optdoc.reading`: the pipeline, page by page: open, clean up, read, structure;
- :mod:`optdoc.output`: the searchable PDF, the reading as JSON, Markdown, the plan;
- :mod:`optdoc.textlayer`: the invisible text layer, one line per OCR line;
- :mod:`optdoc.errors`: the kinds of error and their wording in English and German;
- :mod:`optdoc.offline`: no network, no telemetry;
- :mod:`optdoc.settings`: the settings of the OCR layer;
- :mod:`optdoc.cli` and :mod:`optdoc.bench`: the command line and the test bench.
"""

__version__ = "0.3.0"
