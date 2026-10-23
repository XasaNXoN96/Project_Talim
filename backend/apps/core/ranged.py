"""Serving a stored media file with HTTP Range support (browsers seek in videos with it). Used by achievements and the gallery.
Call it only AFTER the permission check; the file lives in the private storage and has no public address."""
import re

from django.http import Http404, HttpResponse, StreamingHttpResponse


def parse_range(header, size):
    """('ok', start, end) for a single byte range, ('none',) when there is no Range header, ('bad',) when it cannot be satisfied."""
    if not header:
        return ("none",)
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return ("bad",)
    if m.group(1) == "":  # the last N bytes
        n = int(m.group(2))
        if n == 0:
            return ("bad",)
        return ("ok", max(size - n, 0), size - 1)
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else size - 1
    if start >= size or end < start:
        return ("bad",)
    return ("ok", start, min(end, size - 1))


def ranged_file_response(request, field_file, content_type, *, public):
    try:
        handle = field_file.storage.open(field_file.name, "rb")
        size = field_file.storage.size(field_file.name)
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404 from exc
    rng = parse_range(request.headers.get("Range"), size)
    if rng[0] == "bad":
        handle.close()
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    start, end = (rng[1], rng[2]) if rng[0] == "ok" else (0, size - 1)
    length = end - start + 1

    def chunks():
        try:
            handle.seek(start)
            left = length
            while left > 0:
                data = handle.read(min(64 * 1024, left))
                if not data:
                    break
                left -= len(data)
                yield data
        finally:
            handle.close()

    response = StreamingHttpResponse(chunks(), status=206 if rng[0] == "ok" else 200, content_type=content_type)
    response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    if rng[0] == "ok":
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=3600" if public else "private, no-cache"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response
