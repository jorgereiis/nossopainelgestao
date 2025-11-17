"""
Credentials Manager - Gerenciamento de Credenciais Reseller (Integrado com Django)

Este módulo fornece funções para:
- Obter credenciais de ContaReseller model
- Gerenciar JWT em ContaReseller.session_data
- Validar e atualizar sessões
- Integração com criptografia Fernet
"""

import os
import json
from typing import Optional, Tuple, Dict, Any
from django.conf import settings
from django.utils import timezone
from . import logger

# Logger para este módulo
log = logger.setup_module_logger('credentials_manager')


def get_reseller_credentials(conta_reseller) -> Tuple[str, str]:
    """
    Extrai credenciais do modelo ContaReseller

    Args:
        conta_reseller: Instância do modelo ContaReseller

    Returns:
        Tupla (email_login, senha_descriptografada)
    """
    from cadastros.utils import decrypt_password

    log.debug(f"Obtendo credenciais da conta reseller ID={conta_reseller.id}")

    email = conta_reseller.email_login
    senha = decrypt_password(conta_reseller.senha_login)

    log.info(f"Credenciais obtidas para conta ID={conta_reseller.id}, email={email}")

    return (email, senha)


def get_capsolver_api_key() -> str:
    """
    Obtém API Key do CapSolver das configurações Django

    Returns:
        String com API Key do CapSolver
    """
    api_key = os.getenv('CAPSOLVER_API_KEY', '')

    if not api_key or not api_key.startswith('CAP-'):
        log.error("CAPSOLVER_API_KEY não configurada ou inválida no .env")
        raise ValueError("CAPSOLVER_API_KEY não configurada no arquivo .env")

    log.debug(f"API Key CapSolver obtida: {api_key[:20]}...")
    return api_key


def get_jwt_from_conta(conta_reseller) -> Optional[str]:
    """
    Obtém JWT armazenado em ContaReseller.session_data

    Args:
        conta_reseller: Instância do modelo ContaReseller

    Returns:
        String do JWT ou None se não existe/inválido
    """
    log.debug(f"Obtendo JWT da conta reseller ID={conta_reseller.id}")

    if not conta_reseller.session_data:
        log.debug("session_data está vazio")
        return None

    try:
        # session_data pode ser string JSON ou dict
        if isinstance(conta_reseller.session_data, str):
            session_data = json.loads(conta_reseller.session_data)
        else:
            session_data = conta_reseller.session_data

        # Verificar se é JWT direto (string) ou objeto com JWT
        if isinstance(session_data, str) and session_data.startswith('eyJ'):
            log.info(f"JWT obtido da conta ID={conta_reseller.id} (formato string)")
            return session_data
        elif isinstance(session_data, dict) and 'jwt' in session_data:
            jwt = session_data['jwt']
            log.info(f"JWT obtido da conta ID={conta_reseller.id} (formato dict)")
            return jwt
        else:
            log.warning(f"session_data existe mas não contém JWT válido")
            return None

    except json.JSONDecodeError as e:
        log.error(f"Erro ao decodificar session_data: {e}")
        return None
    except Exception as e:
        log.error(f"Erro ao obter JWT: {e}")
        return None


def save_jwt_to_conta(conta_reseller, jwt: str, user_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    Salva JWT em ContaReseller.session_data

    Args:
        conta_reseller: Instância do modelo ContaReseller
        jwt: String do token JWT
        user_data: Dados do usuário (opcional, para enriquecimento)

    Returns:
        True se salvou com sucesso
    """
    from .jwt_utils import decode_jwt

    log.debug(f"Salvando JWT na conta reseller ID={conta_reseller.id}")

    try:
        # Decodificar JWT para extrair informações
        payload = decode_jwt(jwt)

        # Preparar dados completos
        session_data = {
            'jwt': jwt,
            'user_id': payload.get('id') if payload else None,
            'user_type': payload.get('type') if payload else None,
            'email': conta_reseller.email_login,
            'issued_at': payload.get('iat') if payload else None,
            'saved_at': timezone.now().isoformat()
        }

        # Adicionar user_data se fornecido
        if user_data:
            session_data['user_data'] = user_data

        # Salvar como JSON
        conta_reseller.session_data = json.dumps(session_data)
        conta_reseller.sessao_valida = True
        conta_reseller.save()

        log.info(f"JWT salvo com sucesso na conta ID={conta_reseller.id}")
        return True

    except Exception as e:
        log.error(f"Erro ao salvar JWT: {e}")
        logger.log_exception(log, e, f"save_jwt_to_conta(conta_id={conta_reseller.id})")
        return False


def invalidate_session(conta_reseller) -> bool:
    """
    Invalida sessão da conta reseller

    Args:
        conta_reseller: Instância do modelo ContaReseller

    Returns:
        True se invalidou com sucesso
    """
    log.debug(f"Invalidando sessão da conta reseller ID={conta_reseller.id}")

    try:
        conta_reseller.sessao_valida = False
        conta_reseller.save()

        log.info(f"Sessão invalidada para conta ID={conta_reseller.id}")
        return True

    except Exception as e:
        log.error(f"Erro ao invalidar sessão: {e}")
        logger.log_exception(log, e, f"invalidate_session(conta_id={conta_reseller.id})")
        return False


def validate_conta_reseller(conta_reseller) -> Tuple[bool, str]:
    """
    Valida se conta reseller está completa e configurada

    Args:
        conta_reseller: Instância do modelo ContaReseller

    Returns:
        Tupla (is_valid, error_message)
    """
    log.debug(f"Validando conta reseller ID={conta_reseller.id}")

    # Verificar usuário de login
    if not conta_reseller.email_login:
        return False, "Usuário de login não configurado"

    # Verificar senha
    if not conta_reseller.senha_login:
        return False, "Senha de login não configurada"

    # Verificar aplicativo
    if not conta_reseller.aplicativo:
        return False, "Aplicativo não configurado"

    log.debug(f"Conta reseller ID={conta_reseller.id} válida")
    return True, ""


def get_or_create_conta_reseller(aplicativo, usuario):
    """
    Obtém ou cria conta reseller para aplicativo e usuário

    Args:
        aplicativo: Instância do modelo Aplicativo
        usuario: Instância do modelo User

    Returns:
        Tupla (conta_reseller, created)
    """
    from cadastros.models import ContaReseller

    log.debug(f"Obtendo/criando conta reseller para app={aplicativo.nome}, user={usuario.username}")

    conta, created = ContaReseller.objects.get_or_create(
        aplicativo=aplicativo,
        usuario=usuario
    )

    if created:
        log.info(f"Conta reseller criada: ID={conta.id}, app={aplicativo.nome}, user={usuario.username}")
    else:
        log.info(f"Conta reseller encontrada: ID={conta.id}, app={aplicativo.nome}, user={usuario.username}")

    return (conta, created)
