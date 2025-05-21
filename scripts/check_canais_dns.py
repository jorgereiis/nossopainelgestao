import re
import os
import sys
import time
import django
import random
import pickle
import requests
import threading
import unicodedata
from datetime import datetime
from django.db.models import Q, F
from cadastros.utils import get_all_groups
from urllib.parse import urlparse, urlunparse
from django.utils.timezone import now, localtime

# --- Configuração do ambiente Django ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

from cadastros.models import DominiosDNS, SessaoWpp, User

__version__ = "1.0.0"

# --- Constantes globais ---
TIMEOUT = 15
MAX_CANAIS_QTD = 5
MAX_LINHAS_QTD = 10
MAX_TS_CANAIS_QTD = 5
EXTRA_CANAIS_NOME = "Premiere Clubes"
PARAMS_URL = "type=m3u_plus&output=m3u8"

USERNAME = os.getenv("USERNAME_M3U8")
PASSWORD = os.getenv("PASSWORD_M3U8")
URL_API_WPP = os.getenv("URL_API_WPP")
WPP_TELEFONE = os.getenv("MEU_NUM_TIM")
ADM_ENVIA_ALERTAS = os.getenv("NUM_MONITOR")

ERROR_LOG = "logs/error.log"
LOG_FILE = "logs/M3U8/check_canais_dns.log"
THREAD_LOG = "logs/M3U8/check_canais_dns_thread.log"
LISTA_ATUAL = "archives/M3U8/check_lista_atual.m3u8"
LOG_ALERTAS = "logs/M3U8/check_dns_canais_alerta.log"
LOG_FILE_ENVIOS = "logs/M3U8/check_canais_dns_envios.log"
STATUS_SNAPSHOT_FILE = "logs/M3U8/snapshot_dns_status.pkl"

USER_ADMIN = User.objects.get(is_superuser=True)
sessao_wpp = SessaoWpp.objects.get(usuario=USER_ADMIN)
WPP_USER = sessao_wpp.usuario
WPP_TOKEN = sessao_wpp.token

# --- Inicialização de diretórios ---
os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(THREAD_LOG), exist_ok=True)
os.makedirs(os.path.dirname(LISTA_ATUAL), exist_ok=True)
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
def log_com_timestamp(msg, arquivo=LOG_FILE):
    timestamp = localtime().strftime("[%Y-%m-%d %H:%M:%S]")
    if isinstance(msg, (list, tuple)):
        linhas = msg
    else:
        linhas = [msg]
    with open(arquivo, "a", encoding="utf-8") as log:
        for linha in linhas:
            log.write(f"{timestamp}   {linha}\n")

# --- Logger ---
def registrar_log(mensagem, arquivo=LOG_FILE, titulo=None, limitar_linhas=False):
    timestamp = localtime().strftime('%Y-%m-%d %H:%M:%S')
    linhas = mensagem.splitlines() if limitar_linhas else [mensagem]

    # Ajuste a largura do bloco aqui:
    largura_bloco = 42
    ALERTA_TOPO = f"[{timestamp}] ⚠️" + "-" * largura_bloco + "⚠️"
    ALERTA_BASE = ALERTA_TOPO
    AVISO_TEXTO = " O DOMÍNIO PODE DIVERGIR NESSE BLOCO "
    # Centraliza o texto do aviso entre os emojis e completa com traços se quiser
    espacos_laterais = (largura_bloco - len(AVISO_TEXTO)) // 2
    aviso_centralizado = (
        f"[{timestamp}] ⚠️" +
        "-" * espacos_laterais +
        AVISO_TEXTO +
        "-" * (largura_bloco - len(AVISO_TEXTO) - espacos_laterais) +
        "⚠️"
    )

    with open(arquivo, "a", encoding="utf-8") as log:
        if titulo:
            log.write(f"[{timestamp}] 📄 {titulo} (até {MAX_LINHAS_QTD} linhas):\n")
            log.write(aviso_centralizado + "\n")

        for i, linha in enumerate(linhas):
            log.write(f"[{timestamp}]   {linha}\n")
            if limitar_linhas and i >= MAX_LINHAS_QTD:
                log.write(f"[{timestamp}]   ... (demais linhas omitidas)\n")
                break

        if titulo:
            log.write(ALERTA_BASE + "\n")

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
        return url_antigo  # Não é uma URL completa, provavelmente relativo, retorna como está

    try:
        p = urlparse(url_antigo)
        # Monta novo netloc com possível porta (ex: xaea.live:80)
        novo_netloc = urlparse(novo_dominio).netloc or novo_dominio.replace("http://", "").replace("https://", "")
        if ":" in p.netloc:
            if ":" not in novo_netloc:
                # Copia a porta do original, se o novo não tiver
                novo_netloc += ":" + p.netloc.split(":")[1]
        new_url = urlunparse((p.scheme, novo_netloc, p.path, p.params, p.query, p.fragment))
        return new_url
    except Exception:
        return url_antigo
    
