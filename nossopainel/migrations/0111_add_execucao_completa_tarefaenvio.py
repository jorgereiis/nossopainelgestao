# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0110_add_em_execucao_horarioenvios'),
    ]

    operations = [
        migrations.AddField(
            model_name='tarefaenvio',
            name='execucao_completa',
            field=models.BooleanField(
                default=True,
                help_text='Indica se a última execução foi concluída com sucesso'
            ),
        ),
        migrations.AddField(
            model_name='tarefaenvio',
            name='pausado_por_notificacao',
            field=models.BooleanField(
                default=False,
                help_text='Indica se a tarefa está pausada aguardando notificações'
            ),
        ),
        migrations.AddField(
            model_name='tarefaenvio',
            name='pausado_motivo',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Motivo da pausa (ex: "Notificação de vencimentos em execução")',
                max_length=255
            ),
        ),
    ]
