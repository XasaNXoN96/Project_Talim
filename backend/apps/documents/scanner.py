"""ClamAV client (clamd INSTREAM protocol over a local socket).

* The bytes go only to the clamd you configure (a unix socket or a TCP host you name, normally 127.0.0.1). Nothing is
  sent to any external service.
* Fail-closed: anything other than a clear "OK" answer (daemon down, timeout, protocol error, size limit hit,
  unexpected reply) is a failure; callers must NOT treat the file as safe. There is no quarantine queue: a failed scan
  rejects the upload and the user is asked to retry.
* One overall deadline (CLAMAV_TIMEOUT) covers connecting, sending and waiting for the verdict.
* Logs carry only the error type and the signature name; never file names or content.
"""
import logging
import re
import socket
import struct
import time
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

CHUNK = 64 * 1024
SIGNATURE_RE = re.compile(r"[^A-Za-z0-9._\-+/ ]")


class ScanFailed(Exception):
    """The file could NOT be verified. `code` is safe to log: scan_unavailable | scan_timeout | scan_error."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    signature: str = ""  # only set when a threat was found; sanitised
    engine: str = "clamav"


def mode() -> str:
    return getattr(settings, "DOCUMENT_SCAN_MODE", "clamav")


def _connect(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise socket.timeout()
    path = getattr(settings, "CLAMAV_SOCKET", "")
    if path:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(remaining)
        sock.connect(path)
    else:
        sock = socket.create_connection((settings.CLAMAV_HOST, int(settings.CLAMAV_PORT)), timeout=remaining)
    return sock


def _recv_reply(sock, deadline):
    buf = b""
    while not buf.endswith(b"\0") and not buf.endswith(b"\n"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout()
        sock.settimeout(remaining)
        part = sock.recv(4096)
        if not part:
            break
        buf += part
        if len(buf) > 4096:
            break
    return buf.rstrip(b"\0\n").decode("utf-8", "replace")


def scan_bytes(data: bytes) -> ScanResult:
    """Scan `data`. Returns ScanResult; raises ScanFailed whenever a clean verdict was not obtained."""
    timeout = float(getattr(settings, "CLAMAV_TIMEOUT", 20))
    deadline = time.monotonic() + timeout
    sock = None
    try:
        sock = _connect(deadline)
        sock.sendall(b"zINSTREAM\0")
        for start in range(0, len(data), CHUNK):
            if time.monotonic() > deadline:
                raise socket.timeout()
            chunk = data[start:start + CHUNK]
            sock.settimeout(max(deadline - time.monotonic(), 0.001))
            sock.sendall(struct.pack("!I", len(chunk)) + chunk)
        sock.sendall(struct.pack("!I", 0))
        reply = _recv_reply(sock, deadline)
    except socket.timeout as exc:
        logger.error("Virus scan timed out after %ss", timeout)
        raise ScanFailed("scan_timeout") from exc
    except (OSError, ValueError) as exc:  # refused, reset, broken pipe, no such socket, ...
        logger.error("Virus scanner unreachable (%s)", type(exc).__name__)
        raise ScanFailed("scan_unavailable") from exc
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    # Replies: "stream: OK" | "stream: <Signature> FOUND" | "<message> ERROR"
    if reply.endswith(" FOUND") and reply.startswith("stream:"):
        name = SIGNATURE_RE.sub("", reply[len("stream:"):-len(" FOUND")].strip())[:80]
        return ScanResult(clean=False, signature=name or "unknown")
    if reply == "stream: OK":
        return ScanResult(clean=True)
    logger.error("Virus scanner returned an unexpected verdict (%d chars)", len(reply))
    raise ScanFailed("scan_error")


def ping() -> bool:
    """True when clamd answers PONG (used by the health command)."""
    deadline = time.monotonic() + min(float(getattr(settings, "CLAMAV_TIMEOUT", 20)), 5)
    try:
        sock = _connect(deadline)
        try:
            sock.sendall(b"zPING\0")
            return _recv_reply(sock, deadline) == "PONG"
        finally:
            sock.close()
    except (OSError, ValueError):
        return False
