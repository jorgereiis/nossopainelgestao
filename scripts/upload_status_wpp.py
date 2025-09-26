import os
import re
import django
import time
import shutil
import random
import inspect
import logging
import requests
import threading
from datetime import datetime
from django.contrib.auth.models import User
from django.utils.timezone import localtime
from django.shortcuts import get_object_or_404
from cadastros.models import User, ConteudoM3U8, SessaoWpp
from wpp.api_connection import upload_imagem_status, upload_status_sem_imagem

# --- Configura o ambiente Django ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "setup.settings")
django.setup()

# --- Variáveis de ambiente e caminhos ---
MEU_NUM_TIM = os.getenv("MEU_NUM_TIM")
NOME_SCRIPT = "UPLOAD STATUS WPP"
URL_API_WPP = os.getenv("URL_API_WPP")
LOG_FILE = "logs/UploadStatusWpp/upload_status.log"
THREAD_LOG = "logs/UploadStatusWpp/upload_status_thread.log"

# --- Garante que os diretórios dos arquivos de log existam ---
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(THREAD_LOG), exist_ok=True)

# --- Função para registrar log no arquivo e imprimir no terminal ---
def registrar_log(mensagem, log_file):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    print(f"[{timestamp}] [{NOME_SCRIPT}] {mensagem}")
    
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {mensagem}\n")

# --- Envia mensagem privada para número específico ---
def enviar_mensagem(telefone, mensagem, usuario, token):
    url = f"{URL_API_WPP}/{usuario}/send-message"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {'phone': telefone, 'message': mensagem, 'isGroup': False}

    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        registrar_log(f"[OK] Mensagem enviada para número {telefone}", LOG_FILE)
    except Exception as e:
        registrar_log(f"[ERRO] {telefone} => {e}", LOG_FILE)

# --- Monta legenda amigável com temporada/episódio ---
def gerar_legenda(conteudo):
    if conteudo.temporada and conteudo.episodio:
        return f"{conteudo.nome}\nTemporada {conteudo.temporada} - Episódio {conteudo.episodio}"
    return conteudo.nome

# --- Função principal de envio de status no WhatsApp ---
def executar_upload_status():
    registrar_log(f"[INIT] Iniciando envio de status para o WhatsApp.", LOG_FILE)

    conteudos = ConteudoM3U8.objects.filter(upload=False).order_by('criado_em')
    if not conteudos.exists():
        registrar_log("[INFO] Nenhum conteúdo novo para enviar.", LOG_FILE)
        return

    primeiro = conteudos.first()
    usuario = primeiro.usuario
    token_obj = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()

    if not token_obj:
        registrar_log(f"[ERRO] Token do usuário {usuario.username} não encontrado.", LOG_FILE)
        return

    token = token_obj.token

    # Envia mensagem de introdução
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    mensagem_inicial = f"📢 Confira a seguir os novos conteúdos de Filmes/Séries adicionados à nossa grade hoje ({data_hoje})!"
    if not upload_status_sem_imagem(mensagem_inicial, usuario.username, token, LOG_FILE):
        registrar_log(f"[AVISO] Abortando envio para {usuario.username} — erro na mensagem de abertura.", LOG_FILE)
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
        sucesso = upload_imagem_status(item.capa, legenda, usuario.username, token, LOG_FILE)

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
            registrar_log(f"[AVISO] Conteúdo não marcado como enviado: {item.nome}", LOG_FILE)

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
            upload_status_sem_imagem(texto_bloco, usuario.username, token, LOG_FILE)

        if MEU_NUM_TIM:
            texto_mensagem_privada = "\n".join(linhas_mensagem)
            enviar_mensagem(MEU_NUM_TIM, texto_mensagem_privada, usuario.username, token)

        upload_status_sem_imagem(
            "✅ Encerramos por aqui! Agradecemos por acompanhar nossas novidades. Em breve, mais conteúdos incríveis para vocês!",
            usuario.username,
            token,
            LOG_FILE
        )

    registrar_log(f"[OK] Status atualizado para {usuario.username} ({enviados} conteúdos enviados)", LOG_FILE)

####################################################################################
##### FUNÇÃO PARA UPLOAD DE IMAGENS DE STATUS DO WHATSAPP A PARTIR DO TELEGRAM #####
####################################################################################

# --- Caminho base e logs ---
CAMINHO_BASE = "images/telegram_banners/"
LOG_PATH = "logs/UploadStatusWpp/images_from_telegram.log"

# Configuração do logger (arquivo + console)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logger = logging.getLogger("UploadStatusWpp")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(funcName)s] %(message)s")

# Console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Arquivo
file_handler = logging.FileHandler(LOG_PATH)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


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
        logger.error(f"[{user}] Nenhuma sessão ativa encontrada!")
        return

    token = sessao.token
    limpar_diretorios_antigos(CAMINHO_BASE, manter=7)

    if not os.path.exists(pasta_hoje):
        logger.warning(f"[{user}] Nenhuma imagem encontrada para o dia: {hoje_str}")
        return

    arquivos = os.listdir(pasta_hoje)
    imagens = sorted(
        [f for f in arquivos if f.lower().endswith((".jpg", ".jpeg", ".png"))],
        key=extrair_numero,
    )

    if not imagens:
        logger.warning(f"[{user}] Nenhuma imagem válida encontrada na pasta: {pasta_hoje}")
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
                log_path=LOG_PATH,
            )

            if sucesso:
                logger.info(f"[{user}] Imagem enviada '{img_nome}' (tentativa {tentativa+1})")
                break
            else:
                logger.error(f"[{user}] Falha ao enviar '{img_nome}' (tentativa {tentativa+1})")


#################################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO EXECUTAR_UPLOAD_STATUS #####
#################################################################################

executar_upload_status_lock = threading.Lock()
def executar_upload_status_com_lock():
    if executar_upload_status_lock.locked():
        registrar_log("[IGNORADO] Execução ignorada — processo ainda em andamento.", THREAD_LOG)
        return

    with executar_upload_status_lock:
        inicio = datetime.now()
        executar_upload_status()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        registrar_log(f"[END] Tempo de execução: {int(minutos)} min {segundos:.1f} s.", THREAD_LOG)
        return
    
executar_upload_image_from_telegram_lock = threading.Lock()
def executar_upload_image_from_telegram_com_lock():
    if executar_upload_image_from_telegram_lock.locked():
        registrar_log("[IGNORADO] Execução ignorada — processo ainda em andamento.", THREAD_LOG)
        return

    with executar_upload_image_from_telegram_lock:
        inicio = datetime.now()
        upload_image_from_telegram()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        registrar_log(f"[END] Tempo de execução: {int(minutos)} min {segundos:.1f} s.", THREAD_LOG)
        return
##### FIM #####