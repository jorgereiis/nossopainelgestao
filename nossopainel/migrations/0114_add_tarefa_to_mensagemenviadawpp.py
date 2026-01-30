# Generated manually - Adiciona campo tarefa ao MensagemEnviadaWpp

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0113_populate_nome_normalizado'),
    ]

    operations = [
        # Remove a constraint antiga (global por dia)
        migrations.RemoveConstraint(
            model_name='mensagemenviadawpp',
            name='unique_msg_por_usuario_telefone_dia',
        ),

        # Adiciona o campo tarefa
        migrations.AddField(
            model_name='mensagemenviadawpp',
            name='tarefa',
            field=models.ForeignKey(
                blank=True,
                help_text='Tarefa que originou o envio (null para envios legados)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='mensagens_enviadas',
                to='nossopainel.tarefaenvio',
            ),
        ),

        # Adiciona índice para otimizar consultas
        migrations.AddIndex(
            model_name='mensagemenviadawpp',
            index=models.Index(
                fields=['usuario', 'telefone', 'tarefa', 'data_envio'],
                name='nossopainel_msg_envio_idx',
            ),
        ),
    ]
