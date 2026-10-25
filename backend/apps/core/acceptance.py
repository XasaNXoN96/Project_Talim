"""Shared world for the acceptance tests: one small organisation with an object of every kind and an actor of every role.
Fictional data only."""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.access.models import RoleAssignment
from apps.accounts.models import UserSession
from apps.accounts.testing import login_with_two_factor, make_user
from apps.content.models import News, NewsCategory
from apps.documents.models import Document, DocumentCategory
from apps.documents.services import add_version
from apps.documents.testing import upload
from apps.documents.validation import validate_upload
from apps.notifications.models import Notification
from apps.organization.models import Department, Employee, EmployeeImport, Institution, Position
from apps.tasks.models import Task, TaskAttachment

User = get_user_model()
ACTORS = ("anon", "emp", "stranger", "content", "head", "hr", "admin", "sysadmin", "superuser")


class World:
    def __init__(self):
        call_command("seed_roles", verbosity=0)
        self.root = Department.objects.create(name="A")
        self.child = Department.objects.create(name="A1", parent=self.root)
        self.other = Department.objects.create(name="B")
        self.position = Position.objects.create(name="Metodist")
        self.institution = Institution.objects.create(name="1-sonli maktab", kind="school")
        self.users = {
            "emp": make_user("emp", role="employee"), "stranger": make_user("stranger", role="employee"),
            "content": make_user("content", role="content_manager"), "hr": make_user("hrista", role="hr"),
            "admin": make_user("boss", role="admin"), "sysadmin": make_user("sysadm", role="sysadmin"),
            "head": make_user("head", role="employee"),
        }
        self.users["superuser"] = User.objects.create_superuser("root", "root@example.test", "Namuna-Parol-12345")
        RoleAssignment.objects.create(user=self.users["head"], role=Group.objects.get(name="department_head"), scope="department", department=self.root)
        self.card = Employee.objects.create(last_name="Aliyev", first_name="Vali", department=self.child, position=self.position, user=self.users["emp"],
                                            status="active", work_phone="+998 71 111 22 33", work_email="vali@work.example.test",
                                            personal_phone="+998 90 555 66 77", birth_date=datetime.date(1990, 5, 17), hired_at=datetime.date(2020, 1, 1))
        Employee.objects.create(last_name="Botirov", first_name="Sher", department=self.other, user=self.users["stranger"], status="active")
        Employee.objects.create(last_name="Head", first_name="H", department=self.root, user=self.users["head"], status="active")
        from apps.organization.models import EmployeeChangeRequest

        self.change_request = EmployeeChangeRequest.objects.create(
            employee=self.card, requested_by=self.users["emp"], fields=["work_phone"], changes={"work_phone": "+998 90 000 00 01"}, old_values={"work_phone": "+998 71 111 22 33"}
        )
        from apps.attendance.models import AttendanceEvent, WorkZone

        self.work_zone = WorkZone.objects.create(name="Namuna hudud", institution=self.institution, latitude="40.850000", longitude="68.350000", radius_m=150)
        AttendanceEvent.objects.create(employee=self.card, kind="in", inside_zone=True, zone=self.work_zone, latitude="40.850100", longitude="68.350100", accuracy_m=10)
        from apps.chat import services as chat_services
        from apps.chat.models import ChatNoticeAcceptance

        ChatNoticeAcceptance.objects.create(user=self.users["admin"])  # the administrator has read the notice; the others have not
        self.conversation = chat_services.start(self.users["admin"], self.users["emp"])
        chat_services.send(self.users["emp"], self.conversation, "Salom")
        self.task = Task.objects.create(title="Hisobot", description="Matn", created_by=self.users["admin"], status="review", due_date=timezone.localdate())
        self.task.assignees.set([self.users["emp"]])
        self.attachment = TaskAttachment(task=self.task, original_name="a.pdf", extension="pdf", size=10, sha256="0" * 64, uploaded_by=self.users["emp"])
        from apps.documents import files

        checked = validate_upload(upload("a.pdf"))
        self.attachment.sha256 = files.store_file(self.attachment.file, checked)
        self.attachment.size = checked.size
        self.attachment.save()
        cat = DocumentCategory.objects.get(name="Buyruqlar")
        self.doc = Document.objects.create(title="Nizom", category=cat, created_by=self.users["hr"])
        add_version(self.doc, validate_upload(upload("a.pdf")), actor=self.users["hr"])
        self.secret_doc = Document.objects.create(title="Maxfiy", category=cat, created_by=self.users["hr"], access_level="confidential")
        add_version(self.secret_doc, validate_upload(upload("s.pdf")), actor=self.users["hr"])
        self.emp_import = EmployeeImport.objects.create(user=self.users["hr"], file_sha256="0" * 64, rows=[{"n": 2, "raw": {"last_name": "Sinov", "first_name": "Rasul", "department": "A"}}])
        self.user_session = UserSession.objects.create(user=self.users["emp"], session_key="k" * 32)
        self.notification = Notification.objects.create(user=self.users["emp"], kind="task_assigned", task=self.task, title="Hisobot")
        self.news_category = NewsCategory.objects.create(name="Umumiy", slug="umumiy")
        from django.core.files.base import ContentFile

        from apps.achievements.models import Achievement, AchievementImage

        def _jpeg():
            import io

            from PIL import Image

            out = io.BytesIO()
            Image.new("RGB", (8, 8), (10, 20, 30)).save(out, "JPEG")
            return out.getvalue()

        def _mp4():
            import struct

            ftyp = struct.pack(">I4s4sI4s", 20, b"ftyp", b"isom", 0, b"isom")
            moov = struct.pack(">I4s", 8, b"moov")
            mdat = struct.pack(">I4s", 12, b"mdat") + b"\0\0\0\0"
            return ftyp + moov + mdat

        def _achievement(status, **extra):
            from apps.achievements.models import AchievementVideo

            a = Achievement.objects.create(institution=self.institution, created_by=self.users["admin"], title="Yutuq", person_name="Aliyev", status=status, consent_confirmed=True, **extra)
            im = AchievementImage(achievement=a)
            im.file.save("ab/test-image.jpg", ContentFile(_jpeg()), save=False)
            im.save()
            vid = AchievementVideo(achievement=a, content_type="video/mp4", size=len(_mp4()), sha256="0" * 64)
            vid.file.save("ab/test-video.mp4", ContentFile(_mp4()), save=False)
            vid.save()
            return a, im

        from apps.gallery.models import MediaItem

        self.media_item = MediaItem(kind="photo", title="Rasm", content_type="image/jpeg", size=len(_jpeg()), sha256="0" * 64, status="published", publish_at=timezone.now(), consent_confirmed=True)
        self.media_item.file.save("ab/test-media.jpg", ContentFile(_jpeg()), save=False)
        self.media_item.thumb.save("ab/test-media-thumb.jpg", ContentFile(_jpeg()), save=False)
        self.media_item.save()
        self.achievement, self.achievement_image = _achievement("submitted")
        self.pub_achievement, self.pub_image = _achievement("published", publish_at=timezone.now())
        self.news = News.objects.create(title="Yangilik", slug="yangilik", body="Matn", excerpt="Q", status="published", publish_at=timezone.now(), category=self.news_category)
        self.assignment = RoleAssignment.objects.get(user=self.users["emp"])
        self.uid = urlsafe_base64_encode(force_bytes(self.users["emp"].pk))
        self.token = default_token_generator.make_token(self.users["emp"])

    def client(self, actor, *, csrf=False):
        c = Client(enforce_csrf_checks=csrf)
        if actor != "anon":
            login_with_two_factor(c, self.users[actor])
        return c

    def kwargs_for(self, name):
        t, d = self.task.pk, self.doc.pk
        table = {
            "users:detail": {"pk": self.users["emp"].pk}, "users:edit": {"pk": self.users["emp"].pk}, "users:role_add": {"pk": self.users["emp"].pk},
            "users:role_remove": {"pk": self.users["emp"].pk, "assignment_id": self.assignment.pk}, "users:action": {"pk": self.users["emp"].pk, "action": "unlock"},
            "employees:detail": {"pk": self.card.pk}, "employees:photo": {"pk": self.card.pk}, "employees:edit": {"pk": self.card.pk}, "employees:archive": {"pk": self.card.pk}, "employees:restore": {"pk": self.card.pk},
            "employees:department_edit": {"pk": self.child.pk}, "employees:position_edit": {"pk": self.position.pk}, "gallery:file": {"pk": self.media_item.pk, "variant": "thumb"}, "gallery:edit": {"pk": self.media_item.pk}, "gallery:delete": {"pk": self.media_item.pk}, "gallery_public:file": {"pk": self.media_item.pk, "variant": "thumb"}, "reports:school": {"pk": self.institution.pk}, "chat:thread": {"pk": self.conversation.pk}, "attendance:member": {"pk": self.card.pk}, "attendance:correct": {"pk": self.card.pk}, "attendance:zone_detail": {"pk": self.work_zone.pk}, "attendance:zone_edit": {"pk": self.work_zone.pk}, "chat:archive_thread": {"pk": self.conversation.pk}, "employees:change_detail": {"pk": self.change_request.pk}, "employees:change_decide": {"pk": self.change_request.pk, "decision": "reject"}, "employees:change_cancel": {"pk": self.change_request.pk}, "employees:institution_edit": {"pk": self.institution.pk},
            "tasks:detail": {"pk": t}, "tasks:edit": {"pk": t}, "tasks:comment": {"pk": t}, "tasks:attachment_add": {"pk": t},
            "tasks:attachment_download": {"pk": t, "attachment_id": self.attachment.pk}, "tasks:attachment_remove": {"pk": t, "attachment_id": self.attachment.pk},
            "tasks:transition": {"pk": t, "status": "done"},
            "documents:detail": {"pk": d}, "documents:edit": {"pk": d}, "documents:version_add": {"pk": d}, "documents:download": {"pk": d},
            "documents:download_version": {"pk": d, "number": 1}, "documents:preview": {"pk": d}, "documents:preview_version": {"pk": d, "number": 1},
            "documents:inline": {"pk": d}, "documents:inline_version": {"pk": d, "number": 1}, "documents:archive": {"pk": d}, "documents:restore": {"pk": d},
            "notifications:open": {"pk": self.notification.pk}, "notifications:read": {"pk": self.notification.pk},
            "employees:import_detail": {"pk": self.emp_import.pk}, "employees:import_confirm": {"pk": self.emp_import.pk}, "employees:import_cancel": {"pk": self.emp_import.pk},
            "accounts:session_end": {"pk": self.user_session.pk},
            "news_admin:preview": {"pk": self.news.pk}, "news_admin:edit": {"pk": self.news.pk}, "news_admin:status": {"pk": self.news.pk, "action": "archive"},
            "news_admin:category_edit": {"pk": self.news_category.pk},
            "reports:export": {"fmt": "xlsx"}, "content:news_detail": {"slug": self.news.slug}, "achievements:detail": {"pk": self.achievement.pk}, "achievements:edit": {"pk": self.achievement.pk}, "achievements:preview": {"pk": self.achievement.pk}, "achievements:step": {"pk": self.achievement.pk, "step": "archive"}, "achievements:image": {"pk": self.achievement_image.pk}, "achievements:video": {"pk": self.achievement.video.pk}, "achievements_public:detail": {"slug": self.pub_achievement.slug}, "achievements_public:image": {"pk": self.pub_image.pk}, "achievements_public:video": {"pk": self.pub_achievement.video.pk}, "portal:preview": {"section": "media"},
            "accounts:password_reset_confirm": {"uidb64": self.uid, "token": self.token},
        }
        return table.get(name, {})


def app_routes():
    """(name, view class, static permissions) for every route outside the Django admin, from the live URLconf."""
    from django.urls import URLResolver, get_resolver

    out = []

    def walk(patterns, ns=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, ns + (p.namespace + ":" if p.namespace else ""))
            elif p.name:
                cls = getattr(p.callback, "view_class", None)
                out.append((ns + p.name, cls))

    walk(get_resolver().url_patterns)
    return [(n, c) for n, c in out if not n.startswith("admin:")]


DYNAMIC_PERMISSIONS = {
    "employees:department_create": "organization.add_department", "employees:department_edit": "organization.change_department",
    "employees:position_create": "organization.add_position", "employees:position_edit": "organization.change_position",
    "employees:institution_create": "organization.add_institution", "employees:institution_edit": "organization.change_institution",
}


def required_permissions(name, cls):
    if name in DYNAMIC_PERMISSIONS:
        return [DYNAMIC_PERMISSIONS[name]]
    perm = getattr(cls, "permission_required", None) if cls else None
    if perm is None or isinstance(perm, property):
        return []
    return [perm] if isinstance(perm, str) else list(perm)
