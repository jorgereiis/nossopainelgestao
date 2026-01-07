import os
import re
import django
import time
import shutil
import random
import requests
import threading
from datetime import datetime
from django.contrib.auth.models import User
from django.utils.timezone import localtime

# --- Configura o ambiente Django ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "setup.settings")
django.setup()

from nossopainel.models import User, ConteudoM3U8, SessaoWpp
from nossopainel.services.logging_config import get_wpp_logger
from wpp.api_connection import upload_imagem_status, upload_status_sem_imagem

# Configuração do logger centralizado com rotação automática
logger = get_wpp_logger()

# --- Variáveis de ambiente e caminhos ---
MEU_NUM_TIM = os.getenv("MEU_NUM_TIM")
API_WPP_URL_PROD = os.getenv("API_WPP_URL_PROD")

# --- Envia mensagem privada para número específico ---
def enviar_mensagem(telefone, mensagem, usuario, token):
    url = f"{API_WPP_URL_PROD}/{usuario}/send-message"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {'phone': telefone, 'message': mensagem, 'isGroup': False}

    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info("Mensagem enviada | telefone=%s", telefone)
    except Exception as e:
        logger.error("Falha ao enviar mensagem | telefone=%s erro=%s", telefone, str(e))

# --- Monta legenda amigável com temporada/episódio ---
def gerar_legenda(conteudo):
    if conteudo.temporada and conteudo.episodio:
        return f"{conteudo.nome}\nTemporada {conteudo.temporada} - Episódio {conteudo.episodio}"
    return conteudo.nome

# --- Função principal de envio de status no WhatsApp ---
def executar_upload_status():
    logger.info("Iniciando envio de status para WhatsApp")

    conteudos = ConteudoM3U8.objects.filter(upload=False).order_by('criado_em')
    if not conteudos.exists():
        logger.info("Nenhum conteúdo novo para enviar")
        return

    primeiro = conteudos.first()
    usuario = primeiro.usuario
    token_obj = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()

    if not token_obj:
        logger.error("Token não encontrado | usuario=%s", usuario.username)
        return

    token = token_obj.token

    # Envia mensagem de introdução
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    mensagem_inicial = f"📢 Confira a seguir os novos conteúdos de Filmes/Séries adicionados à nossa grade hoje ({data_hoje})!"
    if not upload_status_sem_imagem(mensagem_inicial, usuario.username, token, None):
        logger.warning("Abortando envio | usuario=%s motivo=erro_na_mensagem_abertura", usuario.username)
        return

    enviados = 0
    titulos_enviados = set()
    resumo_envios = {}

    for item in conteudos:
        if item.nome in titulos_enviados:
            # Marca como enviado e agrupa episódio extra
            if item.nome not in resumo_envios:
                resumo_envios[item.nome] = []
            if item.temporada and item.episodio:
                resumo_envios[item.nome].append(f"T{item.temporada}E{item.episodio}")
            item.upload = True
            item.save()
            continue

        legenda = gerar_legenda(item)
        sucesso = upload_imagem_status(item.capa, legenda, usuario.username, token, None)

        if sucesso:
            item.upload = True
            item.save()
            enviados += 1
            titulos_enviados.add(item.nome)

            if item.nome not in resumo_envios:
                resumo_envios[item.nome] = []
            if item.temporada and item.episodio:
                resumo_envios[item.nome].append(f"T{item.temporada}E{item.episodio}")
        else:
            logger.warning("Conteúdo não marcado como enviado | nome=%s", item.nome)

    if enviados > 0:
        # Gera resumo para status e mensagem privada
        linhas_status = []
        linhas_mensagem = [f"🎬 *Resumo das Atualizações*\n📅 Data: *{data_hoje}*\n"]

        for titulo, episodios in resumo_envios.items():
            if episodios:
                ep_str = ", ".join(sorted(set(episodios)))
                linhas_status.append(f"🎞️ *{titulo}* ({ep_str})")
                linhas_mensagem.append(f"🎞️ *{titulo}* ({ep_str})")
            else:
                linhas_status.append(f"🎬 *{titulo}* — Filme")
                linhas_mensagem.append(f"🎬 *{titulo}* — Filme")

        blocos = [linhas_status[i:i+14] for i in range(0, len(linhas_status), 14)]
        total_blocos = len(blocos)

        for idx, bloco in enumerate(blocos, start=1):
            texto_bloco = f"🎬 *Resumo das Atualizações de Hoje (página {idx}/{total_blocos}):*\n\n"
            texto_bloco += "\n".join(bloco)
            upload_status_sem_imagem(texto_bloco, usuario.username, token, None)

        if MEU_NUM_TIM:
            texto_mensagem_privada = "\n".join(linhas_mensagem)
            enviar_mensagem(MEU_NUM_TIM, texto_mensagem_privada, usuario.username, token)

        upload_status_sem_imagem(
            "✅ Encerramos por aqui! Agradecemos por acompanhar nossas novidades. Em breve, mais conteúdos incríveis para vocês!",
            usuario.username,
            token,
            None
        )

    logger.info("Status atualizado | usuario=%s conteudos_enviados=%d", usuario.username, enviados)

