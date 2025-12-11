"""Cliente auxiliar para interação com a API WPPConnect utilizada pelo sistema."""

import base64
import logging
import mimetypes
import os
import random
import sys
import time
from typing import Optional

import requests
from pathlib import Path

# Adiciona o caminho para imports do sistema centralizado de logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nossopainel.services.logging import append_line
from nossopainel.services.logging_config import get_wpp_logger

URL_API_WPP = os.getenv("URL_API_WPP")
MEU_NUM_CLARO = os.getenv("MEU_NUM_CLARO")

# Timeout padrão para requisições à API WPPConnect (em segundos)
REQUEST_TIMEOUT = 30

##################################################################
################ FUNÇÕES AUXILIARES DE REQUISIÇÃO ################
##################################################################


def _safe_json_response(response):
    """Tenta extrair JSON da resposta, retorna dict de erro se falhar."""
    try:
        return response.json()
    except (ValueError, requests.JSONDecodeError):
        return {
            "status": False,
            "error": "invalid_json",
            "raw_response": response.text[:500] if response.text else ""
        }


def _make_request(method: str, url: str, headers: dict = None, json_data: dict = None, timeout: int = REQUEST_TIMEOUT):
    """
    Executa requisição HTTP com tratamento de erros padronizado.

    Args:
        method: "GET" ou "POST"
        url: URL completa do endpoint
        headers: Headers da requisição
        json_data: Dados JSON para enviar (apenas POST)
        timeout: Timeout em segundos

    Returns:
        tuple: (response_data, status_code)
    """
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=timeout)
        else:
            response = requests.post(url, headers=headers, json=json_data, timeout=timeout)
        return _safe_json_response(response), response.status_code
    except requests.Timeout:
        return {"status": False, "error": "timeout", "message": "API não respondeu a tempo"}, 504
    except requests.RequestException as e:
        return {"status": False, "error": "request_failed", "message": str(e)}, 503


##################################################################
################ FUNÇÃO PARA REGISTRAR LOGS ######################
##################################################################

# Logger configurado com rotação automática
logger = get_wpp_logger()


def registrar_log(mensagem: str, log_path: Optional[str]) -> None:
    """Anexa a ``mensagem`` ao arquivo de log indicado.

    Se log_path for None, a função retorna silenciosamente sem fazer nada.
    """
    if log_path is None:
        return
    append_line(log_path, mensagem)

###################################################
##### FUNÇÕES PARA CONEXÃO COM API WPPCONNECT #####
###################################################

##### FUNÇÕES PARA GERENCIAR SESSÕES DO WHATSAPP #####
# --- Estas funções permitem gerar token, iniciar sessão, verificar status, obter QR code, verificar conexão, fechar sessão e fazer logout. ---
def gerar_token(session: str, secret: str):
    """Gera token de autenticação Bearer para a sessão."""
    url = f"{URL_API_WPP}/{session}/{secret}/generate-token"
    return _make_request("POST", url)

def start_session(session: str, token: str, webhook_url: str = ""):
    """
    Inicia sessão WhatsApp e solicita geração de QR Code.

    Args:
        session: Nome da sessão (username)
        token: Token Bearer de autenticação
        webhook_url: URL para receber eventos via webhook (opcional)
    """
    url = f"{URL_API_WPP}/{session}/start-session"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "webhook": webhook_url,
        "waitQrCode": True
    }
    return _make_request("POST", url, headers=headers, json_data=data)

def status_session(session: str, token: str):
    """Consulta status atual da sessão (CONNECTED, QRCODE, CLOSED, etc.)."""
    url = f"{URL_API_WPP}/{session}/status-session"
    headers = {"Authorization": f"Bearer {token}"}
    return _make_request("GET", url, headers=headers)


def get_qrcode(session: str, token: str):
    """
    Obtém imagem do QR Code em base64.

    Nota: Esta função retorna content binário, não usa _make_request.
    """
    url = f"{URL_API_WPP}/{session}/qrcode-session"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        return response.content, response.status_code
    except requests.Timeout:
        return b"", 504
    except requests.RequestException:
        return b"", 503


def check_connection(session: str, token: str):
    """Ping na API para validar se sessão está ativa."""
    url = f"{URL_API_WPP}/{session}/check-connection-session"
    headers = {"Authorization": f"Bearer {token}"}
    return _make_request("GET", url, headers=headers)

def close_session(session: str, token: str):
    """Encerra sessão sem fazer logout do WhatsApp (mantém vinculação)."""
    url = f"{URL_API_WPP}/{session}/close-session"
    headers = {"Authorization": f"Bearer {token}"}
    return _make_request("POST", url, headers=headers)


