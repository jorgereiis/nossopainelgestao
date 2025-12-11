"""Views dedicadas à gestão das sessões do WhatsApp na aplicação."""

from __future__ import annotations

import inspect
import os
import sys
import time

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.timezone import localtime

from nossopainel.models import SecretTokenAPI, SessaoWpp
from nossopainel.services.logging_config import get_logger
from wpp.api_connection import (
    check_connection,
    close_session,
    gerar_token,
    logout_session,
    start_session,
    status_session,
)

# Configuração do logger com rotação automática
logger = get_logger(__name__, log_file="logs/WhatsApp/wpp_views.log")


def is_production() -> bool:
    """
    Detecta se o servidor está em produção (gunicorn) ou desenvolvimento (runserver).

    Returns:
        True se estiver rodando com gunicorn (produção)
        False se estiver rodando com runserver (desenvolvimento)
    """
    # Verifica se gunicorn está no nome do executável
    if 'gunicorn' in sys.argv[0].lower():
        return True
    # Verifica se runserver está nos argumentos (Django dev server)
    if any('runserver' in arg for arg in sys.argv):
        return False
    # Fallback: assumir produção se não for runserver
    return True


def get_webhook_url() -> str:
    """
    Retorna a URL do webhook baseada no ambiente de execução.

    Returns:
        URL do webhook (produção ou desenvolvimento)
    """
    if is_production():
        url = os.getenv('WEBHOOK_WPP_URL_PROD', '')
        logger.info(
            "Ambiente PRODUÇÃO | webhook_url=%s",
            url if url else 'não configurada'
        )
        return url
    else:
        url = os.getenv('WEBHOOK_WPP_URL_DEV', '')
        logger.info(
            "Ambiente DESENVOLVIMENTO | webhook_url=%s",
            url[:50] if url else 'não configurada'
        )
        return url


def _verificar_e_renovar_token(sessao, session_name: str, secret: str):
    """
    Verifica se o token da sessão ainda é válido.
    Se inválido (401/403), gera novo token automaticamente.

    Args:
        sessao: Instância de SessaoWpp
        session_name: Nome da sessão (username)
        secret: Token secreto para gerar novo token

    Returns:
        tuple: (token_valido, foi_renovado)
    """
    # Testa se o token atual funciona
    _, status_code = status_session(session_name, sessao.token)

    if status_code in (401, 403):
        # Token expirado/inválido - gerar novo
        logger.info(
            "Token expirado, gerando novo | usuario=%s",
            session_name
        )
        token_data, token_status = gerar_token(session_name, secret)
        if token_status == 201:
            novo_token = token_data.get("token")
            sessao.token = novo_token
            sessao.save(update_fields=["token"])
            logger.info(
                "Token renovado com sucesso | usuario=%s",
                session_name
            )
            return novo_token, True
        logger.error(
            "Falha ao renovar token | usuario=%s status=%d",
            session_name,
            token_status
        )
        return sessao.token, False

    return sessao.token, False


@login_required
def whatsapp(request):
    """Renderiza o painel de acompanhamento da integração WhatsApp."""
    return render(request, "pages/whatsapp.html")


@login_required
def conectar_wpp(request):
    """
    Gera ou recupera token, solicita QR Code e marca a sessão como ativa.

    Requer requisição POST e retorna resposta JSON sobre o progresso da conexão.
    """
    func_name = inspect.currentframe().f_code.co_name
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido."}, status=405)

    usuario = request.user
    session = usuario.username

    try:
        # Buscar primeiro superusuário disponível (pode haver mais de um)
        user_admin = User.objects.filter(is_superuser=True).first()
        if not user_admin:
            raise User.DoesNotExist("Nenhum superusuário encontrado")
        secret = SecretTokenAPI.objects.get(usuario=user_admin).token
    except (User.DoesNotExist, SecretTokenAPI.DoesNotExist):
        logger.error(
            "Token secreto de integração não encontrado | func=%s usuario=%s",
            func_name,
            usuario
        )
        return JsonResponse({"erro": "Token secreto de integração não encontrado."}, status=500)

    sessao_existente = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
    if sessao_existente:
        # Verificar e renovar token se necessário
        token, foi_renovado = _verificar_e_renovar_token(sessao_existente, session, secret)
        if foi_renovado:
            logger.info(
                "Token renovado automaticamente | func=%s usuario=%s session=%s",
                func_name,
                usuario,
                session
            )
        else:
            logger.info(
                "Token reutilizado | func=%s usuario=%s session=%s",
                func_name,
                usuario,
                session
            )
    else:
        token_data, token_status = gerar_token(session, secret)
        if token_status != 201:
            logger.error(
                "Falha ao gerar token | func=%s usuario=%s session=%s status=%d",
                func_name,
                usuario,
                session,
                token_status
            )
            return JsonResponse({"erro": "Falha ao gerar token de autenticação."}, status=400)
        token = token_data.get("token")
        logger.info(
            "Novo token gerado | func=%s usuario=%s session=%s",
            func_name,
            usuario,
            session
        )

    # Obter URL do webhook baseada no ambiente (produção/desenvolvimento)
    webhook_url = get_webhook_url()

    init_data, _ = start_session(session, token, webhook_url=webhook_url)
    logger.debug(
        "Resposta de start-session | func=%s usuario=%s data=%s",
        func_name,
        usuario,
        init_data
    )

    # Se start_session já retornou o QR code, usar diretamente
    if init_data.get("qrcode"):
        logger.info(
            "QRCode recebido de start_session | func=%s usuario=%s session=%s",
            func_name,
            usuario,
            session
        )
        SessaoWpp.objects.update_or_create(
            usuario=session,
            defaults={
                "user": usuario,
                "token": token,
                "dt_inicio": timezone.now(),
                "is_active": True,
            },
        )
        return JsonResponse(
            {"qrcode": init_data.get("qrcode"), "status": "QRCODE", "session": session, "token": token}
        )

    status_data, status_code = status_session(session, token)
    status = status_data.get("status")
    if status == "CONNECTED":
        logger.info(
            "Sessão já conectada | func=%s usuario=%s session=%s",
            func_name,
            usuario,
            session
        )
        SessaoWpp.objects.update_or_create(
            usuario=session,
            defaults={
                "user": usuario,
                "token": token,
                "dt_inicio": timezone.now(),
                "is_active": True,
            },
        )
        return JsonResponse({"status": "CONNECTED", "mensagem": "Sessão já está conectada.", "session": session})

    max_tentativas = 5
    intervalo_segundos = 2
    for tentativa in range(max_tentativas):
        status_data, status_code = status_session(session, token)
        status = status_data.get("status")
        logger.debug(
            "Aguardando QRCode | func=%s usuario=%s tentativa=%d/%d status=%s",
            func_name,
            usuario,
            tentativa + 1,
            max_tentativas,
            status
        )
        if status == "QRCODE":
            break
        time.sleep(intervalo_segundos)
    else:
        logger.error(
            "QRCode não gerado | func=%s usuario=%s tentativas=%d",
            func_name,
            usuario,
            max_tentativas
        )
        return JsonResponse(
            {
                "erro": "Não foi possível gerar QRCode. Tente novamente em instantes.",
                "detalhes": status_data,
            },
            status=400,
        )

    SessaoWpp.objects.update_or_create(
        usuario=session,
        defaults={
            "user": usuario,
            "token": token,
            "dt_inicio": timezone.now(),
            "is_active": True,
        },
    )
    logger.info(
        "Sessão salva com sucesso | func=%s usuario=%s session=%s",
        func_name,
        usuario,
        session
    )

    return JsonResponse(
        {"qrcode": status_data.get("qrcode"), "status": status_data.get("status"), "session": session, "token": token}
    )