# --- Renderiza a barra de progresso no terminal ---
def render_barra_progresso(atual, total, largura=40):
    """
    Exibe uma barra de progresso simples no terminal com base na porcentagem concluída.

    Parâmetros:
        atual (int): valor atual do progresso.
        total (int): valor total para completar.
        largura (int): largura da barra de progresso (default: 40).
    """
    if total == 0:
        return
    porcentagem = atual / total
    preenchido = int(largura * porcentagem)
    barra = '#' * preenchido + '-' * (largura - preenchido)
    print(f"\r🔄 Progresso: |{barra}| {int(porcentagem * 100)}%", end='', flush=True)

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
        } for dominio in queryset
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
    # Garante que o número do ADM tem DDI '55'
    numero = str(adm_envia_alertas)
    if not numero.startswith('55'):
        numero = f'55{numero}'
    telefone_adm = f"{numero}@c.us"  # Ex: '558393329190@c.us'
    
    grupos_admin = []
    for g in grupos:
        participantes = (
            g.get("groupMetadata", {}).get("participants", [])
            or g.get("participants", [])
        )
        # Procura se ADM_ENVIA_ALERTAS é admin em algum grupo
        eh_admin = any(
            p.get("id", {}).get("_serialized") == telefone_adm
            and (p.get("isAdmin") or p.get("isSuperAdmin"))
            for p in participantes
        )
        if eh_admin:
            group_id = g.get("id", {}).get("_serialized")
            nome = g.get("name") or g.get("groupMetadata", {}).get("subject")
            if group_id:
                grupos_admin.append((group_id, nome))
    return grupos_admin




############################################################
#################### FUNÇÕES OPERACIONAIS ##################
############################################################

