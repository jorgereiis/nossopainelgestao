# Generated by Django 4.2 on 2023-04-28 02:01

import datetime
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cadastros', '0017_mensalidade_dt_cancelamento'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_pagamento',
            field=models.DateField(
                blank=True, default=None, null=True, verbose_name='Data do pagamento'
            ),
        ),
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(
                default=datetime.date(2023, 5, 27), verbose_name='Data do vencimento'
            ),
        ),
        migrations.AlterField(
            model_name='planoindicacao',
            name='valor',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=6,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
