"""
API Client - Cliente para validação de JWT com API Dream TV

Este módulo fornece funções para:
- Validar JWT com API Dream TV
- Obter informações do usuário
- Detectar erros de autenticação (401, 403)
"""

import json
import requests
from typing import Optional, Dict, Any, Tuple
from . import logger

# Configurações da API
API_BASE_URL = 'https://api.dreamtv.life'
DEFAULT_TIMEOUT = 30  # segundos

# Logger para este módulo
log = logger.setup_module_logger('api_client')


def test_jwt_with_api(jwt: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Testa JWT com API Dream TV usando endpoint /reseller

    Args:
        jwt: String do token JWT
        timeout: Timeout em segundos para a requisição

    Returns:
        Tupla (is_valid, user_data, error_message)
        - is_valid: True se JWT é válido (200), False se inválido (401/403)
        - user_data: Dict com dados do usuário se válido, None caso contrário
        - error_message: Mensagem de erro se houver, None se sucesso
    """
    # Endpoint para obter perfil do reseller
    url = f'{API_BASE_URL}/reseller'
    log.debug(f"Testando JWT com API: GET {url}")

    try:
        # Headers conforme documentação (Authorization sem "Bearer")
        headers = {
            'Authorization': jwt,
            'Content-Type': 'application/json'
        }

        # Fazer requisição GET
        logger.log_api_request(log, 'GET', url)
        response = requests.get(url, headers=headers, timeout=timeout)

        # Verificar status
        if response.status_code == 200:
            # JWT válido
            data = response.json()

            if data.get('error') is False:
                # Sucesso - extrair dados do reseller
                message = data.get('message', {})
                user_data = message.get('reseller')

                # DEBUG: Logging detalhado da resposta
                log.debug(f"Resposta completa da API: {json.dumps(data, indent=2)}")
                log.debug(f"user_data extraído (reseller): {user_data}")
                log.debug(f"Tipo de user_data: {type(user_data)}")
                if user_data and isinstance(user_data, dict):
                    log.debug(f"Chaves disponíveis em user_data: {list(user_data.keys())}")

                user_name = user_data.get('name', 'N/A') if user_data else 'N/A'
                log.info(f"JWT válido - Usuário: {user_name}")
                logger.log_api_request(log, 'GET', url, status_code=200)
                return (True, user_data, None)
            else:
                # Erro na resposta mas status 200
                error_msg = data.get('message', 'Erro desconhecido')
                log.warning(f"API retornou erro na resposta 200: {error_msg}")
                logger.log_api_request(log, 'GET', url, status_code=200, error=error_msg)
                return (False, None, error_msg)

        elif response.status_code == 401:
            # JWT inválido ou expirado
            log.warning("JWT inválido ou expirado (401 Unauthorized)")
            logger.log_api_request(log, 'GET', url, status_code=401)
            return (False, None, 'JWT inválido ou expirado (401 Unauthorized)')

        elif response.status_code == 403:
            # Sem permissão
            log.warning("Sem permissão para acessar recurso (403 Forbidden)")
            logger.log_api_request(log, 'GET', url, status_code=403)
            return (False, None, 'Sem permissão para acessar este recurso (403 Forbidden)')

        else:
            # Outro erro
            error_msg = f'Erro HTTP {response.status_code}'
            log.error(f"Erro HTTP inesperado: {response.status_code}")
            logger.log_api_request(log, 'GET', url, status_code=response.status_code)
            return (False, None, error_msg)

    except requests.exceptions.Timeout:
        error_msg = f'Timeout após {timeout} segundos'
        log.error(error_msg)
        logger.log_api_request(log, 'GET', url, error=error_msg)
        return (False, None, error_msg)

    except requests.exceptions.ConnectionError as e:
        error_msg = 'Erro de conexão com API'
        log.error(f"{error_msg}: {str(e)}")
        logger.log_api_request(log, 'GET', url, error=error_msg)
        return (False, None, error_msg)

    except Exception as e:
        error_msg = f'Erro inesperado: {str(e)}'
        log.error(error_msg)
        logger.log_exception(log, e, "test_jwt_with_api")
        logger.log_api_request(log, 'GET', url, error=error_msg)
        return (False, None, error_msg)


def get_user_info(jwt: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[Dict[str, Any]]:
    """
    Obtém informações do usuário usando JWT

    Args:
        jwt: String do token JWT
        timeout: Timeout em segundos

    Returns:
        Dict com informações do usuário ou None se JWT inválido
    """
    log.debug("Obtendo informações do usuário")
    is_valid, user_data, error = test_jwt_with_api(jwt, timeout)

    if is_valid and user_data:
        log.debug(f"Informações do usuário obtidas: {user_data.get('name', 'N/A')}")
        return user_data

    log.warning(f"Não foi possível obter informações do usuário: {error}")
    return None


def validate_jwt(jwt: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """
    Valida JWT de forma simples (retorna apenas True/False)

    Args:
        jwt: String do token JWT
        timeout: Timeout em segundos

    Returns:
        True se JWT é válido, False caso contrário
    """
    log.debug("Validando JWT")
    is_valid, user_data, error = test_jwt_with_api(jwt, timeout)

    if is_valid:
        log.info("JWT validado com sucesso")
    else:
        log.warning(f"JWT inválido: {error}")

    return is_valid


def needs_refresh(jwt: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """
    Verifica se JWT precisa ser renovado

    Args:
        jwt: String do token JWT
        timeout: Timeout em segundos

    Returns:
        True se JWT precisa renovação (401/403), False se ainda válido
    """
    log.debug("Verificando se JWT precisa renovação")
    is_valid, _, error = test_jwt_with_api(jwt, timeout)

    # Se inválido E erro é 401/403, precisa renovar
    if not is_valid and error and ('401' in error or '403' in error):
        log.info(f"JWT precisa renovação: {error}")
        return True

    # Se válido, não precisa renovar
    if is_valid:
        log.debug("JWT ainda válido, não precisa renovação")
        return False

    # Para outros erros (rede, timeout), assumir que NÃO precisa renovar
    log.warning(f"Erro na validação mas não é 401/403: {error}")
    return False
