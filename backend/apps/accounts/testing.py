"""Helpers shared by tests only. Fictional data; nothing here is used at runtime."""
from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.access.models import RoleAssignment

from .twofactor import VERIFIED_KEY

PASSWORD = "Namuna-Parol-12345"  # fictional
User = get_user_model()


def make_user(username="alice", email=None, password=PASSWORD, role=None, **extra):
    user = User.objects.create_user(username=username, email=email or f"{username}@example.test", password=password, **extra)
    if role:
        RoleAssignment.objects.create(user=user, role=Group.objects.get(name=role), scope="all")
    return User.objects.get(pk=user.pk)


def login_with_two_factor(client, user):
    """Sign in as a user who already completed the second factor (what the real flow ends with)."""
    client.force_login(user)
    session = client.session
    session[VERIFIED_KEY] = True
    session.save()


class Clock:
    def __init__(self):
        self.now = timezone.now()

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@contextmanager
def frozen_throttle_clock():
    clock = Clock()
    with mock.patch("apps.accounts.throttle._now", clock):
        yield clock
