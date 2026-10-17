from django.contrib import admin

from apps.audit.admin_mixins import AdminAuditMixin

from .models import DocumentCategory


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(AdminAuditMixin, admin.ModelAdmin):
    """Only categories are editable here. Documents and files deliberately have NO admin: the admin would bypass the
    access levels and the download audit."""

    list_display = ("__str__", "is_active")  # __str__ = the name shown in the active language
