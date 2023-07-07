# Generated by Django 4.2.1 on 2023-07-05 14:35

import datetime
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cadastros', '0008_alter_cliente_data_adesao_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cliente',
            name='data_adesao',
            field=models.DateField(default=datetime.date(2023, 7, 5), verbose_name='Data de adesão'),
        ),
        migrations.AlterField(
            model_name='mensalidade',
            name='dt_vencimento',
            field=models.DateField(default=datetime.date(2023, 8, 4), verbose_name='Data do vencimento'),
        ),
        migrations.CreateModel(
            name='DadosBancarios',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('beneficiario', models.CharField(max_length=255)),
                ('instituicao', models.CharField(max_length=255)),
                ('tipo_chave', models.CharField(max_length=255)),
                ('chave', models.CharField(max_length=255)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]