# Generated migration for interval fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0114_add_tarefa_to_mensagemenviadawpp'),
    ]

    operations = [
        # Remove o campo antigo
        migrations.RemoveField(
            model_name='configuracaoenvio',
            name='intervalo_entre_mensagens',
        ),
        # Adiciona os novos campos
        migrations.AddField(
            model_name='configuracaoenvio',
            name='intervalo_minimo',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Segundos mínimos de espera entre cada mensagem',
                verbose_name='Intervalo Mínimo (seg)'
            ),
        ),
        migrations.AddField(
            model_name='configuracaoenvio',
            name='intervalo_maximo',
            field=models.PositiveIntegerField(
                default=120,
                help_text='Segundos máximos de espera entre cada mensagem',
                verbose_name='Intervalo Máximo (seg)'
            ),
        ),
    ]
