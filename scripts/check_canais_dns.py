import re
import os
import sys
import json
import time
import django
import random
import pickle
import requests
import threading
import traceback
import unicodedata
from datetime import datetime
from collections import Counter
from urllib.parse import urljoin
from django.db.models import Q, F
from cadastros.utils import get_all_groups
from urllib.parse import urlparse, urlunparse
from django.utils.timezone import now, localtime

# --- Configuração do ambiente Django ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

from cadastros.models import DominiosDNS, SessaoWpp, User

__version__ = "2.1.0"

# --- Constantes globais ---
TIMEOUT = 15
MAX_CANAIS_QTD = 5
MAX_LINHAS_QTD = 10
MAX_TS_CANAIS_QTD = 5
EXTRA_CANAIS_NOME = "Premiere Clubes"
PARAMS_URL = "type=m3u_plus&output=m3u8"

USERNAME = json.loads(os.getenv("USERNAME_M3U8"))
PASSWORD = json.loads(os.getenv("PASSWORD_M3U8"))
URL_API_WPP = os.getenv("URL_API_WPP")
WPP_TELEFONE = os.getenv("MEU_NUM_TIM")
ADM_ENVIA_ALERTAS = os.getenv("NUM_MONITOR")

ERROR_LOG = "logs/error.log"
LOG_FILE = "logs/M3U8/check_canais_dns.log"
LOG_ALERTAS = "logs/M3U8/check_canais_dns.log"
THREAD_LOG = "logs/M3U8/check_canais_dns_thread.log"
LOG_FILE_ENVIOS = "logs/M3U8/check_canais_dns_envios.log"
STATUS_SNAPSHOT_FILE = "logs/M3U8/snapshot_dns_status.pkl"
LOG_FILE_GRUPOS_WHATSAPP = "logs/M3U8/check_canais_dns_grupos_wpp.log"

USER_ADMIN = User.objects.get(is_superuser=True)
sessao_wpp = SessaoWpp.objects.get(usuario=USER_ADMIN)
WPP_USER = sessao_wpp.usuario
WPP_TOKEN = sessao_wpp.token

# --- Inicialização de diretórios ---
os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(THREAD_LOG), exist_ok=True)
os.makedirs(os.path.dirname(LOG_ALERTAS), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE_ENVIOS), exist_ok=True)
os.makedirs(os.path.dirname(STATUS_SNAPSHOT_FILE), exist_ok=True)

# --- Verificação de variáveis obrigatórias ---
if not all([USERNAME, PASSWORD, URL_API_WPP, WPP_TELEFONE, WPP_USER, WPP_TOKEN]):
    print("❌ Variáveis obrigatórias não definidas.")
    sys.exit(1)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive"
}

############################################################
#################### FUNÇÕES AUXILIARES ####################
############################################################

# --- Logger ---
def registrar_log(mensagem, arquivo=LOG_FILE, titulo_destacado=None, titulo_m3u_parcial=None, titulo_inicio_fim=None, limitar_linhas=False):
    """
    Escreve mensagem no log, opcionalmente com título, bloco de alerta e limitação de linhas.
    """
    timestamp = localtime().strftime('%Y-%m-%d %H:%M:%S')
    linhas = str(mensagem).splitlines()
    if limitar_linhas:
        linhas = linhas[:MAX_LINHAS_QTD]

    try:
        with open(arquivo, "a", encoding="utf-8") as log:
            if titulo_destacado:
                log.write(f"[{timestamp}] {titulo_destacado}\n")
            if titulo_m3u_parcial:
                log.write(f"[{timestamp}] 📄 {titulo_m3u_parcial} (até {MAX_LINHAS_QTD} linhas):\n")
            for i, linha in enumerate(linhas):
                log.write(f"[{timestamp}]   {linha}\n")
            if limitar_linhas and len(mensagem.splitlines()) > MAX_LINHAS_QTD:
                log.write(f"[{timestamp}] ... (demais linhas omitidas)\n")
            if titulo_inicio_fim:
                log.write(f"[{timestamp}]{titulo_inicio_fim}\n")

    except Exception as e:
        import sys
        print(f"Erro ao gravar log: {e}", file=sys.stderr)


