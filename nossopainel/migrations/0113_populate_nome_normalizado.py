# Generated manually - Migração de dados para popular nome_normalizado

from django.db import migrations
import unicodedata


def normalizar_nome(nome):
    """Remove acentos e converte para minúsculas."""
    if not nome:
        return ""
    return unicodedata.normalize(
        "NFKD", nome
    ).encode("ascii", "ignore").decode("ascii").lower()


def populate_nome_normalizado(apps, schema_editor):
    """Popula o campo nome_normalizado para todos os clientes existentes."""
    Cliente = apps.get_model('nossopainel', 'Cliente')

    # Usar iterator() para eficiência em tabelas grandes
    clientes = Cliente.objects.all().iterator(chunk_size=1000)

    batch = []
    batch_size = 500

    for cliente in clientes:
        cliente.nome_normalizado = normalizar_nome(cliente.nome)
        batch.append(cliente)

        if len(batch) >= batch_size:
            Cliente.objects.bulk_update(batch, ['nome_normalizado'])
            batch = []

    # Atualiza o restante
    if batch:
        Cliente.objects.bulk_update(batch, ['nome_normalizado'])


def reverse_migration(apps, schema_editor):
    """Reverte a migração limpando o campo."""
    Cliente = apps.get_model('nossopainel', 'Cliente')
    Cliente.objects.all().update(nome_normalizado='')


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0112_add_nome_normalizado_cliente'),
    ]

    operations = [
        migrations.RunPython(populate_nome_normalizado, reverse_migration),
    ]
