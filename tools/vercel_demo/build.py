"""Assemble the folder that is deployed to Vercel (online DEMO with fictitious data): python tools/vercel_demo/build.py <output folder>

Needs a local database with the demo data (manage.py seed_demo --yes) to dump the demo file, and the backend virtualenv for collectstatic."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1])
SKIP = {"__pycache__", ".venv", ".ruff_cache", "staticfiles", ".env", ".dev_mail", "tests", "deploy"}


def ignore(_d, names):
    return [n for n in names if n in SKIP or n.endswith(".pyc") or n.startswith("tests")]


py = ROOT / "backend" / ".venv" / "bin" / "python"
manage = ["manage.py"]
subprocess.run([str(py), "manage.py", "dumpdata", "--natural-foreign", "--indent", "0", "-e", "contenttypes", "-e", "auth.permission", "-e", "sessions", "-e", "admin.logentry",
                "-e", "audit.auditlog", "-e", "core.jobrun", "-e", "accounts.usersession", "-e", "accounts.throttlestate", "-e", "reports", "-o", "demo/demo.json"], cwd=ROOT / "backend", check=True)
subprocess.run([str(py), "manage.py", "collectstatic", "--noinput"], cwd=ROOT / "backend", check=True)
if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "api").mkdir(parents=True)
shutil.copytree(ROOT / "backend", OUT / "backend", ignore=ignore)
shutil.copytree(ROOT / "assets", OUT / "assets", ignore=ignore)
shutil.copytree(ROOT / "backend" / "staticfiles", OUT / "public" / "static")
for f in ("index.py", "setup.py"):
    shutil.copy(ROOT / "tools" / "vercel_demo" / "api" / f, OUT / "api" / f)
shutil.copy(ROOT / "tools" / "vercel_demo" / "vercel.json", OUT / "vercel.json")
shutil.copy(ROOT / "backend" / "requirements.txt", OUT / "requirements.txt")
(OUT / ".python-version").write_text("3.12\n")
print("ready:", OUT, sum(1 for _ in OUT.rglob("*") if _.is_file()), "files")
