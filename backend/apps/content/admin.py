from django.contrib import admin

from apps.audit.admin_mixins import AdminAuditMixin, NoCreate, NoDelete

from . import workflow
from .models import News, NewsCategory

# NewsReview (the approval history) is deliberately NOT registered: it cannot be added, changed or deleted from the admin.
# Policy for News in the admin (superusers only):
#   * no add (the portal creates items with an author and a draft status), no delete (it would erase the approval history; archive instead),
#     therefore no bulk "delete selected" either;
#   * status, publication date and author are read-only: they change only through the approval workflow;
#   * text fields (title, slug, excerpt, body, category) are editable with an audit entry, except while the item is UNDER REVIEW (frozen, as in the
#     portal); changing the text of an APPROVED item sends it back to draft with a history row, exactly like the portal does.
TEXT_FIELDS = {"title", "slug", "excerpt", "body", "category"}


@admin.register(NewsCategory)
class NewsCategoryAdmin(AdminAuditMixin, admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(News)
class NewsAdmin(AdminAuditMixin, NoCreate, NoDelete, admin.ModelAdmin):
    list_display = ("title", "category", "status", "publish_at")
    list_filter = ("status", "category")
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("status", "publish_at", "author")

    def get_readonly_fields(self, request, obj=None):
        base = super().get_readonly_fields(request, obj)
        if obj is not None and obj.status == News.Status.REVIEW:
            return tuple(base) + tuple(sorted(TEXT_FIELDS))  # frozen while a reviewer is deciding
        return base

    def get_prepopulated_fields(self, request, obj=None):
        return {} if obj is not None else super().get_prepopulated_fields(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        edited = sorted(set(form.changed_data) & TEXT_FIELDS)
        if change and edited and workflow.reset_after_edit(obj, request.user, request, edited):
            self._audit_state["fields"] = sorted(set(self._audit_state["fields"]) | {"approval_reset"})
