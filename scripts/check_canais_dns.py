import os
import sys
import json
import time
import django
import random
import requests
import threading
from django.utils.timezone import localtime
from wpp.api_connection import get_all_groups, get_ids_grupos_envio

# --- Configuração do ambiente Django ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

from cadastros.models import DominiosDNS, SessaoWpp, User
from cadastros.services.logging_config import get_dns_logger

# Configuração do logger com rotação automática
logger = get_dns_logger()

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

# Arquivos de log consolidados (com rotação automática via logger centralizado)
STATUS_SNAPSHOT_FILE = "logs/DNS/snapshots_dns.pkl"

USER_ADMIN = User.objects.filter(is_superuser=True).order_by('id').first()
sessao_wpp = SessaoWpp.objects.get(usuario=USER_ADMIN)
WPP_USER = sessao_wpp.usuario
WPP_TOKEN = sessao_wpp.token

# --- Inicialização de diretórios ---
os.makedirs(os.path.dirname(STATUS_SNAPSHOT_FILE), exist_ok=True)

# --- Verificação de variáveis obrigatórias ---
if not all([USERNAME, PASSWORD, URL_API_WPP, WPP_TELEFONE, WPP_USER, WPP_TOKEN]):
    logger.critical("Variáveis obrigatórias não definidas")
    sys.exit(1)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive"
}

############################################################
#################### FUNÇÕES AUXILIARES ####################
############################################################


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
        logger.info("Mensagem enviada | telefone=%s is_group=%s", telefone, is_group)
    except Exception as e:
        logger.error("Envio falhou | telefone=%s erro=%s", telefone, str(e))


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
    timeout = (10, 20) # 8 segundos para conectar, 15 segundos para obter resposta
    respostas_ok = 0
    respostas_ok_min = 5 # qtd min de resposta com sucesso
    resposta_tempo_max = 15 # tempo de resposta max
    nome_servidor_padrao = nome_servidor.strip().upper()
    username = USERNAME.get(nome_servidor_padrao)
    password = PASSWORD.get(nome_servidor_padrao)

    url = f"{dominio.rstrip('/')}/get.php?username={username}&password={password}&type=m3u_plus&output=m3u8"
    logger.info("Iniciando validação | dominio=%s servidor=%s", dominio, nome_servidor)

    tempo_inicio = time.time()
    for i in range(tentativas):
        time.sleep(random.randint(5, 10))
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
            logger.debug(
                "Tentativa de validação | dominio=%s tentativa=%d/%d status=%d tempo=%.2fs extinf=%s",
                dominio,
                i+1,
                tentativas,
                r.status_code,
                tempo,
                encontrou_extinf
            )

            if r.status_code == 200 and encontrou_extinf and tempo < resposta_tempo_max:
                respostas_ok += 1

        except requests.exceptions.ConnectTimeout:
            tempos.append(None)
            status_codes.append('ConnectTimeout')
            logger.warning(
                "Timeout na conexão | dominio=%s tentativa=%d/%d",
                dominio,
                i+1,
                tentativas
            )
        except requests.exceptions.ReadTimeout:
            tempos.append(None)
            status_codes.append('ReadTimeout')
            logger.warning(
                "Timeout ao ler resposta | dominio=%s tentativa=%d/%d",
                dominio,
                i+1,
                tentativas
            )
        except requests.exceptions.Timeout:
            tempos.append(None)
            status_codes.append('Timeout')
            logger.warning(
                "Timeout geral | dominio=%s tentativa=%d/%d",
                dominio,
                i+1,
                tentativas
            )
        except Exception as e:
            tempos.append(None)
            status_codes.append(str(e))
            logger.error(
                "Erro inesperado na validação | dominio=%s tentativa=%d/%d erro=%s",
                dominio,
                i+1,
                tentativas,
                repr(e)
            )
            erro = str(e)

    tempo_total = time.time() - tempo_inicio
    online = respostas_ok >= respostas_ok_min

    if online:
        logger.info(
            "Domínio ONLINE | dominio=%s tentativas_ok=%d/%d tempo_total=%.2fs",
            dominio,
            respostas_ok,
            tentativas,
            tempo_total
        )
    else:
        logger.warning(
            "Domínio OFFLINE | dominio=%s tentativas_ok=%d/%d tempo_total=%.2fs",
            dominio,
            respostas_ok,
            tentativas,
            tempo_total
        )
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
    logger.info("Iniciando checagem de status de domínios DNS")
    inicio_global = time.time()

    # Obtém todos os grupos e extrai IDs dos grupos desejados para envio
    grupos = get_all_groups(WPP_TOKEN, sessao_wpp)
    # Nota: log_path não é mais necessário pois get_ids_grupos_envio usa logger interno
    grupos_envio = get_ids_grupos_envio(grupos, ADM_ENVIA_ALERTAS, None)

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
                        logger.info(
                            "Alerta enviado para grupo | tipo=DNS_ONLINE grupo=%s dominio=%s",
                            group_name,
                            dominio.dominio
                        )

                if WPP_TELEFONE:
                    # Envia mensagem para contato privado no WPP, se houver número definido;
                    enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN, is_group=False)
                    logger.info(
                        "Alerta enviado (privado) | tipo=DNS_ONLINE dominio=%s",
                        dominio.dominio
                    )

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
                        logger.warning(
                            "Alerta enviado para grupo | tipo=DNS_OFFLINE grupo=%s dominio=%s",
                            group_name,
                            dominio.dominio
                        )

                if WPP_TELEFONE:
                    enviar_mensagem(WPP_TELEFONE, mensagem, WPP_USER, WPP_TOKEN, is_group=False)
                    logger.warning(
                        "Alerta enviado (privado) | tipo=DNS_OFFLINE dominio=%s",
                        dominio.dominio
                    )

                # Atualiza status para offline
                dominio.status = "offline"
                dominio.data_offline = hora_now
                dominio.data_envio_alerta = hora_now
                dominio.acesso_canais = "INDISPONIVEL"
                dominio.save(update_fields=["status", "data_offline", "data_envio_alerta", "acesso_canais", "data_ultima_verificacao"])
            elif status_anterior == "offline":
                # Se já estava offline, só registra a verificação
                dominio.save(update_fields=["data_ultima_verificacao"])
                logger.info("DNS continua offline | dominio=%s", dominio.dominio)

            # Registra resultados detalhados em log
            logger.debug(
                "Detalhes da validação | success=%s dominio=%s servidor=%s username=%s "
                "tempos=%s status_codes=%s tentativas=%s erro=%s",
                success,
                dominio.dominio,
                servidor,
                username,
                tempos,
                status_codes,
                tentativas,
                error_msg
            )

    fim_global = time.time()
    logger.info("Checagem de DNS concluída | duracao=%.2fs", fim_global - inicio_global)

##################################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO PROCESSAR_NOVOS_TITULOS #####
##################################################################################

executar_check_dns_canais_lock = threading.Lock()

def executar_check_canais_dns_com_lock():

    if executar_check_dns_canais_lock.locked():
        logger.warning("Execução ignorada | motivo=processo_em_andamento funcao=check_dns_canais")
        return

    with executar_check_dns_canais_lock:
        inicio = localtime()
        logger.info("Iniciando execução com lock | funcao=check_dns_canais")
        check_dns_canais()
        fim = localtime()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        logger.info(
            "Execução finalizada | funcao=check_dns_canais duracao=%dmin %.1fs",
            int(minutos),
            segundos
        )
##### FIM #####
