"""Views para Server-Sent Events (SSE) do Chat WhatsApp."""

import json
import queue
import time
from threading import Lock
from django.http import StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from cadastros.services.logging_config import get_logger

logger = get_logger(__name__, log_file="logs/WhatsApp/sse.log")

# Gerenciador de filas por usuário
_user_queues = {}
_queues_lock = Lock()


def get_user_queue(user_id: int) -> queue.Queue:
    """Obtém ou cria fila de eventos para um usuário."""
    with _queues_lock:
        if user_id not in _user_queues:
            _user_queues[user_id] = queue.Queue(maxsize=100)
            logger.info("Fila SSE criada para usuario=%d", user_id)
        return _user_queues[user_id]


def remove_user_queue(user_id: int):
    """Remove fila de eventos de um usuário (quando desconecta)."""
    with _queues_lock:
        if user_id in _user_queues:
            del _user_queues[user_id]
            logger.info("Fila SSE removida para usuario=%d", user_id)


def push_event_to_user(user_id: int, event_type: str, data: dict):
    """Envia evento para a fila de um usuário específico."""
    with _queues_lock:
        if user_id in _user_queues:
            try:
                _user_queues[user_id].put_nowait({
                    "type": event_type,
                    "data": data,
                    "timestamp": int(time.time())
                })
                logger.debug("Evento %s enviado para usuario=%d", event_type, user_id)
            except queue.Full:
                logger.warning("Fila cheia para usuario=%d, descartando evento", user_id)


def push_event_to_session(session_name: str, event_type: str, data: dict):
    """
    Envia evento para o usuário dono de uma sessão WhatsApp.
    Busca o user via FK na SessaoWpp, ou fallback para username.
    """
    from cadastros.models import SessaoWpp
    from django.contrib.auth.models import User

    # Primeiro, tentar via FK no modelo SessaoWpp
    sessao = SessaoWpp.objects.filter(
        usuario=session_name,
        is_active=True
    ).select_related('user').first()

    if sessao and sessao.user:
        logger.debug("Evento SSE via FK: sessao=%s user_id=%d", session_name, sessao.user.id)
        push_event_to_user(sessao.user.id, event_type, data)
        return

    # Fallback: tentar encontrar user com username igual ao session_name
    try:
        user = User.objects.get(username=session_name)
        push_event_to_user(user.id, event_type, data)
    except User.DoesNotExist:
        logger.warning("Usuario nao encontrado para sessao: %s", session_name)


@login_required
def sse_chat_stream(request):
    """
    Endpoint SSE para receber eventos do chat em tempo real.

    Eventos enviados:
    - new_message: Nova mensagem recebida
    - message_ack: Confirmação de leitura
    - message_sent: Mensagem enviada confirmada
    - chat_update: Atualização na lista de chats
    - connected: Confirmação de conexão SSE
    """
    user_id = request.user.id
    logger.info("SSE conectado | usuario=%d", user_id)

    def event_stream():
        user_queue = get_user_queue(user_id)

        # Enviar evento de conexão
        yield f"data: {json.dumps({'type': 'connected', 'userId': user_id})}\n\n"

        try:
            while True:
                try:
                    # Aguardar evento com timeout (30s = heartbeat)
                    event = user_queue.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Heartbeat para manter conexão viva
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            # Cliente desconectou
            logger.info("SSE desconectado | usuario=%d", user_id)
            remove_user_queue(user_id)

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Nginx: desabilitar buffering
    return response