@login_required
def status_wpp(request):
    """Retorna o status atual da sessão do usuário autenticado."""
    usuario = request.user
    session = usuario.username

    sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
    if not sessao:
        return JsonResponse({"status": "DISCONNECTED", "message": "Sessão não encontrada"}, status=404)

    token = sessao.token
    dados_status, status_code = status_session(session, token)

    if status_code != 200:
        return JsonResponse({"status": "ERRO", "message": "Falha ao obter status"}, status=500)

    return JsonResponse(
        {
            "status": dados_status.get("status"),
            "qrcode": dados_status.get("qrcode"),
            "session": session,
            "version": dados_status.get("version"),
        }
    )


@login_required
def check_connection_wpp(request):
    """Efetua um ping na API para validar se a sessão segue ativa."""
    usuario = request.user
    session = usuario.username

    sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
    if not sessao:
        return JsonResponse({"status": False, "message": "Sessão não encontrada"}, status=404)

    token = sessao.token
    dados, status_code = check_connection(session, token)

    return JsonResponse(dados, status=status_code)


@login_required
def desconectar_wpp(request):
    """Solicita logout junto à API e marca a sessão local como inativa."""
    if request.method == "POST":
        usuario = request.user
        session = usuario.username

        sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
        if not sessao:
            return JsonResponse({"erro": "Sessão não encontrada"}, status=404)

        token = sessao.token
        resp_data, resp_status = logout_session(session, token)

        if resp_data.get("status") is True:
            sessao.is_active = False
            sessao.save()

        return JsonResponse(resp_data, status=resp_status)

    return JsonResponse({"erro": "Método não permitido."}, status=405)


@login_required
def cancelar_sessao_wpp(request):
    """
    Força o encerramento da sessão corrente, tratando respostas inconsistentes.

    Ideal para casos em que a API está instável, mas a sessão precisa ser resetada.
    """
    func_name = inspect.currentframe().f_code.co_name

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido."}, status=405)

    usuario = request.user
    session = usuario.username

    sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
    if not sessao:
        logger.warning(
            "Sessão não encontrada para cancelamento | func=%s usuario=%s",
            func_name,
            usuario
        )
        return JsonResponse({"erro": "Sessão não encontrada"}, status=404)

    token = sessao.token
    try:
        resp_data, resp_status = close_session(session, token)

        if isinstance(resp_data, dict) and "status" in resp_data:
            logger.info(
                "Sessão cancelada | func=%s usuario=%s status=%s",
                func_name,
                usuario,
                resp_data.get("status")
            )

            sessao.is_active = False
            sessao.save()

            return JsonResponse(
                {
                    "status": resp_data.get("status", False),
                    "message": resp_data.get("message", "Sessão encerrada com falha não crítica."),
                    "handled": True,
                },
                status=200,
            )

        raise ValueError("Resposta da API não é um JSON válido")

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Exceção ao cancelar sessão | func=%s usuario=%s erro=%s",
            func_name,
            usuario,
            str(exc),
            exc_info=True
        )
        return JsonResponse({"erro": "Erro interno ao cancelar sessão", "detalhes": str(exc)}, status=500)
