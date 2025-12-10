import os
import django
import threading
import requests
import re
import difflib
from datetime import datetime
from django.utils.timezone import localtime

# Configuração do ambiente Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

# Modelos Django
from nossopainel.models import ConteudoM3U8, User

# Variáveis de ambiente e caminhos utilizados no script
NOME_SCRIPT = "PROCESSAR NOVOS TITULOS"
URL_M3U8 = os.getenv("URL_M3U8")
TMDB_API_URL = os.getenv("TMDB_API_URL")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_IMAGE_URL_W500 = os.getenv("TMDB_IMAGE_URL_W500")
LISTA_NOVOS = "archives/M3U8/novos.txt"
TMDB_LOG_FILE = "logs/TMDb/busca-capas.log"
NOVOS_CONTEUDOS_LOG = "logs/M3U8/novos-conteudos.log"
PROCESSAR_NOVOS_TITULOS_LOG = "logs/M3U8/processar_novos_titulos.log"
THREAD_LOG = "logs/M3U8/processar_novos_titulos_thread.log"

# Garantir que os diretórios de log e arquivos existam
os.makedirs(os.path.dirname(TMDB_LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(NOVOS_CONTEUDOS_LOG), exist_ok=True)
os.makedirs(os.path.dirname(LISTA_NOVOS), exist_ok=True)

# Função para registrar mensagens no arquivo de log principal
def registrar_log(mensagem, log_file):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    print(f"[{timestamp}] [{NOME_SCRIPT}] {mensagem}")
    
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {mensagem}\n")

# --- Funções auxiliares ---

def normalizar_titulo(titulo):
    """Remove acentuação, símbolos e espaços extras do título."""
    titulo = titulo.lower()
    titulo = re.sub(r"[^a-z0-9\s]", "", titulo)
    titulo = titulo.replace("&", "e").replace("/", " ")
    return re.sub(r"\s+", " ", titulo).strip()

def titulos_sao_semelhantes(titulo1, titulo2, limiar=0.8):
    """Verifica a similaridade textual entre dois títulos."""
    t1 = normalizar_titulo(titulo1)
    t2 = normalizar_titulo(titulo2)
    return difflib.SequenceMatcher(None, t1, t2).ratio() >= limiar

def buscar_capa_por_titulo(titulo_original):
    """Consulta o título na API do TMDb e retorna metadados estruturados."""
    temporada = episodio = ano = None
    ep_match = re.search(r"S(\d{2})E(\d{2})", titulo_original, flags=re.IGNORECASE)
    if ep_match:
        temporada = int(ep_match.group(1))
        episodio = int(ep_match.group(2))

    ano_match = re.search(r"\b(19|20)\d{2}\b", titulo_original)
    if ano_match:
        ano = int(ano_match.group())

    titulo_limpo = re.sub(r"\[[^\]]*\]", "", titulo_original)
    titulo_limpo = re.sub(r"S\d{2}E\d{2}", "", titulo_limpo, flags=re.IGNORECASE)
    titulo_limpo = re.sub(r"\b(4k|fhd|uhd|hd|1080p|720p)\b", "", titulo_limpo, flags=re.IGNORECASE)
    titulo_limpo = re.sub(r"\(?\b(19|20)\d{2}\)?", "", titulo_limpo).strip()

    params = {
        "api_key": TMDB_API_KEY,
        "query": titulo_limpo,
        "language": "pt-BR"
    }
    if ano:
        params["year"] = ano
        params["first_air_date_year"] = ano

    try:
        response = requests.get(TMDB_API_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("results"):
            primeiro = data["results"][0]
            tipo = primeiro.get("media_type")
            nome_tmdb = primeiro.get("title") or primeiro.get("name")
            original_tmdb = primeiro.get("original_title") or primeiro.get("original_name")
            data_api = primeiro.get("release_date") or primeiro.get("first_air_date")
            ano_api = int(data_api[:4]) if data_api else None

            if ano and ano_api and ano == ano_api and (nome_tmdb or original_tmdb):
                return {
                    "nome": nome_tmdb,
                    "capa": f"{TMDB_IMAGE_URL_W500}{primeiro['poster_path']}" if primeiro.get("poster_path") else None,
                    "tipo": tipo,
                    "temporada": temporada,
                    "episodio": episodio,
                    "ano": ano
                }

            if titulos_sao_semelhantes(titulo_limpo, nome_tmdb) or (
                original_tmdb and titulos_sao_semelhantes(titulo_limpo, original_tmdb)
            ):
                return {
                    "nome": nome_tmdb,
                    "capa": f"{TMDB_IMAGE_URL_W500}{primeiro['poster_path']}" if primeiro.get("poster_path") else None,
                    "tipo": tipo,
                    "temporada": temporada,
                    "episodio": episodio,
                    "ano": ano
                }

            with open(TMDB_LOG_FILE, "a", encoding="utf-8") as log_file:
                log_file.write(f"[{datetime.now()}] [CONFLITO] '{titulo_original}' -> '{nome_tmdb}' (ano: {ano}, retornado: {ano_api})\n")

    except Exception as e:
        with open(TMDB_LOG_FILE, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{datetime.now()}] [ERRO] '{titulo_original}' => {str(e)}\n")

    with open(TMDB_LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"[{datetime.now()}] [NAO ENCONTRADO] '{titulo_original}' -> '{titulo_limpo}'"
            f"{' | S%02dE%02d' % (temporada, episodio) if temporada and episodio else ''}\n"
        )
    return None

# --- Função principal para processar os novos títulos ---

def processar_novos_titulos():
    """Lê e processa os títulos da lista de novos conteúdos M3U8."""
    if not os.path.exists(LISTA_NOVOS):
        registrar_log("Nenhum conteúdo novo para processar.", PROCESSAR_NOVOS_TITULOS_LOG)
        return

    usuario_env = os.getenv("USER_SESSION_WPP")
    if not usuario_env:
        registrar_log("[ERRO] Variável USER_SESSION_WPP não definida.", PROCESSAR_NOVOS_TITULOS_LOG)
        return

    try:
        usuario = User.objects.get(username=usuario_env)
    except User.DoesNotExist:
        registrar_log(f"[ERRO] Usuário '{usuario_env}' não encontrado.", PROCESSAR_NOVOS_TITULOS_LOG)
        return

    with open(LISTA_NOVOS, encoding="utf-8") as f:
        linhas = [linha.strip() for linha in f if linha.strip()]

    if not linhas:
        registrar_log("[INFO] Arquivo 'novos.txt' está vazio.", PROCESSAR_NOVOS_TITULOS_LOG)
        os.remove(LISTA_NOVOS)
        return

    novos = 0
    for linha in linhas:
        nome_match = re.search(r'tvg-name="([^"]+)"', linha)
        grupo_match = re.search(r'group-title="([^"]+)"', linha)

        if not (nome_match and grupo_match):
            continue

        grupo = grupo_match.group(1).lower()
        if any(x in grupo for x in ["canais", "[xxx]", "programas de tv", "cursos"]):
            continue
        if "filme" not in grupo and "serie" not in grupo:
            continue

        nome_m3u8 = nome_match.group(1)
        try:
            dados = buscar_capa_por_titulo(nome_m3u8)
            if not dados:
                continue

            if not ConteudoM3U8.objects.filter(
                nome=dados["nome"],
                capa=dados["capa"],
                temporada=dados.get("temporada"),
                episodio=dados.get("episodio"),
                usuario=usuario
            ).exists():
                ConteudoM3U8.objects.create(
                    nome=dados["nome"],
                    capa=dados["capa"],
                    temporada=dados.get("temporada"),
                    episodio=dados.get("episodio"),
                    usuario=usuario
                )
                with open(NOVOS_CONTEUDOS_LOG, "a", encoding="utf-8") as log_file:
                    log_file.write(f"[{datetime.now()}] [NOVO] {dados['nome']} | T{dados.get('temporada')}E{dados.get('episodio')} | {dados['capa']}\n")
                novos += 1

        except Exception as e:
                registrar_log(f"[ERRO] {nome_m3u8} => {str(e)}", PROCESSAR_NOVOS_TITULOS_LOG)

    
    registrar_log(f"[TOTAL DE NOVOS CONTEÚDOS] {novos}", PROCESSAR_NOVOS_TITULOS_LOG)

    os.remove(LISTA_NOVOS)

# --- Função para executar o processamento de novos títulos
def executar_processar_novos_titulos():
    registrar_log("[INIT] Iniciando processamento de novos títulos...", PROCESSAR_NOVOS_TITULOS_LOG)
    processar_novos_titulos()
##### FIM #####


##################################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO PROCESSAR_NOVOS_TITULOS #####
##################################################################################

executar_processar_novos_titulos_lock = threading.Lock()

def executar_processar_novos_titulos_com_lock():
    os.makedirs(os.path.dirname(THREAD_LOG), exist_ok=True)

    if executar_processar_novos_titulos_lock.locked():
        registrar_log("[IGNORADO] Execução ignorada — processo ainda em andamento.", THREAD_LOG)
        return

    with executar_processar_novos_titulos_lock:
        inicio = datetime.now()
        executar_processar_novos_titulos()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        registrar_log(f"[END] Tempo de execução: {int(minutos)} min {segundos:.1f} s", THREAD_LOG)
##### FIM #####
