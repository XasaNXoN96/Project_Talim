from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin
from apps.documents import files
from apps.documents.forms import FileMixin
from apps.documents.validation import UploadRejected
from apps.notifications.models import Notification
from apps.notifications.services import notify

from . import access
from .forms import CommentForm, TaskForm
from .models import Task, TaskAttachment, TaskEvent


def _event(task, actor, kind, **meta):
    TaskEvent.objects.create(task=task, actor=actor, kind=kind, meta=meta)


class TaskListView(PortalPermissionMixin, ListView):
    permission_required = "tasks.view_task"
    template_name = "portal/tasks/list.html"
    paginate_by = 25
    context_object_name = "tasks"
    TABS = (("mine", _("Menga berilgan")), ("created", _("Men bergan")), ("all", _("Barchasi")))

    def get_queryset(self):
        user = self.request.user
        tab = self.request.GET.get("tab", "mine")
        qs = access.visible_tasks(user).select_related("created_by").prefetch_related("assignees")
        if tab == "mine":
            qs = qs.filter(assignees=user)
        elif tab == "created":
            qs = qs.filter(created_by=user)
        status = self.request.GET.get("status")
        if status in Task.Status.values:
            qs = qs.filter(status=status)
        elif tab != "all":
            qs = qs.exclude(status__in=Task.FINAL) if self.request.GET.get("closed") != "1" else qs
        q = (self.request.GET.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        return qs.order_by("due_date", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g = self.request.GET
        ctx.update(
            tab=g.get("tab", "mine") if g.get("tab") in dict(self.TABS) else "mine", tabs=self.TABS, q=g.get("q", ""), status=g.get("status", ""),
            statuses=Task.Status.choices, can_add=self.request.user.has_perm("tasks.add_task"), today=timezone.localdate(),
            closed=g.get("closed") == "1",
        )
        return ctx


class _TaskBase(PortalPermissionMixin, View):
    permission_required = "tasks.view_task"

    def get_task(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        if not access.can_view(request.user, task):
            raise PermissionDenied  # same answer for "does not exist for you" is not needed: ids are unguessable UUIDs
        return task


class TaskDetailView(_TaskBase):
    def get(self, request, pk, form=None):
        task = self.get_task(request, pk)
        transitions = access.allowed_transitions(request.user, task)
        return render(request, "portal/tasks/detail.html", {
            "task": task, "assignees": task.assignees.all(), "comments": task.comments.select_related("author"),
            "events": task.events.select_related("actor"), "form": form or CommentForm(),
            "transitions": [(c, l) for c, l in Task.Status.choices if c in transitions],
            "can_edit": access.can_edit(request.user, task), "today": timezone.localdate(),
            "attachments": [(a, access.can_remove_attachment(request.user, task, a)) for a in task.attachments.filter(removed_at__isnull=True).select_related("uploaded_by")],
            "can_attach": access.can_attach(request.user, task), "attach_form": FileMixin(),
        })


class TaskCommentView(_TaskBase):
    http_method_names = ["post"]
    permission_required = ["tasks.view_task", "tasks.add_taskcomment"]

    def post(self, request, pk):
        task = self.get_task(request, pk)
        form = CommentForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("Izoh bo‘sh yoki juda uzun."))
            return redirect("tasks:detail", pk=task.pk)
        with transaction.atomic():
            comment = form.save(commit=False)
            comment.task, comment.author = task, request.user
            comment.save()
            _event(task, request.user, TaskEvent.Kind.COMMENTED)
        return redirect("tasks:detail", pk=task.pk)


class TaskCreateView(PortalPermissionMixin, View):
    permission_required = "tasks.add_task"

    def get(self, request):
        return render(request, "portal/tasks/form.html", {"form": TaskForm(assignable=access.assignable_users(request.user)), "creating": True})

    def post(self, request):
        form = TaskForm(request.POST, assignable=access.assignable_users(request.user))
        if form.is_valid():
            with transaction.atomic():
                task = form.save(commit=False)
                task.created_by = request.user
                task.save()
                form.save_m2m()
                _event(task, request.user, TaskEvent.Kind.CREATED, assignees=[str(u.pk) for u in form.cleaned_data["assignees"]])
                for person in form.cleaned_data["assignees"]:
                    notify(person, Notification.Kind.TASK_ASSIGNED, task, actor=request.user)
            messages.success(request, _("Topshiriq yaratildi."))
            return redirect("tasks:detail", pk=task.pk)
        return render(request, "portal/tasks/form.html", {"form": form, "creating": True})


class TaskEditView(_TaskBase):
    permission_required = "tasks.change_task"

    def _task(self, request, pk):
        task = self.get_task(request, pk)
        if not access.can_edit(request.user, task):
            raise PermissionDenied
        return task

    def get(self, request, pk):
        task = self._task(request, pk)
        return render(request, "portal/tasks/form.html", {"form": TaskForm(instance=task, assignable=access.assignable_users(request.user)), "task": task})

    def post(self, request, pk):
        task = self._task(request, pk)
        form = TaskForm(request.POST, instance=task, assignable=access.assignable_users(request.user))
        if form.is_valid():
            changed = sorted(form.changed_data)
            before = set(task.assignees.values_list("pk", flat=True))
            with transaction.atomic():
                form.save()
                if changed:
                    _event(task, request.user, TaskEvent.Kind.EDITED, fields=changed)
                for person in task.assignees.exclude(pk__in=before):
                    notify(person, Notification.Kind.TASK_ASSIGNED, task, actor=request.user)
            messages.success(request, _("Saqlandi."))
            return redirect("tasks:detail", pk=task.pk)
        return render(request, "portal/tasks/form.html", {"form": form, "task": task})


class TaskTransitionView(_TaskBase):
    http_method_names = ["post"]

    def post(self, request, pk, status):
        with transaction.atomic():
            task = get_object_or_404(Task.objects.select_for_update(), pk=pk)
            if not access.can_view(request.user, task):
                raise PermissionDenied
            if status not in access.allowed_transitions(request.user, task):
                messages.error(request, _("Bu holatga o‘tkazib bo‘lmaydi."))
                return redirect("tasks:detail", pk=task.pk)
            old, task.status = task.status, status
            task.closed_at = timezone.now() if status in Task.FINAL else None
            task.save(update_fields=["status", "closed_at", "updated_at"])
            _event(task, request.user, TaskEvent.Kind.STATUS, old=old, new=status)
            S, K = Task.Status, Notification.Kind
            if status == S.REVIEW:
                notify(task.created_by, K.TASK_SUBMITTED, task, actor=request.user)
            else:
                kind = {S.DONE: K.TASK_ACCEPTED, S.CANCELLED: K.TASK_CANCELLED}.get(status) or (K.TASK_RETURNED if old == S.REVIEW else None)
                if kind:
                    for person in task.assignees.all():
                        notify(person, kind, task, actor=request.user)
                    if status == S.CANCELLED:
                        notify(task.created_by, kind, task, actor=request.user)
        messages.success(request, _("Holat o‘zgartirildi."))
        return redirect("tasks:detail", pk=task.pk)


class _AttachmentForm(FileMixin):
    pass


class TaskAttachmentAddView(_TaskBase):
    http_method_names = ["post"]
    permission_required = ["tasks.view_task", "tasks.add_taskattachment"]

    def post(self, request, pk):
        task = self.get_task(request, pk)
        if not access.can_attach(request.user, task):
            raise PermissionDenied
        form = _AttachmentForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, _("Fayl tanlanmagan yoki noto‘g‘ri."))
            return redirect("tasks:detail", pk=task.pk)
        if task.attachments.filter(removed_at__isnull=True).count() >= TaskAttachment.MAX_PER_TASK:
            messages.error(request, gettext("Bitta topshiriqqa %(n)d tadan ortiq fayl biriktirib bo‘lmaydi.") % {"n": TaskAttachment.MAX_PER_TASK})
            return redirect("tasks:detail", pk=task.pk)
        try:
            checked = files.check_or_audit(form.cleaned_data["file"], request=request, user=request.user, object_type="Task", object_id=task.pk)
        except UploadRejected as exc:
            messages.error(request, str(exc))
            return redirect("tasks:detail", pk=task.pk)
        with transaction.atomic():
            att = TaskAttachment(
                task=task, original_name=checked.display_name, extension=checked.extension, size=checked.size,
                scan_status=checked.scan_status, scan_engine=checked.scan_engine, uploaded_by=request.user,
            )
            att.sha256 = files.store_file(att.file, checked)
            att.save()
            _event(task, request.user, TaskEvent.Kind.ATTACHED, attachment=str(att.pk), ext=att.extension, size=att.size)
            record(AuditLog.Action.TASK_ATTACHMENT_ADDED, request=request, user=request.user, object_type="Task", object_id=task.pk,
                   meta={"attachment": str(att.pk), "ext": att.extension, "size": att.size})
        messages.success(request, _("Fayl biriktirildi."))
        return redirect("tasks:detail", pk=task.pk)


def _attachment(task, attachment_id):
    # the attachment must belong to THIS task: another task's attachment id gives 404, whatever the permissions
    return get_object_or_404(TaskAttachment, pk=attachment_id, task_id=task.pk, removed_at__isnull=True)


class TaskAttachmentDownloadView(_TaskBase):
    def get(self, request, pk, attachment_id):
        task = self.get_task(request, pk)  # visibility first: same rules as the task itself, whatever its status
        att = _attachment(task, attachment_id)
        if att.scan_status == "infected":
            raise Http404
        response = files.download_response(att.file, filename=files.safe_download_name(task.title, f"_{att.pk.hex[:6]}.{att.extension}"))
        record(AuditLog.Action.TASK_ATTACHMENT_DOWNLOADED, request=request, user=request.user, object_type="Task", object_id=task.pk, meta={"attachment": str(att.pk)})
        return response


class TaskAttachmentRemoveView(_TaskBase):
    http_method_names = ["post"]
    permission_required = ["tasks.view_task", "tasks.remove_taskattachment"]

    def post(self, request, pk, attachment_id):
        task = self.get_task(request, pk)
        att = _attachment(task, attachment_id)
        if not access.can_remove_attachment(request.user, task, att):
            raise PermissionDenied
        with transaction.atomic():
            att.removed_at, att.removed_by = timezone.now(), request.user
            att.save(update_fields=["removed_at", "removed_by"])
            _event(task, request.user, TaskEvent.Kind.DETACHED, attachment=str(att.pk))
            record(AuditLog.Action.TASK_ATTACHMENT_REMOVED, request=request, user=request.user, object_type="Task", object_id=task.pk, meta={"attachment": str(att.pk)})
        messages.success(request, _("Fayl topshiriqdan olib tashlandi."))
        return redirect("tasks:detail", pk=task.pk)
