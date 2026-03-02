from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0115_alter_configuracaoenvio_intervalos'),
    ]

    operations = [
        migrations.AddField(
            model_name='servidor',
            name='cor_etiqueta',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Cor hexadecimal para a etiqueta do WhatsApp (ex: #4CAF50). '
                          'Tem prioridade sobre o dicionário fixo. Deixe vazio para usar o padrão.',
                max_length=7,
                verbose_name='Cor da etiqueta (hex)',
            ),
        ),
    ]
