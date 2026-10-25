from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.achievements.models import Achievement
from apps.gallery.models import MediaItem

from .covers import cover_response
from .models import News


class HomeView(TemplateView):
    template_name = "content/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["latest_news"] = News.objects.published().select_related("category")[:6]
        context["latest_video"] = MediaItem.objects.published().filter(kind=MediaItem.Kind.VIDEO).first()
        context["latest_photos"] = list(MediaItem.objects.published().filter(kind=MediaItem.Kind.PHOTO)[:5])
        context["latest_achievements"] = Achievement.objects.published().select_related("institution")[:4]
        return context


class NewsListView(ListView):
    template_name = "content/news_list.html"
    context_object_name = "news_list"
    paginate_by = 12

    def get_queryset(self):
        return News.objects.published().select_related("category")


class NewsDetailView(DetailView):
    template_name = "content/news_detail.html"
    context_object_name = "news"

    def get_queryset(self):
        return News.objects.published().select_related("category")


class NewsCoverView(View):
    """The cover of a PUBLISHED news item, for everybody. Anything else (draft, archived, not yet due) does not exist."""

    def get(self, request, pk):
        return cover_response(get_object_or_404(News.objects.published(), pk=pk), public=True)
