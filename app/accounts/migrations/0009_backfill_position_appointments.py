from django.db import migrations


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Position = apps.get_model("accounts", "Position")
    Appointment = apps.get_model("accounts", "PositionAppointment")
    alias = schema_editor.connection.alias
    names = dict(Position.objects.using(alias).values_list("pk", "name"))
    for user in User.objects.using(alias).exclude(position_id=None).iterator():
        Appointment.objects.using(alias).get_or_create(
            user_id=user.pk, ended_at=None,
            defaults={
                "position_id": user.position_id, "position_name": names[user.position_id],
                "term_start": None, "started_at": None,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_position_terms")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
