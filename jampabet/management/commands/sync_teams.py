"""
Management command para sincronizar times brasileiros da API-Football.
"""
from django.core.management.base import BaseCommand
from jampabet.services.api_football import APIFootballService
from jampabet.models import BrazilianTeam


class Command(BaseCommand):
    help = 'Sincroniza times brasileiros da Série A e B com o banco de dados'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Exibe detalhes de cada time processado'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Iniciando sincronização de times...'))

        try:
            count = APIFootballService.sync_brazilian_teams(BrazilianTeam)

            if count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Sincronização concluída: {count} times processados')
                )

                if options['verbose']:
                    self.stdout.write('\nTimes cadastrados:')
                    for team in BrazilianTeam.objects.all():
                        display = team.get_display_name
                        logo = '(custom)' if team.custom_logo_url else ''
                        self.stdout.write(f'  - {team.name} -> {display} {logo}')
            else:
                self.stdout.write(
                    self.style.WARNING('Nenhum time foi sincronizado')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Erro durante sincronização: {str(e)}')
            )
