"""Views para a página de Chat do WhatsApp (Admin only)."""

import base64
import json
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views import View
from django.views.decorators.http import require_POST, require_GET

from cadastros.models import SessaoWpp
from cadastros.services.logging_config import get_logger
from wpp.api_connection import (
    get_all_chats,
    get_messages_in_chat,
    load_earlier_messages,
    get_profile_picture,
    send_text_message,
    send_image_message,
    send_file_message,
    send_audio_message,
    send_reply_message,
    download_media,
)

logger = get_logger(__name__, log_file="logs/WhatsApp/chat.log")


class SuperuserRequiredMixin(UserPassesTestMixin):
    """Mixin que permite acesso apenas para superusuários."""
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        return JsonResponse({"error": "Acesso negado. Apenas administradores."}, status=403)


def _get_session_and_token(user):
    """Obtém sessão ativa e token do usuário."""
    session_name = user.username
    sessao = SessaoWpp.objects.filter(usuario=session_name, is_active=True).first()
    if not sessao:
        return None, None, "Sessão WhatsApp não conectada"
    return session_name, sessao.token, None


class ChatPageView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """Renderiza a página principal do chat."""

    def get(self, request):
        session_name, token, error = _get_session_and_token(request.user)

        context = {
            "page_group": "admin",
            "page": "chat-whatsapp",
            "sessao_ativa": token is not None,
            "error": error,
        }
        return render(request, "pages/chat-whatsapp.html", context)


def _get_chat_id(chat):
    """Extrai o ID do chat (pode ser string ou objeto)."""
    chat_id = chat.get("id", "")
    if isinstance(chat_id, dict):
        return chat_id.get("_serialized", "") or chat_id.get("user", "")
    return str(chat_id) if chat_id else ""


def _is_personal_contact(chat):
    """
    Verifica se o chat é um contato pessoal (não grupo, não broadcast, não status).

    Filtra:
    - @g.us = grupos
    - @broadcast = listas de transmissão
    - status@broadcast = status do WhatsApp
    - @lid = IDs de listas internas
    """
    chat_id = _get_chat_id(chat)
    if not chat_id:
        return False

    # Filtrar grupos, broadcasts, status e listas
    excluded_patterns = ["@g.us", "@broadcast", "status@", "@lid"]
    return not any(pattern in chat_id for pattern in excluded_patterns)


@login_required
def api_chat_list(request):
    """API: Lista todas as conversas (apenas contatos pessoais)."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Acesso negado"}, status=403)

    session_name, token, error = _get_session_and_token(request.user)
    if error:
        logger.warning("Chat list - sessao nao encontrada: %s", error)
        return JsonResponse({"error": error}, status=400)

    logger.info("Buscando lista de chats para sessao: %s", session_name)
    data, status_code = get_all_chats(session_name, token)
    logger.debug("Resposta da API all-chats: status=%d, data=%s", status_code, str(data)[:500])

    # A API WPPConnect retorna {status, response: [...]} ou diretamente o array
    if isinstance(data, dict):
        # Extrair array do envelope se existir
        chats = data.get("response") or data.get("contacts") or data.get("data") or []
        if not isinstance(chats, list):
            chats = []
    elif isinstance(data, list):
        chats = data
    else:
        chats = []

    # Filtrar apenas contatos pessoais (remover grupos, broadcasts, status)
    total_before = len(chats)
    chats = [chat for chat in chats if _is_personal_contact(chat)]

    logger.info("Retornando %d contatos pessoais (de %d total)", len(chats), total_before)
    return JsonResponse(chats, safe=False, status=200)


@login_required
def api_chat_messages(request, phone):
    """API: Obtém mensagens de uma conversa."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Acesso negado"}, status=403)

    session_name, token, error = _get_session_and_token(request.user)
    if error:
        return JsonResponse({"error": error}, status=400)

    logger.info("Buscando mensagens do chat: %s", phone)
    data, status_code = get_messages_in_chat(session_name, token, phone)
    logger.debug("Resposta da API messages: status=%d, type=%s", status_code, type(data).__name__)
    logger.debug("Resposta BRUTA da API messages: %s", str(data)[:1000])

    # A API WPPConnect retorna {status, response: [...]} ou diretamente o array
    if isinstance(data, dict):
        logger.debug("Data e dict, keys: %s", list(data.keys()))
        # Extrair array do envelope se existir
        messages = data.get("response") or data.get("messages") or data.get("data") or []
        if not isinstance(messages, list):
            logger.warning("messages nao e list: type=%s", type(messages).__name__)
            messages = []
    elif isinstance(data, list):
        messages = data
    else:
        logger.warning("data nao e dict nem list: type=%s", type(data).__name__)
        messages = []

    logger.info("Retornando %d mensagens", len(messages))
    return JsonResponse(messages, safe=False, status=200)