def logout_session(session: str, token: str):
    """Logout completo da sessão WhatsApp (remove vinculação)."""
    url = f"{URL_API_WPP}/{session}/logout-session"
    headers = {"Authorization": f"Bearer {token}"}
    return _make_request("POST", url, headers=headers)


def reject_call(session: str, token: str, call_id: str):
    """Rejeita uma chamada recebida no WhatsApp.

    Args:
        session: Nome da sessão
        token: Token de autenticação
        call_id: ID da chamada a ser rejeitada

    Returns:
        tuple: (response_data, status_code)
    """
    url = f"{URL_API_WPP}/{session}/reject-call"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {"callId": call_id}
    return _make_request("POST", url, headers=headers, json_data=data)


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
    """Verifica se o telefone informado está registrado no WhatsApp.

    A validação considera 3 cenários de resposta da API WPPConnect:

    1. Número VÁLIDO e ATIVO:
       - ``id`` é um objeto com ``user``, ``server``, ``_serialized``
       - ``numberExists: true``, ``canReceiveMessage: true``

    2. Número NUNCA EXISTIU (falso positivo da API):
       - ``id`` está AUSENTE (campo não retornado)
       - ``numberExists: true`` (INCORRETO - bug da API)

    3. Número EXISTIU mas FOI DESATIVADO:
       - ``id`` é uma string (ex: "5521972516590@c.us")
       - ``numberExists: false``, ``canReceiveMessage: false``

    Returns
    -------
    dict
        Estrutura com as chaves:
        - ``status`` (bool): True apenas se número realmente existe e pode receber mensagens
        - ``user`` (str ou None): Número corrigido/normalizado pela API
        - ``can_receive`` (bool): Se pode receber mensagens
        - ``error`` (str, opcional): Detalhe textual em caso de erro
    """

    url = f'{URL_API_WPP}/{user}/check-number-status/{telefone}'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code in [200, 201]:
            response_data = response.json()
            resp = response_data.get('response', {})

            number_exists = resp.get('numberExists', False)
            can_receive = resp.get('canReceiveMessage', False)
            id_field = resp.get('id')

            # Validação robusta: o 'id' deve ser um objeto com 'user'
            # Se 'id' está ausente ou é string, o número não é válido
            id_is_valid = isinstance(id_field, dict) and id_field.get('user') is not None
            user_number = id_field.get('user') if id_is_valid else None

            # Número só é considerado válido se:
            # 1. numberExists == True
            # 2. canReceiveMessage == True
            # 3. id é um objeto válido com 'user'
            is_valid = number_exists and can_receive and id_is_valid

            if is_valid:
                logger.info(
                    "[check_number_status] %s | Número VÁLIDO: %s -> %s",
                    user, telefone, user_number
                )
            elif number_exists and not id_is_valid:
                # Falso positivo da API (número nunca existiu)
                logger.warning(
                    "[check_number_status] %s | Falso positivo detectado (sem id válido): %s",
                    user, telefone
                )
            else:
                logger.info(
                    "[check_number_status] %s | Número INVÁLIDO: %s (exists=%s, canReceive=%s)",
                    user, telefone, number_exists, can_receive
                )

            return {
                'status': is_valid,
                'user': user_number,
                'can_receive': can_receive,
                'number_exists_raw': number_exists,  # Valor bruto da API (para debug)
            }

        error_message = f"{response.status_code} - {response.text}"
        logger.error(
            "[check_number_status] %s | Erro ao verificar %s: %s",
            user, telefone, error_message,
        )
        return {'status': False, 'user': None, 'can_receive': False, 'error': error_message}

    except requests.RequestException as exc:
        logger.exception("[check_number_status] %s | Falha de requisição: %s", user, exc)
        return {'status': False, 'user': None, 'can_receive': False, 'error': str(exc)}


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

    telefone = telefone.replace('+', '').replace('@c.us', '').replace('@lid', '').strip()

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


# --- Função para remover todas as labels de um contato ---
def remover_todas_labels_contato(telefone, labels, token, user):
    """Remove todas as labels de um contato no WhatsApp."""
    telefone = telefone.replace('+', '').replace('@c.us', '').replace('@lid', '').strip()

    if not labels:
        return 200, {"status": "skipped", "message": "Nenhuma label para remover"}

    url = f'{URL_API_WPP}/{user}/add-or-remove-label'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    body = {
        "chatIds": [telefone],
        "options": [{"labelId": label, "type": "remove"} for label in labels if label]
    }

    try:
        response = requests.post(url, headers=headers, json=body)
        logger.info(
            "[remover_todas_labels_contato] %s | telefone=%s status=%s",
            user,
            telefone,
            response.status_code
        )

        try:
            response_data = response.json()
        except ValueError:
            response_data = response.text

        return response.status_code, response_data
    except requests.RequestException as exc:
        logger.exception("[remover_todas_labels_contato] %s | Erro: %s", user, exc)
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
def upload_status_sem_imagem(texto_status, usuario, token, log_path=None):
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
def upload_imagem_status(imagem, legenda, usuario, token, log_path=None):
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