# --- Obtém a lista M3U de um domínio ou de cache ---
def obter_lista_canais(dominio_url, conteudo_m3u=None):
    """
    Obtém e processa uma lista M3U de canais a partir de um domínio fornecido.

    Parâmetros:
        dominio_url (str): URL base do domínio (ex: http://example.com).
        conteudo_m3u (iterable, opcional): Linhas da M3U já carregadas para evitar nova requisição.

    Retorno:
        list of tuple: Lista de canais no formato [(nome_canal, url_stream), ...].
                       Inclui canais principais e, se configurado, canais extras filtrados por nome.

    Comportamento:
        - Acessa o endpoint M3U com os parâmetros USERNAME e PASSWORD.
        - Valida se a resposta HTTP foi bem-sucedida.
        - Lê o conteúdo retornado linha a linha e identifica os canais.
        - Loga parte do conteúdo da M3U para fins de auditoria.
        - Retorna uma lista com os canais encontrados (até MAX_CANAIS + extras filtrados).
    """
    if not conteudo_m3u:
        # Monta a URL de acesso à lista M3U com autenticação
        url = f"{dominio_url}/get.php?username={USERNAME}&password={PASSWORD}&{PARAMS_URL}"
        registrar_log(f"🌐 Obtendo lista M3U...")
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
            if r.status_code != 200:
                registrar_log(f"❌ [DOWN] Falha HTTP ao obter lista: {r.status_code}")
                return []
            conteudo_m3u = r.iter_lines()
        except requests.RequestException as e:
            registrar_log(f"❌ [DOWN] Falha ao obter lista M3U: {e}")
            return []

    canais_principais, canais_extra = [], []
    nome_canal = None
    buffer_linhas = []

    # Lê linha a linha da M3U (modo bruto) e armazena para processamento posterior
    try:
        for raw_line in conteudo_m3u:
            linha = raw_line.decode(errors="ignore").strip()
            buffer_linhas.append(linha)
    except Exception as e:
        print(f"❌ Erro ao ler linhas M3U ({dominio_url}): {e}")
        print("Erro registrado em 'error.log'. Dando continuidade...")
        registrar_log(f"❌ Erro ao ler linhas M3U ({dominio_url}): {e}", ERROR_LOG)
        return []
    
    # Registra parte do conteúdo da M3U para auditoria
    registrar_log("\n".join(buffer_linhas), titulo="Conteúdo parcial da M3U", limitar_linhas=True)

    # Percorre as linhas da M3U já armazenadas
    for linha in buffer_linhas:
        if linha.startswith("#EXTINF:"):
            # Captura o nome do canal da linha EXTINF
            partes = linha.split(",", 1)
            nome_canal = partes[1] if len(partes) > 1 else "Desconhecido"

        elif linha.startswith("http"):
            # A linha atual é uma URL de stream. Associa ao último nome_canal lido.
            url_correta = substituir_dominio(linha, dominio_url)
            entrada = (nome_canal or "Sem nome", url_correta)

            # Armazena como canal principal (até MAX_CANAIS)
            if len(canais_principais) < MAX_CANAIS_QTD:
                canais_principais.append(entrada)

            # Armazena como canal extra se bater com o filtro definido
            elif EXTRA_CANAIS_NOME.lower() in (nome_canal or "").lower():
                canais_extra.append(entrada)

    # Caso nenhuma entrada válida tenha sido encontrada
    if not canais_principais and not canais_extra:
        registrar_log("⚠️ Lista M3U não contém canais válidos.")

    # Retorna a lista final de canais principais e extras
    return canais_principais + canais_extra
    
# --- Valida domínio e atualiza status no banco ---
def validar_dominio(dominio_obj, data_execucao):
    """
    Valida se o domínio está acessível via HTTP.
    Atualiza os campos do modelo DominiosDNS:
    - data_online / data_offline
    - data_ultima_verificacao
    - ativo (True/False)
    """
    url = f"{dominio_obj.dominio.strip().rstrip('/')}"
    dominio_obj.data_ultima_verificacao = data_execucao
    log_com_timestamp(f"\n🌐 Verificando domínio: {dominio_obj.dominio}")

    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            dominio_obj.data_online = now()
            dominio_obj.ativo = True
            log_com_timestamp("✅ Domínio online, iniciando validação de canais...")
        else:
            raise Exception(f"Status code {r.status_code}")
    except Exception as e:
        dominio_obj.data_offline = now()
        dominio_obj.ativo = False
        log_com_timestamp(f"❌ [DOWN] Domínio inacessível: {dominio_obj.dominio} - {e}")

    dominio_obj.save(update_fields=["data_online", "data_offline", "data_ultima_verificacao", "ativo"])
    return dominio_obj

