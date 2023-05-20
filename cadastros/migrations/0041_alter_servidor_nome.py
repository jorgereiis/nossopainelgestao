# Generated by Django 4.2.1 on 2023-05-11 02:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0040_remove_dispositivo_modelo_remove_servidor_logotipo_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='servidor',
            name='nome',
            field=models.CharField(choices=[('CLUB', 'CLUB'), ('PlayON', 'PlayON'), ('ALPHA', 'ALPHA'), ('SEVEN', 'SEVEN'), ('FIVE', 'FIVE')], max_length=255, unique=True),
        ),
    ]