"""
JWT Utilities - Funções para manipulação de tokens JWT

Este módulo fornece utilitários para:
- Decodificar payloads JWT
- Validar estrutura de tokens
- Calcular idade de tokens
"""

import json
import base64
from datetime import datetime
from typing import Optional, Dict, Any
from . import logger

# Logger para este módulo
log = logger.setup_module_logger('jwt_utils')


def decode_jwt(jwt: str) -> Optional[Dict[str, Any]]:
    """
    Decodifica o payload de um JWT (sem validar assinatura)

    Args:
        jwt: String do token JWT

    Returns:
        Dict com o payload decodificado ou None se inválido
    """
    log.debug("Decodificando JWT payload")

    try:
        # JWT tem 3 partes separadas por '.'
        parts = jwt.split('.')
        if len(parts) != 3:
            log.warning(f"JWT inválido: esperado 3 partes, encontrado {len(parts)}")
            return None

        # Payload é a segunda parte
        payload = parts[1]

        # Adicionar padding se necessário
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding

        # Decodificar base64
        decoded_bytes = base64.b64decode(payload)
        decoded_str = decoded_bytes.decode('utf-8')

        # Parse JSON
        payload_data = json.loads(decoded_str)

        log.debug(f"JWT decodificado com sucesso: type={payload_data.get('type')}, id={payload_data.get('id')}")
        logger.log_jwt_operation(log, 'decode', success=True, details=f"user_id={payload_data.get('id')}")
        return payload_data

    except Exception as e:
        log.error(f"Erro ao decodificar JWT: {str(e)}")
        logger.log_exception(log, e, "decode_jwt")
        return None


def validate_jwt_structure(jwt: str) -> bool:
    """
    Valida estrutura básica de um JWT

    Args:
        jwt: String do token JWT

    Returns:
        True se estrutura é válida, False caso contrário
    """
    log.debug("Validando estrutura do JWT")

    try:
        # JWT deve ter 3 partes
        parts = jwt.split('.')
        if len(parts) != 3:
            log.warning(f"Estrutura inválida: esperado 3 partes, encontrado {len(parts)}")
            return False

        # Todas as partes devem ser base64url válidas
        for i, part in enumerate(parts):
            if not part:
                log.warning(f"Estrutura inválida: parte {i} está vazia")
                return False

        # Tentar decodificar payload
        payload = decode_jwt(jwt)
        if not payload:
            log.warning("Estrutura inválida: payload não pode ser decodificado")
            return False

        # Validar campos obrigatórios para Dream TV
        required_fields = ['type', 'id', 'iat']
        for field in required_fields:
            if field not in payload:
                log.warning(f"Estrutura inválida: campo obrigatório '{field}' não encontrado")
                return False

        log.debug("Estrutura do JWT válida")
        logger.log_jwt_operation(log, 'validate', success=True, details="estrutura OK")
        return True

    except Exception as e:
        log.error(f"Erro ao validar estrutura do JWT: {str(e)}")
        logger.log_exception(log, e, "validate_jwt_structure")
        return False


def get_jwt_age_hours(jwt: str) -> Optional[float]:
    """
    Calcula idade do JWT em horas desde emissão

    Args:
        jwt: String do token JWT

    Returns:
        Idade em horas ou None se não conseguir calcular
    """
    log.debug("Calculando idade do JWT")

    try:
        payload = decode_jwt(jwt)
        if not payload or 'iat' not in payload:
            log.warning("Não foi possível calcular idade: payload inválido ou sem campo 'iat'")
            return None

        issued_at = payload['iat']
        current_timestamp = datetime.now().timestamp()

        age_seconds = current_timestamp - issued_at
        age_hours = age_seconds / 3600

        log.debug(f"Idade do JWT: {age_hours:.2f} horas")
        return age_hours

    except Exception as e:
        log.error(f"Erro ao calcular idade do JWT: {str(e)}")
        logger.log_exception(log, e, "get_jwt_age_hours")
        return None


def extract_user_info(jwt: str) -> Optional[Dict[str, Any]]:
    """
    Extrai informações do usuário do JWT

    Args:
        jwt: String do token JWT

    Returns:
        Dict com informações do usuário ou None se inválido
    """
    log.debug("Extraindo informações do usuário do JWT")

    try:
        payload = decode_jwt(jwt)
        if not payload:
            log.warning("Não foi possível extrair informações: JWT inválido")
            return None

        user_info = {
            'id': payload.get('id'),
            'type': payload.get('type'),
            'issued_at': payload.get('iat'),
            'email': payload.get('email'),
            'name': payload.get('name')
        }

        log.debug(f"Informações extraídas: user_id={user_info['id']}, type={user_info['type']}")
        return user_info

    except Exception as e:
        log.error(f"Erro ao extrair informações do usuário: {str(e)}")
        logger.log_exception(log, e, "extract_user_info")
        return None
