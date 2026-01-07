# Generated migration for dias_cancelamento and leads valido fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0107_add_whatsapp_lid_to_cliente'),
    ]

    operations = [
        # Adiciona campo dias_cancelamento ao TarefaEnvio
        migrations.AddField(
            model_name='tarefaenvio',
            name='dias_cancelamento',
            field=models.PositiveIntegerField(
                default=10,
                help_text='Quantidade mínima de dias desde o cancelamento para incluir o cliente (apenas para tipo "Cancelados")',
                verbose_name='Dias de Cancelamento'
            ),
        ),
        # Adiciona campo valido ao TelefoneLeads
        migrations.AddField(
            model_name='telefoneleads',
            name='valido',
            field=models.BooleanField(
                default=True,
                help_text='Indica se o número foi validado no WhatsApp. Números inválidos são marcados como False ao invés de deletados.',
                verbose_name='Válido'
            ),
        ),
        # Adiciona campo data_validacao ao TelefoneLeads
        migrations.AddField(
            model_name='telefoneleads',
            name='data_validacao',
            field=models.DateTimeField(
                blank=True,
                help_text='Data/hora da última validação do número',
                null=True,
                verbose_name='Data da Validação'
            ),
        ),
        # Adiciona campo criado_em ao TelefoneLeads
        migrations.AddField(
            model_name='telefoneleads',
            name='criado_em',
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name='Criado Em',
                null=True,  # Temporário para registros existentes
            ),
        ),
        # Adiciona índice para TelefoneLeads
        migrations.AddIndex(
            model_name='telefoneleads',
            index=models.Index(
                fields=['usuario', 'valido'],
                name='lead_usr_valido_idx'
            ),
        ),
    ]
