# Generated by Django 4.2 on 2023-04-24 10:27

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cadastros', '0013_alter_cliente_data_adesao_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cliente',
            name='data_adesao',
            field=models.DateField(
                default=datetime.date(2023, 4, 24), verbose_name='Data de adesão'
            ),
        ),
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(
                default=datetime.date(2023, 5, 24), verbose_name='Data de vencimento'
            ),
        ),
    ]