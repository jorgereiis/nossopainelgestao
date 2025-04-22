import os
import django

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Carregar as configurações do Django
django.setup()

# Importar o modelo ConteudoM3U8
from cadastros.models import ConteudoM3U8, User
from datetime import datetime
import threading
import requests
import re
import os
import difflib

# Carregar as variáveis de ambiente do arquivo .env
URL_M3U8 = os.getenv("URL_M3U8")
TMDB_API_URL = os.getenv("TMDB_API_URL")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_IMAGE_URL_W500 = os.getenv("TMDB_IMAGE_URL_W500")


###############################################################
##### FUNÇÃO PARA MONITORAR NOVOS CONTEÚDOS EM LISTA M3U8 #####
###############################################################

# --- Normaliza o título removendo caracteres especiais e espaços extras
def normalizar_titulo(titulo):
    titulo = titulo.lower()
    titulo = re.sub(r"[^a-z0-9\s]", "", titulo)  # remove pontuação
    titulo = titulo.replace("&", "e").replace("/", " ")
    return re.sub(r"\s+", " ", titulo).strip()

# --- Verifica similaridade entre dois títulos
def titulos_sao_semelhantes(titulo1, titulo2, limiar=0.8):
    t1 = normalizar_titulo(titulo1)
    t2 = normalizar_titulo(titulo2)
    return difflib.SequenceMatcher(None, t1, t2).ratio() >= limiar

# --- Consulta título no TMDb e retorna dados estruturados
def buscar_capa_por_titulo(titulo_original):
    temporada = episodio = ano = None

    # Detectar temporada e episódio
    ep_match = re.search(r"S(\d{2})E(\d{2})", titulo_original, flags=re.IGNORECASE)
    if ep_match:
        temporada = int(ep_match.group(1))
        episodio = int(ep_match.group(2))

    # Detectar ano (1999, 2023, etc.)
    ano_match = re.search(r"\b(19|20)\d{2}\b", titulo_original)
    if ano_match:
        ano = int(ano_match.group())

    # Limpar título
    titulo_limpo = re.sub(r"\[[^\]]*\]", "", titulo_original)
    titulo_limpo = re.sub(r"S\d{2}E\d{2}", "", titulo_limpo, flags=re.IGNORECASE)
    titulo_limpo = re.sub(r"\b(4k|fhd|uhd|hd|1080p|720p)\b", "", titulo_limpo, flags=re.IGNORECASE)
    titulo_limpo = re.sub(r"\(?\b(19|20)\d{2}\)?", "", titulo_limpo).strip()

    # Logs
    log_dir = "logs/TMDb"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "busca-capas.log")

    # Parâmetros da API
    params = {
        "api_key": TMDB_API_KEY,
        "query": titulo_limpo,
        "language": "pt-BR"
    }

    if ano:
        params["year"] = ano
        params["first_air_date_year"] = ano

    try:
        response = requests.get(TMDB_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("results"):
            primeiro = data["results"][0]
            tipo = primeiro.get("media_type")
            nome_tmdb = primeiro.get("title") or primeiro.get("name")
            original_tmdb = primeiro.get("original_title") or primeiro.get("original_name")

            # Verificar ano retornado
            data_api = primeiro.get("release_date") or primeiro.get("first_air_date")
            ano_api = None
            if data_api:
                ano_api = int(data_api[:4])

            # Se o ano bater e houver título razoável, aceita
            if ano and ano_api and ano == ano_api:
                if nome_tmdb or original_tmdb:
                    return {
                        "nome": nome_tmdb,
                        "capa": f"{TMDB_IMAGE_URL_W500}{primeiro['poster_path']}" if primeiro.get("poster_path") else None,
                        "tipo": tipo,
                        "temporada": temporada,
                        "episodio": episodio,
                        "ano": ano
                    }

            # Verificação por similaridade com nome ou original_name
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

            # Caso rejeite, registra como conflito
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(
                    f"[{timestamp}] [CONFLITO] '{titulo_original}' -> '{nome_tmdb}' "
                    f"(não confere com '{titulo_limpo}', ano: {ano}, retornado: {ano_api})\n"
                )
            return None

    except Exception as e:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] [ERRO] '{titulo_original}' => {str(e)}\n")

    # Se não houve resultados
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"[{timestamp}] [NAO ENCONTRADO] '{titulo_original}' -> '{titulo_limpo}'"
            f"{' | S%02dE%02d' % (temporada, episodio) if temporada and episodio else ''}\n"
        )

    return None

# --- Função principal de monitoramento
def processar_novos_titulos():
    caminho_novos = "archives/M3U8/novos.txt"
    log_dir = "logs/M3U8"
    log_novos = os.path.join(log_dir, "novos-conteudos.log")
    log_erros = os.path.join(log_dir, "error.log")
    os.makedirs(log_dir, exist_ok=True)

    usuario_env = os.getenv("USER_SESSION_WPP")
    if not usuario_env:
        print("[ERRO] Variável USER_SESSION_WPP não definida.")
        return

    try:
        usuario = User.objects.get(username=usuario_env)
    except User.DoesNotExist:
        print(f"[ERRO] Usuário '{usuario_env}' não encontrado no sistema.")
        return

    if not os.path.exists(caminho_novos):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [INFO] [PROCESSAR_NOVOS_TITULOS] Nenhum conteúdo novo para processar.")
        return

    with open(caminho_novos, encoding="utf-8") as f:
        linhas = [linha.strip() for linha in f if linha.strip()]

    if not linhas:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [INFO] [PROCESSAR_NOVOS_TITULOS] Arquivo 'novos.txt' está vazio.")
        os.remove(caminho_novos)
        return

    novos = 0

    for linha in linhas:
        nome_match = re.search(r'tvg-name="([^"]+)"', linha)
        grupo_match = re.search(r'group-title="([^"]+)"', linha)

        if not (nome_match and grupo_match):
            continue

        grupo = grupo_match.group(1).lower()
        if any(excluido in grupo for excluido in ["canais", "[xxx]", "programas de tv", "cursos"]):
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
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                with open(log_novos, "a", encoding="utf-8") as log_file:
                    log_file.write(f"[{timestamp}] [NOVO] {dados['nome']} | T{dados.get('temporada')}E{dados.get('episodio')} | {dados['capa']}\n")
                novos += 1

        except Exception as e:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(log_erros, "a", encoding="utf-8") as erro_file:
                erro_file.write(f"[{timestamp}] [ERRO] [PROCESSAR_NOVOS_TITULOS] {nome_m3u8} => {str(e)}\n")

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_novos, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] [TOTAL DE NOVOS CONTEÚDOS] {novos}\n\n")

    os.remove(caminho_novos)
##### FIM #####


###############################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO PROCESSAR_NOVOS_TITULOS #####
###############################################################################

processar_novos_titulos_lock = threading.Lock()
def processar_novos_titulos_com_lock():
    log_dir = "logs/M3U8"
    log_erros = os.path.join(log_dir, "thread_processar-novos-titulos.log")
    os.makedirs(log_dir, exist_ok=True)

    if processar_novos_titulos_lock.locked():
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_erros, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] [IGNORADO] Execução ignorada — processo ainda em andamento\n")
        return

    with processar_novos_titulos_lock:
        inicio = datetime.now()
        processar_novos_titulos()
        fim = datetime.now()
        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60
        with open(log_erros, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{fim.strftime('%Y-%m-%d %H:%M:%S')}] [CONCLUÍDO] Tempo de execução: {int(minutos)} min {segundos:.1f} s\n")
##### FIM #####
