# Generated by Django 5.0.3 on 2024-10-11 02:09

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0031_alter_mensalidade_dt_vencimento'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(default=datetime.date(2024, 11, 9), verbose_name='Data do vencimento'),
        ),
    ]