##################################################################
################ FUNÇÕES PARA O CHAT WHATSAPP ####################
##################################################################


def get_all_chats(session: str, token: str):
    """
    Lista todas as conversas do WhatsApp.

    Usa o endpoint /list-chats (POST) que é o método atual da API WPPConnect.
    O endpoint /all-chats (GET) está deprecated e pode não retornar todos os chats,
    especialmente aqueles com ID no formato @lid (Linked ID).
    """
    url = f"{URL_API_WPP}/{session}/list-chats"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {"onlyWithUnreadMessage": False}
    return _make_request("POST", url, headers=headers, json_data=data)


def get_messages_in_chat(session: str, token: str, phone: str):
    """
    Obtém mensagens de uma conversa específica.
    Usa get-messages que aceita o phone completo (com @c.us ou @g.us).

    Args:
        session: Nome da sessão
        token: Token de autenticação
        phone: Número do contato (com @c.us ou @g.us para grupos)
    """
    url = f"{URL_API_WPP}/{session}/get-messages/{phone}"
    headers = {"Authorization": f"Bearer {token}"}
    return _make_request("GET", url, headers=headers)


def load_earlier_messages(session: str, token: str, phone: str):
    """Carrega mensagens mais antigas de uma conversa."""
    url = f"{URL_API_WPP}/{session}/load-messages-in-chat/{phone}"
    headers = {"Authorization": f"Bearer {token}"}
    return _make_request("GET", url, headers=headers)


def get_profile_picture(session: str, token: str, phone: str):
    """Obtém URL da foto de perfil de um contato."""
    url = f"{URL_API_WPP}/{session}/profile-pic/{phone}"
    headers = {"Authorization": f"Bearer {token}"}
    return _make_request("GET", url, headers=headers)


def send_text_message(session: str, token: str, phone: str, message: str):
    """Envia mensagem de texto."""
    url = f"{URL_API_WPP}/{session}/send-message"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # A API WPPConnect espera o phone SEM sufixo para contatos, mas COM sufixo para grupos
    if "@g.us" in phone:
        # Grupo - usar ID completo
        data = {"phone": phone, "message": message, "isGroup": True}
    elif "@lid" in phone:
        # Linked ID - tentar enviar COM o sufixo @lid
        data = {"phone": phone, "message": message}
        logger.info("[send_text_message] DEBUG @lid | phone=%s", phone)
    else:
        # Contato normal - remover @c.us
        clean_phone = phone.replace("@c.us", "")
        data = {"phone": clean_phone, "message": message}

    result, status = _make_request("POST", url, headers=headers, json_data=data)

    # DEBUG: Log da resposta
    if "@lid" in phone:
        logger.info("[send_text_message] DEBUG @lid response | status=%s result=%s", status, result)

    return result, status


def _normalize_phone(phone: str) -> tuple:
    """
    Normaliza o número de telefone para a API WPPConnect.

    Returns:
        tuple: (phone_normalizado, is_group)
    """
    if "@g.us" in phone:
        return phone, True
    # Remover @c.us ou @lid para contatos
    return phone.replace("@c.us", "").replace("@lid", ""), False


def send_image_message(session: str, token: str, phone: str, base64_image: str, caption: str = ""):
    """Envia imagem (base64 ou URL)."""
    url = f"{URL_API_WPP}/{session}/send-image"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    normalized_phone, is_group = _normalize_phone(phone)
    data = {"phone": normalized_phone, "base64": base64_image, "caption": caption}
    if is_group:
        data["isGroup"] = True
    return _make_request("POST", url, headers=headers, json_data=data)


def send_file_message(session: str, token: str, phone: str, base64_file: str, filename: str):
    """Envia arquivo (documento, PDF, etc.)."""
    url = f"{URL_API_WPP}/{session}/send-file-base64"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    normalized_phone, is_group = _normalize_phone(phone)
    data = {"phone": normalized_phone, "base64": base64_file, "filename": filename}
    if is_group:
        data["isGroup"] = True
    return _make_request("POST", url, headers=headers, json_data=data)


def send_audio_message(session: str, token: str, phone: str, base64_audio: str):
    """Envia mensagem de áudio."""
    url = f"{URL_API_WPP}/{session}/send-voice-base64"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    normalized_phone, is_group = _normalize_phone(phone)
    data = {"phone": normalized_phone, "base64Ptt": base64_audio}
    if is_group:
        data["isGroup"] = True
    return _make_request("POST", url, headers=headers, json_data=data)


