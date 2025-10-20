"""Cliente auxiliar para interação com a API WPPConnect utilizada pelo sistema."""

import base64
import logging
import mimetypes
import os
import random
import time

import requests
from cadastros.services.logging import append_line

URL_API_WPP = os.getenv("URL_API_WPP")
MEU_NUM_CLARO = os.getenv("MEU_NUM_CLARO")

##################################################################
################ FUNÇÃO PARA REGISTRAR LOGS ######################
##################################################################

# Função para registrar mensagens no arquivo de log principal
logger = logging.getLogger(__name__)


def registrar_log(mensagem: str, log_path: str) -> None:
    """Anexa a ``mensagem`` ao arquivo de log indicado."""
    append_line(log_path, mensagem)

###################################################
##### FUNÇÕES PARA CONEXÃO COM API WPPCONNECT #####
###################################################

##### FUNÇÕES PARA GERENCIAR SESSÕES DO WHATSAPP #####
# --- Estas funções permitem gerar token, iniciar sessão, verificar status, obter QR code, verificar conexão, fechar sessão e fazer logout. ---
def gerar_token(session: str, secret: str):
    url = f"{URL_API_WPP}/{session}/{secret}/generate-token"
    response = requests.post(url)
    return response.json(), response.status_code

def start_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/start-session"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "webhook": "",
        "waitQrCode": True
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json(), response.status_code

def status_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/status-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json(), response.status_code

def get_qrcode(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/qrcode-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.content, response.status_code

def check_connection(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/check-connection-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json(), response.status_code

def close_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/close-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers)
    time.sleep(3)  # Aguarda se necessário
    return response.json(), response.status_code

def logout_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/logout-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers)
    time.sleep(3)
    return response.json(), response.status_code

##### FUNÇÕES PARA GERENCIAR CONTATOS E LABELS #####
# --- Função para obter labels de um contato ---
def get_label_contact(telefone, token, user):
    """Obtém as labels associadas a um contato específico."""

    url = f'{URL_API_WPP}/{user}/contact/{telefone}'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    body = {
        "phone": telefone,
    }

    try:
        response = requests.get(url, headers=headers, json=body)

        if response.status_code in [200, 201]:
            response_data = response.json()
            labels = (response_data.get('response') or {}).get('labels', [])
            return labels

        logger.error(
            "[get_label_contact] %s | Erro ao obter labels (%s): %s",
            user,
            response.status_code,
            response.text,
        )
        return []
    except requests.RequestException as exc:
        logger.exception("[get_label_contact] %s | Falha na requisição: %s", user, exc)
        return []

# --- Função para verificar se o número existe no WhatsApp ---
def check_number_status(telefone, token, user):
    """Verifica se o telefone informado está registrado no WhatsApp."""

    url = f'{URL_API_WPP}/{user}/check-number-status/{telefone}'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    body = {
        "phone": telefone,
    }

    try:
        response = requests.get(url, headers=headers, json=body)

        if response.status_code in [200, 201]:
            response_data = response.json()
            status = response_data.get('response', {}).get('numberExists', False)
            user_data = response_data.get('response', {}).get('id') or {}
            user_number = user_data.get('user')
            logger.info("[check_number_status] %s | Número válido: %s", user, telefone)
            return {'status': status, 'user': user_number}

        logger.error(
            "[check_number_status] %s | Erro ao verificar %s: %s - %s",
            user,
            telefone,
            response.status_code,
            response.text,
        )
        return False
    except requests.RequestException as exc:
        logger.exception("[check_number_status] %s | Falha de requisição: %s", user, exc)
        return False


# --- Função para obter todas as labels disponíveis para um contato ---
def get_all_labels(token, user):
    """Retorna todas as labels disponíveis na instância WPP do usuário."""

    url = f'{URL_API_WPP}/{user}/get-all-labels'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    body = {
        "phone": MEU_NUM_CLARO,
    }

    try:
        response = requests.get(url, headers=headers, json=body)

        if response.status_code in [200, 201]:
            response_data = response.json()
            labels = response_data.get('response', [])
            logger.info("[get_all_labels] %s | %s labels recuperadas.", user, len(labels))
            return labels

        logger.error(
            "[get_all_labels] %s | Erro ao obter labels: %s - %s",
            user,
            response.status_code,
            response.text,
        )
        return []
    except requests.RequestException as exc:
        logger.exception("[get_all_labels] %s | Falha na requisição: %s", user, exc)
        return []


