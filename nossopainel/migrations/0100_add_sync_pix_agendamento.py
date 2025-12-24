# Generated migration - Adiciona job de sincronização PIX

from django.db import migrations


def adicionar_sync_pix(apps, schema_editor):
    """Adiciona o job de sincronização de pagamentos PIX."""
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')

    # Verifica se já existe para evitar duplicatas
    if not ConfiguracaoAgendamento.objects.filter(nome='sync_pix').exists():
        ConfiguracaoAgendamento.objects.create(
            nome='sync_pix',
            nome_exibicao='Sincronização PIX',
            descricao=(
                'Sincroniza pagamentos PIX pendentes com a API FastDePix. '
                'Funciona como rede de segurança para casos onde o webhook falhe. '
                'Verifica cobranças pendentes criadas há mais de 30 minutos e ainda não expiradas.'
            ),
            icone='refresh-cw',
            horario='A cada 30 minutos',
            ativo=True,
            bloqueado=False,
            ordem=9,
            templates_mensagem={}
        )


def remover_sync_pix(apps, schema_editor):
    """Remove o job de sincronização PIX."""
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')
    ConfiguracaoAgendamento.objects.filter(nome='sync_pix').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0099_add_valor_anual_pf_configuracao_limite'),
    ]

    operations = [
        migrations.RunPython(adicionar_sync_pix, remover_sync_pix),
    ]
