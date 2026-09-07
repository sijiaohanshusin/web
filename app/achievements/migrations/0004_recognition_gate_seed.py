from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model('achievements', 'RecognitionGate').objects.using(schema_editor.connection.alias).get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [('achievements', '0003_recognitiongate_recognitiontask')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
