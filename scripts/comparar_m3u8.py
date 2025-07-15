import os
import django
import threading
from django.utils.timezone import now, localtime

# Definir a variável de ambiente para o Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Inicializar o ambiente Django para acesso aos modelos
django.setup()

import requests
from datetime import datetime

# Variáveis de ambiente e caminhos de arquivos
URL_M3U8 = os.getenv("URL_M3U8")
NOME_SCRIPT = "COMPARAR M3U8"
LISTA_ATUAL = "archives/M3U8/lista_atual.m3u8"
LISTA_ANTERIOR = "archives/M3U8/lista_anterior.m3u8"
LISTA_NOVOS = "archives/M3U8/novos.txt"
LOG_FILE = "logs/M3U8/comparar_m3u8.log"
THREAD_LOG = "logs/M3U8/comparar_m3u8_thread.log"

# Criar diretórios necessários para salvar os arquivos e logs (se ainda não existirem)
os.makedirs(os.path.dirname(LISTA_ATUAL), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Função para registrar mensagens no arquivo de log principal
def registrar_log(mensagem, log_file):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    print(f"[{timestamp}] [{NOME_SCRIPT}] {mensagem}")
    
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {mensagem}\n")

# Função para baixar a lista M3U8 da URL configurada
def baixar_lista():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(URL_M3U8, headers=headers, timeout=30)
        response.raise_for_status()

        # Salva a lista baixada
        with open(LISTA_ATUAL, "w", encoding="utf-8") as f:
            f.write(response.text)

        registrar_log("[SUCESSO] Lista M3U8 baixada com sucesso.", LOG_FILE)
        return True

    except Exception as e:
        registrar_log(f"[ERRO] Falha ao baixar a lista M3U8: {e}", LOG_FILE)
        return False

# Função auxiliar para extrair linhas com "#EXTINF" da lista M3U8
def extrair_extinf(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        return set(linha.strip() for linha in f if linha.startswith("#EXTINF"))

# Função para comparar listas atual e anterior e detectar conteúdos novos
def comparar_listas():
    if not os.path.exists(LISTA_ANTERIOR):
        # Primeira execução: não há lista anterior para comparar
        registrar_log("[INFO] Nenhuma lista anterior encontrada. Esta será usada como referência inicial.", LOG_FILE)
        os.rename(LISTA_ATUAL, LISTA_ANTERIOR)
        return

    atual = extrair_extinf(LISTA_ATUAL)
    anterior = extrair_extinf(LISTA_ANTERIOR)

    novos = atual - anterior

    if novos:
        # Conteúdos novos foram detectados
        registrar_log(f"[INFO] Novos conteúdos identificados: {len(novos)}", LOG_FILE)

        # Salva os novos conteúdos detectados
        with open(LISTA_NOVOS, "w", encoding="utf-8") as f:
            for item in novos:
                f.write(item + "\n")

        # Atualiza a lista anterior
        os.remove(LISTA_ANTERIOR)
        os.rename(LISTA_ATUAL, LISTA_ANTERIOR)

        registrar_log("[INFO] Lista anterior substituída com a nova.", LOG_FILE)

    else:
        # Nenhuma mudança detectada
        registrar_log("[INFO] Nenhum conteúdo novo encontrado.", LOG_FILE)
        os.remove(LISTA_ATUAL)

# Função principal para baixar e comparar a lista
def executar_comparar_lista_m3u8():
    registrar_log("[INIT] Iniciando comparação de listas M3U8.", LOG_FILE)
    if baixar_lista():
        comparar_listas()

#######################################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO EXECUTAR_COMPARAR_LISTA_M3U8 #####
#######################################################################################

# Lock global para evitar concorrência
executar_comparar_lista_m3u8_lock = threading.Lock()

# Função com proteção de lock para execução segura (útil para agendamentos)
def executar_comparar_lista_m3u8_com_lock():
    if executar_comparar_lista_m3u8_lock.locked():
        # Se já estiver em execução, não executa novamente
        registrar_log("[IGNORADO] Execução ignorada — processo ainda em andamento\n", THREAD_LOG)
        return

    # Executa com lock para garantir exclusividade
    with executar_comparar_lista_m3u8_lock:
        inicio = datetime.now()
        executar_comparar_lista_m3u8()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        registrar_log(f"[END] Tempo de execução: {int(minutos)} min {segundos:.1f} s\n", THREAD_LOG)

##### FIM #####
