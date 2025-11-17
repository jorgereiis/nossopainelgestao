"""
Logger Module - Sistema centralizado de logging para Automação Reseller

Este módulo fornece logging configurável integrado com o sistema Django:
- Múltiplos níveis (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Output para console e arquivo
- Rotação automática de logs
- Formatação detalhada
- Integração com estrutura Django existente
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from django.conf import settings

# Diretório de logs (usar estrutura Django)
LOGS_DIR = os.path.join(settings.BASE_DIR, 'logs', 'Reseller')

# Garantir que diretório existe
os.makedirs(LOGS_DIR, exist_ok=True)

# Configurações padrão
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB (mesmo padrão do Django)
DEFAULT_BACKUP_COUNT = 5  # Manter 5 backups

# Aliases de níveis de log
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL


def get_logger(name, log_file=None, level=None, console=True):
    """
    Cria e configura um logger

    Args:
        name: Nome do logger (geralmente __name__ do módulo)
        log_file: Nome do arquivo de log (sem path, vai para logs/Reseller/)
        level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console: Se True, também exibe logs no console

    Returns:
        Logger configurado
    """
    # Criar logger
    logger = logging.getLogger(name)

    # Evitar duplicação de handlers
    if logger.handlers:
        return logger

    # Definir nível
    if level is None:
        level = DEFAULT_LOG_LEVEL
    logger.setLevel(level)

    # Prevent propagation to parent loggers (avoid duplicate log entries)
    logger.propagate = False

    # Formato detalhado
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-25s | %(funcName)-25s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler para arquivo (com rotação)
    if log_file:
        log_path = os.path.join(LOGS_DIR, log_file)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)  # Arquivo sempre captura tudo
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Handler para console
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)

        # Formato mais simples para console
        console_formatter = logging.Formatter(
            '%(levelname)-8s | %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


def get_automation_logger(user=None, log_level=None):
    """
    Cria logger específico para automação de reseller (integrado com Django)

    Args:
        user: Instância do usuário Django (opcional, para log contextual)
        log_level: Nível de log (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Logger configurado para automação
    """
    # Determinar nível de log
    level = log_level if log_level else DEFAULT_LOG_LEVEL

    # Nome do arquivo de log
    log_file = "automation.log"

    # Criar logger
    logger_name = f'reseller_automation'
    if user:
        logger_name += f'.user_{user.id}'

    logger = get_logger(logger_name, log_file, level=level, console=False)

    # Log inicial
    if user:
        logger.info("=" * 80)
        logger.info(f"[USER:{user.username}] Sessão de automação iniciada")
        logger.info(f"Nível de log: {logging.getLevelName(level)}")
        logger.info("=" * 80)

    return logger


def setup_module_logger(module_name, parent_logger_name='reseller_automation'):
    """
    Cria logger para um módulo/biblioteca

    Args:
        module_name: Nome do módulo (ex: 'jwt_utils', 'api_client')
        parent_logger_name: Nome do logger pai

    Returns:
        Logger configurado
    """
    # Usar hierarquia de loggers
    full_name = f"{parent_logger_name}.{module_name}"

    logger = logging.getLogger(full_name)

    # Herda configuração do pai
    # Não precisa adicionar handlers (herda do pai)

    return logger


def log_exception(logger, exception, context=""):
    """
    Loga uma exceção com contexto completo

    Args:
        logger: Logger instance
        exception: Exceção capturada
        context: Contexto adicional sobre onde ocorreu
    """
    if context:
        logger.error(f"EXCEÇÃO em {context}: {type(exception).__name__}: {str(exception)}")
    else:
        logger.error(f"EXCEÇÃO: {type(exception).__name__}: {str(exception)}")

    logger.debug("Stack trace:", exc_info=True)


def log_function_call(logger, func_name, **kwargs):
    """
    Loga chamada de função com parâmetros

    Args:
        logger: Logger instance
        func_name: Nome da função
        **kwargs: Parâmetros da função
    """
    params_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.debug(f"Chamando {func_name}({params_str})")


def log_api_request(logger, method, url, status_code=None, error=None):
    """
    Loga requisição de API

    Args:
        logger: Logger instance
        method: Método HTTP (GET, POST, etc)
        url: URL da requisição
        status_code: Código de status da resposta
        error: Mensagem de erro se houver
    """
    if error:
        logger.error(f"API {method} {url} - ERRO: {error}")
    elif status_code:
        if status_code >= 400:
            logger.warning(f"API {method} {url} - Status: {status_code}")
        else:
            logger.info(f"API {method} {url} - Status: {status_code}")
    else:
        logger.debug(f"API {method} {url} - Iniciando requisição")


def log_jwt_operation(logger, operation, success=True, details=""):
    """
    Loga operação com JWT

    Args:
        logger: Logger instance
        operation: Tipo de operação (load, save, decode, validate)
        success: Se operação foi bem-sucedida
        details: Detalhes adicionais
    """
    status = "SUCESSO" if success else "FALHA"
    msg = f"JWT {operation.upper()}: {status}"

    if details:
        msg += f" - {details}"

    if success:
        logger.debug(msg)
    else:
        logger.warning(msg)


def log_browser_action(logger, action, details=""):
    """
    Loga ação do navegador/Selenium

    Args:
        logger: Logger instance
        action: Ação realizada (navigate, click, fill, etc)
        details: Detalhes da ação
    """
    msg = f"Browser: {action}"
    if details:
        msg += f" - {details}"

    logger.debug(msg)


def log_capsolver_event(logger, event, details=""):
    """
    Loga evento do CapSolver

    Args:
        logger: Logger instance
        event: Evento (task_created, polling, solved, error)
        details: Detalhes do evento
    """
    msg = f"CapSolver: {event}"
    if details:
        msg += f" - {details}"

    if event == "error":
        logger.error(msg)
    elif event == "solved":
        logger.info(msg)
    else:
        logger.debug(msg)
