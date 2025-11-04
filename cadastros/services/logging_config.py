"""
Configuração centralizada de logging para todo o sistema.

Este módulo fornece:
- Formatadores padronizados
- Handlers com rotação automática
- Factory de loggers configurados
- Templates de mensagens comuns

Uso:
    from cadastros.services.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("Mensagem informativa")
    logger.error("Mensagem de erro", extra={"usuario": "admin", "telefone": "+5583999999999"})
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# ==================== CONSTANTES ====================

# Formatos de log
FORMATO_CONSOLE = "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
FORMATO_ARQUIVO = "[%(asctime)s] [%(levelname)-8s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
FORMATO_ARQUIVO_SIMPLES = "[%(asctime)s] [%(levelname)-8s] %(message)s"
FORMATO_TIMESTAMP = "%d-%m-%Y %H:%M:%S"

# Configurações de rotação
MAX_BYTES_PER_FILE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5  # 5 arquivos históricos

# Diretório base de logs
BASE_LOG_DIR = Path("logs")


# ==================== FORMATADORES ====================

def get_console_formatter() -> logging.Formatter:
    """Retorna formatador para logs de console."""
    return logging.Formatter(FORMATO_CONSOLE, FORMATO_TIMESTAMP)


def get_file_formatter(detailed: bool = True) -> logging.Formatter:
    """
    Retorna formatador para logs de arquivo.

    Args:
        detailed: Se True, inclui nome da função e linha. Se False, formato simples.
    """
    formato = FORMATO_ARQUIVO if detailed else FORMATO_ARQUIVO_SIMPLES
    return logging.Formatter(formato, FORMATO_TIMESTAMP)


# ==================== HANDLERS ====================

def get_rotating_file_handler(
    log_path: str | Path,
    max_bytes: int = MAX_BYTES_PER_FILE,
    backup_count: int = BACKUP_COUNT,
    level: int = logging.DEBUG,
    detailed: bool = True,
) -> RotatingFileHandler:
    """
    Cria um RotatingFileHandler configurado.

    Args:
        log_path: Caminho do arquivo de log
        max_bytes: Tamanho máximo por arquivo (padrão: 10MB)
        backup_count: Número de arquivos de backup (padrão: 5)
        level: Nível mínimo de log (padrão: DEBUG)
        detailed: Se True, inclui detalhes da função/linha

    Returns:
        RotatingFileHandler configurado
    """
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        filename=str(path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(get_file_formatter(detailed=detailed))

    return handler


def get_console_handler(level: int = logging.INFO) -> logging.StreamHandler:
    """
    Cria um StreamHandler para console configurado.

    Args:
        level: Nível mínimo de log para console (padrão: INFO)

    Returns:
        StreamHandler configurado
    """
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(get_console_formatter())

    return handler


# ==================== FACTORY DE LOGGERS ====================

def get_logger(
    name: str,
    log_file: Optional[str | Path] = None,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    propagate: bool = False,
) -> logging.Logger:
    """
    Cria ou retorna um logger configurado.

    Args:
        name: Nome do logger (geralmente __name__)
        log_file: Caminho do arquivo de log (opcional)
        console_level: Nível mínimo para console (padrão: INFO)
        file_level: Nível mínimo para arquivo (padrão: DEBUG)
        propagate: Se True, propaga para logger pai (padrão: False)

    Returns:
        Logger configurado

    Exemplo:
        >>> logger = get_logger(__name__, log_file="logs/meu_modulo.log")
        >>> logger.info("Operação concluída")
        >>> logger.debug("Detalhes técnicos", extra={"usuario": "admin"})
    """
    logger = logging.getLogger(name)

    # Evita duplicação de handlers se logger já existe
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = propagate

    # Handler de console
    logger.addHandler(get_console_handler(level=console_level))

    # Handler de arquivo (se especificado)
    if log_file:
        logger.addHandler(
            get_rotating_file_handler(
                log_path=log_file,
                level=file_level,
            )
        )

    return logger


def get_scheduler_logger() -> logging.Logger:
    """
    Retorna logger específico para o scheduler.

    Configuração:
    - Console: INFO e superior
    - Arquivo: DEBUG e superior com rotação
    """
    return get_logger(
        name="Scheduler",
        log_file=BASE_LOG_DIR / "Scheduler" / "scheduler.log",
        console_level=logging.INFO,
        file_level=logging.DEBUG,
    )


def get_audit_logger() -> logging.Logger:
    """
    Retorna logger específico para auditoria.

    Configuração:
    - Sem console (apenas arquivo)
    - Arquivo: DEBUG e superior com rotação
    """
    logger = logging.getLogger("Audit")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Apenas arquivo, sem console
    logger.addHandler(
        get_rotating_file_handler(
            log_path=BASE_LOG_DIR / "Audit" / "envios_wpp.log",
            level=logging.DEBUG,
            detailed=False,  # Logs de auditoria não precisam de detalhes da função
        )
    )

    return logger


def get_wpp_logger() -> logging.Logger:
    """
    Retorna logger específico para operações de WhatsApp.

    Configuração:
    - Console: INFO e superior
    - Arquivo: DEBUG e superior com rotação
    """
    return get_logger(
        name="WhatsApp",
        log_file=BASE_LOG_DIR / "WhatsApp" / "wpp.log",
        console_level=logging.INFO,
        file_level=logging.DEBUG,
    )


def get_groups_logger() -> logging.Logger:
    """
    Retorna logger específico para envios em grupos.

    Configuração:
    - Console: INFO e superior
    - Arquivo: DEBUG e superior com rotação
    """
    return get_logger(
        name="Groups",
        log_file=BASE_LOG_DIR / "Envios grupos" / "envios.log",
        console_level=logging.INFO,
        file_level=logging.DEBUG,
    )


def get_dns_logger() -> logging.Logger:
    """
    Retorna logger específico para monitoramento DNS/Canais.

    Configuração:
    - Console: INFO e superior
    - Arquivo: DEBUG e superior com rotação
    """
    return get_logger(
        name="DNS",
        log_file=BASE_LOG_DIR / "DNS" / "monitoring.log",
        console_level=logging.INFO,
        file_level=logging.DEBUG,
    )


def get_m3u8_logger() -> logging.Logger:
    """
    Retorna logger específico para operações M3U8.

    Configuração:
    - Console: INFO e superior
    - Arquivo: DEBUG e superior com rotação
    """
    return get_logger(
        name="M3U8",
        log_file=BASE_LOG_DIR / "M3U8" / "processing.log",
        console_level=logging.INFO,
        file_level=logging.DEBUG,
    )


def get_telegram_logger() -> logging.Logger:
    """
    Retorna logger específico para integração Telegram.

    Configuração:
    - Console: INFO e superior
    - Arquivo: DEBUG e superior com rotação
    """
    return get_logger(
        name="Telegram",
        log_file=BASE_LOG_DIR / "TelegramConnection" / "telegram_connection.log",
        console_level=logging.INFO,
        file_level=logging.DEBUG,
    )


def get_reseller_logger() -> logging.Logger:
    """
    Retorna logger específico para automação de painéis reseller.

    Configuração:
    - Console: INFO e superior
    - Arquivo: DEBUG e superior com rotação
    - Usado para login manual, migração DNS, e operações Playwright

    Exemplo:
        >>> logger = get_reseller_logger()
        >>> logger.info("Iniciando migração DNS", extra={"usuario": "admin", "tarefa_id": 123})
        >>> logger.error("Falha no login", extra={"aplicativo": "DreamTV", "erro": "timeout"})
    """
    return get_logger(
        name="ResellerAutomation",
        log_file=BASE_LOG_DIR / "Reseller" / "automation.log",
        console_level=logging.INFO,
        file_level=logging.DEBUG,
    )


# ==================== TEMPLATES DE MENSAGENS ====================

class LogTemplates:
    """Templates padronizados para mensagens de log comuns."""

    # Envios de mensagens
    ENVIO_SUCESSO = "Mensagem enviada | tipo=%s usuario=%s telefone=%s"
    ENVIO_FALHA = "Falha ao enviar | tipo=%s usuario=%s telefone=%s tentativa=%d/%d erro=%s"
    ENVIO_IGNORADO_DIARIO = "Envio ignorado (já enviado hoje) | usuario=%s telefone=%s"
    ENVIO_IGNORADO_MENSAL = "Envio ignorado (já enviado este mês) | usuario=%s telefone=%s tipo=%s"

    # Validações
    TELEFONE_INVALIDO = "Telefone inválido | tipo=%s usuario=%s telefone=%s"
    NUMERO_NAO_WHATSAPP = "Número não está no WhatsApp | usuario=%s telefone=%s"

    # Sessões
    SESSAO_INDISPONIVEL = "Sessão WPP indisponível | usuario=%s"
    SESSAO_TOKEN_AUSENTE = "Token não encontrado para sessão | usuario=%s"

    # Dados
    DADOS_BANCARIOS_AUSENTES = "Dados bancários não encontrados | usuario=%s"
    MENSALIDADE_NAO_ENCONTRADA = "Mensalidade não encontrada | cliente=%s mensalidade_id=%s"

    # Scheduler
    JOB_INICIADO = "Job iniciado | nome=%s"
    JOB_FINALIZADO = "Job finalizado | nome=%s duracao=%.2fs"
    JOB_ERRO = "Erro no job | nome=%s erro=%s"

    # Locks
    LOCK_ADQUIRIDO = "Lock adquirido | usuario=%s tipo=%s"
    LOCK_JA_TRAVADO = "Lock já travado por outro processo | usuario=%s tipo=%s"
    LOCK_LIBERADO = "Lock liberado | usuario=%s tipo=%s"

    # API
    API_REQUEST = "Requisição API | endpoint=%s method=%s"
    API_RESPONSE = "Resposta API | endpoint=%s status=%d"
    API_ERROR = "Erro na API | endpoint=%s status=%d erro=%s"


# ==================== FUNÇÕES AUXILIARES ====================

def log_exception(logger: logging.Logger, message: str, **kwargs) -> None:
    """
    Loga uma exceção com contexto adicional.

    Args:
        logger: Logger a ser usado
        message: Mensagem descritiva
        **kwargs: Contexto adicional (será incluído em extra)

    Exemplo:
        >>> try:
        ...     operacao_perigosa()
        ... except Exception:
        ...     log_exception(logger, "Falha na operação", usuario="admin", operacao="delete")
    """
    logger.exception(message, extra=kwargs)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **context
) -> None:
    """
    Loga uma mensagem com contexto estruturado.

    Args:
        logger: Logger a ser usado
        level: Nível de log (logging.DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Mensagem principal
        **context: Contexto adicional (chave=valor)

    Exemplo:
        >>> log_with_context(
        ...     logger, logging.INFO,
        ...     "Mensagem enviada com sucesso",
        ...     usuario="admin",
        ...     telefone="+5583999999999",
        ...     tipo_envio="vencimentos"
        ... )
    """
    logger.log(level, message, extra=context)


# ==================== CONFIGURAÇÃO GLOBAL ====================

def configure_root_logger(level: int = logging.WARNING) -> None:
    """
    Configura o logger raiz para evitar logs duplicados.

    Args:
        level: Nível mínimo para o logger raiz (padrão: WARNING)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove handlers existentes
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Adiciona apenas console handler básico
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(get_console_formatter())
    root_logger.addHandler(console)


# ==================== INICIALIZAÇÃO ====================

# Configura logger raiz na importação
configure_root_logger()