# --- Valida canais TS registrados no banco para um domínio ---
def validar_canais_ts(dominio, lista_canais):
    """
    Valida canais da lista passada e mostra logs detalhados do processo.
    """
    acessos = {}
    base_url = dominio.dominio.rstrip("/")

    for idx, (nome, url_stream) in enumerate(lista_canais, 1):
        if any(x in (nome or "").upper() for x in ["H265", "4K"]):
            continue

        ts_urls = []
        log_com_timestamp(f"📺 Canal {idx}: {nome}")
        log_com_timestamp(f"🔍 Verificando canal: {nome}")
        log_com_timestamp(f"🔗 URL: {url_stream}")

        try:
            r = requests.get(url_stream, headers=HEADERS, timeout=TIMEOUT)
            log_com_timestamp(f"📥 Status da playlist do canal: {r.status_code}")
            if r.status_code != 200:
                acessos.setdefault(nome, []).append(False)
                continue

            for linha_ts in r.text.splitlines():
                linha_ts = linha_ts.decode(errors="ignore") if isinstance(linha_ts, bytes) else linha_ts
                if ".ts" in linha_ts:
                    if linha_ts.startswith("http"):
                        ts_url = linha_ts
                    else:
                        ts_url = base_url + (linha_ts if linha_ts.startswith("/") else "/" + linha_ts)
                    if ts_url not in ts_urls:
                        ts_urls.append(ts_url)
                if len(ts_urls) >= MAX_TS_CANAIS_QTD:
                    break

            valido = False
            for ts_url in ts_urls:
                log_com_timestamp(f"🎯 Testando segmento TS: {ts_url}")
                try:
                    resp = requests.head(ts_url, headers=HEADERS, timeout=TIMEOUT)
                    log_com_timestamp(f"📶 Status do segmento TS: {resp.status_code}")
                    if resp.status_code == 200:
                        valido = True
                except Exception as e:
                    log_com_timestamp(f"📶 [ERRO] Falha ao testar segmento TS: {ts_url} - {e}")
            if valido:
                log_com_timestamp(f"✅ [UP] Canal '{nome}' online e segmento acessível.\n")
            else:
                log_com_timestamp(f"❌ [DOWN] Canal '{nome}' offline ou segmento inacessível.\n")
            acessos[nome] = [valido]
        except Exception as e:
            log_com_timestamp(f"[ERRO] Falha ao validar canal {nome}: {e}\n")
            acessos.setdefault(nome, []).append(False)

    total = len(acessos)
    total_ok = sum(any(statuses) for statuses in acessos.values())
    if total_ok == total:
        dominio.acesso_canais = "TOTAL"
    elif total_ok == 0:
        dominio.acesso_canais = "INDISPONIVEL"
    else:
        dominio.acesso_canais = "PARCIAL"
    dominio.save(update_fields=["acesso_canais"])
    log_com_timestamp(f"📶 Validação de canais TS finalizada para domínio {dominio.dominio}: {dominio.acesso_canais}")

##################################################
#################### PRINCIPAIS ##################
##################################################

