# Generated manually on 2025-11-01
# Migration para renomear campos de URL para domínio

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0042_contareseller_tarefamigracaodns_and_more'),
    ]

    operations = [
        # Renomear dominio_origem_url para dominio_origem
        migrations.RenameField(
            model_name='tarefamigracaodns',
            old_name='dominio_origem_url',
            new_name='dominio_origem',
        ),
        # Renomear dominio_destino_url para dominio_destino
        migrations.RenameField(
            model_name='tarefamigracaodns',
            old_name='dominio_destino_url',
            new_name='dominio_destino',
        ),
        # Alterar tipo de campo de URLField para CharField
        migrations.AlterField(
            model_name='tarefamigracaodns',
            name='dominio_origem',
            field=models.CharField(
                max_length=255,
                verbose_name='Domínio Origem',
                help_text='Domínio DNS atual (protocolo + host + porta, ex: http://dominio.com:8080)'
            ),
        ),
        migrations.AlterField(
            model_name='tarefamigracaodns',
            name='dominio_destino',
            field=models.CharField(
                max_length=255,
                verbose_name='Domínio Destino',
                help_text='Novo domínio DNS (protocolo + host + porta, ex: http://dominio-novo.com)'
            ),
        ),
    ]
