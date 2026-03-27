"""
Seed FuncionalidadePlano para a chave 'pagamentos_automatizados',
que substituiu 'bancario_fastdepix' + 'bancario_outras_integracoes'.
Bronze: desativado  |  Prata: ativado  |  Ouro: ativado
"""

from django.db import migrations

CHAVE = 'pagamentos_automatizados'

PLANO_ATIVO = {
    'bronze': False,
    'prata':  True,
    'ouro':   True,
}


def seed(apps, schema_editor):
    PlanoAssinatura     = apps.get_model('nossopainel', 'PlanoAssinatura')
    FuncionalidadePlano = apps.get_model('nossopainel', 'FuncionalidadePlano')

    for plano in PlanoAssinatura.objects.filter(tipo__in=PLANO_ATIVO.keys()):
        FuncionalidadePlano.objects.update_or_create(
            plano=plano,
            chave=CHAVE,
            defaults={'ativo': PLANO_ATIVO[plano.tipo]},
        )


def deseed(apps, schema_editor):
    FuncionalidadePlano = apps.get_model('nossopainel', 'FuncionalidadePlano')
    FuncionalidadePlano.objects.filter(chave=CHAVE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0127_populate_controle_acesso_pagina'),
    ]

    operations = [
        migrations.RunPython(seed, deseed),
    ]
