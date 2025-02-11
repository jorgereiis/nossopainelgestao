# Generated by Django 5.0.3 on 2024-09-09 09:40

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0026_mensalidade_dt_notif_wpp1_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='nao_enviar_msgs',
            field=models.BooleanField(default=False, verbose_name='Não enviar'),
        ),
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(default=datetime.date(2024, 10, 9), verbose_name='Data do vencimento'),
        ),
    ]
