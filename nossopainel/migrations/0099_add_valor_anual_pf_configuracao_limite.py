# Generated migration for adding valor_anual_pf to ConfiguracaoLimite

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0098_push_subscription'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracaolimite',
            name='valor_anual_pf',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('60000.00'),
                help_text='Valor máximo anual permitido para contas Pessoa Física',
                max_digits=12,
                verbose_name='Limite Anual Pessoa Física (R$)'
            ),
        ),
    ]
