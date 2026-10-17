"""Portal for the content team: list, write, preview, submit for review, approve, publish and archive news.

Rules (checked on the server for every request, the menu only mirrors them; the status rules live in apps.content.workflow):
  * view_news            list, preview and the review history (any status)
  * add_news             create
  * change_news          edit and submit/withdraw one's own items (anyone's, together with review_news or publish_news)
  * review_news          approve or return for changes (never one's own item, unless approve_own_news)
  * publish_news         publish an APPROVED item, unpublish, archive, restore, and edit what is public
Nothing here grants access to the Django admin."""
import uuid

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin

from .manage_forms import NewsCategoryForm, NewsForm
from . import workflow
from .models import News, NewsCategory

S = News.Status


def _audit(action, request, news, **meta):
    record(action, request=request, user=request.user, object_type="News", object_id=news.pk, meta=meta)


def is_live(news):
    return news.status == S.PUBLISHED and news.publish_at is not None and news.publish_at <= timezone.now()


class NewsListView(PortalPermissionMixin, ListView):
    permission_required = "content.view_news"
    template_name = "portal/news/list.html"
    paginate_by = 20
    context_object_name = "items"

    def get_queryset(self):
        qs = News.objects.select_related("category", "author")
        g = self.request.GET
        q = (g.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(excerpt__icontains=q))
        if g.get("status") in S.values:
            qs = qs.filter(status=g["status"])
        if g.get("category"):
            try:
                qs = qs.filter(category_id=uuid.UUID(g["category"]))
            except ValueError:
                qs = qs.none()
        return qs.order_by("-updated_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g = self.request.GET
        u = self.request.user
        ctx.update(q=g.get("q", ""), status=g.get("status", ""), category=g.get("category", ""), statuses=S.choices,
                   categories=NewsCategory.objects.all(), can_add=u.has_perm("content.add_news"), can_publish=u.has_perm("content.publish_news"),
                   can_categories=u.has_perm("content.view_newscategory"), now=timezone.now(),
                   review_count=News.objects.filter(status=S.REVIEW).count() if u.has_perm("content.review_news") else None)
        return ctx


class NewsCreateView(PortalPermissionMixin, View):
    permission_required = "content.add_news"

    def get(self, request):
        return render(request, "portal/news/form.html", {"form": NewsForm(), "creating": True})

    def post(self, request):
        form = NewsForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                news = form.save(commit=False)
                news.status, news.author = S.DRAFT, request.user  # nothing is born public
                news.save()
                _audit(AuditLog.Action.NEWS_CREATED, request, news)
            messages.success(request, _("Qoralama saqlandi. Nashr etishdan oldin ko‘rib chiqing."))
            return redirect("news_admin:preview", pk=news.pk)
        messages.error(request, _("Formada xatolar bor. Kiritilgan ma’lumotlar saqlanib turibdi."))
        return render(request, "portal/news/form.html", {"form": form, "creating": True})


class _NewsBase(PortalPermissionMixin, View):
    permission_required = "content.view_news"

    def get_news(self, pk):
        return get_object_or_404(News.objects.select_related("category", "author"), pk=pk)


class NewsEditView(_NewsBase):
    permission_required = "content.change_news"

    def _news(self, pk, user, lock=False):
        qs = News.objects.select_related("category", "author")
        news = get_object_or_404(qs.select_for_update(of=("self",)) if lock else qs, pk=pk)
        if not workflow.can_edit(news, user):
            raise PermissionDenied
        return news

    def get(self, request, pk):
        news = self._news(pk, request.user)
        return render(request, "portal/news/form.html", {"form": NewsForm(instance=news), "news": news})

    def post(self, request, pk):
        with transaction.atomic():
            news = self._news(pk, request.user, lock=True)  # the row is locked: a parallel submit/approve waits, then sees the new status
            old_date = news.publish_at
            form = NewsForm(request.POST, instance=news)
            if form.is_valid():
                changed = sorted(f for f in form.changed_data if f != "publish_at")
                new_date = form.cleaned_data["publish_at"]
                if new_date != old_date and (old_date is None or new_date is None or abs(new_date - old_date).total_seconds() >= 60):
                    changed.append("publish_at")  # the form only knows minutes: a re-submitted value is not a change
                    changed.sort()
                form.save()
                reset = workflow.reset_after_edit(news, request.user, request, changed)
                if changed:
                    _audit(AuditLog.Action.NEWS_UPDATED, request, news, fields=changed, **({"approval_reset": True} if reset else {}))
                messages.success(request, _("Saqlandi.") if not reset else _("Saqlandi. Yangilik ma’qullangandan keyin o‘zgartirildi, shuning uchun qayta tekshiruv kerak."))
                return redirect("news_admin:preview", pk=news.pk)
        messages.error(request, _("Formada xatolar bor. Kiritilgan ma’lumotlar saqlanib turibdi."))
        return render(request, "portal/news/form.html", {"form": form, "news": news})


class NewsPreviewView(_NewsBase):
    def get(self, request, pk):
        news = self.get_news(pk)
        u = request.user
        return render(request, "portal/news/preview.html", {
            "news": news, "live": is_live(news), "can_edit": workflow.can_edit(news, u), "steps": workflow.allowed_steps(news, u),
            "reviews": news.reviews.select_related("actor"), "last_return": news.reviews.filter(action="request_changes").last() if news.status == S.CHANGES_REQUESTED else None,
        })


class NewsStatusView(_NewsBase):
    """GET asks for confirmation (and a comment where one is needed), POST does it. The permission depends on the step; the rest is in workflow.perform."""

    def get_permission_required(self):
        step = workflow.STEPS.get(self.kwargs.get("action"))
        return (step.permission,) if step else ("content.view_news",)

    def _step(self, action):
        if action not in workflow.STEPS:
            raise Http404
        return workflow.STEPS[action]

    def get(self, request, pk, action):
        step = self._step(action)
        news = self.get_news(pk)
        if news.status not in step.sources:
            messages.error(request, _("Bu amalni hozirgi holatda bajarib bo‘lmaydi."))
            return redirect("news_admin:preview", pk=news.pk)
        try:
            workflow.check_actor(action, news, request.user)
        except workflow.WorkflowError as exc:
            messages.error(request, str(exc))
            return redirect("news_admin:preview", pk=news.pk)
        return render(request, "portal/news/confirm.html", {"news": news, "action": action, "question": step.question, "step": step, "version": workflow.version_token(news)})

    def post(self, request, pk, action):
        self._step(action)
        get_object_or_404(News, pk=pk)
        try:
            news = workflow.perform(action, pk, request.user, request=request, comment=request.POST.get("comment", ""), version=request.POST.get("version") or None)
        except workflow.WorkflowError as exc:
            messages.error(request, str(exc))
            return redirect("news_admin:preview", pk=pk)
        messages.success(request, workflow.STEPS[action].success)
        return redirect("news_admin:preview", pk=news.pk)


class CategoryListView(PortalPermissionMixin, View):
    permission_required = "content.view_newscategory"

    def get(self, request):
        return render(request, "portal/news/categories.html", {
            "categories": NewsCategory.objects.all(), "can_add": request.user.has_perm("content.add_newscategory"),
            "can_change": request.user.has_perm("content.change_newscategory"),
        })


class _CategoryForm(PortalPermissionMixin, View):
    def render_form(self, request, form, category=None):
        return render(request, "portal/news/category_form.html", {"form": form, "category": category})

    def save(self, request, form, category=None):
        if form.is_valid():
            saved = form.save()
            _audit_category(request, saved, "created" if category is None else "renamed")
            messages.success(request, _("Saqlandi."))
            return redirect("news_admin:categories")
        return self.render_form(request, form, category)


def _audit_category(request, category, what):
    record(AuditLog.Action.NEWS_CATEGORY_CHANGED, request=request, user=request.user, object_type="NewsCategory", object_id=category.pk, meta={"what": what})


class CategoryCreateView(_CategoryForm):
    permission_required = "content.add_newscategory"

    def get(self, request):
        return self.render_form(request, NewsCategoryForm())

    def post(self, request):
        return self.save(request, NewsCategoryForm(request.POST))


class CategoryEditView(_CategoryForm):
    permission_required = "content.change_newscategory"

    def get(self, request, pk):
        c = get_object_or_404(NewsCategory, pk=pk)
        return self.render_form(request, NewsCategoryForm(instance=c), c)

    def post(self, request, pk):
        c = get_object_or_404(NewsCategory, pk=pk)
        return self.save(request, NewsCategoryForm(request.POST, instance=c), c)
