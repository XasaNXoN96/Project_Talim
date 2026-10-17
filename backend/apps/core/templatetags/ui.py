from django import template

from apps.access.roles import RoleCode
from apps.tasks.models import Task

register = template.Library()


@register.filter
def role_label(code):
    """Role (group) code -> translated label. Unknown codes are shown as they are."""
    try:
        return RoleCode(code).label
    except ValueError:
        return code


@register.filter
def task_status_label(code):
    return dict(Task.Status.choices).get(code, code)