# --- Função para adicionar ou remover labels de um contato ---
def add_or_remove_label_contact(label_id_1, label_id_2, label_name, telefone, token, user):
    """Aplica a label desejada ao contato e remove labels anteriores."""

    telefone = telefone.replace('+', '').replace('@c.us', '').strip()

    labels_atual = label_id_2 if isinstance(label_id_2, list) else [label_id_2]

    if label_id_1 in labels_atual:
        logger.info("[add_or_remove_label_contact] %s | Label '%s' já atribuída.", user, label_name)
        return 200, {"status": "skipped", "message": "Label já atribuída"}

    url = f'{URL_API_WPP}/{user}/add-or-remove-label'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    # Remove todas as labels anteriores e adiciona a nova
    body = {
        "chatIds": [telefone],
        "options": [
            {"labelId": label_id_1, "type": "add"}
        ] + [
            {"labelId": label, "type": "remove"} for label in labels_atual if label and label != label_id_1
        ]
    }
  
    try:
        response = requests.post(url, headers=headers, json=body)
        logger.info(
            "[add_or_remove_label_contact] %s | status=%s body=%s",
            user,
            response.status_code,
            response.text,
        )

        if response.status_code in [200, 201]:
            logger.info(
                "[add_or_remove_label_contact] %s | Label aplicada: %s (%s)",
                user,
                label_name,
                label_id_1,
            )
        else:
            logger.error(
                "[add_or_remove_label_contact] %s | Falha ao ajustar label de %s: %s - %s",
                user,
                telefone,
                response.status_code,
                response.text,
            )

        try:
            response_data = response.json()
        except ValueError:
            response_data = response.text

        return response.status_code, response_data
    except requests.RequestException as exc:
        logger.exception("[add_or_remove_label_contact] %s | Erro de requisição: %s", user, exc)
        return 500, {"status": "error", "message": str(exc)}


# --- Função para criar uma nova label se não existir ---
def criar_label_se_nao_existir(nome_label, token, user, hex_color=None):
    """Cria a label no WhatsApp caso ainda não exista e retorna o ID correspondente."""

    labels = get_all_labels(token, user)

    label_existente = next((label for label in labels if label["name"].strip().lower() == nome_label.lower()), None)
    if label_existente:
        return label_existente.get("id")

    url = f"{URL_API_WPP}/{user}/add-new-label"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    body = {"name": nome_label}

    if hex_color:
        try:
            color_int = int(hex_color.lstrip("#"), 16) + (255 << 24)
            body["options"] = {"labelColor": color_int}
        except ValueError:
            logger.error("[criar_label_se_nao_existir] %s | Cor inválida '%s'.", user, hex_color)

    try:
        response = requests.post(url, headers=headers, json=body)
    except requests.RequestException as exc:
        logger.exception("[criar_label_se_nao_existir] %s | Erro na requisição: %s", user, exc)
        return None

    if response.status_code in [200, 201]:
        logger.info("[criar_label_se_nao_existir] %s | Label '%s' criada.", user, nome_label)

        try:
            labels = get_all_labels(token, user)
            nova_label = next((label for label in labels if label["name"].strip().lower() == nome_label.lower()), None)
            if nova_label:
                return nova_label.get("id")
            logger.info("[criar_label_se_nao_existir] %s | Label '%s' criada mas não localizada.", user, nome_label)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.exception("[criar_label_se_nao_existir] %s | Erro ao buscar labels: %s", user, exc)
            return None

    else:
        logger.error(
            "[criar_label_se_nao_existir] %s | Falha ao criar '%s': %s - %s",
            user,
            nome_label,
            response.status_code,
            response.text,
        )
        return None

##### FUNÇÃO PARA GERENCIAR GRUPOS DO WHATSAPP #####
# --- Obter todos os grupos disponíveis na sessão do WhatsApp ---
def get_all_groups(token, user):
    """Obtém todos os grupos acessíveis para a sessão informada."""

    url = f'{URL_API_WPP}/{user}/all-groups'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    try:
        response = requests.get(url, headers=headers)

        if response.status_code in [200, 201]:
            response_data = response.json()
            groups = response_data.get('response', [])
            return groups

        logger.error(
            "[get_all_groups] %s | Erro ao obter grupos: %s - %s",
            user,
            response.status_code,
            response.text,
        )
        return []
    except requests.RequestException as exc:
        logger.exception("[get_all_groups] %s | Falha na requisição: %s", user, exc)
        return []
    
