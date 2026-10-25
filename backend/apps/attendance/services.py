"""Attendance rules. The views only call these; they cannot be bypassed by another view.

Privacy by design: the location is read ONLY when the person presses the button; nothing follows them in the background. It is compared
with the zones that apply to them and stored with the press; the coordinates are wiped after ATTENDANCE_LOCATION_RETENTION_DAYS
(`purge_locations`), the times and the inside/outside flag stay."""
import datetime
import math
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.organization.access import covered_departments_for, covered_institutions_for
from apps.organization.models import Employee

from .models import NOTICE_VERSION, AttendanceEvent, AttendanceNoticeAcceptance, WorkZone

MIN_GAP_SECONDS = 20       # two presses closer than this are a double click
MAX_ACCURACY_M = 200       # a reading less precise than this is refused
MAX_NOTE = 300
TEAM_PERMISSION = "attendance.view_team_attendance"


class AttendanceError(Exception):
    """A refusal with a message that is safe to show."""


def has_accepted(user):
    return AttendanceNoticeAcceptance.objects.filter(user=user, version=NOTICE_VERSION).exists()


def accept_notice(user):
    AttendanceNoticeAcceptance.objects.update_or_create(user=user, defaults={"version": NOTICE_VERSION})


def employee_of(user):
    return Employee.objects.select_related("institution", "department").filter(user=user).first()


def zones_for(employee):
    """Active zones that apply to this person: the general ones and those of their own institution."""
    q = Q(institution__isnull=True)
    if employee.institution_id:
        q |= Q(institution_id=employee.institution_id)
    return WorkZone.objects.filter(is_active=True).filter(q)


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp, dl = p2 - p1, math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_zone(zones, lat, lon):
    """(zone, distance in metres) of the closest zone EDGE-wise (distance minus radius), or (None, None)."""
    best = None
    for z in zones:
        d = haversine_m(lat, lon, z.latitude, z.longitude)
        if best is None or d - z.radius_m < best[1] - best[0].radius_m:
            best = (z, d)
    return best if best else (None, None)


def _coord(value, low, high):
    if value in (None, ""):
        return None
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise AttendanceError(_("Joylashuv ma’lumoti noto‘g‘ri."))
    if not d.is_finite() or d < low or d > high:
        raise AttendanceError(_("Joylashuv ma’lumoti noto‘g‘ri."))
    return d.quantize(Decimal("0.000001"))


def _accuracy(value):
    if value in (None, ""):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise AttendanceError(_("Joylashuv ma’lumoti noto‘g‘ri."))
    if not math.isfinite(v) or v < 0:
        raise AttendanceError(_("Joylashuv ma’lumoti noto‘g‘ri."))
    return int(round(v))


def last_event(employee):
    return AttendanceEvent.objects.filter(employee=employee).order_by("-at").first()


@transaction.atomic
def clock(user, kind, *, lat=None, lon=None, accuracy=None, note="", now=None):
    """Record the person's own press. Raises AttendanceError (message safe to show) for every refusal."""
    if kind not in (AttendanceEvent.Kind.IN, AttendanceEvent.Kind.OUT):
        raise AttendanceError(_("Noto‘g‘ri amal."))
    emp = Employee.objects.select_for_update().filter(user=user).first()
    if emp is None:
        raise AttendanceError(_("Hisobingiz xodim kartasiga ulanmagan. Kadrlar bo‘limiga murojaat qiling."))
    if emp.status in (Employee.Status.ARCHIVED, Employee.Status.ON_LEAVE):
        raise AttendanceError(_("Xodim holati bo‘yicha belgilab bo‘lmaydi."))
    now = now or timezone.now()
    note = (note or "").strip()[:MAX_NOTE]
    last = last_event(emp)
    if last is not None:
        if (now - last.at).total_seconds() < MIN_GAP_SECONDS:
            raise AttendanceError(_("Juda tez bosdingiz. Bir necha soniyadan keyin qayta urinib ko‘ring."))
        stale = timezone.localdate(last.at) != timezone.localdate(now)
        if last.kind == kind and not (kind == AttendanceEvent.Kind.IN and stale):
            raise AttendanceError(_("Siz allaqachon kirgansiz.") if kind == AttendanceEvent.Kind.IN else _("Siz allaqachon chiqqansiz."))
    elif kind == AttendanceEvent.Kind.OUT:
        raise AttendanceError(_("Avval «Kirish» ni bosing."))

    zones = list(zones_for(emp))
    lat_d, lon_d, acc = _coord(lat, Decimal(-90), Decimal(90)), _coord(lon, Decimal(-180), Decimal(180)), _accuracy(accuracy)
    if (lat_d is None) != (lon_d is None):
        raise AttendanceError(_("Joylashuv ma’lumoti noto‘g‘ri."))
    zone = inside = distance = None
    if zones:
        if lat_d is None:
            if getattr(settings, "ATTENDANCE_REQUIRE_LOCATION", True):
                raise AttendanceError(_("Joylashuv aniqlanmadi. Brauzerda joylashuvga ruxsat bering va qayta urinib ko‘ring."))
        else:
            if acc is not None and acc > MAX_ACCURACY_M:
                raise AttendanceError(_("Joylashuv aniqligi past (%(m)d m). Ochiq joyda qayta urinib ko‘ring.") % {"m": acc})
            zone, d = nearest_zone(zones, lat_d, lon_d)
            distance = int(round(max(0.0, d - zone.radius_m)))  # metres beyond the edge of the zone
            inside = d <= zone.radius_m
            if not inside and not note:
                raise AttendanceError(_("Siz ish hududidan taxminan %(m)d m tashqaridasiz. Sababini «Izoh» maydoniga yozib, qayta bosing.") % {"m": distance})
    else:
        lat_d = lon_d = acc = None  # nothing to compare with: the position is not kept
    return AttendanceEvent.objects.create(
        employee=emp, kind=kind, at=now, zone=zone, latitude=lat_d, longitude=lon_d, accuracy_m=acc,
        inside_zone=inside, distance_m=distance, note=note, source=AttendanceEvent.Source.SELF, created_by=user,
    )