# --- Envio de mensagens via WPPConnect ---
def enviar_mensagem(telefone, mensagem, usuario, token, is_group=False):
    url = f"{URL_API_WPP}/{usuario}/send-message"
    headers_envio = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    body = {'phone': telefone, 'message': mensagem, 'isGroup': is_group}
    delay_envio = random.randint(5, 15)

    try:
        time.sleep(delay_envio)
        response = requests.post(url, json=body, headers=headers_envio, timeout=30)
        response.raise_for_status()
        registrar_log(f"[OK] Mensagem enviada para contato informado.", LOG_FILE_ENVIOS)
    except Exception as e:
        registrar_log(f"[ERRO] Envio para contato falhou => {e}", LOG_FILE_ENVIOS)


def substituir_dominio(url_antigo, novo_dominio):
    """
    Substitui o domínio da url_antigo por novo_dominio, mantendo path/params/query.
    """
    if not url_antigo.startswith("http"):
        return url_antigo  # Não é uma URL completa, provavelmente relativo

    try:
        p = urlparse(url_antigo)
        novo_p = urlparse(novo_dominio if novo_dominio.startswith("http") else f"http://{novo_dominio}")
        novo_netloc = novo_p.netloc or novo_dominio.replace("http://", "").replace("https://", "")
        
        # Mantém a porta original se novo_dominio não especifica
        original_port = p.netloc.split(":")[1] if ":" in p.netloc else ""
        if ":" not in novo_netloc and original_port:
            novo_netloc += f":{original_port}"

        # Usa o mesmo esquema da url_antigo
        new_url = urlunparse((p.scheme, novo_netloc, p.path, p.params, p.query, p.fragment))
        return new_url
    except Exception:
        return url_antigo


# --- Gera um snapshot de status atual dos domínios ---
def snapshot_status(queryset):
    """
    Gera uma estrutura simplificada de status dos domínios com base no queryset.
    Utilizado para comparação com snapshots anteriores e detecção de mudanças.

    Retorna:
        dict: Mapeia domínio => {data_online, data_offline, acesso_canais}
    """
    return {
        dominio.dominio: {
            "data_online": dominio.data_online.replace(microsecond=0) if dominio.data_online else None,
            "data_offline": dominio.data_offline.replace(microsecond=0) if dominio.data_offline else None,
            "acesso_canais": dominio.acesso_canais
        } for dominio in queryset.order_by('dominio')
    }


# --- Divide mensagens longas em blocos menores ---
def dividir_mensagem_em_blocos(mensagem, max_tamanho=3900):
    """
    Divide uma mensagem longa em blocos menores para envio via WhatsApp.
    Cada bloco respeita o tamanho máximo permitido pela API (padrão: 3900).

    Parâmetros:
        mensagem (str): Texto a ser dividido.
        max_tamanho (int): Tamanho máximo de cada bloco (default: 3900).

    Retorna:
        list[str]: Lista de blocos prontos para envio.
    """
    blocos = []
    bloco_atual = ""
    for linha in mensagem.splitlines(keepends=True):
        if len(bloco_atual) + len(linha) > max_tamanho:
            blocos.append(bloco_atual)
            bloco_atual = ""
        bloco_atual += linha
    if bloco_atual:
        blocos.append(bloco_atual)
    return blocos


# --- Extrai ID dos grupos do WhatsApp para envio das notificações ---
def get_ids_grupos_envio(grupos, adm_envia_alertas):
    """
    Retorna lista de grupos do WhatsApp em que o ADM é admin.
    Cada item: (group_id, nome)
    """
    numero = str(adm_envia_alertas)
    if not numero.startswith('55'):
        numero = f'55{numero}'
    telefone_adm = f"{numero}@c.us"

    grupos_admin = []
    for g in grupos:
        participantes = (
            g.get("groupMetadata", {}).get("participants", [])
            or g.get("participants", [])
        )
        eh_admin = any(
            p.get("id", {}).get("_serialized") == telefone_adm and (
                bool(p.get("isAdmin")) or bool(p.get("isSuperAdmin"))
            )
            for p in participantes
        )
        if eh_admin:
            group_id = g.get("id", {}).get("_serialized")
            nome = g.get("name") or g.get("groupMetadata", {}).get("subject") or "Grupo sem nome"
            if group_id:
                grupos_admin.append((group_id, nome))
                registrar_log(f"Grupo autorizado: {nome} ({group_id})", LOG_FILE_GRUPOS_WHATSAPP)
    return grupos_admin


