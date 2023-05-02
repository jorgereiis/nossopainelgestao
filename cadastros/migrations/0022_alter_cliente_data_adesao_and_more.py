# Generated by Django 4.2 on 2023-05-02 13:37

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cadastros', '0021_alter_cliente_data_adesao_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cliente',
            name='data_adesao',
            field=models.DateField(
                default=datetime.date(2023, 5, 2), verbose_name='Data de adesão'
            ),
        ),
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(
                default=datetime.date(2023, 6, 1), verbose_name='Data do vencimento'
            ),
        ),
    ]
