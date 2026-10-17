"""Fictional users for the nginx check database."""
import django

django.setup()
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402

from apps.access.models import RoleAssignment  # noqa: E402

U = get_user_model()
for name, role in (("alice", "employee"), ("hrista", "hr"), ("bob", "employee")):
    u = U.objects.create_user(name, f"{name}@example.test", "Namuna-Parol-12345")
    RoleAssignment.objects.create(user=u, role=Group.objects.get(name=role), scope="all")
print("seeded")
