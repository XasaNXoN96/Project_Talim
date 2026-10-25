import datetime
import uuid

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin

from . import services
from .forms import ManualEventForm, ZoneForm
from .models import AttendanceEvent, WorkZone

# The clock page asks the browser for the position, so it alone relaxes the site-wide "geolocation=()".
GEO_POLICY = "camera=(), microphone=(), geolocation=(self), payment=(), usb=()"


def _day(value):
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return timezone.localdate()


def _bounds(day):
    start = timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))
    return start, start + datetime.timedelta(days=1)


class _AttBase(PortalPermissionMixin, View):
    """Pressing needs `use_attendance` AND that the person has read the notice (what is recorded and who may see it)."""

    permission_required = "attendance.use_attendance"
    needs_notice = True

    def dispatch(self, request, *args, **kwargs):
        u = request.user
        if self.needs_notice and u.is_authenticated and u.has_perm(self.permission_required) and not services.has_accepted(u):
            return redirect("attendance:notice")
        return super().dispatch(request, *args, **kwargs)


class NoticeView(_AttBase):
    needs_notice = False

    def get(self, request):
        return render(request, "portal/attendance/notice.html", {"accepted": services.has_accepted(request.user), "retention": _retention()})

    def post(self, request):
        if request.POST.get("agree") != "1":
            messages.error(request, _("Davom etish uchun ogohlantirish bilan tanishganingizni tasdiqlang."))
            return redirect("attendance:notice")
        services.accept_notice(request.user)
        record(AuditLog.Action.ATTENDANCE_NOTICE_ACCEPTED, request=request, user=request.user, object_type="User", object_id=request.user.pk)
        return redirect("attendance:clock")


def _retention():
    from django.conf import settings

    return int(getattr(settings, "ATTENDANCE_LOCATION_RETENTION_DAYS", 90))


class ClockView(_AttBase):
    def get(self, request):
        emp = services.employee_of(request.user)
        ctx = {"emp": emp, "zones": [], "last": None, "days": [], "can_in": False, "can_out": False, "now_ms": int(timezone.now().timestamp() * 1000), "tz_name": timezone.get_current_timezone_name()}
        if emp:
            last = services.last_event(emp)
            ctx["zones"] = list(services.zones_for(emp))
            ctx["last"] = last
            since = timezone.now() - datetime.timedelta(days=30)
            ctx["days"] = services.build_days(AttendanceEvent.objects.filter(employee=emp, at__gte=since))[:30]
            ctx["can_in"] = last is None or last.kind == AttendanceEvent.Kind.OUT or timezone.localdate(last.at) != timezone.localdate()
            ctx["can_out"] = last is not None and last.kind == AttendanceEvent.Kind.IN
            ctx["can_team"] = request.user.has_perm(services.TEAM_PERMISSION)
        resp = render(request, "portal/attendance/clock.html", ctx)
        resp.headers["Permissions-Policy"] = GEO_POLICY
        return resp

    def post(self, request):
        kind = request.POST.get("kind", "")
        try:
            ev = services.clock(
                request.user, kind, lat=request.POST.get("lat"), lon=request.POST.get("lon"),
                accuracy=request.POST.get("acc"), note=request.POST.get("note", ""),
            )
        except services.AttendanceError as exc:
            messages.error(request, str(exc))
            return redirect("attendance:clock")
        record(AuditLog.Action.ATTENDANCE_CLOCKED, request=request, user=request.user, object_type="Employee", object_id=ev.employee_id,
               meta={"kind": ev.kind, "inside": ev.inside_zone})  # no coordinates in the log
        if ev.inside_zone is False:
            messages.warning(request, _("Belgilandi. Siz ish hududidan tashqaridasiz: izohingiz saqlandi."))
        else:
            messages.success(request, _("Kirish belgilandi.") if ev.kind == AttendanceEvent.Kind.IN else _("Chiqish belgilandi."))
        return redirect("attendance:clock")


