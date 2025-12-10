"""Views para receber webhooks do WPPConnect."""

import json
import logging
import threading
import time

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from nossopainel.models import SessaoWpp
from nossopainel.services.logging_config import get_logger
from nossopainel.views_sse import push_event_to_session

# Configuração do logger com rotação automática
logger = get_logger(__name__, log_file="logs/WhatsApp/webhook_wpp.log")


@csrf_exempt
@require_POST
def webhook_wppconnect(request):
    """
    Endpoint para receber eventos do WPPConnect.

    Este endpoint recebe notificações push da API WPPConnect sobre mudanças
    de estado das sessões do WhatsApp.

    Eventos tratados:
    - status-find: Mudança de status da sessão (CONNECTED, QRCODE, CLOSED, etc.)
    - qrcode: Novo QR code gerado
    - session-logged / onconnected: Sessão conectada com sucesso
    - session-closed / ondisconnected: Sessão encerrada/desconectada
    - onmessage: Mensagem recebida (para log apenas)

    Returns:
        JsonResponse com status da operação
    """
    # Log do IP de origem para debug
    client_ip = _get_client_ip(request)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error(
            "Webhook recebeu payload inválido | ip=%s",
            client_ip
        )
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    event = payload.get('event', '')
    session = payload.get('session', '')

    logger.info(
        "Webhook recebido | event=%s session=%s ip=%s",
        event,
        session,
        client_ip
    )

    if not session:
        logger.warning("Webhook sem session | event=%s ip=%s", event, client_ip)
        return JsonResponse({"error": "Session not provided"}, status=400)

    # Buscar sessão no banco
    sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()

    # Processar evento
    if event == 'status-find':
        _handle_status_find(payload, sessao, session)

    elif event in ('session-logged', 'onconnected'):
        _handle_connected(sessao, session)

    elif event in ('session-closed', 'ondisconnected'):
        _handle_disconnected(sessao, session)

    elif event == 'qrcode':
        _handle_qrcode(payload, session)

    elif event == 'onmessage':
        _handle_message(payload, session)

    elif event == 'onack':
        _handle_ack(payload, session)

    elif event in ('onmessage-sent', 'onsendmessage'):
        _handle_message_sent(payload, session)

    elif event == 'incomingcall':
        _handle_incoming_call(payload, sessao, session)

    else:
        logger.debug(
            "Evento não tratado | event=%s session=%s",
            event,
            session
        )

    return JsonResponse({"status": "ok"})


def _handle_status_find(payload: dict, sessao, session: str):
    """Trata evento de mudança de status."""
    status = payload.get('status', '')
    logger.info(
        "Status change | session=%s status=%s",
        session,
        status
    )

    if status == 'CLOSED' and sessao:
        sessao.is_active = False
        sessao.save(update_fields=['is_active'])
        logger.info(
            "Sessão marcada como inativa via webhook | session=%s",
            session
        )


def _handle_connected(sessao, session: str):
    """Trata evento de conexão bem-sucedida."""
    logger.info(
        "Sessão conectada via webhook | session=%s",
        session
    )


def _handle_disconnected(sessao, session: str):
    """Trata evento de desconexão."""
    if sessao:
        sessao.is_active = False
        sessao.save(update_fields=['is_active'])
        logger.info(
            "Sessão desconectada via webhook | session=%s",
            session
        )


def _handle_qrcode(payload: dict, session: str):
    """Trata evento de novo QR code."""
    logger.debug(
        "QR Code recebido via webhook | session=%s",
        session
    )


def _handle_message(payload: dict, session: str):
    """Trata evento de mensagem recebida - envia via SSE."""
    message_data = payload.get('data', {}) or payload
    msg_from = message_data.get('from', '') or payload.get('from', '')
    msg_type = message_data.get('type', '') or payload.get('type', '')

    # Extrair nome do contato (pode vir em diferentes campos)
    sender_name = (
        message_data.get('notifyName') or
        message_data.get('pushname') or
        message_data.get('sender', {}).get('pushname') or
        message_data.get('sender', {}).get('name') or
        ''
    )

    logger.info(
        "Nova mensagem recebida | session=%s from=%s type=%s name=%s",
        session,
        msg_from,
        msg_type,
        sender_name
    )

    # Enviar evento SSE para o frontend com dados completos
    push_event_to_session(session, 'new_message', {
        'chatId': msg_from,
        'senderName': sender_name,
        'message': message_data
    })


def _handle_ack(payload: dict, session: str):
    """Trata evento de confirmação de leitura - envia via SSE."""
    ack_data = payload.get('data', {}) or payload
    message_id = ack_data.get('id', {})
    ack_level = ack_data.get('ack', 0)

    # Extrair chatId (para quem a mensagem foi enviada)
    chat_id = ack_data.get('to', '') or ack_data.get('from', '')

    # Extrair ID serializado se for objeto
    if isinstance(message_id, dict):
        message_id = message_id.get('_serialized', '') or message_id.get('id', '')

    logger.debug(
        "ACK recebido | session=%s chatId=%s messageId=%s ack=%s",
        session,
        chat_id,
        str(message_id)[:50],
        ack_level
    )

    # Enviar evento SSE para o frontend
    push_event_to_session(session, 'message_ack', {
        'chatId': chat_id,
        'messageId': message_id,
        'ack': ack_level
    })


