# Generated manually on 2025-12-22

from django.db import migrations


def atualizar_icone(apps, schema_editor):
    """Atualiza o ícone do GP Futebol para ícone de bola."""
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')

    ConfiguracaoAgendamento.objects.filter(nome='gp_futebol').update(icone='bi-dribbble')


def reverter_icone(apps, schema_editor):
    """Reverte o ícone do GP Futebol para trophy."""
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')

    ConfiguracaoAgendamento.objects.filter(nome='gp_futebol').update(icone='trophy')


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0093_desbloquear_gp_futebol_vendas'),
    ]

    operations = [
        migrations.RunPython(atualizar_icone, reverter_icone),
    ]
