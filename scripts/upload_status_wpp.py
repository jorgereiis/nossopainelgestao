import os
import django
import time
import random
import requests
from datetime import datetime
from django.contrib.auth.models import User
import threading
from cadastros.models import ConteudoM3U8, SessaoWpp

# Configura o ambiente Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "setup.settings")
django.setup()

# Variáveis de ambiente e caminhos
MEU_NUM = os.getenv("MEU_NUM_TIM")
NOME_SCRIPT = "UPLOAD STATUS WPP"
URL_API_WPP = os.getenv("URL_API_WPP")
LOG_FILE = "logs/UploadStatusWpp/upload_status.log"
THREAD_LOG = "logs/UploadStatusWpp/upload_status_thread.log"

# Garante que os diretórios dos arquivos de log existam
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(THREAD_LOG), exist_ok=True)

# --- Função para registrar log no arquivo e imprimir no terminal ---
def registrar_log(mensagem, log_file):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{NOME_SCRIPT}] {mensagem}")
    
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {mensagem}\n")

# --- Aguarda aleatoriamente entre 10 e 30 segundos entre os envios ---
def delay():
    segundos = random.randint(10, 30)
    registrar_log(f"[INFO] Aguardando {segundos} segundos antes do próximo envio...", LOG_FILE)
    time.sleep(segundos)

# --- Envia mensagem de texto para o status do WhatsApp ---
def upload_status_sem_imagem(texto_status, usuario, token):
    url = f"{URL_API_WPP}/{usuario}/send-text-storie"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {"text": texto_status}

    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        registrar_log(f"[OK] Mensagem de status enviada para {usuario}", LOG_FILE)
        delay()
        return True
    except Exception as e:
        registrar_log(f"[ERRO] {usuario} => {e}", LOG_FILE)
        return False

# --- Envia imagem com legenda para o status do WhatsApp ---
def upload_imagem_status(imagem, legenda, usuario, token):
    url = f"{URL_API_WPP}/{usuario}/send-image-storie"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {"path": imagem, "caption": legenda}

    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        registrar_log(f"[OK] Capa enviada para {usuario}: {legenda}", LOG_FILE)
        delay()
        return True
    except Exception as e:
        registrar_log(f"[ERRO] {usuario} => {e}", LOG_FILE)
        return False

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
    token_obj = SessaoWpp.objects.filter(usuario=usuario).first()

    if not token_obj:
        registrar_log(f"[ERRO] Token do usuário {usuario.username} não encontrado.", LOG_FILE)
        return

    token = token_obj.token

    # --- Envia mensagem de introdução ---
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    mensagem_inicial = f"📢 Confira a seguir os novos conteúdos de Filmes/Séries adicionados à nossa grade hoje ({data_hoje})!"
    if not upload_status_sem_imagem(mensagem_inicial, usuario.username, token):
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
        sucesso = upload_imagem_status(item.capa, legenda, usuario.username, token)

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

    # --- Gera resumo para status e mensagem privada ---
    if enviados > 0:
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

        # Dividir linhas_status em blocos de no máximo 14 linhas cada
        blocos = [linhas_status[i:i+14] for i in range(0, len(linhas_status), 14)]
        total_blocos = len(blocos)

        for idx, bloco in enumerate(blocos, start=1):
            texto_bloco = f"🎬 *Resumo das Atualizações de Hoje (página {idx}/{total_blocos}):*\n\n"
            texto_bloco += "\n".join(bloco)
            upload_status_sem_imagem(texto_bloco, usuario.username, token)

        # Envia também a mensagem privada (tudo de uma vez)
        if MEU_NUM:
            texto_mensagem_privada = "\n".join(linhas_mensagem)
            enviar_mensagem(MEU_NUM, texto_mensagem_privada, usuario.username, token)

        # Mensagem final
        upload_status_sem_imagem(
            "✅ Encerramos por aqui!\nMuito obrigado por acompanhar nossas atualizações. Em breve, mais conteúdos incríveis chegando pra você! 🎉",
            usuario.username,
            token
        )

    registrar_log(f"[OK] Status atualizado para {usuario.username} ({enviados} conteúdos enviados)", LOG_FILE)


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
##### FIM #####