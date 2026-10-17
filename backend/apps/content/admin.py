from django.contrib import admin

from .models import News, NewsCategory


@admin.register(NewsCategory)
class NewsCategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "publish_at")
    list_filter = ("status", "category")
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    # Status, publication date and author change ONLY through the approval workflow (apps.content.workflow): the admin would leave no history,
    # no audit entry and no approval. Deleting would also erase the review history; items are archived instead.
    readonly_fields = ("status", "publish_at", "author")

    def has_delete_permission(self, request, obj=None):
        return False
