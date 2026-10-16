from .models import AuditLog


def client_ip(request):
    """REMOTE_ADDR only. X-Forwarded-For is attacker-controlled; trust it only once a proxy is configured."""
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


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
