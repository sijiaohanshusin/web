from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("showcase", "0002_adopt_consented_members")]
    operations = [
        migrations.AddField(model_name="showcaseasset", name="display_name", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="showcaseasset", name="byte_size", field=models.PositiveIntegerField(default=0)),
    ]