class TeamView(PortalPermissionMixin, View):
    permission_required = "attendance.view_team_attendance"

    def get(self, request):
        day = _day(request.GET.get("date"))
        q = (request.GET.get("q") or "").strip()[:100]
        staff = services.team_employees(request.user)
        if q:
            staff = staff.filter(Q(last_name__icontains=q) | Q(first_name__icontains=q) | Q(institution__name__icontains=q) | Q(department__name__icontains=q))
        staff = staff.order_by("last_name", "first_name")
        page = Paginator(staff, 40).get_page(request.GET.get("page"))
        start, end = _bounds(day)
        by_emp = {}
        for ev in AttendanceEvent.objects.filter(employee__in=[e.pk for e in page.object_list], at__gte=start, at__lt=end).order_by("at"):
            by_emp.setdefault(ev.employee_id, []).append(ev)
        rows = []
        for e in page.object_list:
            evs = by_emp.get(e.pk, [])
            days = services.build_days(evs)
            d = days[0] if days else None
            rows.append({"emp": e, "day": d, "state": _state(evs)})
        record(AuditLog.Action.ATTENDANCE_TEAM_VIEWED, request=request, user=request.user, object_type="Attendance", object_id="",
               meta={"date": day.isoformat(), "people": len(rows)})
        return render(request, "portal/attendance/team.html", {
            "rows": rows, "page_obj": page, "paginator": page.paginator, "day": day, "q": q, "today": timezone.localdate(),
            "prev_day": day - datetime.timedelta(days=1), "next_day": day + datetime.timedelta(days=1),
        })


def _state(evs):
    if not evs:
        return "none"
    last = evs[-1]
    if last.kind == AttendanceEvent.Kind.OUT:
        return "out"
    return "in_zone" if last.inside_zone else ("outside" if last.inside_zone is False else "in")


class MemberView(PortalPermissionMixin, View):
    permission_required = "attendance.view_team_attendance"

    def _employee(self, request, pk):
        return get_object_or_404(services.team_employees(request.user), pk=pk)

    def get(self, request, pk):
        emp = self._employee(request, pk)
        since = timezone.now() - datetime.timedelta(days=30)
        events = AttendanceEvent.objects.filter(employee=emp, at__gte=since).select_related("zone", "created_by")
        days = services.build_days(events)
        record(AuditLog.Action.ATTENDANCE_TEAM_VIEWED, request=request, user=request.user, object_type="Employee", object_id=emp.pk, meta={"member": True})
        can_correct = request.user.has_perm("attendance.correct_attendance")
        return render(request, "portal/attendance/member.html", {
            "emp": emp, "days": days, "can_correct": can_correct, "form": ManualEventForm(), "show_coords": can_correct,
        })


class CorrectView(PortalPermissionMixin, View):
    permission_required = "attendance.correct_attendance"
    http_method_names = ["post"]

    def post(self, request, pk):
        emp = get_object_or_404(services.team_employees(request.user), pk=pk)
        form = ManualEventForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("Ma’lumotlarni tekshiring: vaqt va sabab to‘ldirilishi kerak."))
            return redirect("attendance:member", pk=emp.pk)
        d = form.cleaned_data
        try:
            ev = services.add_manual(request.user, emp, d["kind"], d["at"], d["note"])
        except services.AttendanceError as exc:
            messages.error(request, str(exc))
            return redirect("attendance:member", pk=emp.pk)
        record(AuditLog.Action.ATTENDANCE_CORRECTED, request=request, user=request.user, object_type="Employee", object_id=emp.pk, meta={"kind": ev.kind, "event": str(ev.pk)})
        messages.success(request, _("Tuzatish qo‘shildi."))
        return redirect("attendance:member", pk=emp.pk)


# ------------------------------------------------------------------ zones ("Geolokatsiya")

