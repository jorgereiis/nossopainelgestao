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

URL_API_WPP = os.getenv("URL_API_WPP")
MEU_NUM = os.getenv("MEU_NUM")
LOG_DIR = "logs/UploadStatusWpp"
LOG_FILE = os.path.join(LOG_DIR, "upload_status.log")
os.makedirs(LOG_DIR, exist_ok=True)

# --- Escreve mensagem no log ---
def registrar_log(mensagem):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    linha = f"[{timestamp}] {mensagem}"
    print(linha)
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(linha + "\n")

# --- Atraso aleatório entre envios ---
def delay():
    segundos = random.randint(10, 30)
    print(f"[INFO] [UPLOAD_WPP] Aguardando {segundos} segundos antes do próximo envio...")
    registrar_log(f"[INFO] Aguardando {segundos} segundos antes do próximo envio...")
    time.sleep(segundos)

# --- Envia texto para o status ---
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

        print(f"[OK] [UPLOAD_STATUS_SEM_IMAGEM] Mensagem de status enviada para {usuario}")
        registrar_log(f"[OK] Mensagem de status enviada para {usuario}")
        delay()
        return True
    except Exception as e:
        print(f"[ERRO] [UPLOAD_STATUS_SEM_IMAGEM] {usuario} => {e}")
        registrar_log(f"[ERRO] [UPLOAD_STATUS_SEM_IMAGEM] {usuario} => {e}")
        return False

# --- Envia imagem com legenda para o status ---
def upload_imagem_status(imagem, legenda, usuario, token):
    url = f"{URL_API_WPP}/{usuario}/send-image-storie"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {
        "path": imagem,
        "caption": legenda
    }
    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()

        print(f"[OK] [UPLOAD_IMAGEM_STATUS] Capa enviada para {usuario}: {legenda}")
        registrar_log(f"[OK] Capa enviada para {usuario}: {legenda}")
        delay()
        return True
    except Exception as e:
        registrar_log(f"[ERRO] [UPLOAD_IMAGEM_STATUS] {usuario} => {e}")
        return False

# --- Envia mensagem direta com a lista completa ---
def enviar_mensagem(telefone, mensagem, usuario, token):
    url = f"{URL_API_WPP}/{usuario}/send-message"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {
        'phone': telefone,
        'message': mensagem,
        'isGroup': False
    }
    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()

        print(f"[OK] [UPLOAD_STATUS-ENVIAR_MENSAGEM] Mensagem enviada para número {telefone}")
        registrar_log(f"[OK] Mensagem enviada para número {telefone}")
    except Exception as e:
        registrar_log(f"[ERRO] [UPLOAD_STATUS-ENVIAR_MENSAGEM] {telefone} => {e}")

# --- Gera legenda com base nas informações do conteúdo ---
def gerar_legenda(conteudo):
    if conteudo.temporada and conteudo.episodio:
        return f"{conteudo.nome}\nTemporada {conteudo.temporada} - Episódio {conteudo.episodio}"
    return conteudo.nome

# --- Função principal ---
def executar_upload_status():
    conteudos = ConteudoM3U8.objects.filter(upload=False).order_by('criado_em')

    if not conteudos.exists():
        print("[INFO] [EXECUTAR_UPLOAD_STATUS] Nenhum conteúdo novo para enviar.")
        registrar_log("[INFO] [EXECUTAR_UPLOAD_STATUS] Nenhum conteúdo novo para enviar.")
        return

    primeiro = conteudos.first()
    usuario = primeiro.usuario
    token_obj = SessaoWpp.objects.filter(usuario=usuario).first()

    if not token_obj:
        print(f"[ERRO] [EXECUTAR_UPLOAD_STATUS] Token do usuário {usuario.username} não encontrado.")
        registrar_log(f"[ERRO] [EXECUTAR_UPLOAD_STATUS] Token do usuário {usuario.username} não encontrado.")
        return

    token = token_obj.token

    # Mensagem de abertura
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    mensagem_inicial = f"📢 Confira a seguir os novos conteúdos de Filmes/Séries adicionados à nossa grade hoje ({data_hoje})!"
    sucesso_abertura = upload_status_sem_imagem(mensagem_inicial, usuario.username, token)

    if not sucesso_abertura:
        print(f"[AVISO] [EXECUTAR_UPLOAD_STATUS] Abortando envio para {usuario.username} — erro na mensagem de abertura.")
        registrar_log(f"[AVISO] [EXECUTAR_UPLOAD_STATUS] Abortando envio para {usuario.username} — erro na mensagem de abertura.")
        return

    enviados = 0
    titulos_enviados = set()
    resumo_envios = {}

    for item in conteudos:
        if item.nome in titulos_enviados:
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
            print(f"[AVISO] [EXECUTAR_UPLOAD_STATUS] Conteúdo não enviado: {item.nome}")
            registrar_log(f"[AVISO] Conteúdo não marcado como enviado: {item.nome}")

    if enviados > 0:
        linhas_resumo = ["🎬 *Resumo das Atualizações de Hoje:*\n"]
        linhas_resumo_com_data = [f"🎬 *Resumo das Atualizações*\n📅 Data: *{datetime.now().strftime('%d/%m/%Y')}*\n"]
        
        for titulo, episodios in resumo_envios.items():
            if episodios:
                ep_str = ", ".join(sorted(set(episodios)))
                linhas_resumo.append(f"🎞️ *{titulo}* ({ep_str})")
                linhas_resumo_com_data.append(f"🎞️ *{titulo}* ({ep_str})")
            else:
                linhas_resumo.append(f"🎬 *{titulo}* — Filme")
                linhas_resumo_com_data.append(f"🎬 *{titulo}* — Filme")

        texto_resumo_status = "\n".join(linhas_resumo)
        texto_resumo_mensagem = "\n".join(linhas_resumo_com_data)
        upload_status_sem_imagem(texto_resumo_status, usuario.username, token)

        # Envio como mensagem privada para o número definido
        if MEU_NUM:
            enviar_mensagem(MEU_NUM, texto_resumo_mensagem, usuario.username, token)

        mensagem_final = "✅ Encerramos por aqui! Agradecemos por acompanhar nossas novidades. Em breve, mais conteúdos incríveis para vocês!"
        upload_status_sem_imagem(mensagem_final, usuario.username, token)

    registrar_log(f"[OK] [EXECUTAR_UPLOAD_STATUS] Status atualizado para {usuario.username} ({enviados} conteúdos enviados)")
    registrar_log("[FIM] [EXECUTAR_UPLOAD_STATUS] Execução concluída.")



###############################################################################
##### LOCK PARA EVITAR EXECUÇÃO SIMULTÂNEA DA FUNÇÃO EXECUTAR_UPLOAD_STATUS #####
###############################################################################

executar_upload_status_lock = threading.Lock()
def executar_upload_status_com_lock():
    if executar_upload_status_lock.locked():
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [IGNORADO] [EXECUTAR_UPLOAD_STATUS] Execução ignorada — processo ainda em andamento.")
        return

    with executar_upload_status_lock:
        inicio = datetime.now()
        executar_upload_status()
        fim = datetime.now()

        duracao = (fim - inicio).total_seconds()
        minutos = duracao // 60
        segundos = duracao % 60

        print(f"[{fim.strftime('%Y-%m-%d %H:%M:%S')}] [CONCLUÍDO] [EXECUTAR_UPLOAD_STATUS] Tempo de execução: {int(minutos)} min {segundos:.1f} s.")
##### FIM #####