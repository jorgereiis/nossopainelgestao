import os
import django
import threading
import requests
from datetime import datetime
from django.utils.timezone import now, localtime

# Definir a variável de ambiente para o Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Inicializar o ambiente Django para acesso aos modelos
django.setup()

from cadastros.services.logging_config import get_m3u8_logger

# Configuração do logger centralizado com rotação automática
logger = get_m3u8_logger()

# Variáveis de ambiente e caminhos de arquivos
URL_M3U8 = os.getenv("URL_M3U8")
LISTA_ATUAL = "archives/M3U8/lista_atual.m3u8"
LISTA_ANTERIOR = "archives/M3U8/lista_anterior.m3u8"
LISTA_NOVOS = "archives/M3U8/novos.txt"

# Criar diretórios necessários para salvar os arquivos (se ainda não existirem)
os.makedirs(os.path.dirname(LISTA_ATUAL), exist_ok=True)

# Função para baixar a lista M3U8 da URL configurada
def baixar_lista():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(URL_M3U8, headers=headers, timeout=30)
        response.raise_for_status()

        # Salva a lista baixada
        with open(LISTA_ATUAL, "w", encoding="utf-8") as f:
            f.write(response.text)

        logger.info("Lista M3U8 baixada com sucesso")
        return True

    except Exception as e:
        logger.error("Falha ao baixar lista M3U8 | erro=%s", str(e))
        return False

# Função auxiliar para extrair linhas com "#EXTINF" da lista M3U8
def extrair_extinf(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        return set(linha.strip() for linha in f if linha.startswith("#EXTINF"))

# Função para comparar listas atual e anterior e detectar conteúdos novos
def comparar_listas():
    if not os.path.exists(LISTA_ANTERIOR):
        # Primeira execução: não há lista anterior para comparar
        logger.info("Nenhuma lista anterior encontrada | acao=criando_referencia_inicial")
        os.rename(LISTA_ATUAL, LISTA_ANTERIOR)
        return

    atual = extrair_extinf(LISTA_ATUAL)
    anterior = extrair_extinf(LISTA_ANTERIOR)

    novos = atual - anterior

    if novos:
        # Conteúdos novos foram detectados
        logger.info("Novos conteúdos identificados | quantidade=%d", len(novos))

        # Salva os novos conteúdos detectados
        with open(LISTA_NOVOS, "w", encoding="utf-8") as f:
            for item in novos:
                f.write(item + "\n")

        # Atualiza a lista anterior
        os.remove(LISTA_ANTERIOR)
        os.rename(LISTA_ATUAL, LISTA_ANTERIOR)

        logger.info("Lista anterior substituída com a nova")

    else:
        # Nenhuma mudança detectada
        logger.info("Nenhum conteúdo novo encontrado")
        os.remove(LISTA_ATUAL)

# Função principal para baixar e comparar a lista
def executar_comparar_lista_m3u8():
    logger.info("Iniciando comparação de listas M3U8")
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
        logger.warning("Execução ignorada | motivo=processo_em_andamento funcao=executar_comparar_lista_m3u8")
        return

    # Executa com lock para garantir exclusividade
    with executar_comparar_lista_m3u8_lock:
        inicio = datetime.now()
        logger.info("Iniciando execução com lock | funcao=executar_comparar_lista_m3u8")
        executar_comparar_lista_m3u8()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        logger.info("Execução finalizada | funcao=executar_comparar_lista_m3u8 duracao=%dmin %.1fs", int(minutos), segundos)

##### FIM #####