# --- Extrai ID dos grupos do WhatsApp para envio das notificações ---
def get_ids_grupos_envio(grupos, adm_envia_alertas, log_path):
    """
    Retorna lista de grupos do WhatsApp em que o USER é admin.
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
                registrar_log(f"Grupo autorizado: {nome} ({group_id})", log_path)
    return grupos_admin

# --- Buscar IDs de grupos a partir de nomes fornecidos ---
def get_group_ids_by_names(token, user, group_names, log_path=None):
    """Retorna IDs dos grupos cujos nomes contenham valores em ``group_names``."""

    try:
        grupos = get_all_groups(token, user)
        if not grupos:
            logger.warning("[get_group_ids_by_names] %s | Nenhum grupo encontrado.", user)
            return []

        nomes_busca = [n.strip().lower() for n in group_names]

        grupos_encontrados = []
        for g in grupos:
            group_id = g.get("id", {}).get("_serialized")
            nome = g.get("name") or g.get("groupMetadata", {}).get("subject") or "Grupo sem nome"

            if nome and any(n in nome.lower() for n in nomes_busca):
                grupos_encontrados.append((group_id, nome))
                if log_path:
                    registrar_log(f"Grupo encontrado: {nome} ({group_id})", log_path)

        if not grupos_encontrados:
            logger.info(
                "[get_group_ids_by_names] %s | Nenhum grupo correspondente encontrado para %s.",
                user,
                group_names,
            )

        return grupos_encontrados

    except Exception as exc:  # noqa: BLE001
        logger.exception("[get_group_ids_by_names] %s | Erro ao buscar grupos: %s", user, exc)
        return []


##### FUNÇÃO PARA ENVIAR MENSAGENS DE STATUS NO WHATSAPP #####
# --- Envia mensagem de texto para o status do WhatsApp ---
def upload_status_sem_imagem(texto_status, usuario, token, log_path):
    url = f"{URL_API_WPP}/{usuario}/send-text-storie"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {"text": texto_status}

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=30)
        ctype = resp.headers.get("content-type", "")
        payload = resp.json() if "application/json" in ctype else resp.text
        ok = (200 <= resp.status_code < 300) and (
            (isinstance(payload, dict) and (payload.get("success") is True or payload.get("status") in ("OK","success","SENT")))
            or (isinstance(payload, str) and "success" in payload.lower())
        )
        if ok:
            registrar_log(f"[OK] Mensagem de status enviada para {usuario}", log_path)
            time.sleep(random.randint(10, 30))
            return True, payload
        else:
            registrar_log(f"[ERRO] {usuario} => status={resp.status_code} payload={payload}", log_path)
            return False, payload
    except Exception as e:
        registrar_log(f"[ERRO] {usuario} => {e}", log_path)
        return False, f"exception: {e}"


# --- Envia imagem com legenda para o status do WhatsApp ---
def upload_imagem_status(imagem, legenda, usuario, token, log_path):
    try:
        # Se for uma URL (http ou https), envia diretamente
        if imagem.startswith("http://") or imagem.startswith("https://"):
            path_param = imagem
        else:
            # Arquivo local — converte para base64 com tipo MIME
            if not os.path.exists(imagem):
                raise FileNotFoundError(f"Arquivo não encontrado: {imagem}")
            mime_type, _ = mimetypes.guess_type(imagem)
            if not mime_type:
                raise ValueError("Tipo MIME não identificado para a imagem.")
            with open(imagem, "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode("utf-8")
            path_param = f"data:{mime_type};base64,{img_base64}"

        url = f"{URL_API_WPP}/{usuario}/send-image-storie"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': 'Bearer ' + token
        }
        body = {"path": path_param, "caption": (legenda or "")}

        resp = requests.post(url, json=body, headers=headers, timeout=60)
        ctype = resp.headers.get("content-type", "")
        payload = resp.json() if "application/json" in ctype else resp.text

        ok = (200 <= resp.status_code < 300) and (
            (isinstance(payload, dict) and (payload.get("success") is True or payload.get("status") in ("OK","success","SENT")))
            or (isinstance(payload, str) and "success" in payload.lower())
        )
        if ok:
            registrar_log(f"[OK] Imagem enviada para {usuario}: {os.path.basename(imagem)}", log_path)
            return True, payload
        else:
            registrar_log(f"[ERRO] {usuario} => status={resp.status_code} payload={payload}", log_path)
            return False, payload
    except Exception as e:
        registrar_log(f"[ERRO] {usuario} => {e}", log_path)
        return False, f"exception: {e}"
