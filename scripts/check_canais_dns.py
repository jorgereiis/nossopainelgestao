import os
import sys
import json
import time
import django
import random
import requests
import threading
from cadastros.utils import get_all_groups
from django.utils.timezone import localtime

# --- Configuração do ambiente Django ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

from cadastros.models import DominiosDNS, SessaoWpp, User

__version__ = "2.2.0"

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
LOG_FILE = "logs/DNS/consultas_dns.log"
THREAD_LOG = "logs/DNS/run_dns_thread.log"
STATUS_SNAPSHOT_FILE = "logs/DNS/snapshots_dns.pkl"
LOG_FILE_ENVIOS = "logs/DNS/envio_pv_notificacoes.log"
LOG_FILE_GRUPOS_WHATSAPP = "logs/DNS/envio_gp_notificacoes.log"

USER_ADMIN = User.objects.get(is_superuser=True)
sessao_wpp = SessaoWpp.objects.get(usuario=USER_ADMIN)
WPP_USER = sessao_wpp.usuario
WPP_TOKEN = sessao_wpp.token

# --- Inicialização de diretórios ---
os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(THREAD_LOG), exist_ok=True)
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
                log.write(f"[{timestamp}]   📄 {titulo_m3u_parcial} (até {MAX_LINHAS_QTD} linhas):\n")
            for i, linha in enumerate(linhas):
                log.write(f"[{timestamp}]   {linha}\n")
            if limitar_linhas and len(mensagem.splitlines()) > MAX_LINHAS_QTD:
                log.write(f"[{timestamp}]   ... (demais linhas omitidas)\n")
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