def _handle_message_sent(payload: dict, session: str):
    """Trata evento de mensagem enviada confirmada - envia via SSE."""
    message_data = payload.get('data', {}) or payload
    msg_to = message_data.get('to', '') or payload.get('to', '')

    logger.debug(
        "Mensagem enviada confirmada | session=%s to=%s",
        session,
        msg_to
    )

    # Enviar evento SSE para o frontend
    push_event_to_session(session, 'message_sent', {
        'chatId': msg_to,
        'message': message_data
    })


def _should_reject_call(sessao) -> bool:
    """Verifica se deve rejeitar chamada baseado nas configurações da sessão."""
    if not sessao.reject_call_enabled:
        return False

    # Se não tem horários definidos, rejeita sempre
    if not sessao.reject_call_horario_inicio or not sessao.reject_call_horario_fim:
        return True

    # Verificar se está dentro do horário configurado
    from django.utils import timezone
    agora = timezone.localtime().time()
    inicio = sessao.reject_call_horario_inicio
    fim = sessao.reject_call_horario_fim

    # Trata caso de horário que atravessa meia-noite (ex: 22:00 às 06:00)
    if inicio <= fim:
        return inicio <= agora <= fim
    else:
        return agora >= inicio or agora <= fim


def _handle_incoming_call(payload: dict, sessao, session: str):
    """
    Trata evento de chamada recebida.

    Fluxo para GRUPOS:
    1. Rejeita a chamada (sem mensagem, sem marcar não lido)

    Fluxo para CONTATOS:
    1. Rejeita a chamada
    2. Aguarda 2 segundos
    3. Envia mensagem informando que não atendemos chamadas
    4. Aguarda 10 segundos
    5. Marca a conversa como não lida
    """
    from wpp import api_connection

    call_id = payload.get('id', '')
    caller = payload.get('peerJid', '')
    is_group = payload.get('isGroup', False)

    if not sessao:
        logger.warning(
            "Chamada recebida sem sessão ativa | session=%s",
            session
        )
        return

    # Verificar se deve rejeitar chamada (configuração + horário)
    if not _should_reject_call(sessao):
        logger.info(
            "Rejeição de chamadas desativada ou fora do horário | session=%s caller=%s",
            session,
            caller
        )
        return

    token = sessao.token

    # 1. Rejeitar chamada (sempre, grupo ou contato)
    logger.info(
        "Rejeitando chamada | session=%s callId=%s caller=%s is_group=%s",
        session,
        call_id,
        caller,
        is_group
    )
    reject_result, reject_status = api_connection.reject_call(session, token, call_id)

    if reject_status not in (200, 201):
        logger.error(
            "Falha ao rejeitar chamada | session=%s status=%s response=%s",
            session,
            reject_status,
            reject_result
        )

    # Se for grupo, para aqui (sem mensagem, sem marcar não lido)
    if is_group:
        logger.info(
            "Chamada de grupo rejeitada | session=%s caller=%s",
            session,
            caller
        )
        return

    # Se for @lid, para aqui (limitação do WhatsApp - não é possível enviar mensagem)
    if "@lid" in caller:
        logger.info(
            "Chamada @lid rejeitada (sem envio de mensagem - limitação WhatsApp) | session=%s caller=%s",
            session,
            caller
        )
        return

    # 2. Contato direto: executar envio + marcação em thread separada
    def _processo_pos_rejeicao():
        try:
            phone = caller

            # Aguarda 2s antes de enviar mensagem
            time.sleep(2)

            mensagem = (
                "🚫 *NÃO ATENDEMOS CHAMADAS* 🚫\n\n"
                "Estaremos lhe atendendo em alguns instantes.\n\n"
                "Enquanto isso, informe aqui como podemos ajudá-lo(a)."
            )
            msg_result, msg_status = api_connection.send_text_message(
                session, token, phone, mensagem
            )

            if msg_status not in (200, 201):
                logger.error(
                    "Falha ao enviar mensagem pós-chamada | session=%s phone=%s status=%s",
                    session,
                    phone,
                    msg_status
                )

            # Aguarda 10s antes de marcar como não lido
            time.sleep(10)

            unread_result, unread_status = api_connection.mark_chat_unread(
                session, token, phone
            )

            if unread_status not in (200, 201):
                logger.error(
                    "Falha ao marcar conversa como não lida | session=%s phone=%s status=%s",
                    session,
                    phone,
                    unread_status
                )
        except Exception as e:
            logger.error(
                "Erro no processo pós-rejeição | session=%s caller=%s error=%s",
                session,
                caller,
                str(e)
            )

    threading.Thread(target=_processo_pos_rejeicao, daemon=True).start()

    logger.info(
        "Chamada rejeitada com sucesso | session=%s caller=%s",
        session,
        caller
    )


def _get_client_ip(request) -> str:
    """Extrai o IP real do cliente considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        return x_real_ip.strip()
    return request.META.get('REMOTE_ADDR', 'unknown')