class ZonesView(PortalPermissionMixin, View):
    permission_required = "attendance.view_workzone"

    def get(self, request):
        zones = WorkZone.objects.select_related("institution").order_by("-is_active", "name")
        can_team = request.user.has_perm(services.TEAM_PERMISSION)
        statuses = []
        if can_team:
            staff = list(services.team_employees(request.user).order_by("last_name", "first_name")[:200])
            start, end = _bounds(timezone.localdate())
            by_emp = {}
            for ev in AttendanceEvent.objects.filter(employee__in=[e.pk for e in staff], at__gte=start, at__lt=end).order_by("at"):
                by_emp.setdefault(ev.employee_id, []).append(ev)
            statuses = [{"emp": e, "state": _state(by_emp.get(e.pk, []))} for e in staff]
            record(AuditLog.Action.ATTENDANCE_TEAM_VIEWED, request=request, user=request.user, object_type="Attendance", object_id="",
                   meta={"date": timezone.localdate().isoformat(), "people": len(statuses), "zones_page": True})
        return render(request, "portal/attendance/zones.html", {
            "zones": zones, "statuses": statuses, "can_team": can_team, "can_add": request.user.has_perm("attendance.add_workzone"),
            "can_change": request.user.has_perm("attendance.change_workzone"),
        })


class ZoneFormView(PortalPermissionMixin, View):
    permission_required = "attendance.add_workzone"

    def _obj(self, pk):
        return get_object_or_404(WorkZone, pk=pk) if pk else None

    def get_permission_required(self):
        return ("attendance.change_workzone",) if self.kwargs.get("pk") else ("attendance.add_workzone",)

    def get(self, request, pk=None):
        obj = self._obj(pk)
        return render(request, "portal/attendance/zone_form.html", {"form": ZoneForm(instance=obj), "obj": obj})

    def post(self, request, pk=None):
        obj = self._obj(pk)
        form = ZoneForm(request.POST, instance=obj)
        if not form.is_valid():
            return render(request, "portal/attendance/zone_form.html", {"form": form, "obj": obj})
        zone = form.save()
        record(AuditLog.Action.ORG_CHANGED, request=request, user=request.user, object_type="WorkZone", object_id=zone.pk, meta={"created": obj is None})
        messages.success(request, _("Ish hududi saqlandi."))
        return redirect("attendance:zones")


class ZoneDetailView(PortalPermissionMixin, View):
    """A schematic (no map tiles are loaded from outside): the zone circle and where the recent presses were, WITHOUT names."""

    permission_required = "attendance.view_team_attendance"

    def get(self, request, pk):
        zone = get_object_or_404(WorkZone.objects.select_related("institution"), pk=pk)
        scope = list(services.team_employees(request.user).values_list("pk", flat=True))
        since = timezone.now() - datetime.timedelta(days=7)
        pts = []
        half = float(zone.radius_m) * 2.0
        for ev in AttendanceEvent.objects.filter(zone=zone, latitude__isnull=False, at__gte=since, employee_id__in=scope)[:300]:
            dx = services.haversine_m(zone.latitude, ev.longitude, zone.latitude, zone.longitude) * (1 if ev.longitude >= zone.longitude else -1)
            dy = services.haversine_m(ev.latitude, zone.longitude, zone.latitude, zone.longitude) * (1 if ev.latitude >= zone.latitude else -1)
            if abs(dx) <= half and abs(dy) <= half:
                pts.append({"x": round(150 + dx / half * 150, 1), "y": round(150 - dy / half * 150, 1), "in": ev.inside_zone, "kind": ev.kind})
        r = round(float(zone.radius_m) / half * 150, 1)
        record(AuditLog.Action.ATTENDANCE_TEAM_VIEWED, request=request, user=request.user, object_type="WorkZone", object_id=zone.pk, meta={"zone": True})
        return render(request, "portal/attendance/zone_detail.html", {"zone": zone, "points": pts, "r": r, "count": len(pts)})