def send_reply_message(session: str, token: str, phone: str, message: str, message_id: str):
    """Responde a uma mensagem específica."""
    url = f"{URL_API_WPP}/{session}/send-reply"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    normalized_phone, is_group = _normalize_phone(phone)
    data = {"phone": normalized_phone, "message": message, "messageId": message_id}
    if is_group:
        data["isGroup"] = True
    return _make_request("POST", url, headers=headers, json_data=data)


def download_media(session: str, token: str, message_id: str):
    """
    Baixa mídia de uma mensagem (imagem, áudio, documento).

    A API WPPConnect retorna JSON com dados base64:
    {"status": "success", "response": {"mimetype": "...", "data": "base64..."}}

    Returns:
        tuple: (data_dict, status_code) onde data_dict contém 'mimetype' e 'data' (base64)
    """
    url = f"{URL_API_WPP}/{session}/get-media-by-message/{message_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=60)  # Timeout maior para mídia

        if response.status_code == 200:
            try:
                json_data = response.json()
                # Extrair dados do envelope da API
                media_data = json_data.get("response") or json_data
                return media_data, 200
            except (ValueError, requests.JSONDecodeError):
                # Se não for JSON, retornar como binário
                return {"data": base64.b64encode(response.content).decode("utf-8")}, 200

        return {"error": f"HTTP {response.status_code}"}, response.status_code
    except requests.Timeout:
        return {"error": "timeout"}, 504
    except requests.RequestException as e:
        return {"error": str(e)}, 503


def send_seen(session: str, token: str, phone: str):
    """
    Marca conversa como lida (envia confirmação de visualização).

    Isso sincroniza o status de leitura com o WhatsApp no celular,
    marcando todas as mensagens do chat como lidas.

    Args:
        session: Nome da sessão
        token: Token de autenticação
        phone: ID do chat (número@c.us ou grupo@g.us)

    Returns:
        tuple: (response_data, status_code)
    """
    url = f"{URL_API_WPP}/{session}/send-seen"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {"phone": phone}
    return _make_request("POST", url, headers=headers, json_data=data)


def mark_chat_unread(session: str, token: str, phone: str):
    """
    Marca conversa como não lida.

    Args:
        session: Nome da sessão
        token: Token de autenticação
        phone: ID do chat (número@c.us, número@lid ou grupo@g.us)

    Returns:
        tuple: (response_data, status_code)
    """
    url = f"{URL_API_WPP}/{session}/mark-unseen"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Para @lid, tentar COM o sufixo; para @c.us, remover
    if "@lid" in phone:
        # Tentar com @lid
        logger.info("[mark_chat_unread] DEBUG @lid | phone=%s", phone)
    elif "@g.us" not in phone:
        # Contato normal - remover @c.us
        phone = phone.replace("@c.us", "")

    data = {"phone": phone}
    result, status = _make_request("POST", url, headers=headers, json_data=data)

    # DEBUG: Log da resposta
    if "@lid" in phone or status not in (200, 201):
        logger.info("[mark_chat_unread] DEBUG response | phone=%s status=%s result=%s", phone, status, result)

    return result, status


def get_phone_from_lid(session: str, token: str, lid: str):
    """
    Tenta obter o número de telefone real a partir de um @lid.

    O formato @lid é usado pelo WhatsApp Multi-Device e não é um número
    de telefone válido. Esta função usa o endpoint /contact/{lid} para
    obter informações do contato, incluindo o número real.

    Args:
        session: Nome da sessão
        token: Token de autenticação
        lid: ID no formato número@lid

    Returns:
        tuple: (phone_number ou None, status_code)
    """
    # Usar endpoint /contact/{lid} para obter informações do contato
    url = f"{URL_API_WPP}/{session}/contact/{lid}"
    headers = {"Authorization": f"Bearer {token}"}
    data, status = _make_request("GET", url, headers=headers)

    # DEBUG: Log completo da resposta
    logger.info(
        "[get_phone_from_lid] DEBUG | url=%s status=%s response=%s",
        url,
        status,
        data
    )

    if status == 200 and data:
        response = data.get("response", {})
        if isinstance(response, dict):
            # Tentar extrair phoneNumber (estrutura do wa-js)
            phone_number = response.get("phoneNumber", {})
            if isinstance(phone_number, dict):
                phone = phone_number.get("_serialized", "") or phone_number.get("id", "")
                if phone:
                    return phone.replace("@c.us", ""), status

            # Fallback: tentar campo id.user ou number
            id_obj = response.get("id", {})
            if isinstance(id_obj, dict):
                phone = id_obj.get("user", "")
                if phone:
                    return phone, status

            # Fallback: campo number direto
            phone = response.get("number", "")
            if phone:
                return phone, status

    return None, status
