# Generated migration for ConfiguracaoEnvio model

from datetime import time
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0108_tarefaenvio_dias_cancelamento_and_leads_valido'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracaoEnvio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('limite_envios_por_execucao', models.PositiveIntegerField(
                    default=100,
                    help_text='Máximo de mensagens enviadas por execução de tarefa',
                    verbose_name='Limite de Envios por Execução'
                )),
                ('intervalo_entre_mensagens', models.PositiveIntegerField(
                    default=5,
                    help_text='Segundos de espera entre cada mensagem enviada',
                    verbose_name='Intervalo Entre Mensagens (seg)'
                )),
                ('horario_inicio_permitido', models.TimeField(
                    default=time(8, 0),
                    help_text='Horário mínimo para iniciar envios',
                    verbose_name='Horário Início Permitido'
                )),
                ('horario_fim_permitido', models.TimeField(
                    default=time(20, 0),
                    help_text='Horário máximo para envios',
                    verbose_name='Horário Fim Permitido'
                )),
                ('atualizado_em', models.DateTimeField(
                    auto_now=True,
                    verbose_name='Atualizado Em'
                )),
            ],
            options={
                'db_table': 'cadastros_configuracaoenvio',
                'verbose_name': 'Configuração de Envio',
                'verbose_name_plural': 'Configurações de Envio',
            },
        ),
    ]
