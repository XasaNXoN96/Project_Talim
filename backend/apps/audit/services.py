from apps.core import network

from .models import AuditLog


def client_ip(request):
    """Real client address; forwarded headers are honoured only from configured trusted proxies (apps.core.network)."""
    if request is None:
        return None
    return network.client_ip(request)


def record(action, *, request=None, user=None, object_type="", object_id="", meta=None):
    user_agent = ""
    if request is not None:
        user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:255]
    if user is not None and not getattr(user, "pk", None):
        user = None
    return AuditLog.objects.create(
        user=user,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id else "",
        ip=client_ip(request),
        user_agent=user_agent,
        meta=meta or {},
    )
