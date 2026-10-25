"""Demo data for walking through the whole site by hand (docs/WALKTHROUGH.md). LOCAL DEVELOPMENT ONLY.

Creates one account per role with a known demo password, three fictitious schools (the third has no director account on purpose), staff of a
school, tasks for the schools, achievements and gallery photos. Everything is fictitious and marked DEMO. It REFUSES to run when DEBUG is off
(that is: on a server), so a known password can never reach a real installation. Idempotent: running it again adds only what is missing."""
import datetime
import io

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.access.models import RoleAssignment
from apps.accounts import services
from apps.achievements.models import Achievement
from apps.organization.models import Department, Employee, Institution, Position
from apps.tasks.models import Task

PASSWORD = "Demo-Parol-2026!"  # fictitious, for local walkthroughs only
User = get_user_model()

# username, role, last name, first name, position
PEOPLE = [
    ("demo_admin", "admin", "Namuna", "Administrator", "Bo‘lim boshlig‘i"),
    ("demo_sysadmin", "sysadmin", "Namuna", "Sysadmin", None),
    ("demo_content", "content_manager", "Namuna", "Kontent", "Metodist"),
    ("demo_hr", "hr", "Namuna", "Kadrlar", "Kadrlar bo‘yicha mutaxassis"),
    ("demo_head", "department_head", "Namuna", "Boshliq", "Bosh mutaxassis"),
    ("demo_employee", "employee", "Namuna", "Xodim", "Inspektor"),
]


def _picture(color, label):
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (1600, 1067), color)
    d = ImageDraw.Draw(im)
    for k in range(18):
        x, y, r = (k * 211) % 1600, (k * 347) % 1067, 60 + (k * 37) % 180
        d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(min(255, c + 25 + (k * 9) % 60) for c in color))
    d.rectangle((600, 380, 1000, 700), fill=(255, 255, 255))
    d.text((760, 530), label, fill=(20, 20, 20))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    full = out.getvalue()
    im.thumbnail((480, 480))
    t = io.BytesIO()
    im.save(t, "JPEG", quality=80)
    return full, t.getvalue()


class Command(BaseCommand):
    help = "Create fictitious demo accounts and data for a hand-made walkthrough (local development only)."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="confirm that this is a local development database")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refused: DEBUG is off, this looks like a server. seed_demo creates accounts with a KNOWN password and is for local development only.")
        if not options["yes"]:
            raise CommandError("This writes demo accounts and data into the CURRENT database. Run it only on your local test database, with --yes.")
        call_command("seed_roles", verbosity=0)
        call_command("seed_positions", verbosity=0)
        created = []
        dept, _c = Department.objects.get_or_create(name="DEMO bo‘lim", parent=None)
        admin = None
        for username, role, last, first, position in PEOPLE:
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User.objects.create_user(username=username, email=f"{username}@example.test", password=PASSWORD, first_name=first, last_name=last)
                scope, department = ("department", dept) if role == "department_head" else ("all", None)
                a = RoleAssignment(user=user, role=Group.objects.get(name=role), scope=scope, department=department)
                a.save()
                created.append(username)
            if position and not Employee.objects.filter(user=user).exists():
                Employee.objects.create(user=user, last_name=last, first_name=first, department=dept, position=Position.objects.filter(name=position).first(),
                                        status=Employee.Status.ACTIVE, work_email=user.email, work_phone="+998 00 000 00 00")
            if username == "demo_admin":
                admin = user
        schools = [Institution.objects.get_or_create(name=f"DEMO {i}-maktab", defaults={"kind": "school", "head_name": f"Namuna Direktor {i}", "is_published": i < 3})[0] for i in (1, 2, 3)]
        directors = []
        for i, school in enumerate(schools[:2], 1):
            username = f"demo_director{i}"
            user = User.objects.filter(username=username).first()
            if user is None:
                user = services.create_user(admin, username=username, email=f"{username}@example.test", first_name=f"Direktor{i}", last_name="Namuna", role="school_director",
                                            department=None, institution=school, request=None)
                user.set_password(PASSWORD)
                user.save()
                created.append(username)
            directors.append(user)
        s1 = schools[0]
        for last, first, pos in (("Namunaviy", "Ustoz A", "O‘qituvchi"), ("Namunaviy", "Ustoz B", "Amaliy psixolog")):
            if not Employee.objects.filter(last_name=last, first_name=first, institution=s1).exists():
                from apps.organization.access import school_staff_department

                Employee.objects.create(last_name=last, first_name=first, department=school_staff_department(), institution=s1, position=Position.objects.filter(name=pos).first(),
                                        status=Employee.Status.ACTIVE, work_phone="+998 00 000 00 01")
        today = timezone.localdate()
        day = lambda n: today + datetime.timedelta(days=n)
        now = timezone.now()
        if not Task.objects.filter(title__startswith="DEMO:").exists():
            def task(title, who, status="new", due=0, time=None, priority="normal", closed=False):
                t = Task.objects.create(title="DEMO: " + title, description="Namunaviy topshiriq (haqiqiy emas).", created_by=admin, status=status, priority=priority,
                                        due_date=day(due), due_time=time, closed_at=now if closed else None)
                t.assignees.set(who)
                return t

            task("Chorak hisobotini topshirish", [directors[0]], "in_progress", -2, datetime.time(17, 0), "urgent")
            task("O‘quvchilar ro‘yxatini yangilash", [directors[0]], "done", -6, None, "high", True)
            task("Yoz tadbirlari rejasi", [directors[0], directors[1]], "new", 9)
            task("Bino holatini tekshirish", [directors[1]], "new", -1, None, "high")
            task("Metodik tavsiyalarni o‘rganish", [directors[1]], "done", 4, None, "normal", True)
        from apps.attendance.models import WorkZone

        if not WorkZone.objects.filter(name__startswith="DEMO").exists():
            WorkZone.objects.create(name="DEMO: bo‘lim binosi (umumiy)", latitude="40.850000", longitude="68.350000", radius_m=200)
            WorkZone.objects.create(name="DEMO: 1-maktab hovlisi", institution=s1, latitude="40.860000", longitude="68.360000", radius_m=150)
        if not Achievement.objects.filter(title__startswith="DEMO:").exists():
            mk = lambda title, status, **kw: Achievement.objects.create(
                institution=s1, created_by=directors[0], title="DEMO: " + title, person_name="Namunaviy Ustoz A", person_position="Matematika", level="district", kind="medal",
                description="Namunaviy yutuq (haqiqiy emas).", consent_confirmed=True, status=status, **kw)
            mk("Tuman olimpiadasi, 1-o‘rin", "published", publish_at=now)
            mk("Respublika tanlovi, ishtirokchi sertifikati", "submitted")
            mk("Qoralama yutuq", "draft")
        from apps.core.demo_content import seed_rich

        seed_rich(admin, {u.username: u for u in User.objects.filter(username__startswith="demo_")}, schools, directors, self.stdout)
        self.stdout.write(self.style.SUCCESS("Demo data is ready." + (f" New accounts: {', '.join(created)}." if created else " Nothing new to add.")))
        self.stdout.write(f"Password of every demo account: {PASSWORD}")
        self.stdout.write("Accounts: " + ", ".join([p[0] for p in PEOPLE] + ["demo_director1", "demo_director2"]))
        self.stdout.write("demo_admin and demo_sysadmin need an authenticator app (two-factor is mandatory for them).")
