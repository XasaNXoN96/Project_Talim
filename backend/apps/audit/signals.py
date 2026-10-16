import hashlib

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import AuditLog
from .services import record


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record(AuditLog.Action.LOGIN, request=request, user=user, object_type="User", object_id=user.pk)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        record(AuditLog.Action.LOGOUT, request=request, user=user, object_type="User", object_id=user.pk)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    # The typed identifier may be a mistyped password, so only a short hash and the length are stored.
    identifier = str(credentials.get("username") or "")
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:16]
    record(
        AuditLog.Action.LOGIN_FAILED,
        request=request,
        meta={"identifier_sha256_16": digest, "identifier_length": len(identifier)},
    )
