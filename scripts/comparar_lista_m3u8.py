import os
import django

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Carregar as configurações do Django
django.setup()

import requests
from datetime import datetime

URL_M3U8 = os.getenv("URL_M3U8")
LISTA_ATUAL = "archives/M3U8/lista_atual.m3u8"
LISTA_ANTERIOR = "archives/M3U8/lista_anterior.m3u8"
LISTA_NOVOS = "archives/M3U8/novos.txt"
DIR_M3U8 = "archives/M3U8"
LOGS_DIR = "logs/M3U8"
LOG_FILE_NAME = "comparar_m3u8.log"

# Criar diretórios
os.makedirs(DIR_M3U8, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

def registrar_log(mensagem):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    caminho_log = os.path.join(LOGS_DIR, LOG_FILE_NAME)

    with open(caminho_log, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {mensagem}\n")

def baixar_lista():
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(URL_M3U8, headers=headers, timeout=10)
        response.raise_for_status()
        with open(LISTA_ATUAL, "w", encoding="utf-8") as f:
            f.write(response.text)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        registrar_log(f"[{timestamp}] [SUCESSO] Lista M3U8 baixada com sucesso.")
        print(f"[{timestamp}] [SUCESSO] [COMPARAR M3U8] Lista M3U8 baixada com sucesso.")
        return True
    
    except Exception as e:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        registrar_log(f"[{timestamp}] [ERRO] Falha ao baixar a lista M3U8: {e}")
        print(f"[{timestamp}] [ERRO] [COMPARAR M3U8] Falha ao baixar a lista M3U8: {e}")
        return False

def extrair_extinf(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        return set(linha.strip() for linha in f if linha.startswith("#EXTINF"))

def comparar_listas():
    if not os.path.exists(LISTA_ANTERIOR):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        registrar_log(f"[{timestamp}] [INFO] Nenhuma lista anterior encontrada. Esta será usada como referência inicial.")
        print(f"[{timestamp}] [INFO] [COMPARAR M3U8] Nenhuma lista anterior encontrada. Esta será usada como referência inicial.")
        os.rename(LISTA_ATUAL, LISTA_ANTERIOR)
        return

    atual = extrair_extinf(LISTA_ATUAL)
    anterior = extrair_extinf(LISTA_ANTERIOR)

    novos = atual - anterior

    if novos:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        registrar_log(f"[{timestamp}] [INFO] Novos conteúdos identificados: {len(novos)}")
        print(f"[{timestamp}] [INFO] [COMPARAR M3U8] Novos conteúdos identificados: {len(novos)}")
        with open(LISTA_NOVOS, "w", encoding="utf-8") as f:
            for item in novos:
                f.write(item + "\n")

        os.remove(LISTA_ANTERIOR)
        os.rename(LISTA_ATUAL, LISTA_ANTERIOR)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        registrar_log(f"[{timestamp}] [INFO] Lista anterior substituída com a nova.")
        print(f"[{timestamp}] [INFO] [COMPARAR M3U8] Lista anterior substituída com a nova.")
    
    else:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        registrar_log(f"[{timestamp}] [INFO] Nenhum conteúdo novo encontrado.")
        print(f"[{timestamp}] [INFO] [COMPARAR M3U8] Nenhum conteúdo novo encontrado.")
        os.remove(LISTA_ATUAL)

def executar_comparar_lista_m3u8():
    if baixar_lista():
        comparar_listas()