# --- Função principal ---
def main():
    data_execucao = now()
    dominios = DominiosDNS.objects.all().order_by("-dominio")
    total = dominios.count()
    print(f"\n🔎 Iniciando verificação de {total} domínios...")

    data_formatada = localtime().strftime('%d/%m')
    hora_formatada = localtime().strftime('%Hh%M')
    relatorio = [
        "📋 *RELATÓRIO DETALHADO*",
        f"📆 _Data: {data_formatada}_",
        f"⏰ _Hora: {hora_formatada}_",
        "📡 _Monitoramento de DNSes_",
        ""
    ]

    for i, dominio in enumerate(dominios, 1):
        render_barra_progresso(i, total)

        if validar_dominio(dominio, data_execucao):
            lista_canais_url = obter_lista_canais(dominio.dominio)
            if lista_canais_url:
                validar_canais_ts(dominio, lista_canais_url)

    print("\n")
    analisados = DominiosDNS.objects.filter(data_ultima_verificacao=data_execucao)
    status_anterior = {}
    if os.path.exists(STATUS_SNAPSHOT_FILE):
        with open(STATUS_SNAPSHOT_FILE, "rb") as f:
            status_anterior = pickle.load(f)
    status_atual = snapshot_status(analisados)
    houve_mudanca = status_anterior != status_atual

    # Online: ativo, e (data_online > data_offline OU data_offline é None)
    online = analisados.filter(ativo=True).filter(Q(data_offline__isnull=True) | Q(data_online__gt=F('data_offline')))
    relatorio.append("✅ *DOMÍNIOS ONLINE:*")
    print("✅ DOMÍNIOS ONLINE:")
    for d in online:
        if d.acesso_canais == "TOTAL":
            status = "✔️"
            info = "acesso normal aos canais"
        elif d.acesso_canais == "PARCIAL":
            status = "⚠️"
            info = "acesso parcial aos canais, alguns parecem estar indisponíveis ou instáveis"
        else:
            status = "🔻"
            info = "sem acesso aos canais"
        linha = f"🌐 {d.dominio}\n{status} {info}\n"
        print(linha)
        relatorio.append(linha)

    # Offline: não ativo, e (data_offline > data_online OU data_online é None)
    offline = analisados.filter(ativo=False).filter(Q(data_online__isnull=True) | Q(data_offline__gt=F('data_online')))
    relatorio.append("")
    relatorio.append("❌ *DOMÍNIOS OFFLINE:*")
    print("\n❌ DOMÍNIOS OFFLINE:")
    for d in offline:
        ultima = d.data_online.strftime('%d-%b-%Y às %Hh%M') if d.data_online else "Sem registro"
        linha = f"🌐 {d.dominio}\n📆 Última vez online: {ultima}\n"
        print(linha)
        relatorio.append(linha)

    mensagem = "\n".join(relatorio)

    if houve_mudanca:
        if len(mensagem) > 3900:
            blocos = dividir_mensagem_em_blocos(mensagem)
            for bloco in blocos:
                enviar_mensagem(WPP_TELEFONE, bloco, WPP_USER, WPP_TOKEN)
        else:
            enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN)
        log_com_timestamp("[OK] Relatório geral enviado via WhatsApp.")
    else:
        log_com_timestamp("[INFO] Nenhuma alteração detectada. Relatório não enviado.")

    with open(STATUS_SNAPSHOT_FILE, "wb") as f:
        pickle.dump(status_atual, f)

    print("\n⏳ Verificação concluída. Aguardando próxima execução...")

