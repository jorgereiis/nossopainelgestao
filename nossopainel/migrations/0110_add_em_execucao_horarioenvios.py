# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0109_add_configuracao_envio'),
    ]

    operations = [
        migrations.AddField(
            model_name='horarioenvios',
            name='em_execucao',
            field=models.BooleanField(
                default=False,
                help_text='Indica se o envio está sendo executado no momento',
                verbose_name='Em Execução'
            ),
        ),
        migrations.AddField(
            model_name='horarioenvios',
            name='execucao_iniciada_em',
            field=models.DateTimeField(
                blank=True,
                help_text='Data/hora do início da execução atual',
                null=True,
                verbose_name='Execução Iniciada Em'
            ),
        ),
    ]
