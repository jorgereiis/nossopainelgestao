"""
Data migration: cria os 3 planos padrão (Bronze/Prata/Ouro) com suas funcionalidades,
e cria AssinaturaPlataforma em trial para todos os usuários não-superuser existentes.
"""

from datetime import date, timedelta

from django.db import migrations

# ─────────────────────────────────────────────────────────────────────────────
# Mapeamento de funcionalidades por grupo
# ─────────────────────────────────────────────────────────────────────────────
TODAS_FUNCIONALIDADES = [
    # Grupo 1 — Clientes
    'clientes_cadastro',
    'clientes_edicao',
    'clientes_cancelamento',
    'clientes_reativacao',
    'clientes_importacao_lote',
    'clientes_exportacao',
    'clientes_logs',
    'clientes_cancelados_lista',
    # Grupo 2 — Dashboard / Relatórios
    'dash_cards',
    'relatorio_evolucao_patrimonio',
    'relatorio_receita_anual',
    'relatorio_adesoes_cancelamentos',
    'relatorio_mapa_clientes',
    'relatorio_pagamentos',
    'relatorio_indicacoes',
    # Grupo 3 — WhatsApp
    'whatsapp_sessao',
    'whatsapp_tarefas_envio',
    'whatsapp_templates',
    'whatsapp_historico_execucoes',
    'whatsapp_estatisticas',
    'whatsapp_preview_alcance',
    'whatsapp_leads',
    # Grupo 4 — Financeiro
    'financeiro_mensalidades',
    'financeiro_pagamento_manual',
    'financeiro_pix_geracao',
    'financeiro_pix_webhook',
    'financeiro_formas_pgto',
    'financeiro_planos_pgto',
    # Grupo 5 — Bancário
    'bancario_contas',
    'bancario_fastdepix',
    'bancario_outras_integracoes',
    'bancario_limite_mei',
    # Grupo 6 — Atendimentos
    'atendimento_registrar',
    'atendimento_historico',
    'atendimento_categorias',
    'atendimento_imagens',
    # Grupo 7 — Atendentes
    'atendentes_gestao',
    'atendentes_limite',
    'atendentes_produtividade',
    # Grupo 8 — Infraestrutura
    'infra_servidores',
    'infra_dispositivos',
    'infra_aplicativos',
    'infra_contas_app',
    # Grupo 9 — Segurança / Perfil
    'seguranca_2fa',
    'seguranca_push_notif',
    'perfil_historico',
    'perfil_privacidade',
    # Grupo 10 — Avançado
    'avancado_revendedores',
    'avancado_migracao_dns',
    'avancado_logs_auditoria',
    'avancado_integracoes_api',
]

# Bronze: funcionalidades básicas (sem relatórios avançados, sem WhatsApp avançado, sem bancário avançado)
BRONZE_FEATURES = {
    'clientes_cadastro', 'clientes_edicao', 'clientes_cancelamento',
    'clientes_reativacao', 'clientes_cancelados_lista',
    'dash_cards',
    'financeiro_mensalidades', 'financeiro_pagamento_manual', 'financeiro_formas_pgto', 'financeiro_planos_pgto',
    'atendimento_registrar', 'atendimento_historico', 'atendimento_categorias',
    'infra_servidores', 'infra_dispositivos', 'infra_aplicativos', 'infra_contas_app',
    'seguranca_2fa', 'perfil_privacidade',
}

# Prata: tudo do Bronze + relatórios + WhatsApp básico + exportação + logs
PRATA_FEATURES = BRONZE_FEATURES | {
    'clientes_importacao_lote', 'clientes_exportacao', 'clientes_logs',
    'relatorio_evolucao_patrimonio', 'relatorio_receita_anual', 'relatorio_adesoes_cancelamentos',
    'relatorio_indicacoes',
    'whatsapp_sessao', 'whatsapp_tarefas_envio', 'whatsapp_templates',
    'financeiro_pix_geracao',
    'bancario_contas',
    'atendimento_imagens',
    'atendentes_gestao', 'atendentes_limite',
    'seguranca_push_notif', 'perfil_historico',
}

# Ouro: todas as funcionalidades
OURO_FEATURES = set(TODAS_FUNCIONALIDADES)

PLANOS_CONFIG = [
    {
        'tipo': 'bronze',
        'valor': '69.90',
        'descricao': 'Plano Bronze — funcionalidades essenciais para gestão de clientes.',
        'features': BRONZE_FEATURES,
    },
    {
        'tipo': 'prata',
        'valor': '119.90',
        'descricao': 'Plano Prata — inclui relatórios, WhatsApp e recursos avançados.',
        'features': PRATA_FEATURES,
    },
    {
        'tipo': 'ouro',
        'valor': '219.90',
        'descricao': 'Plano Ouro — acesso completo a todas as funcionalidades da plataforma.',
        'features': OURO_FEATURES,
    },
]


def criar_planos(apps, schema_editor):
    PlanoAssinatura = apps.get_model('nossopainel', 'PlanoAssinatura')
    FuncionalidadePlano = apps.get_model('nossopainel', 'FuncionalidadePlano')

    for cfg in PLANOS_CONFIG:
        plano, _ = PlanoAssinatura.objects.get_or_create(
            tipo=cfg['tipo'],
            defaults={'valor': cfg['valor'], 'descricao': cfg['descricao'], 'ativo': True},
        )
        for chave in TODAS_FUNCIONALIDADES:
            FuncionalidadePlano.objects.get_or_create(
                plano=plano,
                chave=chave,
                defaults={'ativo': chave in cfg['features']},
            )


def criar_assinaturas_trial(apps, schema_editor):
    """Cria AssinaturaPlataforma em trial para todos os usuários não-superuser existentes."""
    User = apps.get_model('auth', 'User')
    AssinaturaPlataforma = apps.get_model('nossopainel', 'AssinaturaPlataforma')

    for user in User.objects.filter(is_superuser=False):
        # Atendentes (usuários que têm PerfilAtendente) não precisam de assinatura própria
        try:
            PerfilAtendente = apps.get_model('nossopainel', 'PerfilAtendente')
            PerfilAtendente.objects.get(user=user)
            continue  # é atendente — pular
        except Exception:
            pass

        trial_fim = user.date_joined.date() + timedelta(days=30)
        AssinaturaPlataforma.objects.get_or_create(
            usuario=user,
            defaults={
                'status': 'trial',
                'trial_fim': trial_fim,
                'dias_extras': 0,
            },
        )


def desfazer_planos(apps, schema_editor):
    PlanoAssinatura = apps.get_model('nossopainel', 'PlanoAssinatura')
    PlanoAssinatura.objects.filter(tipo__in=['bronze', 'prata', 'ouro']).delete()


def desfazer_assinaturas(apps, schema_editor):
    AssinaturaPlataforma = apps.get_model('nossopainel', 'AssinaturaPlataforma')
    AssinaturaPlataforma.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0124_add_sistema_assinatura'),
    ]

    operations = [
        migrations.RunPython(criar_planos, desfazer_planos),
        migrations.RunPython(criar_assinaturas_trial, desfazer_assinaturas),
    ]
