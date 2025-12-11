"""Management command para limpar sessões WPP antigas e inativas."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from nossopainel.models import SessaoWpp


class Command(BaseCommand):
    help = "Remove sessões WPP inativas mais antigas que N dias (padrão: 7)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dias',
            type=int,
            default=7,
            help='Número de dias para considerar sessão antiga (padrão: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria removido sem executar'
        )
        parser.add_argument(
            '--incluir-ativas',
            action='store_true',
            help='Incluir também sessões ativas antigas (cuidado!)'
        )

    def handle(self, *args, **options):
        dias = options['dias']
        dry_run = options['dry_run']
        incluir_ativas = options['incluir_ativas']

        data_limite = timezone.now() - timedelta(days=dias)

        # Filtro base: sessões antigas
        filtro = {'dt_inicio__lt': data_limite}

        # Por padrão, apenas sessões inativas
        if not incluir_ativas:
            filtro['is_active'] = False

        sessoes_antigas = SessaoWpp.objects.filter(**filtro)
        total = sessoes_antigas.count()

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS("Nenhuma sessão antiga encontrada para remoção.")
            )
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"[DRY-RUN] Seriam removidas {total} sessões")
            )
            self.stdout.write("")
            self.stdout.write("Sessões que seriam removidas:")
            for s in sessoes_antigas[:10]:
                status = "ATIVA" if s.is_active else "INATIVA"
                self.stdout.write(
                    f"  - {s.usuario} | {s.dt_inicio.strftime('%d/%m/%Y %H:%M')} | {status}"
                )
            if total > 10:
                self.stdout.write(f"  ... e mais {total - 10} sessões")
            self.stdout.write("")
            self.stdout.write(
                self.style.NOTICE("Execute sem --dry-run para remover de fato.")
            )
        else:
            deleted, details = sessoes_antigas.delete()
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(f"✓ Removidas {deleted} sessões antigas")
            )
            if details:
                for model, count in details.items():
                    if count > 0:
                        self.stdout.write(f"  - {model}: {count}")
            self.stdout.write("")
