"""
JampaBet - Script de Monitoramento de Partidas ao Vivo

Este script:
1. Verifica partidas do dia atual no banco
2. Muda status para 'live' quando chega o horario de inicio
3. Faz polling da API para atualizar placares em tempo real
4. Muda status para 'finished' quando a API retornar esse status

Executado a cada 1 minuto pelo agendador.
"""

import os
import sys
import logging
import threading
import time
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from django.utils import timezone
from django.db import transaction

# Imports dos modelos e servicos do JampaBet
from jampabet.models import Match, APIConfig
from jampabet.services.api_football import APIFootballService

# Configuracao do logger
LOG_DIR = "logs/JampaBet"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("JampaBetLive")
logger.setLevel(logging.DEBUG)
logger.propagate = False

# File handler
fh = logging.FileHandler(os.path.join(LOG_DIR, "live_matches.log"), encoding="utf-8")
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


# ================= VARIAVEIS GLOBAIS =================
_polling_thread = None
_polling_active = False
_last_polling_interval = 60


def get_config():
    """Obtem configuracoes da API"""
    try:
        return APIConfig.get_config()
    except Exception as e:
        logger.error(f"Erro ao obter configuracoes: {e}")
        return None


def check_matches_to_start():
    """
    Verifica partidas que deveriam ter comecado e muda status para 'live'.
    Executado a cada 1 minuto.
    """
    config = get_config()
    if not config or not config.auto_start_matches:
        return 0

    now = timezone.now()
    started_count = 0

    # Busca partidas com status 'upcoming' que ja passaram do horario de inicio
    matches_to_start = Match.objects.filter(
        status='upcoming',
        date__lte=now  # Data/hora ja passou
    )

    for match in matches_to_start:
        try:
            # Calcula quanto tempo passou desde o inicio
            minutes_elapsed = (now - match.date).total_seconds() / 60

            # Se passou menos de 3 horas (180 min), considera que esta ao vivo
            # Depois disso, provavelmente ja encerrou e precisa de sync manual
            if minutes_elapsed <= 180:
                old_status = match.status
                match.status = 'live'
                match.elapsed_time = int(min(minutes_elapsed, 90))  # Max 90 min
                match.save(update_fields=['status', 'elapsed_time', 'updated_at'])

                logger.info(
                    f"Partida iniciada: {match.home_team} x {match.away_team} "
                    f"(ID: {match.id}, status: {old_status} -> live, elapsed: {match.elapsed_time}min)"
                )
                started_count += 1
            else:
                # Partida passou de 3h, provavelmente encerrada
                logger.warning(
                    f"Partida pode ter encerrado: {match.home_team} x {match.away_team} "
                    f"(ID: {match.id}, {minutes_elapsed:.0f} min desde inicio)"
                )

        except Exception as e:
            logger.error(f"Erro ao atualizar partida {match.id}: {e}")

    if started_count > 0:
        logger.info(f"Total de partidas iniciadas: {started_count}")

    return started_count


def update_live_matches_from_api():
    """
    Atualiza placares das partidas ao vivo consultando a API.
    """
    config = get_config()
    if not config:
        return 0

    if not config.api_enabled:
        logger.debug("API desabilitada, pulando atualizacao")
        return 0

    if not config.auto_update_scores:
        logger.debug("Atualizacao automatica de placares desabilitada")
        return 0

    # Busca partidas ao vivo
    live_matches = Match.objects.filter(status='live')

    if not live_matches.exists():
        logger.debug("Nenhuma partida ao vivo para atualizar")
        config.update_poll_status('idle', 'Nenhuma partida ao vivo')
        return 0

    updated_count = 0
    errors = []

    for match in live_matches:
        try:
            # Se nao tem external_id, nao consegue consultar API
            if not match.external_id:
                logger.warning(f"Partida {match.id} sem external_id, pulando")
                continue

            # Consulta API pelo ID da partida
            fixture = APIFootballService.get_fixture_by_id(match.external_id)
            config.increment_api_calls()

            if not fixture:
                logger.warning(f"Partida {match.external_id} nao encontrada na API")
                continue

            # Parse dos dados
            fixture_data = fixture.get("fixture", {})
            goals = fixture.get("goals", {})
            teams = fixture.get("teams", {})

            # Determina qual lado e o Bahia
            home_team = teams.get("home", {})
            away_team = teams.get("away", {})
            is_bahia_home = home_team.get("id") == 118  # ID do Bahia

            if is_bahia_home:
                result_bahia = goals.get("home")
                result_opponent = goals.get("away")
            else:
                result_bahia = goals.get("away")
                result_opponent = goals.get("home")

            # Mapeia status da API
            api_status = fixture_data.get("status", {}).get("short", "")
            elapsed = fixture_data.get("status", {}).get("elapsed")

            new_status = match.status
            if api_status in ["FT", "AET", "PEN"]:
                new_status = "finished"
            elif api_status in ["1H", "HT", "2H", "ET", "BT", "P", "LIVE"]:
                new_status = "live"
            elif api_status in ["CANC", "ABD", "AWD", "WO"]:
                new_status = "cancelled"
            elif api_status in ["PST"]:
                new_status = "postponed"

            # Atualiza apenas se houve mudanca
            changed = False
            changes = []

            # Se a partida vai encerrar, deixa o BetService processar tudo
            # (ele atualiza resultado, status e calcula pontuacoes)
            if new_status == 'finished' and match.status != 'finished':
                changes.append(f"status: {match.status} -> {new_status}")
                changes.append(f"gols_bahia: {match.result_bahia} -> {result_bahia}")
                changes.append(f"gols_adv: {match.result_opponent} -> {result_opponent}")

                # Processa resultado e pontuacoes via BetService
                process_match_result(match, result_bahia, result_opponent)

                updated_count += 1
                logger.info(
                    f"Partida encerrada: {match.home_team} x {match.away_team} "
                    f"({', '.join(changes)})"
                )
            else:
                # Partida ainda em andamento - atualiza normalmente
                if match.result_bahia != result_bahia:
                    changes.append(f"gols_bahia: {match.result_bahia} -> {result_bahia}")
                    match.result_bahia = result_bahia
                    changed = True

                if match.result_opponent != result_opponent:
                    changes.append(f"gols_adv: {match.result_opponent} -> {result_opponent}")
                    match.result_opponent = result_opponent
                    changed = True

                if elapsed and match.elapsed_time != elapsed:
                    changes.append(f"tempo: {match.elapsed_time} -> {elapsed}")
                    match.elapsed_time = elapsed
                    changed = True

                if match.status != new_status:
                    changes.append(f"status: {match.status} -> {new_status}")
                    match.status = new_status
                    changed = True

                if changed:
                    match.save()
                    updated_count += 1
                    logger.info(
                        f"Partida atualizada: {match.home_team} x {match.away_team} "
                        f"({', '.join(changes)})"
                    )

        except Exception as e:
            error_msg = f"Erro ao atualizar partida {match.id}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    # Atualiza status do polling
    if errors:
        config.update_poll_status('error', f"Erros: {len(errors)} | Atualizadas: {updated_count}")
    else:
        config.update_poll_status('success', f"Atualizadas: {updated_count} partidas ao vivo")

    return updated_count


