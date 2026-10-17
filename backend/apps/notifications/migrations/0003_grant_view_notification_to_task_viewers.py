"""Notifications get their own permission (the Django default `notifications.view_notification`) instead of riding on `tasks.view_task`.

To change NOTHING for anybody at deployment time, everyone who could open the notifications page until now (a group or a user holding
`tasks.view_task`) is given the new permission here. Roles defined by the project also receive it from `seed_roles`; this migration covers
groups and direct grants that exist in the database. Nobody gains access to anyone else's notifications: the views still filter by the
signed-in user. The migration only ADDS; reversing it is a deliberate no-op (removing it could lock people out)."""
from django.db import migrations


def grant(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ct, _ = ContentType.objects.get_or_create(app_label="notifications", model="notification")
    new, _ = Permission.objects.get_or_create(content_type=ct, codename="view_notification", defaults={"name": "Can view notification"})
    old = Permission.objects.filter(content_type__app_label="tasks", codename="view_task").first()
    if old is None:
        return
    for group in Group.objects.filter(permissions=old):
        group.permissions.add(new)
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(user_permissions=old):
        user.user_permissions.add(new)


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_notification_news_alter_notification_kind"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("accounts", "0004_usersession"),
        ("tasks", "0001_initial"),
    ]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
