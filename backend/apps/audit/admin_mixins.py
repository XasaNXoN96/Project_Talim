"""Audit trail for the Django admin, in the project's own AuditLog (no parallel journal).

What an entry holds: who (the signed-in superuser), when, the model and the object id, and WHAT KIND of change: the NAMES of the changed fields,
the permission codenames added or removed, and old -> new for a few harmless flags. It never holds field values (so no passwords or hashes, no
news text, no internal notes, no personal data). Django's own admin history (LogEntry) keeps running as before.

Every write path of a ModelAdmin is covered: save_model (+ many-to-many through save_related), delete_model, delete_queryset (the bulk
"delete selected" action). Models whose deletion or creation is not allowed in the admin also lose the matching bulk action automatically
(Django offers `delete_selected` only when has_delete_permission is true). The audit row is written inside the admin's own transaction:
if the change fails, no entry remains; if the entry fails, the change is rolled back."""
from .models import AuditLog
from .services import record

# harmless booleans whose old and new value is written down (security relevant flags)
VISIBLE_FLAGS = ("is_superuser", "is_staff", "is_active", "must_change_password", "is_published")


def _perm_names(manager):
    return sorted(f"{ct}.{code}" for ct, code in manager.values_list("content_type__app_label", "codename"))


class AdminAuditMixin:
    audited_m2m: tuple = ()  # names of PERMISSION many-to-many fields (permissions, user_permissions): members are recorded by codename

    def _meta_for(self, obj, **extra):
        return {"via": "django_admin", **extra}

    def save_model(self, request, obj, form, change):
        before_flags = {}
        watched = [f for f in VISIBLE_FLAGS if f in form.changed_data]
        if change and obj.pk and watched:
            before_flags = type(obj).objects.filter(pk=obj.pk).values(*watched).first() or {}
        before_m2m = {name: set() for name in self.audited_m2m}  # on creation everything that is set counts as added
        if change and obj.pk:
            stored = type(obj).objects.get(pk=obj.pk)
            for name in self.audited_m2m:
                before_m2m[name] = set(_perm_names(getattr(stored, name)))
        self._audit_state = {"change": change, "fields": sorted(form.changed_data), "flags_before": before_flags, "m2m_before": before_m2m}
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        state = getattr(self, "_audit_state", {"change": change, "fields": sorted(form.changed_data), "flags_before": {}, "m2m_before": {}})
        obj = form.instance
        meta = self._meta_for(obj, fields=state["fields"])
        flags = {f: [state["flags_before"][f], getattr(obj, f)] for f in state["flags_before"] if state["flags_before"][f] != getattr(obj, f)}
        if flags:
            meta["flags"] = flags
        for name, before in state["m2m_before"].items():
            after = set(_perm_names(getattr(obj, name)))
            if after != before:
                meta[f"{name}_added"], meta[f"{name}_removed"] = sorted(after - before), sorted(before - after)
        if change and not state["fields"] and len(meta) == 2:
            return  # nothing changed: no entry
        record(AuditLog.Action.ADMIN_CHANGED if change else AuditLog.Action.ADMIN_CREATED, request=request, user=request.user,
               object_type=type(obj).__name__, object_id=obj.pk, meta=meta)

    def delete_model(self, request, obj):
        record(AuditLog.Action.ADMIN_DELETED, request=request, user=request.user, object_type=type(obj).__name__, object_id=obj.pk, meta=self._meta_for(obj))
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for pk in list(queryset.values_list("pk", flat=True)):
            record(AuditLog.Action.ADMIN_DELETED, request=request, user=request.user, object_type=queryset.model.__name__, object_id=pk,
                   meta=self._meta_for(None, bulk=True))
        super().delete_queryset(request, queryset)


class NoCreate:
    def has_add_permission(self, request):
        return False


class NoDelete:
    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(NoCreate, NoDelete):
    def has_change_permission(self, request, obj=None):
        return False
