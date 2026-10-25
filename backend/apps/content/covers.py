"""Serving a news cover: the same careful response as the achievement pictures (nosniff, sandboxed, never guessed by name)."""
from django.http import FileResponse, Http404


def cover_response(news, *, public):
    if not news.cover:
        raise Http404
    try:
        handle = news.cover.storage.open(news.cover.name, "rb")
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404 from exc
    response = FileResponse(handle, content_type="image/jpeg")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=3600" if public else "private, no-cache"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response
