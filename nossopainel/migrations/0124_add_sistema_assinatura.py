import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0123_registroatendimento_resolvido'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. PlanoAssinatura
        migrations.CreateModel(
            name='PlanoAssinatura',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(
                    choices=[('bronze', 'Bronze'), ('prata', 'Prata'), ('ouro', 'Ouro')],
                    max_length=10, unique=True, verbose_name='Tipo',
                )),
                ('valor', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='Valor mensal (R$)')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('descricao', models.TextField(blank=True, verbose_name='Descrição')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Plano de Assinatura',
                'verbose_name_plural': 'Planos de Assinatura',
                'db_table': 'assinaturas_plano',
                'ordering': ['valor'],
            },
        ),
        # 2. FuncionalidadePlano
        migrations.CreateModel(
            name='FuncionalidadePlano',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plano', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='funcionalidades',
                    to='nossopainel.planoassinatura',
                )),
                ('chave', models.CharField(max_length=100, verbose_name='Chave da funcionalidade')),
                ('ativo', models.BooleanField(default=True, verbose_name='Habilitado')),
            ],
            options={
                'verbose_name': 'Funcionalidade do Plano',
                'verbose_name_plural': 'Funcionalidades dos Planos',
                'db_table': 'assinaturas_funcionalidade',
                'unique_together': {('plano', 'chave')},
            },
        ),
        # 3. AssinaturaPlataforma
        migrations.CreateModel(
            name='AssinaturaPlataforma',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('usuario', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='assinatura_plataforma',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('plano', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='nossopainel.planoassinatura',
                    verbose_name='Plano',
                )),
                ('status', models.CharField(
                    choices=[
                        ('trial', 'Trial'),
                        ('ativo', 'Ativo'),
                        ('suspenso', 'Suspenso'),
                        ('cancelado', 'Cancelado'),
                    ],
                    default='trial', max_length=20, verbose_name='Status',
                )),
                ('data_inicio', models.DateField(blank=True, null=True, verbose_name='Início da assinatura')),
                ('data_fim', models.DateField(blank=True, null=True, verbose_name='Fim do período pago')),
                ('trial_fim', models.DateField(blank=True, null=True, verbose_name='Fim do período trial')),
                ('dias_extras', models.IntegerField(default=0, verbose_name='Dias extras gratuitos')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Assinatura de Plataforma',
                'verbose_name_plural': 'Assinaturas de Plataforma',
                'db_table': 'assinaturas_assinatura_plataforma',
            },
        ),
        # 4. CobrancaAssinaturaPlataforma
        migrations.CreateModel(
            name='CobrancaAssinaturaPlataforma',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('usuario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cobranças_assinatura',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('plano', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='nossopainel.planoassinatura',
                )),
                ('assinatura', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='nossopainel.assinaturaplataforma',
                )),
                ('valor', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='Valor')),
                ('status', models.CharField(
                    choices=[
                        ('pendente', 'Pendente'),
                        ('pago', 'Pago'),
                        ('expirado', 'Expirado'),
                        ('cancelado', 'Cancelado'),
                    ],
                    default='pendente', max_length=20,
                )),
                ('cobranca_id_externo', models.CharField(blank=True, max_length=255, verbose_name='ID FastDePix')),
                ('qr_code', models.TextField(blank=True, verbose_name='QR Code Base64')),
                ('pix_copia_cola', models.TextField(blank=True, verbose_name='PIX Copia e Cola')),
                ('qr_code_url', models.CharField(blank=True, max_length=500, verbose_name='URL QR Code')),
                ('link_pagamento', models.CharField(blank=True, max_length=500, verbose_name='Link de pagamento')),
                ('data_pagamento', models.DateTimeField(blank=True, null=True, verbose_name='Data do pagamento')),
                ('data_expiracao', models.DateTimeField(blank=True, null=True, verbose_name='Expiração da cobrança')),
                ('periodo_inicio', models.DateField(blank=True, null=True, verbose_name='Início do período')),
                ('periodo_fim', models.DateField(blank=True, null=True, verbose_name='Fim do período')),
                ('criado_por', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='cobranças_assinatura_geradas',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Cobrança de Assinatura',
                'verbose_name_plural': 'Cobranças de Assinatura',
                'db_table': 'assinaturas_cobranca',
                'ordering': ['-criado_em'],
            },
        ),
    ]
