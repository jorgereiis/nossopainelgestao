import os, sys, time, asyncio, threading, logging
from datetime import datetime
import schedule
import socket

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from mensagem_gp_wpp import (
    chamada_funcao_gp_vendas,
    chamada_funcao_gp_futebol,
)
from mensagens_wpp import (
    obter_mensalidades_canceladas,
    executar_envios_agendados,
    run_scheduled_tasks,
    backup_db_sh,
)
from upload_status_wpp import executar_upload_image_from_telegram_com_lock
from comparar_m3u8 import executar_comparar_lista_m3u8_com_lock
from check_canais_dns import executar_check_canais_dns_com_lock
from integracoes.telegram_connection import telegram_connection

################################################
##### CONFIGURAÇÃO DO AGENDADOR DE TAREFAS #####
################################################

# ----------------- Logging do scheduler -----------------
LOG_DIR = "logs/Scheduler"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("Scheduler")
logger.setLevel(logging.DEBUG)
logger.propagate = False

# File handler (para todos os logs)
fh = logging.FileHandler(os.path.join(LOG_DIR, "scheduler.log"), encoding="utf-8")
fh.setLevel(logging.DEBUG)

# Console handler (INFO e superior)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%d-%m-%Y %H:%M:%S")
fh.setFormatter(fmt)
ch.setFormatter(fmt)

if not logger.handlers:
    logger.addHandler(fh)
    logger.addHandler(ch)

# Logger só para arquivo (silencioso no console)
logger_fileonly = logging.getLogger("SchedulerFile")
logger_fileonly.setLevel(logging.DEBUG)
logger_fileonly.propagate = False
if not logger_fileonly.handlers:
    # handler dedicado só para arquivo
    fh_fileonly = logging.FileHandler(os.path.join(LOG_DIR, "scheduler.log"), encoding="utf-8")
    fh_fileonly.setFormatter(fmt)
    fh_fileonly.setLevel(logging.DEBUG)
    logger_fileonly.addHandler(fh_fileonly)

INSTANCE_ID = f"{socket.gethostname()}-{os.getpid()}"
logger.info(f"=" * 60)
logger.info(f"SCHEDULER INICIADO - Instância única")
logger.info(f"ID: {INSTANCE_ID}")
logger.info(f"PID: {os.getpid()}")
logger.info(f"Hostname: {socket.gethostname()}")
logger.info(f"=" * 60)

# --------------- Helpers ---------------
def log_jobs_state():
    """Loga o estado atual dos jobs agendados."""
    jobs = schedule.get_jobs()
    for j in jobs:
        logger.info(f"[JOB] tag={j.tags} next_run={j.next_run} interval={j.interval} unit={j.unit}")

def run_threaded_sync(job_func, *args, **kwargs):
    """Executa o job em uma thread separada, com logs de início/fim no console."""
    def _target():
        try:
            logger.info(f"Iniciando job sync: {job_func.__name__}")
            job_func(*args, **kwargs)
            logger.info(f"Finalizado job sync: {job_func.__name__}")
        except Exception as e:
            logger.exception(f"Falha job sync {job_func.__name__}: {e}")
    t = threading.Thread(target=_target, daemon=True)
    t.start()

def run_threaded_sync_nolog(job_func, *args, **kwargs):
    """Executa o job sem imprimir nada no console; erros vão apenas para o arquivo de log."""
    def _target():
        try:
            job_func(*args, **kwargs)
        except Exception as e:
            logger_fileonly.exception(f"Falha job sync (nolog) {job_func.__name__}: {e}")
    t = threading.Thread(target=_target, daemon=True)
    t.start()

def run_threaded_async(async_coro_func, *args, **kwargs):
    """Executa uma coroutine async em uma thread separada com loop dedicado."""
    def _target():
        try:
            logger.info(f"Iniciando job async: {async_coro_func.__name__}")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(async_coro_func(*args, **kwargs))
            finally:
                loop.run_until_complete(asyncio.sleep(0))
                loop.close()
            logger.info(f"Finalizado job async: {async_coro_func.__name__}")
        except Exception as e:
            logger.exception(f"Falha job async {async_coro_func.__name__}: {e}")
    t = threading.Thread(target=_target, daemon=True)
    t.start()

# --------------- Agendamentos ---------------
# Jobs diários em horários fixos:
schedule.every().day.at("09:05").do(run_threaded_sync, chamada_funcao_gp_futebol).tag("gp_futebol")
schedule.every().day.at("10:00").do(run_threaded_sync, chamada_funcao_gp_vendas).tag("gp_vendas_manha")
schedule.every().day.at("12:00").do(run_threaded_sync, run_scheduled_tasks).tag("run_scheduled_tasks")
schedule.every().day.at("17:00").do(run_threaded_sync, obter_mensalidades_canceladas).tag("mensalidades_canceladas")
schedule.every().day.at("20:00").do(run_threaded_sync, chamada_funcao_gp_vendas).tag("gp_vendas_noite")

# Jobs async com loop dedicado:
schedule.every().day.at("23:00").do(run_threaded_async, telegram_connection).tag("telegram_connection")
schedule.every().day.at("23:50").do(run_threaded_sync, executar_upload_image_from_telegram_com_lock).tag("upload_telegram")

# Jobs em frequência curta:
schedule.every(60).minutes.do(run_threaded_sync, backup_db_sh).tag("backup_db")
schedule.every(1).minutes.do(run_threaded_sync_nolog, executar_envios_agendados).tag("envios_agendados")

logger.info("Scheduler iniciado.")
log_jobs_state()

# Loop principal usando idle_seconds()
while True:
    try:
        schedule.run_pending()
        # Loga heartbeat e próxima execução a cada ~5min
        if int(time.time()) % 300 == 0:
            logger.info("Heartbeat OK")
            log_jobs_state()
        # dorme exatamente o necessário até o próximo job
        sleep_for = schedule.idle_seconds()
        if sleep_for is None or sleep_for < 0:
            sleep_for = 1
        time.sleep(min(sleep_for, 5))  # nunca dorme mais que 5s
    except Exception as e:
        logger.exception(f"Erro no loop do scheduler: {e}")
        time.sleep(2)