####################################################################################
##### FUNÇÃO PARA UPLOAD DE IMAGENS DE STATUS DO WHATSAPP A PARTIR DO TELEGRAM #####
####################################################################################

# --- Caminho base ---
CAMINHO_BASE = "images/telegram_banners/"


def extrair_numero(nome_arquivo):
    numeros = re.findall(r"\d+", nome_arquivo)
    return int(numeros[-1]) if numeros else 0


def limpar_diretorios_antigos(caminho_base, manter=7):
    """
    Mantém apenas os últimos 'manter' diretórios baseados no nome em formato dd-mm-YYYY.
    Remove os mais antigos.
    """
    padrao_data = re.compile(r"^\d{2}-\d{2}-\d{4}$")
    diretorios = [
        d for d in os.listdir(caminho_base)
        if os.path.isdir(os.path.join(caminho_base, d)) and padrao_data.match(d)
    ]

    diretorios_ordenados = sorted(
        diretorios,
        key=lambda d: datetime.strptime(d, "%d-%m-%Y"),
        reverse=True,
    )

    for dir_antigo in diretorios_ordenados[manter:]:
        dir_path = os.path.join(caminho_base, dir_antigo)
        try:
            shutil.rmtree(dir_path)
            logger.info(f"Diretório removido: {dir_path}")
        except Exception as e:
            logger.error(f"Falha ao remover {dir_path}: {e}")


def upload_image_from_telegram():
    hoje_str = localtime().strftime("%d-%m-%Y")
    pasta_hoje = os.path.join(CAMINHO_BASE, hoje_str)

    # Recarregar user e sessão ativa a cada execução
    user = User.objects.get(id=1)
    sessao = SessaoWpp.objects.filter(usuario=user, is_active=True).first()
    if not sessao:
        logger.error("Nenhuma sessão ativa encontrada | usuario=%s", user.username)
        return

    token = sessao.token
    limpar_diretorios_antigos(CAMINHO_BASE, manter=7)

    if not os.path.exists(pasta_hoje):
        logger.warning("Nenhuma imagem encontrada | usuario=%s dia=%s", user.username, hoje_str)
        return

    arquivos = os.listdir(pasta_hoje)
    imagens = sorted(
        [f for f in arquivos if f.lower().endswith((".jpg", ".jpeg", ".png"))],
        key=extrair_numero,
    )

    if not imagens:
        logger.warning("Nenhuma imagem válida encontrada | usuario=%s pasta=%s", user.username, pasta_hoje)
        return

    for img_nome in imagens:
        caminho_img = os.path.join(pasta_hoje, img_nome)

        for tentativa in range(2):  # tenta 2x
            time.sleep(random.randint(10, 15))
            sucesso = upload_imagem_status(
                imagem=caminho_img,
                legenda="",
                usuario=user,
                token=token,
                log_path=None,
            )

            if sucesso:
                logger.info("Imagem enviada | usuario=%s imagem=%s tentativa=%d", user.username, img_nome, tentativa+1)
                break
            else:
                logger.error("Falha ao enviar imagem | usuario=%s imagem=%s tentativa=%d", user.username, img_nome, tentativa+1)


#################################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO EXECUTAR_UPLOAD_STATUS #####
#################################################################################

executar_upload_status_lock = threading.Lock()
def executar_upload_status_com_lock():
    if executar_upload_status_lock.locked():
        logger.warning("Execução ignorada | motivo=processo_em_andamento funcao=executar_upload_status")
        return

    with executar_upload_status_lock:
        inicio = datetime.now()
        logger.info("Iniciando execução com lock | funcao=executar_upload_status")
        executar_upload_status()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        logger.info("Execução finalizada | funcao=executar_upload_status duracao=%dmin %.1fs", int(minutos), segundos)
        return

executar_upload_image_from_telegram_lock = threading.Lock()
def executar_upload_image_from_telegram_com_lock():
    if executar_upload_image_from_telegram_lock.locked():
        logger.warning("Execução ignorada | motivo=processo_em_andamento funcao=upload_image_from_telegram")
        return

    with executar_upload_image_from_telegram_lock:
        inicio = datetime.now()
        logger.info("Iniciando execução com lock | funcao=upload_image_from_telegram")
        upload_image_from_telegram()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        logger.info("Execução finalizada | funcao=upload_image_from_telegram duracao=%dmin %.1fs", int(minutos), segundos)
        return
##### FIM #####