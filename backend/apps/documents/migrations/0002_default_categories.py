from django.db import migrations

NAMES = ["Buyruqlar", "Nizomlar va yo‘riqnomalar", "Hisobotlar", "Shablonlar va namunalar", "Boshqa"]


def create(apps, schema_editor):
    Category = apps.get_model("documents", "DocumentCategory")
    for name in NAMES:
        Category.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]
    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
