import hashlib
import os
import re

from django.conf import settings
from django.core.management.base import CommandError
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.twofactor import VERIFIED_KEY
from apps.core.jobs import TrackedCommand
from apps.documents import access
from apps.documents.models import Document

PER_LEVEL = 3
MAX_USERS = 60


class Command(TrackedCommand):
    help = (
        "Part of the restore check: against a RESTORED COPY (never the live database), call the real download view for a sample of "
        "documents of every access level. Anonymous visitors must be refused, a person the access rules allow must get exactly the bytes "
        "recorded at upload (SHA-256), a person they do not allow must get 403. Refuses to run unless RESTORE_CHECK=1 and the database "
        "name says restore/scratch/check. It only reads, apart from the audit entries a download normally writes into the scratch copy."
    )
    job_name = "verify_document_files"  # lock/record are not used (see --no-record); the name only picks a lock id for the base class

    def handle(self, *args, **options):
        name = settings.DATABASES["default"]["NAME"]
        if os.environ.get("RESTORE_CHECK") != "1" or not re.search(r"restore|scratch|check", name):
            raise CommandError("refusing: this command is only for a scratch copy made by restore_check.sh (RESTORE_CHECK=1).")
        options["no_record"] = True
        super().handle(*args, **options)

    def run_job(self, run, *args, **options):
        from django.contrib.auth import get_user_model

        users = list(get_user_model().objects.filter(is_active=True, must_change_password=False).order_by("date_joined")[:MAX_USERS])
        counts = {"documents": 0, "allowed_ok": 0, "denied_ok": 0, "anonymous_ok": 0}
        with override_settings(ALLOWED_HOSTS=["testserver"]):
            for level in Document.Access.values:
                docs = Document.objects.filter(access_level=level, status=Document.Status.ACTIVE).order_by("created_at")
                for doc in [d for d in docs if d.versions.exclude(scan_status="infected").exists()][:PER_LEVEL]:
                    counts["documents"] += 1
                    version = doc.versions.exclude(scan_status="infected").order_by("-number").first()
                    url = reverse("documents:download", args=[doc.pk])
                    run.processed += 1
                    anon = Client().get(url)
                    if anon.status_code == 302 and "/accounts/login/" in anon["Location"]:
                        counts["anonymous_ok"] += 1
                    else:
                        run.errors += 1
                        self.stderr.write(f"anonymous access to document {doc.pk} was not refused ({anon.status_code})")
                    allowed = next((u for u in users if access.can_view(u, doc)), None)
                    denied = next((u for u in users if not access.can_view(u, doc)), None)
                    if allowed is not None:
                        r = self._get(allowed, url)
                        body = b"".join(r.streaming_content) if r.status_code == 200 else b""
                        if r.status_code == 200 and hashlib.sha256(body).hexdigest() == version.sha256:
                            counts["allowed_ok"] += 1
                        else:
                            run.errors += 1
                            self.stderr.write(f"document {doc.pk}: an allowed person got {r.status_code} or different bytes")
                    if denied is not None:
                        r = self._get(denied, url)
                        if r.status_code == 403:
                            counts["denied_ok"] += 1
                        else:
                            run.errors += 1
                            self.stderr.write(f"document {doc.pk}: a person without access got {r.status_code}")
        self.stdout.write("access_check " + " ".join(f"{k}={v}" for k, v in counts.items()) + f" errors={run.errors}")

    @staticmethod
    def _get(user, url):
        client = Client()
        client.force_login(user)
        session = client.session
        session[VERIFIED_KEY] = True  # the second factor belongs to the live system, not to this check
        session.save()
        return client.get(url)