############################################################
#################### FUNÇÕES OPERACIONAIS ##################
############################################################

# --- Obtém a lista M3U de um domínio ---
def obter_lista_canais(dominio_url, nome_servidor, conteudo_m3u=None):
    """
    Obtém e processa uma lista M3U de canais a partir de um domínio fornecido, utilizando as credenciais adequadas ao servidor.

    Parâmetros:
        dominio_url (str): URL base do domínio (ex: http://example.com).
        nome_servidor (str): Nome do servidor associado ao domínio, usado para selecionar USERNAME/PASSWORD.
        conteudo_m3u (iterable, opcional): Linhas da M3U já carregadas para evitar nova requisição.

    Retorno:
        list of tuple: Lista de canais no formato [(nome_canal, url_stream), ...].
                       Inclui canais principais e, se configurado, canais extras filtrados por nome.
    """

    inicio = time.time()
    registrar_log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    registrar_log(f"🟢 INICIANDO processamento da lista M3U do domínio: {dominio_url} (servidor: {nome_servidor})")

    # Obtém credenciais de acordo com o servidor informado
    nome_servidor_padrao = nome_servidor.strip().upper()
    username = USERNAME.get(nome_servidor_padrao)
    password = PASSWORD.get(nome_servidor_padrao)

    if not username or not password:
        registrar_log(f"❌ [ERRO] Não foi possível obter credenciais para o servidor '{nome_servidor}'. Verifique o dicionário de credenciais.")
        registrar_log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        return {
            "success": False,
            "error": "Não foi possível acessar uma ou mais credenciais do servidor.",
            "servidor": nome_servidor_padrao,
            "username": username,
            "password": password
        }

    if not conteudo_m3u:
        url = f"{dominio_url}/get.php?username={username}&password={password}&{PARAMS_URL}"
        registrar_log(f"🌐 Requisitando lista M3U: {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True, allow_redirects=True)
            registrar_log(f"🔎 Status HTTP: {r.status_code}")
            if r.status_code != 200:
                registrar_log(f"❌ [DOWN] Falha HTTP ao obter lista ({url}): {r.status_code}")
                registrar_log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                return {
                    "success": False,
                    "error": f"Falha HTTP ao obter lista M3U.",
                    "dominio": url,
                    "status_code": r.status_code,
                    "servidor": nome_servidor_padrao
                }
            conteudo_m3u = r.iter_lines()
        except requests.RequestException as e:
            registrar_log(f"❌ [DOWN] Erro grave ao obter lista M3U ({url}): {e}")
            registrar_log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            return {
                "success": False,
                "error": f"Erro grave ao obter lista M3U: {e}",
                "dominio": url,
                "servidor": nome_servidor_padrao
            }

    canais_principais, canais_extra = [], []
    buffer_linhas = []
    nome_canal = None
    total_linhas = 0

    try:
        for raw_line in conteudo_m3u:
            linha = raw_line.decode(errors="ignore").strip()
            buffer_linhas.append(linha)
            total_linhas += 1
    except Exception as e:
        registrar_log(f"❌ Erro ao ler linhas M3U ({dominio_url}): {e}", ERROR_LOG)
        registrar_log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        return {
            "success": False,
            "error": f"Erro ao ler linhas M3U: {e}",
            "dominio": dominio_url,
            "servidor": nome_servidor_padrao
        }

    registrar_log(f"📝 Total de linhas lidas da M3U: {total_linhas}")
    log_preview = "\n".join(buffer_linhas[:30])
    registrar_log(log_preview, titulo_m3u_parcial="Conteúdo parcial da M3U", limitar_linhas=True)
    registrar_log(f"🔍 Iniciando parsing das linhas para extrair canais...")

    canais_vistos = set()
    urls_vistas = set()
    duplicados_nome = []
    duplicados_url = []

    for idx, linha in enumerate(buffer_linhas):
        if linha.startswith("#EXTINF:"):
            partes = linha.split(",", 1)
            nome_canal = partes[1].strip() if len(partes) > 1 else "Desconhecido"

        elif linha.startswith("http"):
            url_correta = substituir_dominio(linha, dominio_url)
            entrada = (nome_canal or "Sem nome", url_correta)

            # Checa duplicidade de nome de canal
            if nome_canal in canais_vistos:
                duplicados_nome.append(nome_canal)
            else:
                canais_vistos.add(nome_canal)

            # Checa duplicidade de URL
            if url_correta in urls_vistas:
                duplicados_url.append(url_correta)
            else:
                urls_vistas.add(url_correta)

            # Armazena como canal principal (até MAX_CANAIS)
            if len(canais_principais) < MAX_CANAIS_QTD:
                canais_principais.append(entrada)
                registrar_log(f"✔️ Adicionado canal principal: {nome_canal} -> {url_correta}")
            
            # Armazena como canal extra se bater com o filtro definido
            elif EXTRA_CANAIS_NOME.lower() in (nome_canal or "").lower():
                canais_extra.append(entrada)
                registrar_log(f"➕ Adicionado canal extra (filtro): {nome_canal} -> {url_correta}")

    if not canais_principais and not canais_extra:
        registrar_log("⚠️ Lista M3U não contém canais válidos.")

    registrar_log(f"🔢 Total canais principais: {len(canais_principais)} | Extras: {len(canais_extra)}")
    registrar_log(f"🗂️ Total canais únicos por nome: {len(canais_vistos)}")
    registrar_log(f"🔗 Total URLs únicas: {len(urls_vistas)}")

    tempo_total = time.time() - inicio
    registrar_log(f"⏱️ Tempo total de processamento da M3U: {tempo_total:.2f}s")
    registrar_log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    return {"lista_m3u": canais_principais + canais_extra,}


# --- Valida domínio e atualiza status no banco ---
def validar_dominio_servidor(dominio):
    """
    Valida se o domínio está publicado/acessível via HTTP (qualquer status code!).
    """

    url = f"{dominio.strip().rstrip('/')}"
    registrar_log("", titulo_destacado=f"🌍 Verificando domínio: {dominio}")

    tempo_inicio = time.time()
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        tempo_resposta = time.time() - tempo_inicio
        online = True
        registrar_log(
            f"✅ Domínio respondeu HTTP {r.status_code} ({r.reason}) — publicado e acessível)"
        )
    except Exception as e:
        tempo_resposta = time.time() - tempo_inicio
        online = False
        tb = traceback.format_exc()
        registrar_log(
            f"❌ [DOWN] Erro ao acessar domínio {dominio} ({type(e).__name__}): {e} (tempo: {tempo_resposta:.2f}s)\n{tb}"
        )

    return online


# --- Validação de domínio através da URL M3U ---
def validar_url_m3u(dominio, nome_servidor):
    """
    Valida se o domínio está publicado/acessível para obter lista M3U.
    Retorna um dicionário informando o sucesso ou erro da validação.
    """
    nome_servidor_padrao = nome_servidor.strip().upper()
    username = USERNAME.get(nome_servidor_padrao)
    password = PASSWORD.get(nome_servidor_padrao)
    url = f"{dominio.strip().rstrip('/')}/get.php?username={username}&password={password}&{PARAMS_URL}"

    registrar_log("", titulo_destacado=f"🌍 Verificando domínio: {dominio} (servidor: {nome_servidor_padrao})")

    tempo_inicio = time.time()
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        tempo_resposta = time.time() - tempo_inicio

        registrar_log(
            f"✅ Domínio respondeu HTTP {r.status_code} ({r.reason}) — publicado e acessível (tempo: {tempo_resposta:.2f}s)"
        )

        # Opcional: Validar se conteúdo é realmente M3U (ex: r.text.lstrip().startswith("#EXTM3U"))
        return {
            "success": True,
            "status_code": r.status_code,
            "reason": r.reason,
            "tempo_resposta": tempo_resposta,
            "url": url,
            "servidor": nome_servidor_padrao
        }

    except Exception as e:
        tempo_resposta = time.time() - tempo_inicio
        tb = traceback.format_exc()
        registrar_log(
            f"❌ [DOWN] Erro ao acessar domínio {dominio} ({type(e).__name__}): {e} (tempo: {tempo_resposta:.2f}s)\n{tb}"
        )
        return {
            "success": False,
            "error": str(e),
            "traceback": tb,
            "url": url,
            "servidor": nome_servidor_padrao
        }


# --- Valida acesso aos canais TS para cada domínio ---
def validar_canais_ts(dominio, lista_canais):
    """
    Valida canais da lista passada e mostra logs detalhados do processo.
    """
    acessos = {}
    canais_ok = []
    canais_erro = []
    base_url = dominio.dominio.rstrip("/")
    inicio = time.time()

    registrar_log("", titulo_destacado=f"🚩 INICIANDO validação de canais TS para domínio: {dominio.dominio}")
    registrar_log(f"Total de canais a validar: {len(lista_canais)}")

    for idx, (nome, url_stream) in enumerate(lista_canais, 1):
        if any(x in (nome or "").upper() for x in ["H265", "4K"]):
            registrar_log(f"⏭️ Ignorando canal {idx}: {nome} (motivo: filtro H265/4K)")
            continue

        ts_urls = []
        canal_valido = False
        canal_erros = []
        registrar_log(f"─────────────────────────────────────────────")
        registrar_log("", titulo_destacado=f"📺 Canal {idx}: {nome}")
        registrar_log(f"🔍 Verificando canal: {nome}")
        registrar_log(f"🔗 URL: {url_stream}")

        try:
            r = requests.get(url_stream, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            m3u8_final_url = r.url
            registrar_log(f"📥 Status da playlist do canal: {r.status_code}")
            if r.status_code != 200:
                acessos[nome] = False
                registrar_log(f"❌ [DOWN] Playlist do canal {nome} retornou status {r.status_code}")
                canais_erro.append((nome, f"Playlist status {r.status_code}"))
                continue

            for linha_ts in r.text.splitlines():
                linha_ts = linha_ts.decode(errors="ignore") if isinstance(linha_ts, bytes) else linha_ts
                if ".ts" in linha_ts:
                    ts_url = linha_ts if linha_ts.startswith("http") else urljoin(m3u8_final_url, linha_ts)
                    #ts_url = linha_ts if linha_ts.startswith("http") else urljoin(base_url + "/", linha_ts)
                    if ts_url not in ts_urls:
                        ts_urls.append(ts_url)
                if len(ts_urls) >= MAX_TS_CANAIS_QTD:
                    break

            if not ts_urls:
                acessos[nome] = False
                registrar_log(f"❌ [DOWN] Nenhum segmento TS encontrado para o canal {nome}.")
                canais_erro.append((nome, "Sem segmentos TS"))
                continue

            ts_sucesso = []
            ts_falha = []
            for ts_url in ts_urls:
                registrar_log(f"🎯 Testando segmento TS: {ts_url}")
                try:
                    resp = requests.head(ts_url, headers=HEADERS, timeout=TIMEOUT)
                    registrar_log(f"📶 Status do segmento TS: {resp.status_code}")
                    if resp.status_code == 200:
                        canal_valido = True
                        ts_sucesso.append(ts_url)
                    else:
                        ts_falha.append((ts_url, resp.status_code))
                except Exception as e:
                    ts_falha.append((ts_url, f"Erro: {e}"))
                    registrar_log(f"📶 [ERRO] Falha ao testar segmento TS: {ts_url} - {e}")

            if canal_valido:
                registrar_log(f"✅ [UP] Canal '{nome}' online. Segmentos acessíveis: {len(ts_sucesso)}/{len(ts_urls)}")
                canais_ok.append(nome)
                if ts_falha:
                    registrar_log(f"⚠️ Segmentos TS com erro: {ts_falha}")
            else:
                registrar_log(f"❌ [DOWN] Canal '{nome}' offline ou nenhum segmento TS acessível.")
                canais_erro.append((nome, f"Falha nos TS: {ts_falha}"))
            acessos[nome] = canal_valido

        except Exception as e:
            registrar_log(f"[ERRO] Falha ao validar canal {nome}: {e}")
            acessos[nome] = False
            canais_erro.append((nome, f"Erro: {e}"))

    total = len(acessos)
    total_ok = sum(1 for status in acessos.values() if status)
    if total_ok == total and total > 0:
        dominio.acesso_canais = "TOTAL"
    elif total_ok == 0:
        dominio.acesso_canais = "INDISPONIVEL"
    else:
        dominio.acesso_canais = "PARCIAL"
    dominio.save(update_fields=["acesso_canais"])

    tempo_total = time.time() - inicio

    registrar_log(f"─────────────────────────────────────────────")
    registrar_log("", titulo_destacado=f"📶 Validação finalizada para domínio {dominio.dominio}: {dominio.acesso_canais} | Tempo: {tempo_total:.2f}s")
    registrar_log("", titulo_destacado=f"🟢 Canais OK ({len(canais_ok)}): {', '.join(canais_ok) if canais_ok else 'Nenhum'}")
    if canais_erro:
        registrar_log("", titulo_destacado=f"🔴 Canais com erro ({len(canais_erro)}):")
        for nome, motivo in canais_erro:
            registrar_log(f"    - {nome}: {motivo}")
    registrar_log(f"─────────────────────────────────────────────")


##################################################
#################### PRINCIPAIS ##################
##################################################

def check_dns_canais():
    time.sleep(random.randint(10, 20))
    registrar_log("", titulo_inicio_fim=f"[INIT] Checagem de status de domínios DNS.")
    print(f"[{localtime().strftime('%Y-%m-%d %H:%M:%S')}] [INIT] Checagem de status de domínios DNS.")
    inicio_global = time.time()

    # Obtém todos os grupos e extrai IDs dos grupos desejados para envio
    grupos = get_all_groups(WPP_TOKEN)
    grupos_envio = get_ids_grupos_envio(grupos, ADM_ENVIA_ALERTAS)

    # Pega todos os domínios do sistema (online e offline) ordenados por Servidor
    dominios = DominiosDNS.objects.all().order_by("servidor")
    for dominio in dominios:
        hora_now = localtime()
        status_anterior = dominio.ativo
        dominio.data_ultima_verificacao = hora_now
        
        # 1. Validação de status do domínio
        # - Verifica status de acesso à lista e aos canais através do domínio válido;
        lista_dict = obter_lista_canais(dominio.dominio, dominio.servidor.nome)
        servidor = lista_dict.get("servidor", "N/A")
        username = lista_dict.get("username", "N/A")
        password = lista_dict.get("password", "N/A")
        dominio_url = lista_dict.get("dominio", "N/A")
        dominio_online = lista_dict.get("success", True)
        status_code = lista_dict.get("status_code", "N/A")
        error_msg = lista_dict.get("error", "Erro não informado")
        lista_m3u = lista_dict.get("lista_m3u", None)

        if dominio_online:
            # 2. Verifica see mudou de status OFFLINE para ONLINE agora:
            if (not status_anterior) and (
                (dominio.data_offline and dominio.data_online and dominio.data_offline > dominio.data_online) or
                (dominio.data_offline and not dominio.data_online)
            ):
                mensagem = (
                    f"✅ *DNS ONLINE*\n"
                    f"🌐 *Domínio:*\n`{dominio.dominio}`\n"
                    f"🕓 *Horário:* {hora_now.strftime('%Y/%m %Hh%M')}\n"
                    f"📺 *Servidor:* {dominio.servidor}\n\n"
                    f"🔔 _O domínio voltou a responder normalmente!_"
                )
                if grupos_envio:
                    # Envia notificação para grupos no WPP, se houver ID válido obtido;
                    for group_id, group_name in grupos_envio:
                        enviar_mensagem(group_id, mensagem, WPP_USER, WPP_TOKEN, is_group=True)
                        registrar_log(f"🚨 [GRUPO] ALERTA enviado para '{group_name}': DNS ONLINE {dominio.dominio}", LOG_FILE)

                if WPP_TELEFONE:
                    # Envia mensagem para contato privado no WPP, se houver número definido;
                    enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN, is_group=False)
                    registrar_log(f"🚨 [PRIVADO] ALERTA enviado: DNS ONLINE {dominio.dominio}", LOG_FILE)

                # Atualiza status para online;
                dominio.ativo = True
                dominio.data_online = hora_now
                dominio.data_envio_alerta = hora_now
                dominio.save(update_fields=["ativo", "data_online", "data_ultima_verificacao", "data_envio_alerta"])
            else:
                # Se o status anterior não mudou, então continua online;
                # Apenas registra a data da verificação;
                dominio.save(update_fields=["data_ultima_verificacao"])

            # Apesar de estar online, valida se possui acesso aos canais;
            # - Tipos dos status: TOTAL, PARCIAL ou INDISPONÍVEL;
            validar_canais_ts(dominio, lista_m3u)

            # Registra log;
            registrar_log(f"✅ DNS online: {dominio.dominio}", LOG_FILE)

        else:
            # 3. Se mudou de status ONLINE para OFFLINE agora:
            if (status_anterior and (
                (dominio.data_online and dominio.data_offline and dominio.data_online > dominio.data_offline) or
                (dominio.data_online and not dominio.data_offline))
            ):
                mensagem = (
                    f"❌ *DNS OFFLINE*\n"
                    f"🌐 *Domínio:*\n`{dominio.dominio}`\n"
                    f"🕓 *Horário:* {localtime().strftime('%Y/%m %Hh%M')}\n"
                    f"📺 *Servidor:* {dominio.servidor}\n\n"
                    f"⚠️ _O domínio parou de responder._\n⚠️ _Caso esteja em uso, alguns clientes poderão ficar sem acesso temporariamente!_"
                )
                
                if grupos_envio:
                    for group_id, group_name in grupos_envio:
                        enviar_mensagem(group_id, mensagem, WPP_USER, WPP_TOKEN, is_group=True)
                        registrar_log(f"🚨 [GRUPO] ALERTA enviado para '{group_name}': DNS OFFLINE {dominio.dominio}", LOG_FILE)

                if WPP_TELEFONE:
                    enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN, is_group=False)
                    registrar_log(f"🚨 [PRIVADO] ALERTA enviado: DNS OFFLINE {dominio.dominio}", LOG_FILE)

                # Atualiza status para offline
                dominio.ativo = False
                dominio.data_offline = hora_now
                dominio.data_envio_alerta = hora_now
                dominio.acesso_canais = "INDISPONIVEL"
                dominio.save(update_fields=["ativo", "data_offline", "data_ultima_verificacao", "acesso_canais"])
            elif not status_anterior:
                # Se já estava offline, só registra a verificação
                dominio.save(update_fields=["data_ultima_verificacao"])
                registrar_log(f"❌ DNS offline: {dominio.dominio}", LOG_FILE)
            if status_code != "N/A":
                # Se o erro retornado por 'obter_lista_canais()' não teve relação com o status da requição,
                # Então o erro obtido não tem relação com a requisição;
                # Apenas registra em log;
                log_msg = (
                    f"[{localtime().strftime('%Y-%m-%d %H:%M:%S')}]\n"
                    f"[ERROR] {error_msg}\n"
                    f"[SERVIDOR] {servidor}\n"
                    f"[DOMINIO] {dominio_url}\n"
                    f"[USERNAME] {username}\n"
                    f"[PASSWORD] {str(password)[:3] + '***' if password != 'N/A' else password}\n"
                    f"[HTTP_CODE] {status_code}\n"
                    f"[RAW] {repr(lista_m3u)}"
                )
                registrar_log(log_msg)

    fim_global = time.time()
    registrar_log("", titulo_inicio_fim=f"[END] Checagem de status de domínios DNS concluída em: {fim_global-inicio_global:.2f}s\n")
    print(f"[{localtime().strftime('%Y-%m-%d %H:%M:%S')}] [END] Checagem de status de domínios DNS concluída em: {fim_global-inicio_global:.2f}s\n")

##################################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO PROCESSAR_NOVOS_TITULOS #####
##################################################################################

executar_check_dns_canais_lock = threading.Lock()

def executar_check_canais_dns_com_lock():

    if executar_check_dns_canais_lock.locked():
        registrar_log("[IGNORADO] Execução de CHECK_DNS_CANAIS ignorada — processo ainda em andamento.", THREAD_LOG)
        return

    with executar_check_dns_canais_lock:
        inicio = localtime()
        check_dns_canais()
        fim = localtime()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        registrar_log(f"[END] Tempo de execução da CHECK_DNS_CANAIS: {int(minutos)} min {segundos:.1f} s", THREAD_LOG)
##### FIM #####
