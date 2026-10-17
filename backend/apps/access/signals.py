from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.audit.models import AuditLog
from apps.audit.services import record

from .models import RoleAssignment


@receiver(post_save, sender=RoleAssignment)
def sync_group_on_save(sender, instance, created, **kwargs):
    instance.user.groups.add(instance.role)
    if created:
        record(
            AuditLog.Action.ROLE_ASSIGNED,
            request=getattr(instance, "_audit_request", None),
            user=getattr(instance, "_audit_actor", None),  # who did it (None when done from the shell/admin without context)
            object_type="RoleAssignment",
            object_id=instance.pk,
            meta={"user_id": str(instance.user_id), "role": instance.role.name, "scope": instance.scope},
        )


@receiver(post_delete, sender=RoleAssignment)
def sync_group_on_delete(sender, instance, **kwargs):
    # Do not touch instance.user: it may already be gone when the delete is a cascade from the user.
    if not RoleAssignment.objects.filter(user_id=instance.user_id, role_id=instance.role_id).exists():
        get_user_model().groups.through.objects.filter(user_id=instance.user_id, group_id=instance.role_id).delete()
    record(
        AuditLog.Action.ROLE_REVOKED,
        request=getattr(instance, "_audit_request", None),
        user=getattr(instance, "_audit_actor", None),
        object_type="RoleAssignment",
        object_id=instance.pk,
        meta={"user_id": str(instance.user_id), "role_id": instance.role_id, "scope": instance.scope},
    )
