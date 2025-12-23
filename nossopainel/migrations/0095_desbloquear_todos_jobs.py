# Generated manually on 2025-12-22

from django.db import migrations


def desbloquear_todos(apps, schema_editor):
    """Desbloqueia todos os jobs para permitir edição na interface."""
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')
    ConfiguracaoAgendamento.objects.all().update(bloqueado=False)


def bloquear_todos(apps, schema_editor):
    """Reverte: bloqueia todos os jobs exceto envios_vencimento."""
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')
    ConfiguracaoAgendamento.objects.exclude(
        nome__in=['envios_vencimento', 'gp_futebol', 'gp_vendas']
    ).update(bloqueado=True)


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0094_update_icone_gp_futebol'),
    ]

    operations = [
        migrations.RunPython(desbloquear_todos, bloquear_todos),
    ]
