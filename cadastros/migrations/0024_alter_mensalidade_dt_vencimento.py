# Generated by Django 5.0.3 on 2024-08-07 03:36

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0023_alter_cliente_data_adesao'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(default=datetime.date(2024, 9, 6), verbose_name='Data do vencimento'),
        ),
    ]
