from django.db import migrations


PAGINAS = [
    {
        'chave': 'gestao_dns',
        'nome_exibicao': 'Gestão de Domínios DNS',
        'descricao': 'Consulta e gerenciamento de registros DNS vinculados aos servidores.',
        'icone': 'globe',
        'rota_nome': 'gestao-dns',
    },
    {
        'chave': 'relatorio_pagamentos',
        'nome_exibicao': 'Relatório de Pagamentos',
        'descricao': 'Relatório detalhado de mensalidades pagas, pendentes e atrasadas.',
        'icone': 'bar-chart-2',
        'rota_nome': 'relatorio-pagamentos',
    },
    {
        'chave': 'importar_clientes',
        'nome_exibicao': 'Importação de Clientes',
        'descricao': 'Importação em lote de clientes a partir de planilha CSV.',
        'icone': 'upload',
        'rota_nome': 'importar-clientes',
    },
    {
        'chave': 'tarefas_envio',
        'nome_exibicao': 'Tarefas de Envio WhatsApp',
        'descricao': 'Criação e gestão de tarefas automáticas de envio de mensagens via WhatsApp.',
        'icone': 'bi-whatsapp',
        'rota_nome': 'tarefas-envio-lista',
    },
    {
        'chave': 'cadastro_assinatura',
        'nome_exibicao': 'Cadastro de Assinaturas',
        'descricao': 'Cadastro e gestão de assinaturas de clientes.',
        'icone': 'credit-card',
        'rota_nome': 'cadastro-assinatura',
    },
]


def populate(apps, schema_editor):
    ControleAcessoPagina = apps.get_model('nossopainel', 'ControleAcessoPagina')
    for p in PAGINAS:
        ControleAcessoPagina.objects.get_or_create(chave=p['chave'], defaults=p)


def depopulate(apps, schema_editor):
    ControleAcessoPagina = apps.get_model('nossopainel', 'ControleAcessoPagina')
    ControleAcessoPagina.objects.filter(chave__in=[p['chave'] for p in PAGINAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0126_controle_acesso_pagina'),
    ]

    operations = [
        migrations.RunPython(populate, depopulate),
    ]
