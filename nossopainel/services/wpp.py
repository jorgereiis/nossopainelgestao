"""Serviços de apoio para envio de mensagens via integração WhatsApp."""

from __future__ import annotations

import os
import random
import time
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

import requests
from django.utils.timezone import localtime

logger = logging.getLogger(__name__)


def _sanitize_response(response: Any, max_length: int = 500) -> Any:
    """
    Sanitiza respostas para evitar que HTML de páginas de erro seja registrado.

    - Se for dict, retorna como está
    - Se for string HTML, extrai informações úteis (status code, mensagem)
    - Se for string longa, trunca
    """
    if response is None:
        return None

    if isinstance(response, dict):
        return response

    if isinstance(response, str):
        response_lower = response.lower()
        # Detecta se é uma página HTML de erro
        if '<!doctype' in response_lower or '<html' in response_lower:
            # Tenta extrair informações úteis do HTML de erro
            error_info = {"tipo": "html_error_page"}

            # Extrai o título/código de erro comum (Cloudflare, Nginx, etc.)
            if 'gateway time-out' in response_lower or '504' in response:
                error_info["codigo"] = 504
                error_info["mensagem"] = "Gateway time-out"
            elif 'bad gateway' in response_lower or '502' in response:
                error_info["codigo"] = 502
                error_info["mensagem"] = "Bad Gateway"
            elif 'service unavailable' in response_lower or '503' in response:
                error_info["codigo"] = 503
                error_info["mensagem"] = "Service Unavailable"
            elif 'not found' in response_lower or '404' in response:
                error_info["codigo"] = 404
                error_info["mensagem"] = "Not Found"
            elif 'cloudflare' in response_lower:
                error_info["origem"] = "Cloudflare"
                error_info["mensagem"] = "Erro de proxy Cloudflare"
            else:
                error_info["mensagem"] = "Página de erro HTML recebida"

            return error_info

        # Para strings não-HTML, trunca se muito longa
        if len(response) > max_length:
            return response[:max_length] + "... [truncado]"

    return response


JsonDict = Dict[str, Any]
AuditCallback = Callable[[JsonDict], None]
LogWriter = Callable[[str], None]


@dataclass(frozen=True)
class LogTemplates:
    """Modela o conjunto de templates de log utilizados nos envios."""

    success: str
    failure: str
    invalid: str


@dataclass
class MessageSendConfig:
    """
    Representa a configuração completa para envio de uma mensagem.

    Inclui informações da sessão, destinatário, templates de log e ganchos de auditoria.
    """

    usuario: str
    token: str
    telefone: str
    mensagem: str
    tipo_envio: str
    cliente: str
    log_writer: LogWriter
    log_templates: LogTemplates
    is_group: bool = False
    max_attempts: int = 2
    retry_wait: Tuple[float, float] = (5.0, 10.0)
    audit_callback: Optional[AuditCallback] = None
    audit_base_payload: Optional[JsonDict] = None

    def build_audit_payload(self) -> JsonDict:
        """
        Monta o payload base que será enviado ao callback de auditoria.

        Retorna:
            Dicionário com dados do envio, combinado com o conteúdo adicional definido pelo chamador.
        """
        payload: JsonDict = {
            "usuario": self.usuario,
            "cliente": self.cliente,
            "telefone": self.telefone,
            "tipo_envio": self.tipo_envio,
            "mensagem": self.mensagem,
        }
        if self.audit_base_payload:
            payload.update(self.audit_base_payload)
        return payload


@dataclass
class MessageSendResult:
    """Descreve o resultado final do envio, incluindo tentativas e respostas da API."""

    success: bool
    status_code: Optional[int]
    response: Any
    attempts: int
    error: Optional[str] = None
    reason: Optional[str] = None


def _get_base_url() -> str:
    """
    Recupera a URL base da API a partir das variáveis de ambiente.

    Levanta:
        RuntimeError: caso a variável não esteja definida.
    """
    base_url = os.getenv("URL_API_WPP")
    if not base_url:
        raise RuntimeError("URL_API_WPP environment variable is not set.")
    return base_url.rstrip("/")


def send_raw_message(
    usuario: str,
    token: str,
    telefone: str,
    mensagem: str,
    *,
    is_group: bool = False,
) -> Tuple[int, Any]:
    """
    Envia a mensagem diretamente à API do WhatsApp e retorna status/resposta.

    Retorna:
        Tupla contendo o código HTTP e o JSON/texto devolvido pela API.
    """
    url = f"{_get_base_url()}/{usuario}/send-message"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    body = {"phone": telefone, "message": mensagem, "isGroup": is_group}

    response = requests.post(url, headers=headers, json=body)
    try:
        payload = response.json()
    except ValueError:
        # Sanitiza para evitar propagar HTML de páginas de erro
        payload = _sanitize_response(response.text)
    return response.status_code, payload


