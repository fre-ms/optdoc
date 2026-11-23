"""optdoc never goes on the network; :func:`forbid_network` makes sure nothing it loads does.

The documents optdoc reads are often a patient's, and it runs on computers that may have
no network at all.  Everything it needs travels with it: the OCR models come in the
RapidOCR wheel.  RapidOCR can download models and dictionaries it does not find, though,
and other libraries may want to look something up.  The command line therefore closes
the door before it does anything else: every attempt to resolve a name or open a
connection raises :class:`NetworkForbidden` (an :class:`~optdoc.errors.OptdocError` of
kind "network") instead of going out, and is counted.

An application that embeds optdoc decides for its own process; the guard is not set by
importing optdoc.  Unix sockets (``AF_UNIX``) stay usable; internet sockets are refused
even towards this computer (loopback), which optdoc has no use for either.

The guard sees what Python does; native code passes it by.  ONNX Runtime, which runs
RapidOCR's models, carries Microsoft's telemetry (1DS) in its native library: measured
with onnxruntime 1.32 on macOS, every run wrote a device identifier, the computer's
model, processor and system into a queue for sending, under
``~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime`` and a ``.ses``
file in the temporary folder.  No document goes into it, but nothing is to leave the
computer, and nothing is to be written outside the folder given.  The library reads
``ORT_DISABLE_TELEMETRY`` once, when it is loaded; :func:`no_telemetry` sets it, and
optdoc calls it before it loads RapidOCR (its own ``disable_telemetry_events()`` comes
too late: the queue is set up by then).  With it, nothing is written and nothing is
queued.
"""

from __future__ import annotations

import os
import socket
import sys
from typing import Any

from optdoc.errors import OptdocError

attempts = 0  # how many times something tried to go out since the guard was set
_closed = False


class NetworkForbidden(OptdocError):
    """Something tried to reach the network; nothing was sent."""

    def __init__(self) -> None:
        super().__init__("network")


def _refuse(*_args: Any, **_kwargs: Any) -> Any:
    """Count the attempt and refuse it."""
    global attempts
    attempts += 1
    raise NetworkForbidden()


class _GuardedSocket(socket.socket):
    """A socket that may only be local: connecting or sending to an address of the
    internet families is refused."""

    def connect(self, address: Any) -> None:  # type: ignore[override]
        """Connect, unless the socket would leave the computer."""
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _refuse()
        super().connect(address)

    def connect_ex(self, address: Any) -> int:  # type: ignore[override]
        """As :meth:`connect`."""
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _refuse()
        return super().connect_ex(address)

    def sendto(self, *args: Any) -> int:  # type: ignore[override]
        """Send a datagram, unless it would leave the computer."""
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _refuse()
        return super().sendto(*args)


def forbid_network() -> None:
    """From now on, no name is resolved and no internet socket connects in this process."""
    global _closed
    if _closed:
        return
    socket.socket = _GuardedSocket  # type: ignore[misc]
    socket.getaddrinfo = _refuse  # type: ignore[assignment]
    socket.gethostbyname = _refuse  # type: ignore[assignment]
    socket.gethostbyname_ex = _refuse  # type: ignore[assignment]
    socket.create_connection = _refuse  # type: ignore[assignment]
    _closed = True


def no_telemetry() -> bool:
    """Switch off ONNX Runtime's telemetry, which only works before the library is loaded;
    returns False when it was loaded already (by the application, before optdoc)."""
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"
    return "onnxruntime" not in sys.modules


def network_forbidden() -> bool:
    """True once :func:`forbid_network` has run in this process."""
    return _closed