def process_match_result(match, result_bahia, result_opponent):
    """
    Processa resultado de uma partida encerrada e calcula pontos.

    O BetService.process_match_result ira:
    1. Reverter pontos anteriores (se a partida ja tinha resultado)
    2. Atualizar o resultado da partida
    3. Calcular e distribuir os novos pontos

    Args:
        match: Instancia do Match
        result_bahia: Gols do Bahia
        result_opponent: Gols do adversario
    """
    try:
        from jampabet.services.bet_service import BetService
        BetService.process_match_result(
            match=match,
            result_bahia=result_bahia,
            result_opponent=result_opponent
        )
        logger.info(f"Resultado processado para partida {match.id}: Bahia {result_bahia} x {result_opponent}")
    except Exception as e:
        logger.error(f"Erro ao processar resultado da partida {match.id}: {e}")


def start_live_polling():
    """
    Inicia thread de polling para partidas ao vivo.
    O polling roda em background enquanto houver partidas live.
    """
    global _polling_thread, _polling_active, _last_polling_interval

    # Se ja esta rodando, nao inicia outra
    if _polling_active and _polling_thread and _polling_thread.is_alive():
        logger.debug("Polling ja esta ativo")
        return

    config = get_config()
    if not config:
        return

    # Verifica se tem partidas ao vivo
    live_count = Match.objects.filter(status='live').count()
    if live_count == 0:
        logger.debug("Nenhuma partida ao vivo, polling nao necessario")
        return

    _polling_active = True
    _last_polling_interval = config.polling_interval

    def polling_loop():
        global _polling_active, _last_polling_interval

        logger.info(f"Iniciando polling de partidas ao vivo (intervalo: {_last_polling_interval}s)")

        while _polling_active:
            try:
                # Atualiza partidas da API
                update_live_matches_from_api()

                # Verifica se ainda tem partidas ao vivo
                live_count = Match.objects.filter(status='live').count()
                if live_count == 0:
                    logger.info("Nenhuma partida ao vivo, encerrando polling")
                    _polling_active = False
                    break

                # Recarrega config para pegar intervalo atualizado
                config = get_config()
                if config:
                    _last_polling_interval = config.polling_interval

                # Aguarda intervalo
                time.sleep(_last_polling_interval)

            except Exception as e:
                logger.error(f"Erro no loop de polling: {e}")
                time.sleep(30)  # Espera 30s em caso de erro

        logger.info("Polling de partidas ao vivo encerrado")

    _polling_thread = threading.Thread(target=polling_loop, daemon=True)
    _polling_thread.start()


def stop_live_polling():
    """Para o polling de partidas ao vivo."""
    global _polling_active
    _polling_active = False
    logger.info("Solicitado encerramento do polling")


def run_check_and_poll():
    """
    Funcao principal executada pelo agendador a cada 1 minuto.
    1. Verifica partidas que devem iniciar
    2. Inicia polling se houver partidas ao vivo
    """
    try:
        logger.debug("Executando verificacao de partidas...")

        # 1. Verifica partidas que devem iniciar
        started = check_matches_to_start()

        # 2. Inicia polling se houver partidas ao vivo
        live_count = Match.objects.filter(status='live').count()
        if live_count > 0:
            start_live_polling()
            logger.debug(f"Partidas ao vivo: {live_count}")
        else:
            logger.debug("Nenhuma partida ao vivo no momento")

        return started

    except Exception as e:
        logger.error(f"Erro na verificacao de partidas: {e}")
        return 0


# ================= EXECUCAO DIRETA =================
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("JampaBet Live Matches - Execucao manual")
    logger.info("=" * 60)

    # Executa verificacao inicial
    run_check_and_poll()

    # Se houver partidas ao vivo, mantem rodando
    try:
        while _polling_active:
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Encerrando por interrupcao do usuario...")
        stop_live_polling()
