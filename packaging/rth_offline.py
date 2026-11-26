"""Runtime hook of the standalone program, run before anything else: ONNX Runtime reads
``ORT_DISABLE_TELEMETRY`` once, when it is loaded, and must find it set (see
:mod:`doccor.offline`).  The command line sets it as well; this makes it hold even if
something loaded the library earlier."""

import os

os.environ["ORT_DISABLE_TELEMETRY"] = "1"