# --- Valida status do domínio ---
def validar_dominio(dominio, nome_servidor):
    """
    Valida domínio e credenciais do servidor realizando múltiplas tentativas na URL da lista M3U.
    Retorna dicionário detalhado de status e tempos para uso em check_dns_canais().

    Parâmetros:
        dominio (str): URL do domínio a ser testado.
        nome_servidor (str): Nome do servidor para escolher credenciais.

    Retorno:
        dict: {
            'success': True/False,
            'online': True/False,
            'tempos': [...],
            'status_codes': [...],
            'tentativas': int,
            'url_testada': str,
            'erro': str (se houver)
        }
    """

    erro = None
    tempos = []
    tentativas = 5
    status_codes = []
    timeout = (8, 15) # 8 segundos para conectar, 15 segundos para obter resposta
    respostas_ok = 0
    respostas_ok_min = 4 # qtd min de resposta com sucesso
    resposta_tempo_max = 15 # tempo de resposta max

    nome_servidor_padrao = nome_servidor.strip().upper()
    username = USERNAME.get(nome_servidor_padrao)
    password = PASSWORD.get(nome_servidor_padrao)

    url = f"{dominio.rstrip('/')}/get.php?username={username}&password={password}&type=m3u_plus&output=m3u8"
    registrar_log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    registrar_log("", titulo_destacado=f"🌍 INICIANDO: {dominio} ({nome_servidor})")

    tempo_inicio = time.time()
    for i in range(tentativas):
        inicio = time.time()
        encontrou_extinf = False
        linhas_lidas = 0
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
            status_codes.append(r.status_code)
            for linha in r.iter_lines(decode_unicode=False):
                linhas_lidas += 1
                if b"#EXTINF" in linha:
                    encontrou_extinf = True
                    break
                if linhas_lidas >= 5:
                    break
            tempo = time.time() - inicio
            tempos.append(tempo)
            registrar_log(f"🕓 Tentativa {i+1}: status {r.status_code}, tempo da requisição {tempo:.2f}s, #EXTINF encontrado: {encontrou_extinf}")

            if r.status_code == 200 and encontrou_extinf and tempo < resposta_tempo_max:
                respostas_ok += 1

        except requests.exceptions.ConnectTimeout:
            tempos.append(None)
            status_codes.append('ConnectTimeout')
            registrar_log(f"⚠️ Tentativa {i+1}: TIMEOUT na conexão (5s)")
        except requests.exceptions.ReadTimeout:
            tempos.append(None)
            status_codes.append('ReadTimeout')
            registrar_log(f"⚠️ Tentativa {i+1}: TIMEOUT ao ler resposta (10s)")
        except requests.exceptions.Timeout:
            tempos.append(None)
            status_codes.append('Timeout')
            registrar_log(f"⚠️ Tentativa {i+1}: TIMEOUT geral")
        except Exception as e:
            tempos.append(None)
            status_codes.append(str(e))
            registrar_log(f"❌ Tentativa {i+1}: Erro inesperado: {repr(e)}")
            erro = str(e)

    tempo_total = time.time() - tempo_inicio
    online = respostas_ok >= respostas_ok_min
    registrar_log(f"🔁 Tentativas bem-sucedidas: {respostas_ok}/{tentativas}")
    registrar_log(f"⏱️ Tempo total: {tempo_total:.2f}s")
    if online:
        registrar_log("", titulo_destacado=f"✅ ONLINE!!")
    else:
        registrar_log("", titulo_destacado=f"🔻 OFFLINE!!")
    registrar_log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    time.sleep(random.randint(10, 20))

    return {
        "success": online,
        "online": online,
        "tempos": tempos,
        "status_codes": status_codes,
        "tentativas": tentativas,
        "error": erro,
        "servidor": nome_servidor_padrao,
        "username": username,
        "password": password,
        "tempo_total": tempo_total
    }


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
    dominios = DominiosDNS.objects.filter(monitorado=True).order_by("servidor")
    for dominio in dominios:
        hora_now = localtime()
        status_anterior = dominio.status
        dominio.data_ultima_verificacao = hora_now
        
        # 1. Validação de status do domínio
        # - Verifica status de acesso à lista e aos canais através do domínio válido;
        lista_dict = validar_dominio(dominio.dominio, dominio.servidor.nome)
        success = lista_dict.get("success", True)
        dominio_online = lista_dict.get("online", True)
        tempos = lista_dict.get("tempos", "N/A")
        status_codes = lista_dict.get("status_codes", "N/A")
        tentativas = lista_dict.get("tentativas", "N/A")
        error_msg = lista_dict.get("error", "Erro não informado")
        servidor = lista_dict.get("servidor", "N/A")
        username = lista_dict.get("username", "N/A")
        password = lista_dict.get("password", "N/A")

        if dominio_online:
            # 2. Verifica see mudou de status OFFLINE para ONLINE agora:
            if status_anterior == "offline":
                mensagem = (
                    f"✅ *DNS ONLINE*\n"
                    f"🌐 *Domínio:*\n`{dominio.dominio}`\n"
                    f"🕓 *Horário:* {hora_now.strftime('%d/%m %Hh%M')}\n"
                    f"📺 *Servidor:* {dominio.servidor}\n\n"
                    f"🔔 _O domínio voltou a responder normalmente!_"
                )
                if grupos_envio:
                    # Envia notificação para grupos no WPP, se houver ID válido obtido;
                    for group_id, group_name in grupos_envio:
                        enviar_mensagem(group_id, mensagem, WPP_USER, WPP_TOKEN, is_group=True)
                        registrar_log("", titulo_destacado=f"🚨 [GRUPO] ALERTA enviado para '{group_name}': DNS ONLINE {dominio.dominio}", LOG_FILE)

                if WPP_TELEFONE:
                    # Envia mensagem para contato privado no WPP, se houver número definido;
                    enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN, is_group=False)
                    registrar_log("", titulo_destacado=f"🚨 [PRIVADO] ALERTA enviado: DNS ONLINE {dominio.dominio}", LOG_FILE)

                # Atualiza status para online;
                dominio.status = "online"
                dominio.data_online = hora_now
                dominio.acesso_canais = "TOTAL"
                dominio.data_envio_alerta = hora_now
                dominio.save(update_fields=["status", "data_online", "acesso_canais", "data_envio_alerta", "data_ultima_verificacao"])
            else:
                # Se o status anterior não mudou, então continua online;
                # Apenas registra a data da verificação;
                dominio.save(update_fields=["data_ultima_verificacao"])

        else:
            # 3. Se mudou de status ONLINE para OFFLINE agora:
            if status_anterior == "online":
                mensagem = (
                    f"❌ *DNS OFFLINE*\n"
                    f"🌐 *Domínio:*\n`{dominio.dominio}`\n"
                    f"🕓 *Horário:* {localtime().strftime('%d/%m %Hh%M')}\n"
                    f"📺 *Servidor:* {dominio.servidor}\n\n"
                    f"⚠️ _O domínio parou de responder._\n⚠️ _Caso esteja em uso, alguns clientes poderão ficar sem acesso temporariamente!_"
                )
                
                if grupos_envio:
                    for group_id, group_name in grupos_envio:
                        enviar_mensagem(group_id, mensagem, WPP_USER, WPP_TOKEN, is_group=True)
                        registrar_log("", titulo_destacado=f"🚨 [GRUPO] ALERTA enviado para '{group_name}': DNS OFFLINE {dominio.dominio}", LOG_FILE)

                if WPP_TELEFONE:
                    enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN, is_group=False)
                    registrar_log(f"🚨 [PRIVADO] ALERTA enviado: DNS OFFLINE {dominio.dominio}", LOG_FILE)

                # Atualiza status para offline
                dominio.status = "offline"
                dominio.data_offline = hora_now
                dominio.data_envio_alerta = hora_now
                dominio.acesso_canais = "INDISPONIVEL"
                dominio.save(update_fields=["status", "data_offline", "data_envio_alerta", "acesso_canais", "data_ultima_verificacao"])
            elif status_anterior == "offline":
                # Se já estava offline, só registra a verificação
                dominio.save(update_fields=["data_ultima_verificacao"])
                registrar_log("", titulo_destacado=f"❌ DNS offline: {dominio.dominio}", LOG_FILE)

            # Registra em log resultados detalhados em log;
            log_msg = (
                f"[SUCCESS] {success}\n"
                f"[TEMPOS] {tempos}\n"
                f"[STATUS_CODES] {status_codes}\n"
                f"[TENTATIVAS] {tentativas}\n"
                f"[ERROR] {error_msg}\n"
                f"[SERVIDOR] {servidor}\n"
                f"[DOMINIO] {dominio.dominio}\n"
                f"[USERNAME] {username}\n"
                f"[PASSWORD] {str(password)[:3] + '***' if password != 'N/A' else password}\n"
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
