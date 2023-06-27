# Generated by Django 4.2.1 on 2023-06-26 15:41

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0004_alter_cliente_data_adesao_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cliente',
            name='data_adesao',
            field=models.DateField(default=datetime.date(2023, 6, 26), verbose_name='Data de adesão'),
        ),
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(default=datetime.date(2023, 7, 26), verbose_name='Data do vencimento'),
        ),
    ]
