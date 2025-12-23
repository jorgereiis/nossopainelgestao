import os, sys, time, asyncio, threading, logging, fcntl, signal, atexit
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
    executar_envios_agendados_com_lock,
    run_scheduled_tasks_from_db,
    backup_db_sh,
)
from upload_status_wpp import executar_upload_image_from_telegram_com_lock
from integracoes.telegram_connection import telegram_connection
from jampabet_live_matches import run_check_and_poll as jampabet_check_live_matches

################################################
##### PROTEÇÃO CONTRA MÚLTIPLAS INSTÂNCIAS #####
################################################

LOCK_FILE = "/tmp/scheduler_agendamentos.lock"
lock_file_handle = None

def acquire_scheduler_lock():
    """
    Adquire um lock de sistema para garantir que apenas uma instância do scheduler execute.
    Retorna o file handle se bem-sucedido, ou None se já existe outra instância.
    """
    global lock_file_handle
    try:
        lock_file_handle = open(LOCK_FILE, 'w')
        # Tenta adquirir lock exclusivo não-bloqueante
        fcntl.flock(lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Escreve PID no arquivo para debug
        lock_file_handle.write(f"{os.getpid()}\n")
        lock_file_handle.flush()
        return lock_file_handle
    except IOError:
        # Outra instância já está rodando
        return None
    except Exception as e:
        # Usa print aqui pois logger ainda não está configurado neste ponto
        import sys
        print(f"[ERRO] Falha ao adquirir lock: {e}", file=sys.stderr)
        return None

def release_scheduler_lock():
    """Libera o lock e remove o arquivo."""
    global lock_file_handle
    if lock_file_handle:
        try:
            fcntl.flock(lock_file_handle.fileno(), fcntl.LOCK_UN)
            lock_file_handle.close()
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception as e:
            print(f"[AVISO] Erro ao liberar lock: {e}")

def signal_handler(signum, frame):
    """Handler para sinais de terminação."""
    print(f"\n[SIGNAL] Recebido sinal {signum}. Encerrando graciosamente...")
    release_scheduler_lock()
    sys.exit(0)

# Registra handlers de sinal e cleanup
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
atexit.register(release_scheduler_lock)

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
def is_job_ativo(job_nome):
    """
    Verifica se o job está ativo na ConfiguracaoAgendamento.
    Retorna True se ativo ou se não encontrar configuração (fallback).
    """
    try:
        from nossopainel.models import ConfiguracaoAgendamento
        config = ConfiguracaoAgendamento.objects.filter(nome=job_nome).first()
        if config is None:
            # Se não existe configuração, permite execução (fallback)
            return True
        return config.ativo
    except Exception as e:
        logger_fileonly.warning(f"Erro ao verificar status do job {job_nome}: {e}")
        # Em caso de erro, permite execução (fallback seguro)
        return True


def get_job_horario(job_nome, default_horario):
    """
    Obtém o horário de execução do job do banco de dados.
    Retorna o horário configurado ou o default se não encontrar.
    """
    try:
        from nossopainel.models import ConfiguracaoAgendamento
        config = ConfiguracaoAgendamento.objects.filter(nome=job_nome).first()
        if config and config.horario and ':' in config.horario and len(config.horario) == 5:
            return config.horario
        return default_horario
    except Exception as e:
        logger_fileonly.warning(f"Erro ao obter horário do job {job_nome}: {e}")
        return default_horario


def job_wrapper(job_nome, job_func, *args, **kwargs):
    """
    Wrapper que verifica se o job está ativo antes de executar.
    """
    if not is_job_ativo(job_nome):
        logger_fileonly.debug(f"Job {job_nome} está INATIVO - pulando execução")
        return
    job_func(*args, **kwargs)


async def async_job_wrapper(job_nome, async_job_func, *args, **kwargs):
    """
    Wrapper async que verifica se o job está ativo antes de executar.
    """
    if not is_job_ativo(job_nome):
        logger_fileonly.debug(f"Job async {job_nome} está INATIVO - pulando execução")
        return
    await async_job_func(*args, **kwargs)


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
# Busca horários do banco de dados (com fallback para horário padrão)
horario_gp_futebol = get_job_horario("gp_futebol", "08:00")
horario_gp_vendas = get_job_horario("gp_vendas", "10:00")
horario_mensalidades_canceladas = get_job_horario("mensalidades_canceladas", "17:00")
horario_telegram_connection = get_job_horario("telegram_connection", "23:00")
horario_upload_telegram = get_job_horario("upload_telegram", "23:50")

logger.info(f"Horários configurados:")
logger.info(f"  - GP Futebol: {horario_gp_futebol}")
logger.info(f"  - GP Vendas: {horario_gp_vendas}")
logger.info(f"  - Mensalidades Canceladas: {horario_mensalidades_canceladas}")
logger.info(f"  - Telegram Connection: {horario_telegram_connection}")
logger.info(f"  - Upload Telegram: {horario_upload_telegram}")

# Jobs diários em horários fixos (com verificação de status no banco):
schedule.every().day.at(horario_gp_futebol).do(
    run_threaded_sync, job_wrapper, "gp_futebol", chamada_funcao_gp_futebol
).tag("gp_futebol")

schedule.every().day.at(horario_gp_vendas).do(
    run_threaded_sync, job_wrapper, "gp_vendas", chamada_funcao_gp_vendas
).tag("gp_vendas")

schedule.every().day.at(horario_mensalidades_canceladas).do(
    run_threaded_sync, job_wrapper, "mensalidades_canceladas", obter_mensalidades_canceladas
).tag("mensalidades_canceladas")

# Jobs async com loop dedicado:
schedule.every().day.at(horario_telegram_connection).do(
    run_threaded_async, async_job_wrapper, "telegram_connection", telegram_connection
).tag("telegram_connection")

schedule.every().day.at(horario_upload_telegram).do(
    run_threaded_sync, job_wrapper, "upload_telegram", executar_upload_image_from_telegram_com_lock
).tag("upload_telegram")

# Jobs em frequência curta:
schedule.every(60).minutes.do(
    run_threaded_sync, job_wrapper, "backup_db", backup_db_sh
).tag("backup_db")

schedule.every(1).minutes.do(
    run_threaded_sync_nolog, job_wrapper, "envios_vencimento", executar_envios_agendados_com_lock
).tag("envios_agendados")

schedule.every(1).minutes.do(
    run_threaded_sync_nolog, job_wrapper, "tarefas_envio_db", run_scheduled_tasks_from_db
).tag("tarefas_envio_db")

# JampaBet - Verificacao de partidas ao vivo (a cada 1 minuto) - SEM wrapper, job será removido
schedule.every(1).minutes.do(run_threaded_sync_nolog, jampabet_check_live_matches).tag("jampabet_live")

# --------------- Verificação de Lock de Instância Única ---------------
if not acquire_scheduler_lock():
    # Logger já está configurado neste ponto, mas usa sys.stderr para garantir visibilidade
    logger.critical("BLOQUEADO: Outra instância do scheduler já está em execução.")
    logger.info("Verifique o arquivo %s para detalhes.", LOCK_FILE)
    sys.exit(0)

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