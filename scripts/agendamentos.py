import os
import sys
import django

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carregar as configurações do Django
django.setup()

import time
import asyncio
import schedule
import threading
from mensagem_gp_wpp import (
    chamada_funcao_gp_vendas
)
from mensagens_wpp import (
    run_scheduled_tasks,
    executar_envios_agendados,
    obter_mensalidades_canceladas,
    backup_db_sh,
)
from processar_novos_titulos_m3u8 import executar_processar_novos_titulos_com_lock
from upload_status_wpp import executar_upload_image_from_telegram_com_lock
from comparar_m3u8 import executar_comparar_lista_m3u8_com_lock
from check_canais_dns import executar_check_canais_dns_com_lock
from upload_status_wpp import executar_upload_status_com_lock
from integracoes.telegram_connection import telegram_connection

################################################
##### CONFIGURAÇÃO DO AGENDADOR DE TAREFAS #####
################################################

# Threading para executar os jobs em paralelo
def run_threaded(job):
    job_thread = threading.Thread(target=job)
    job_thread.daemon = True # Permite que o programa feche mesmo com threads ativas
    job_thread.start()

# Função para executar a tarefa assíncrona de agendamento
def run_telegram_connection():
    asyncio.run(telegram_connection())

# Agendar a execução das tarefas em horários específicos
schedule.every().day.at("08:00").do(
    run_threaded, chamada_funcao_gp_vendas
)
schedule.every().day.at("12:00").do(
    run_threaded, run_scheduled_tasks
)
schedule.every().day.at("17:00").do(
    run_threaded, obter_mensalidades_canceladas
)
schedule.every().day.at("20:00").do(
    run_threaded, chamada_funcao_gp_vendas
)
schedule.every().day.at("23:00").do(
    run_threaded, run_telegram_connection
)
schedule.every().day.at("23:50").do(
    run_threaded, executar_upload_image_from_telegram_com_lock
)
"""schedule.every().day.at("00:15").do(
    run_threaded, executar_comparar_lista_m3u8_com_lock
)
schedule.every().day.at("00:25").do(
    run_threaded, executar_processar_novos_titulos_com_lock
)
schedule.every().day.at("00:35").do(
    run_threaded, executar_upload_status_com_lock
)"""

# Agendar a execução das tarefas em minutos específicos
schedule.every(60).minutes.do(
    run_threaded, backup_db_sh
)
"""schedule.every(10).minutes.do(
    run_threaded, executar_check_canais_dns_com_lock
)"""
schedule.every(1).minutes.do(
    run_threaded, executar_envios_agendados
)

# Executa imediatamente ao iniciar o servidor
#run_threaded(run_scheduled_tasks)

# Executar indefinidamente
while True:
    schedule.run_pending()
    time.sleep(5)

