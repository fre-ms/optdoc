"""optdoc: makes photographed and scanned pages faithful.

Finds the sheet in a photo and unwarps it in its true proportions, turns and straightens
the page, cleans dark borders, evens out light and noise, and keeps the page's own
colours.  A PDF stays a PDF and a picture a picture, in the type it came in.  Every
decision is kept in a configuration document, from which the same result is made again,
byte for byte.  Reading the pages is the next step, ocrdoc's.  Everything runs locally.

The modules:

- :mod:`optdoc.loading`: open PDFs and pictures (HEIC too), every page upright;
- :mod:`optdoc.pictures`: a picture read and written again in its own type;
- :mod:`optdoc.cleanup`: the steps of the preparation and their automatic suggestion;
- :mod:`optdoc.orientation` and :mod:`optdoc.models`: which way up a page stands, told by
  a model where one was fetched (an optional download);
- :mod:`optdoc.project`: the preparation of one document and its configuration document;
- :mod:`optdoc.output`: the prepared document and its configuration document, written;
- :mod:`optdoc.errors`: optdoc's own kinds of error, worded in English and German;
- :mod:`optdoc.cli`: the command line.

What every tool of docrepro shares (configuration documents, the command line's manners,
no network, the window's building blocks) is doccor's (:mod:`doccor`).
"""

__version__ = "0.10.1"