def alerta_disponibilidade_dns_canal():
    timestamp = localtime().strftime('%d/%m %Hh%M')
    registrar_log(f"🔍 [INÍCIO - {timestamp}] Verificação crítica de domínios iniciada.", LOG_ALERTAS)
    print(f"🔍 [{timestamp}] Iniciando verificação crítica de domínios...")

    # Obtém todos os grupos e extrai IDs dos grupos para envio
    grupos = get_all_groups(WPP_TOKEN)
    grupos_envio = get_ids_grupos_envio(grupos, ADM_ENVIA_ALERTAS)

    # Pega todos os domínios do sistema (online e offline)
    dominios = DominiosDNS.objects.all().order_by("dominio")
    for dominio in dominios:
        online = False

        # 1. Tenta validar o domínio (reutilizando sua função principal)
        try:
            r = requests.get(dominio.dominio.strip().rstrip('/'), headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                online = True
        except Exception as e:
            online = False

        # FLUXO: domínio responde (ficou online)
        if online:
            # Se ficou online agora e estava inativo/offline antes:
            if (not dominio.ativo) and (
                (dominio.data_offline and dominio.data_online and dominio.data_offline > dominio.data_online) or
                (dominio.data_offline and not dominio.data_online)
            ):
                mensagem = (
                    f"✅ *DNS ONLINE*\n"
                    f"🌐 *Domínio:* `{dominio.dominio}`\n"
                    f"🕓 *Horário:* {timestamp}\n"
                    f"📺 *Servidor:* {dominio.servidor}\n\n"
                    f"🔔 _O domínio voltou a responder normalmente!_"
                )
                if grupos_envio:
                    # Envia mensagem para grupos, se houver ID válido obtido
                    for group_id, group_name in grupos_envio:
                        enviar_mensagem(group_id, mensagem, WPP_USER, WPP_TOKEN, is_group=True)
                        registrar_log(f"🚨 [GRUPO] ALERTA enviado para '{group_name}': DNS ONLINE {dominio.dominio}", LOG_ALERTAS)

                if WPP_TELEFONE:
                    # Envia mensagem para contato privado, se houver número definido
                    enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN, is_group=False)
                    registrar_log(f"🚨 [PRIVADO] ALERTA enviado: DNS ONLINE {dominio.dominio}", LOG_ALERTAS)

            # Atualiza status para online
            dominio.ativo = True
            dominio.data_online = now()
            dominio.data_ultima_verificacao = now()
            # Aqui você pode chamar a validação dos canais, se quiser incluir
            lista_canais_url = obter_lista_canais(dominio.dominio)
            if lista_canais_url:
                validar_canais_ts(dominio, lista_canais_url)
            dominio.save(update_fields=["ativo", "data_online", "data_ultima_verificacao", "acesso_canais"])
            registrar_log(f"✅ DNS online: {dominio.dominio}", LOG_ALERTAS)

        # FLUXO: domínio NÃO responde (ficou offline)
        else:
            # Se ficou offline agora e estava ativo/online antes:
            if dominio.ativo and (
                (dominio.data_online and dominio.data_offline and dominio.data_online > dominio.data_offline) or
                (dominio.data_online and not dominio.data_offline)
            ):
                mensagem = (
                    f"❌ *DNS OFFLINE*\n"
                    f"🌐 *Domínio:* `{dominio.dominio}`\n"
                    f"🕓 *Horário:* {timestamp}\n"
                    f"📺 *Servidor:* {dominio.servidor}\n\n"
                    f"⚠️ _O domínio parou de responder._\n⚠️ _Caso esteja em uso, alguns clientes poderão ficar sem acesso temporariamente!_"
                )
                
                if grupos_envio:
                    # Envia mensagem para grupos, se houver ID válido obtido
                    for group_id, group_name in grupos_envio:
                        enviar_mensagem(group_id, mensagem, WPP_USER, WPP_TOKEN, is_group=True)
                        registrar_log(f"🚨 [GRUPO] ALERTA enviado para '{group_name}': DNS OFFLINE {dominio.dominio}", LOG_ALERTAS)

                if WPP_TELEFONE:
                    # Envia mensagem para contato privado, se houver número definido
                    enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN, is_group=False)
                    registrar_log(f"🚨 [PRIVADO] ALERTA enviado: DNS OFFLINE {dominio.dominio}", LOG_ALERTAS)

            # Atualiza status para offline
            dominio.ativo = False
            dominio.data_offline = now()
            dominio.acesso_canais = "INDISPONIVEL"
            dominio.data_ultima_verificacao = now()
            dominio.save(update_fields=["ativo", "data_offline", "data_ultima_verificacao", "acesso_canais"])
            registrar_log(f"❌ DNS offline: {dominio.dominio}", LOG_ALERTAS)

    registrar_log(f"✅ [FIM - {localtime().strftime('%d/%m %Hh%M')}] Verificação crítica concluída.\n", LOG_ALERTAS)
    print("✅ Verificação crítica finalizada. Aguardando 5min...\n")

##################################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO PROCESSAR_NOVOS_TITULOS #####
##################################################################################

executar_main_lock = threading.Lock()
executar_alerta_disponibilidade_dns_canal_lock = threading.Lock()

def executar_check_canais_dns_com_lock_1():

    if executar_main_lock.locked():
        log_com_timestamp("[IGNORADO] Execução da MAIN ignorada — processo ainda em andamento.", THREAD_LOG)
        return

    with executar_main_lock:
        inicio = datetime.now()
        main()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        log_com_timestamp(f"[END] Tempo de execução da MAIN: {int(minutos)} min {segundos:.1f} s", THREAD_LOG)

def executar_check_canais_dns_com_lock_2():

    if executar_alerta_disponibilidade_dns_canal_lock.locked():
        log_com_timestamp("[IGNORADO] Execução de DISPONIBILIDADE_DNS_CANAIS ignorada — processo ainda em andamento.", THREAD_LOG)
        return

    with executar_alerta_disponibilidade_dns_canal_lock:
        inicio = datetime.now()
        alerta_disponibilidade_dns_canal()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        log_com_timestamp(f"[END] Tempo de execução da DISPONIBILIDADE_DNS_CANAIS: {int(minutos)} min {segundos:.1f} s", THREAD_LOG)
##### FIM #####
