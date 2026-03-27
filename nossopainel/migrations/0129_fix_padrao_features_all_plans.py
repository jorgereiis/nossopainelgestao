"""
Garante que todas as FUNCIONALIDADES_PADRAO estejam ativo=True em todos os planos.
Bronze tinha clientes_cadastro, clientes_logs e bancario_contas com ativo=False.
"""

from django.db import migrations

PADRAO = [
    'clientes_cadastro', 'clientes_edicao', 'clientes_cancelamento',
    'clientes_reativacao', 'clientes_cancelados_lista', 'clientes_logs',
    'dash_cards',
    'financeiro_mensalidades', 'financeiro_pagamento_manual',
    'financeiro_formas_pgto', 'financeiro_planos_pgto',
    'bancario_contas',
    'infra_servidores', 'infra_dispositivos', 'infra_aplicativos', 'infra_contas_app',
]


def fix(apps, schema_editor):
    PlanoAssinatura     = apps.get_model('nossopainel', 'PlanoAssinatura')
    FuncionalidadePlano = apps.get_model('nossopainel', 'FuncionalidadePlano')
    for plano in PlanoAssinatura.objects.all():
        for chave in PADRAO:
            FuncionalidadePlano.objects.update_or_create(
                plano=plano,
                chave=chave,
                defaults={'ativo': True},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0128_seed_pagamentos_automatizados'),
    ]

    operations = [
        migrations.RunPython(fix, migrations.RunPython.noop),
    ]
