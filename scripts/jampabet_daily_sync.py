"""
JampaBet - Script de Sincronização Diária

Este script sincroniza todos os dados do JampaBet com a API-Football:
1. Competições brasileiras
2. Times brasileiros
3. Partidas de todas as competições monitoradas (Fixture)
4. Partidas do Bahia para palpites (Match)

Executado diariamente à meia-noite pelo scheduler.
"""

import os
import sys
import logging
from datetime import datetime

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from django.utils import timezone

# Imports dos modelos e serviços do JampaBet
from jampabet.models import Match, Fixture, Competition, BrazilianTeam
from jampabet.services.api_football import APIFootballService

# Configuração do logger
LOG_DIR = "logs/JampaBet"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("JampaBetSync")
logger.setLevel(logging.DEBUG)
logger.propagate = False

# File handler
fh = logging.FileHandler(os.path.join(LOG_DIR, "daily_sync.log"), encoding="utf-8")
fh.setLevel(logging.DEBUG)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%d-%m-%Y %H:%M:%S")
fh.setFormatter(fmt)
ch.setFormatter(fmt)

if not logger.handlers:
    logger.addHandler(fh)
    logger.addHandler(ch)


def sync_all():
    """
    Sincroniza todos os dados do JampaBet.
    Retorna um dicionário com o resultado de cada sincronização.
    """
    results = {
        'competitions': {'success': False, 'count': 0, 'error': None},
        'teams': {'success': False, 'count': 0, 'error': None},
        'fixtures': {'success': False, 'count': 0, 'error': None},
        'matches': {'success': False, 'count': 0, 'error': None},
    }

    start_time = timezone.now()
    logger.info("=" * 60)
    logger.info("JAMPABET - SINCRONIZAÇÃO DIÁRIA INICIADA")
    logger.info(f"Data/Hora: {start_time.strftime('%d/%m/%Y %H:%M:%S')}")
    logger.info("=" * 60)

    current_year = datetime.now().year

    # 1. Sincroniza Competições
    logger.info("\n[1/4] Sincronizando competições...")
    try:
        count = APIFootballService.sync_competitions(Competition)
        results['competitions'] = {'success': True, 'count': count, 'error': None}
        logger.info(f"      ✓ {count} competições sincronizadas")
    except Exception as e:
        results['competitions'] = {'success': False, 'count': 0, 'error': str(e)}
        logger.error(f"      ✗ Erro: {e}")

    # 2. Sincroniza Times
    logger.info("\n[2/4] Sincronizando times brasileiros...")
    try:
        count = APIFootballService.sync_brazilian_teams(BrazilianTeam)
        results['teams'] = {'success': True, 'count': count, 'error': None}
        logger.info(f"      ✓ {count} times sincronizados")
    except Exception as e:
        results['teams'] = {'success': False, 'count': 0, 'error': str(e)}
        logger.error(f"      ✗ Erro: {e}")

    # 3. Sincroniza Fixtures (todas as competições monitoradas)
    logger.info("\n[3/4] Sincronizando partidas (Fixtures)...")
    try:
        total_fixtures = 0

        # Sincroniza ano atual e próximo
        for season in [current_year, current_year + 1]:
            logger.info(f"      Temporada {season}...")
            count = APIFootballService.sync_fixtures(
                Fixture, Competition, BrazilianTeam,
                league_id=None,  # Todas as competições monitoradas
                season=season
            )
            total_fixtures += count
            logger.info(f"      - {count} partidas sincronizadas")

        results['fixtures'] = {'success': True, 'count': total_fixtures, 'error': None}
        logger.info(f"      ✓ Total: {total_fixtures} partidas")
    except Exception as e:
        results['fixtures'] = {'success': False, 'count': 0, 'error': str(e)}
        logger.error(f"      ✗ Erro: {e}")

    # 4. Sincroniza Matches (partidas do Bahia para palpites)
    logger.info("\n[4/4] Sincronizando partidas do Bahia (Matches)...")
    try:
        count = APIFootballService.sync_matches(Match)
        results['matches'] = {'success': True, 'count': count, 'error': None}
        logger.info(f"      ✓ {count} partidas do Bahia sincronizadas")
    except Exception as e:
        results['matches'] = {'success': False, 'count': 0, 'error': str(e)}
        logger.error(f"      ✗ Erro: {e}")

    # Resumo final
    end_time = timezone.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("RESUMO DA SINCRONIZAÇÃO")
    logger.info("=" * 60)
    logger.info(f"Competições: {results['competitions']['count']} {'✓' if results['competitions']['success'] else '✗'}")
    logger.info(f"Times:       {results['teams']['count']} {'✓' if results['teams']['success'] else '✗'}")
    logger.info(f"Fixtures:    {results['fixtures']['count']} {'✓' if results['fixtures']['success'] else '✗'}")
    logger.info(f"Matches:     {results['matches']['count']} {'✓' if results['matches']['success'] else '✗'}")
    logger.info(f"Duração:     {duration:.1f} segundos")
    logger.info("=" * 60 + "\n")

    return results


def run_daily_sync():
    """
    Função chamada pelo scheduler.
    Executa a sincronização completa.
    """
    try:
        results = sync_all()

        # Verifica se houve erros
        errors = [k for k, v in results.items() if not v['success']]
        if errors:
            logger.warning(f"Sincronização concluída com erros em: {', '.join(errors)}")
        else:
            logger.info("Sincronização concluída com sucesso!")

        return results

    except Exception as e:
        logger.exception(f"Erro fatal na sincronização diária: {e}")
        return None


# Execução direta (para testes)
if __name__ == "__main__":
    logger.info("Executando sincronização diária manualmente...")
    run_daily_sync()
