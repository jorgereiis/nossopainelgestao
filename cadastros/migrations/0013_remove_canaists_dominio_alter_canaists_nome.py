# Generated by Django 5.0.12 on 2025-05-19 23:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0012_canaists_nome'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='canaists',
            name='dominio',
        ),
        migrations.AlterField(
            model_name='canaists',
            name='nome',
            field=models.CharField(max_length=255, verbose_name='Nome do canal'),
        ),
    ]