@login_required
def api_load_earlier_messages(request, phone):
    """API: Carrega mensagens mais antigas."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Acesso negado"}, status=403)

    session_name, token, error = _get_session_and_token(request.user)
    if error:
        return JsonResponse({"error": error}, status=400)

    data, status_code = load_earlier_messages(session_name, token, phone)
    return JsonResponse(data, safe=False, status=status_code)


@login_required
def api_profile_picture(request, phone):
    """API: Obtém foto de perfil de um contato."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Acesso negado"}, status=403)

    session_name, token, error = _get_session_and_token(request.user)
    if error:
        return JsonResponse({"error": error}, status=400)

    try:
        data, status_code = get_profile_picture(session_name, token, phone)

        # Extrair URL da foto do envelope da API
        if isinstance(data, dict):
            # A API pode retornar {status, response: {eurl: "..."}} ou diretamente {eurl: "..."}
            response_data = data.get("response") or data
            if isinstance(response_data, dict):
                profile_url = response_data.get("eurl") or response_data.get("profilePicUrl") or ""
                return JsonResponse({"profilePicUrl": profile_url}, status=200)

        return JsonResponse({"profilePicUrl": ""}, status=200)
    except Exception as e:
        logger.warning("Erro ao obter foto de perfil de %s: %s", phone, str(e))
        return JsonResponse({"profilePicUrl": ""}, status=200)


@login_required
@require_POST
def api_send_message(request):
    """API: Envia mensagem de texto."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Acesso negado"}, status=403)

    session_name, token, error = _get_session_and_token(request.user)
    if error:
        return JsonResponse({"error": error}, status=400)

    try:
        body = json.loads(request.body)
        phone = body.get("phone")
        message = body.get("message")
        reply_to = body.get("replyTo")  # ID da mensagem para responder

        if not phone or not message:
            return JsonResponse({"error": "phone e message são obrigatórios"}, status=400)

        if reply_to:
            data, status_code = send_reply_message(session_name, token, phone, message, reply_to)
        else:
            data, status_code = send_text_message(session_name, token, phone, message)

        return JsonResponse(data, status=status_code)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)


@login_required
@require_POST
def api_send_file(request):
    """API: Envia arquivo (imagem, documento, áudio)."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Acesso negado"}, status=403)

    session_name, token, error = _get_session_and_token(request.user)
    if error:
        return JsonResponse({"error": error}, status=400)

    phone = request.POST.get("phone")
    file_type = request.POST.get("type", "file")  # image, file, audio
    caption = request.POST.get("caption", "")

    if not phone:
        return JsonResponse({"error": "phone é obrigatório"}, status=400)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"error": "Nenhum arquivo enviado"}, status=400)

    # Converter para base64
    file_content = uploaded_file.read()
    base64_content = base64.b64encode(file_content).decode("utf-8")
    mime_type = uploaded_file.content_type
    base64_data = f"data:{mime_type};base64,{base64_content}"

    if file_type == "image":
        data, status_code = send_image_message(session_name, token, phone, base64_data, caption)
    elif file_type == "audio":
        data, status_code = send_audio_message(session_name, token, phone, base64_data)
    else:
        data, status_code = send_file_message(session_name, token, phone, base64_data, uploaded_file.name)

    return JsonResponse(data, status=status_code)


@login_required
def api_download_media(request, message_id):
    """API: Baixa mídia de uma mensagem."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Acesso negado"}, status=403)

    session_name, token, error = _get_session_and_token(request.user)
    if error:
        return JsonResponse({"error": error}, status=400)

    logger.info("Download media: %s", message_id)
    data, status_code = download_media(session_name, token, message_id)
    logger.debug("Download media response: status=%d, keys=%s", status_code, list(data.keys()) if isinstance(data, dict) else "not dict")

    if status_code == 200 and isinstance(data, dict):
        # A API retorna base64 no campo 'data'
        base64_data = data.get("data")
        mimetype = data.get("mimetype", "application/octet-stream")

        if base64_data:
            try:
                # Decodificar base64
                binary_content = base64.b64decode(base64_data)
                response = HttpResponse(binary_content, content_type=mimetype)
                # Não forçar download para imagens (permitir exibição inline)
                if mimetype.startswith("image/"):
                    response["Content-Disposition"] = "inline"
                else:
                    response["Content-Disposition"] = f'attachment; filename="{message_id}"'
                return response
            except Exception as e:
                logger.error("Erro ao decodificar base64: %s", str(e))
                return JsonResponse({"error": "Falha ao decodificar mídia"}, status=500)

    error_msg = data.get("error", "Falha ao baixar mídia") if isinstance(data, dict) else "Falha ao baixar mídia"
    return JsonResponse({"error": error_msg}, status=status_code)