def send_message(config: MessageSendConfig) -> MessageSendResult:
    """
    Realiza o envio com tratamento de tentativas, logging e auditoria.

    Parâmetros:
        config: Instância com todas as informações necessárias para o envio.

    Retorna:
        Estrutura com o resultado final (sucesso ou falha) e metadados da chamada.
    """
    timestamp_fmt = "%d-%m-%Y %H:%M:%S"
    timestamp = localtime().strftime(timestamp_fmt)

    if not config.telefone:
        log_line = config.log_templates.invalid.format(
            timestamp, config.tipo_envio.upper(), config.usuario, config.cliente
        )
        config.log_writer(log_line)
        if config.audit_callback:
            payload = config.build_audit_payload()
            payload.update(
                {
                    "status": "cancelado_sem_telefone",
                    "motivo": "telefone_nao_informado",
                }
            )
            config.audit_callback(payload)
        return MessageSendResult(
            success=False,
            status_code=None,
            response=None,
            attempts=0,
            reason="missing_phone",
        )

    attempts = 0
    last_status: Optional[int] = None
    last_response: Any = None
    last_error: Optional[str] = None

    for attempts in range(1, config.max_attempts + 1):
        timestamp = localtime().strftime(timestamp_fmt)
        try:
            status_code, response_payload = send_raw_message(
                config.usuario,
                config.token,
                config.telefone,
                config.mensagem,
                is_group=config.is_group,
            )
            last_status = status_code
            last_response = response_payload
            error_message = None

            # Detectar sessão inativa no WPPCONNECT (404)
            # Retorna imediatamente sem retry - não adianta tentar novamente
            if status_code == 404:
                error_msg = ""
                if isinstance(response_payload, dict):
                    error_msg = response_payload.get("message", "")

                if "não está ativa" in error_msg or "Disconnected" in str(response_payload):
                    logger.warning(
                        f"Sessão {config.usuario} com problema no WPPCONNECT (404) - "
                        f"não realizará retry, tentará no próximo horário"
                    )

                    log_line = config.log_templates.failure.format(
                        timestamp,
                        config.tipo_envio.upper(),
                        config.usuario,
                        config.cliente,
                        404,
                        attempts,
                        "Sessão WhatsApp desconectada no servidor - sem retry",
                    )
                    config.log_writer(log_line)

                    if config.audit_callback:
                        payload = config.build_audit_payload()
                        payload.update(
                            {
                                "status": "falha",
                                "tentativa": attempts,
                                "http_status": 404,
                                "erro": "session_disconnected_wppconnect",
                                "response": response_payload,
                            }
                        )
                        config.audit_callback(payload)

                    # NÃO marcar sessão como inativa no Django
                    # Após rebuild do container WPPCONNECT, a sessão volta a funcionar
                    return MessageSendResult(
                        success=False,
                        status_code=404,
                        response=response_payload,
                        attempts=attempts,
                        error="Sessão desconectada no WPPCONNECT",
                        reason="session_disconnected_wppconnect",
                    )

        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            last_status = getattr(response, "status_code", None)
            try:
                last_response = response.json() if response else None
            except (ValueError, AttributeError):
                # Sanitiza para evitar registrar HTML de páginas de erro (ex: Cloudflare 504)
                last_response = _sanitize_response(getattr(response, "text", None))
            error_message = str(exc)
        except RuntimeError as exc:
            last_status = None
            last_response = None
            error_message = str(exc)

        if last_status in (200, 201):
            log_line = config.log_templates.success.format(
                timestamp, config.tipo_envio.upper(), config.usuario, config.telefone
            )
            config.log_writer(log_line)
            if config.audit_callback:
                payload = config.build_audit_payload()
                payload.update(
                    {
                        "status": "sucesso",
                        "tentativa": attempts,
                        "http_status": last_status,
                        "response": last_response,
                    }
                )
                config.audit_callback(payload)
            return MessageSendResult(
                success=True,
                status_code=last_status,
                response=last_response,
                attempts=attempts,
            )

        if error_message is None:
            if isinstance(last_response, dict):
                # Suporta tanto respostas da API quanto dicts sanitizados de HTML
                error_message = last_response.get("message") or last_response.get("mensagem", "Erro desconhecido")
            else:
                error_message = str(last_response)
        last_error = error_message

        log_line = config.log_templates.failure.format(
            timestamp,
            config.tipo_envio.upper(),
            config.usuario,
            config.cliente,
            last_status if last_status is not None else "N/A",
            attempts,
            error_message,
        )
        config.log_writer(log_line)

        if config.audit_callback:
            payload = config.build_audit_payload()
            payload.update(
                {
                    "status": "falha",
                    "tentativa": attempts,
                    "http_status": last_status,
                    "erro": error_message,
                    "response": last_response,
                }
            )
            config.audit_callback(payload)

        if attempts < config.max_attempts:
            wait_min, wait_max = config.retry_wait
            time.sleep(random.uniform(wait_min, wait_max))

    return MessageSendResult(
        success=False,
        status_code=last_status,
        response=last_response,
        attempts=attempts,
        error=last_error,
        reason="max_retries_exceeded",
    )


def get_active_token(usuario: str) -> Optional[str]:
    """
    Retorna o token ativo associado ao usuário informado, se existir.

    Parâmetros:
        usuario: Identificador da sessão persistida.
    """
    from nossopainel.models import SessaoWpp  # Import local para evitar ciclo.

    session = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    return session.token if session else None
