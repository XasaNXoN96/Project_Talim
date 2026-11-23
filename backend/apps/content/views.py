from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.achievements.models import Achievement
from apps.gallery.models import MediaItem
from apps.organization.models import Employee, Institution

from .covers import cover_response
from .models import Announcement, Faq, Leader, News, SiteEvent


class HomeView(TemplateView):
    template_name = "content/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["latest_news"] = News.objects.published().select_related("category")[:6]
        context["latest_video"] = MediaItem.objects.published().filter(kind=MediaItem.Kind.VIDEO).first()
        context["latest_photos"] = list(MediaItem.objects.published().filter(kind=MediaItem.Kind.PHOTO)[:5])
        today = timezone.localdate()
        context["ticker"] = [a for a in Announcement.objects.filter(is_published=True)[:8] if a.text]
        context["events"] = SiteEvent.objects.filter(is_published=True, date__gte=today)[:4]
        context["leaders"] = Leader.objects.filter(is_published=True)[:3]
        context["faqs"] = Faq.objects.filter(is_published=True)[:8]
        context["map_schools"] = Institution.objects.filter(is_published=True, map_x__isnull=False, map_y__isnull=False)[:40]
        context["latest_achievements"] = Achievement.objects.published().filter(images__isnull=False).distinct().select_related("institution").prefetch_related("images")[:4]
        return context


class NewsListView(ListView):
    template_name = "content/news_list.html"
    context_object_name = "news_list"
    paginate_by = 12

    def get_queryset(self):
        qs = News.objects.published().select_related("category")
        q = (self.request.GET.get("q") or "").strip()[:80]
        return qs.filter(title__icontains=q) if q else qs


class NewsDetailView(DetailView):
    template_name = "content/news_detail.html"
    context_object_name = "news"

    def get_queryset(self):
        return News.objects.published().select_related("category")


class NewsCoverView(View):
    """The cover of a PUBLISHED news item, for everybody. Anything else (draft, archived, not yet due) does not exist."""

    def get(self, request, pk):
        return cover_response(get_object_or_404(News.objects.published(), pk=pk), public=True)


class InstitutionListView(ListView):
    """Public catalogue of the published institutions, with a name search and a type filter."""

    template_name = "content/institution_list.html"
    context_object_name = "institutions"
    paginate_by = 12

    def get_queryset(self):
        qs = Institution.objects.filter(is_published=True)
        q = (self.request.GET.get("q") or "").strip()[:80]
        kind = self.request.GET.get("kind") or ""
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(address__icontains=q))
        if kind in dict(Institution.Kind.choices):
            qs = qs.filter(kind=kind)
        return qs.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["kinds"] = Institution.Kind.choices
        context["q"] = (self.request.GET.get("q") or "").strip()[:80]
        context["kind"] = self.request.GET.get("kind") or ""
        return context


class InstitutionDetailView(DetailView):
    template_name = "content/institution_detail.html"
    context_object_name = "inst"

    def get_queryset(self):
        return Institution.objects.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inst = self.object
        context["achievements"] = Achievement.objects.published().filter(institution=inst).prefetch_related("images")[:4]
        context["teachers"] = _public_staff().filter(institution=inst)[:8]
        return context


def _public_staff():
    return Employee.objects.filter(show_on_site=True, status=Employee.Status.ACTIVE).exclude(photo="").select_related("position", "institution")


class TeacherListView(ListView):
    """Public page of the staff members who agreed to be shown (flag on the card)."""

    template_name = "content/teacher_list.html"
    context_object_name = "people"
    paginate_by = 16

    def get_queryset(self):
        qs = _public_staff().order_by("last_name", "first_name")
        q = (self.request.GET.get("q") or "").strip()[:80]
        inst = self.request.GET.get("inst") or ""
        if q:
            qs = qs.filter(Q(last_name__icontains=q) | Q(first_name__icontains=q) | Q(position__name__icontains=q))
        if inst:
            qs = qs.filter(institution_id=inst) if inst.replace("-", "").isalnum() and len(inst) <= 40 else qs.none()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = (self.request.GET.get("q") or "").strip()[:80]
        context["inst"] = self.request.GET.get("inst") or ""
        context["institutions"] = Institution.objects.filter(is_published=True, employees__show_on_site=True).distinct().order_by("name")
        return context


class TeacherPhotoView(View):
    """Public photo of a person only while the card is marked for the site and the person is active; everything else is a 404."""

    def get(self, request, pk):
        employee = _public_staff().filter(pk=pk).first()
        if employee is None:
            raise Http404
        try:
            handle = employee.photo.storage.open(employee.photo.name, "rb")
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise Http404 from exc
        response = FileResponse(handle, content_type="image/jpeg")
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "public, max-age=3600"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


class SearchView(TemplateView):
    """One search over what the public may see: news, achievements, institutions, staff on the site."""

    template_name = "content/search.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = (self.request.GET.get("q") or "").strip()[:80]
        context["q"] = q
        if len(q) >= 2:
            context["news"] = News.objects.published().filter(Q(title__icontains=q) | Q(excerpt__icontains=q))[:8]
            context["achievements"] = Achievement.objects.published().filter(Q(title__icontains=q) | Q(person_name__icontains=q)).prefetch_related("images")[:8]
            context["institutions"] = Institution.objects.filter(is_published=True).filter(Q(name__icontains=q) | Q(address__icontains=q))[:8]
            context["people"] = _public_staff().filter(Q(last_name__icontains=q) | Q(first_name__icontains=q) | Q(position__name__icontains=q))[:8]
            context["found"] = any(context[k] for k in ("news", "achievements", "institutions", "people"))
        return context


class EventListView(ListView):
    template_name = "content/event_list.html"
    context_object_name = "events"
    paginate_by = 20

    def get_queryset(self):
        return SiteEvent.objects.filter(is_published=True, date__gte=timezone.localdate())


class LeaderPhotoView(View):
    """Public photo of a leader, only while the entry is published."""

    def get(self, request, pk):
        leader = Leader.objects.filter(pk=pk, is_published=True).exclude(photo="").first()
        if leader is None:
            raise Http404
        try:
            handle = leader.photo.storage.open(leader.photo.name, "rb")
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise Http404 from exc
        response = FileResponse(handle, content_type="image/jpeg")
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "public, max-age=3600"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response
