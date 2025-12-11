"""Views para Server-Sent Events (SSE) do Chat WhatsApp."""

import json
import queue
import time
from threading import Lock
from django.http import StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from nossopainel.services.logging_config import get_logger

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
                logger.info("Evento %s enviado para usuario=%d", event_type, user_id)
                return True
            except queue.Full:
                logger.warning("Fila cheia para usuario=%d, descartando evento", user_id)
                return False
        return False


def broadcast_event_to_all(event_type: str, data: dict):
    """Envia evento para TODOS os usuários com fila SSE ativa."""
    with _queues_lock:
        sent_count = 0
        for user_id, user_queue in _user_queues.items():
            try:
                user_queue.put_nowait({
                    "type": event_type,
                    "data": data,
                    "timestamp": int(time.time())
                })
                sent_count += 1
            except queue.Full:
                logger.warning("Fila cheia para usuario=%d, descartando evento", user_id)
        if sent_count > 0:
            logger.info("Evento %s enviado para %d usuarios via broadcast", event_type, sent_count)
        return sent_count


def push_event_to_session(session_name: str, event_type: str, data: dict):
    """
    Envia evento para usuários visualizando uma sessão WhatsApp.

    Como o Chat WhatsApp é acessível apenas por superusuários,
    fazemos broadcast para todos os usuários conectados ao SSE.
    Isso garante que admins visualizando o chat recebam os eventos
    independentemente de qual sessão estejam usando.
    """
    # Adicionar session_name aos dados para o frontend poder filtrar se necessário
    data['session'] = session_name

    # Broadcast para todos os usuários conectados ao SSE
    # Isso é seguro porque apenas superusuários acessam a página de chat
    sent = broadcast_event_to_all(event_type, data)

    if sent == 0:
        logger.warning("Nenhum usuario SSE ativo para receber evento %s da sessao %s", event_type, session_name)


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
                    # Aguardar evento com timeout curto (10s) para forçar flush frequente
                    # Django runserver tem buffering, heartbeats frequentes ajudam
                    event = user_queue.get(timeout=10)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Heartbeat para manter conexão viva e forçar flush
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            # Cliente desconectou
            logger.info("SSE desconectado | usuario=%d", user_id)
            remove_user_queue(user_id)

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['X-Accel-Buffering'] = 'no'  # Nginx: desabilitar buffering
    # Nota: Connection é um header hop-by-hop, não pode ser definido em WSGI
    return response
