from django.views.generic import DetailView, ListView, TemplateView

from apps.achievements.models import Achievement

from .models import News


class HomeView(TemplateView):
    template_name = "content/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["latest_news"] = News.objects.published().select_related("category")[:6]
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
