"""Guards the existing static demo (GitHub Pages) and keeps secrets out of Git."""
import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REPO = settings.REPO_ROOT

STATIC_PAGES = [
    "index.html", "login.html", "news.html", "news-detail.html", "ustozlar.html", "ustoz.html",
    "media.html", "tashkilot.html", "hujjatlar.html",
    "app/dashboard.html", "app/xodimlar.html", "app/yangiliklar.html", "app/topshiriqlar.html",
    "app/kirish-chiqish.html", "app/geolokatsiya.html", "app/hujjatlar.html", "app/yutuqlar.html",
    "app/sertifikatlar.html", "app/media.html", "app/tashkilot.html", "app/chat.html",
    "app/bildirishnomalar.html", "app/hisobotlar.html", "app/admin.html",
]


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [REPO / line for line in out.splitlines() if line]


class StaticSiteIntactTests(SimpleTestCase):
    def test_all_static_pages_still_exist(self):
        missing = [p for p in STATIC_PAGES if not (REPO / p).is_file()]
        self.assertEqual(missing, [])

    def test_static_assets_and_pages_marker_exist(self):
        for path in ("assets/css/styles.css", "assets/js/app.js", "assets/js/data.js", "assets/js/pages.js", ".nojekyll"):
            self.assertTrue((REPO / path).is_file(), path)

    def test_django_reuses_static_assets_instead_of_copying_them(self):
        self.assertIn(("assets", REPO / "assets"), settings.STATICFILES_DIRS)
        self.assertFalse((settings.BASE_DIR / "static" / "assets").exists())

    def test_old_district_name_is_absent_from_backend(self):
        needle = "Ulug" + "‘bek"  # built from parts so this file does not contain the old name
        offenders = []
        for path in settings.BASE_DIR.rglob("*"):
            if path.suffix in {".py", ".html", ".js", ".md", ".txt", ".in"} and ".venv" not in path.parts and "__pycache__" not in path.parts:
                if needle in path.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(str(path))
        self.assertEqual(offenders, [])


class SecretsNotInGitTests(SimpleTestCase):
    def test_env_files_are_not_tracked(self):
        files = tracked_files()
        if files is None:
            self.skipTest("git is not available")
        bad = [str(f) for f in files if f.name.startswith(".env") and f.name != ".env.example"]
        self.assertEqual(bad, [])

    def test_real_secret_values_do_not_appear_in_tracked_files(self):
        files = tracked_files()
        if files is None:
            self.skipTest("git is not available")
        secrets = [v for v in (os.environ.get("DB_PASSWORD"), settings.SECRET_KEY) if v and len(v) >= 16 and not v.startswith("test-only")]
        if not secrets:
            self.skipTest("no real secrets in this environment")
        for path in files:
            if not path.is_file() or path.suffix in {".png", ".jpg", ".woff2", ".ico"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for secret in secrets:
                self.assertNotIn(secret, text, msg=f"secret value found in {path}")

    def test_env_example_has_no_real_values(self):
        text = (settings.BASE_DIR / ".env.example").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("DJANGO_SECRET_KEY="):
                self.assertIn("change-me", line)
            if line.startswith("DB_PASSWORD="):
                self.assertIn("change-me", line)
