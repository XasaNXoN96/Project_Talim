import uuid

from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    """Random UUID primary key: ids are not guessable or enumerable in URLs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class JobRun(models.Model):
    """One execution of a scheduled/background command (see apps.core.jobs). Holds counts and a short error CLASS only:
    never messages, paths, record contents or secrets. `running` for longer than jobs.RUNNING_STALE means the result is unknown."""

    class Status(models.TextChoices):
        RUNNING = "running", "running"
        SUCCESS = "success", "success"
        FAILED = "failed", "failed"

    name = models.CharField(max_length=40)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.RUNNING)
    processed = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)
    error_class = models.CharField(max_length=60, blank=True)
    note = models.CharField(max_length=80, blank=True)  # a non-sensitive label of what a successful run produced (e.g. the backup folder name)

    class Meta:
        indexes = [models.Index(fields=["name", "-started_at"])]
        ordering = ["-started_at"]
