"""
Utilitarios do Painel do Cliente.
"""

import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def validar_recaptcha(recaptcha_response, remote_ip=None):
    """
    Valida a resposta do reCAPTCHA v2.

    Args:
        recaptcha_response: Token retornado pelo widget reCAPTCHA (g-recaptcha-response)
        remote_ip: IP do cliente (opcional, para validacao adicional)

    Returns:
        tuple: (sucesso: bool, mensagem_erro: str ou None)
    """
    if not recaptcha_response:
        return False, "Por favor, confirme que você não é um robô."

    secret_key = getattr(settings, 'RECAPTCHA_PRIVATE_KEY', None)
    if not secret_key:
        # Em modo DEBUG, permite passar sem reCAPTCHA configurado
        if settings.DEBUG:
            logger.warning("[reCAPTCHA] RECAPTCHA_PRIVATE_KEY nao configurada (modo desenvolvimento)")
            return True, None
        else:
            # Em producao, falha se reCAPTCHA nao estiver configurado
            logger.error("[reCAPTCHA] RECAPTCHA_PRIVATE_KEY nao configurada em PRODUCAO!")
            return False, "Erro de configuração do sistema. Contate o suporte."

    try:
        payload = {
            'secret': secret_key,
            'response': recaptcha_response,
        }
        if remote_ip:
            payload['remoteip'] = remote_ip

        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data=payload,
            timeout=10
        )
        result = response.json()

        if result.get('success'):
            return True, None
        else:
            error_codes = result.get('error-codes', [])
            logger.warning(f"[reCAPTCHA] Validacao falhou: {error_codes}")
            return False, "Verificação de seguranca falhou. Tente novamente."

    except requests.RequestException as e:
        logger.error(f"[reCAPTCHA] Erro de conexao: {e}")
        # Em caso de erro de rede, permite passar para nao bloquear usuarios
        return True, None
    except Exception as e:
        logger.exception(f"[reCAPTCHA] Erro inesperado: {e}")
        return True, None


def get_recaptcha_site_key():
    """
    Retorna a chave publica do reCAPTCHA.
    """
    return getattr(settings, 'RECAPTCHA_PUBLIC_KEY', '')
