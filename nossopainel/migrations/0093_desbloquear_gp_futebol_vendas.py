# Generated manually on 2025-12-22

from django.db import migrations


def desbloquear_jobs(apps, schema_editor):
    """Desbloqueia GP Futebol e GP Vendas para permitir edição na interface."""
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')

    ConfiguracaoAgendamento.objects.filter(
        nome__in=['gp_futebol', 'gp_vendas']
    ).update(bloqueado=False)


def bloquear_jobs(apps, schema_editor):
    """Reverte: bloqueia GP Futebol e GP Vendas novamente."""
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')

    ConfiguracaoAgendamento.objects.filter(
        nome__in=['gp_futebol', 'gp_vendas']
    ).update(bloqueado=True)


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0092_add_configuracao_agendamento'),
    ]

    operations = [
        migrations.RunPython(desbloquear_jobs, bloquear_jobs),
    ]
