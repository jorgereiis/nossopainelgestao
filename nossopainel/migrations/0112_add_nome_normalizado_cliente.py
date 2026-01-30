# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0111_add_execucao_completa_tarefaenvio'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='nome_normalizado',
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                help_text='Nome sem acentos para busca (preenchido automaticamente)',
                max_length=255,
                default='',
            ),
            preserve_default=False,
        ),
    ]
