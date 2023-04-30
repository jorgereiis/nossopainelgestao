# Generated by Django 4.2 on 2023-04-28 21:55

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cadastros', '0018_alter_mensalidade_dt_pagamento_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cliente',
            name='data_adesao',
            field=models.DateField(
                default=datetime.date(2023, 4, 28), verbose_name='Data de adesão'
            ),
        ),
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(
                default=datetime.date(2023, 5, 28), verbose_name='Data do vencimento'
            ),
        ),
    ]