@transaction.atomic
def add_manual(actor, employee, kind, at, note):
    """A correction made by HR / an administrator: an extra event with a mandatory reason (nothing is edited or removed)."""
    note = (note or "").strip()[:MAX_NOTE]
    if not note:
        raise AttendanceError(_("Tuzatish sababini yozing."))
    if at > timezone.now() + datetime.timedelta(minutes=5):
        raise AttendanceError(_("Kelajak vaqtini kiritib bo‘lmaydi."))
    return AttendanceEvent.objects.create(employee=employee, kind=kind, at=at, note=note, source=AttendanceEvent.Source.MANUAL, created_by=actor)


def purge_locations(now=None):
    """Wipe coordinates (not times, not the inside/outside flag) older than the retention period. Returns how many events changed."""
    days = int(getattr(settings, "ATTENDANCE_LOCATION_RETENTION_DAYS", 90))
    cutoff = (now or timezone.now()) - datetime.timedelta(days=days)
    return AttendanceEvent.objects.filter(at__lt=cutoff, latitude__isnull=False).update(latitude=None, longitude=None, accuracy_m=None)


# ------------------------------------------------------------------ reading

def team_employees(user):
    """Cards of people with an account the user may see attendance of, by the SCOPE of their roles (own card is always theirs)."""
    base = Employee.objects.filter(user__isnull=False).exclude(status=Employee.Status.ARCHIVED).select_related("department", "position", "institution")
    if not user.has_perm(TEAM_PERMISSION):
        return Employee.objects.none()
    depts = covered_departments_for(user, TEAM_PERMISSION)
    if depts is None:
        return base
    insts = covered_institutions_for(user, TEAM_PERMISSION)
    q = Q(pk__in=[])
    if depts:
        q |= Q(department_id__in=depts)
    if insts:
        q |= Q(institution_id__in=insts)
    return base.filter(q)


def build_days(events):
    """Group events (any order) into days by the local date of each "in"; pair in/out for the worked time.
    -> list of dicts, newest day first: date, first_in, last_out, worked (timedelta), open (still inside), outside (any press outside), events."""
    days = {}
    current = None
    for ev in sorted(events, key=lambda e: e.at):
        d = timezone.localdate(ev.at)
        if ev.kind == AttendanceEvent.Kind.IN or current is None:
            current = d
        day = days.setdefault(current, {"date": current, "first_in": None, "last_out": None, "worked": datetime.timedelta(), "open": False, "outside": False, "events": [], "_in": None})
        day["events"].append(ev)
        if ev.inside_zone is False:
            day["outside"] = True
        if ev.kind == AttendanceEvent.Kind.IN:
            if day["first_in"] is None:
                day["first_in"] = ev.at
            day["_in"] = ev.at
        else:
            day["last_out"] = ev.at
            if day["_in"] is not None:
                day["worked"] += ev.at - day["_in"]
                day["_in"] = None
    out = []
    for day in days.values():
        day["open"] = day.pop("_in") is not None
        secs = int(day["worked"].total_seconds())
        day["worked_label"] = f"{secs // 3600}:{secs % 3600 // 60:02d}" if secs else "—"
        out.append(day)
    return sorted(out, key=lambda d: d["date"], reverse=True)


def state_of(employee, on=None):
    """Where the person is now, from their last press of the local day `on` (default today): in_zone / outside / in / out / none."""
    on = on or timezone.localdate()
    ev = AttendanceEvent.objects.filter(employee=employee).order_by("-at").first()
    if ev is None or timezone.localdate(ev.at) != on:
        return "none"
    if ev.kind == AttendanceEvent.Kind.OUT:
        return "out"
    return "in_zone" if ev.inside_zone else ("outside" if ev.inside_zone is False else "in")
