# Generated by Django 5.0.3 on 2024-08-13 21:28

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0024_alter_mensalidade_dt_vencimento'),
    ]

    operations = [
        migrations.AddField(
            model_name='mensalidade',
            name='notificacao_wpp1',
            field=models.BooleanField(default=False, verbose_name='Notificação PROMO'),
        ),
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(default=datetime.date(2024, 9, 12), verbose_name='Data do vencimento'),
        ),
    ]
