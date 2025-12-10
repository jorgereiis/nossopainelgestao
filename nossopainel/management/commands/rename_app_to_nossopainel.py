"""
Management command para atualizar o nome do app de 'cadastros' para 'nossopainel'
no banco de dados (django_migrations e django_content_type).

Uso:
    python manage.py rename_app_to_nossopainel
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Atualiza o nome do app de 'cadastros' para 'nossopainel' no banco de dados"

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # 1. Atualizar django_migrations
            cursor.execute(
                "UPDATE django_migrations SET app = 'nossopainel' WHERE app = 'cadastros'"
            )
            migrations_updated = cursor.rowcount
            self.stdout.write(
                f"django_migrations: {migrations_updated} registros atualizados"
            )

            # 2. Atualizar django_content_type
            cursor.execute(
                "UPDATE django_content_type SET app_label = 'nossopainel' WHERE app_label = 'cadastros'"
            )
            content_types_updated = cursor.rowcount
            self.stdout.write(
                f"django_content_type: {content_types_updated} registros atualizados"
            )

            # 3. Verificar
            cursor.execute(
                "SELECT COUNT(*) FROM django_migrations WHERE app = 'nossopainel'"
            )
            total_migrations = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM django_content_type WHERE app_label = 'nossopainel'"
            )
            total_content_types = cursor.fetchone()[0]

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Concluído! "
                f"Migrações: {total_migrations}, ContentTypes: {total_content_types}"
            )
        )
