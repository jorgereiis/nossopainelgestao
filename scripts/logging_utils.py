"""
Utilitários auxiliares para logging estruturado.

Fornece:
- Decorators para logging automático de funções
- Context managers para logging de blocos
- Funções auxiliares para logs especializados
"""

from __future__ import annotations

import functools
import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from django.utils.timezone import localtime


# ==================== TIPOS ====================

JsonDict = Dict[str, Any]


# ==================== DECORATORS ====================

def log_execution(logger: logging.Logger, level: int = logging.INFO):
    """
    Decorator que loga início e fim de execução de função.

    Args:
        logger: Logger a ser usado
        level: Nível de log (padrão: INFO)

    Exemplo:
        >>> @log_execution(logger)
        ... def processar_dados(usuario):
        ...     # código aqui
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            logger.log(level, f"Iniciando {func_name}")

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.log(level, f"Finalizado {func_name} em {duration:.2f}s")
                return result
            except Exception as exc:
                duration = time.time() - start_time
                logger.exception(
                    f"Erro em {func_name} após {duration:.2f}s: {exc}"
                )
                raise

        return wrapper
    return decorator


def log_execution_with_args(logger: logging.Logger, level: int = logging.DEBUG):
    """
    Decorator que loga início/fim de execução E os argumentos da função.

    Args:
        logger: Logger a ser usado
        level: Nível de log (padrão: DEBUG)

    Exemplo:
        >>> @log_execution_with_args(logger)
        ... def enviar_mensagem(telefone, mensagem):
        ...     # código aqui
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__

            # Formata argumentos para log
            args_repr = [repr(a) for a in args[:3]]  # Limita a 3 para não poluir
            kwargs_repr = {k: repr(v) for k, v in list(kwargs.items())[:3]}

            logger.log(
                level,
                f"Iniciando {func_name} | args={args_repr} kwargs={kwargs_repr}"
            )

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.log(level, f"Finalizado {func_name} em {duration:.2f}s")
                return result
            except Exception as exc:
                duration = time.time() - start_time
                logger.exception(
                    f"Erro em {func_name} após {duration:.2f}s | "
                    f"args={args_repr} kwargs={kwargs_repr}: {exc}"
                )
                raise

        return wrapper
    return decorator


def suppress_exceptions(logger: logging.Logger, default_return=None):
    """
    Decorator que captura exceções, loga e retorna valor padrão.

    Args:
        logger: Logger a ser usado
        default_return: Valor a retornar em caso de exceção

    Exemplo:
        >>> @suppress_exceptions(logger, default_return=[])
        ... def buscar_dados():
        ...     # Se der erro, retorna []
        ...     return fazer_consulta_arriscada()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                logger.exception(f"Exceção suprimida em {func.__name__}: {exc}")
                return default_return

        return wrapper
    return decorator


# ==================== CONTEXT MANAGERS ====================

@contextmanager
def log_block(logger: logging.Logger, description: str, level: int = logging.INFO):
    """
    Context manager para logar início e fim de um bloco de código.

    Args:
        logger: Logger a ser usado
        description: Descrição do bloco
        level: Nível de log (padrão: INFO)

    Exemplo:
        >>> with log_block(logger, "Processamento de mensalidades"):
        ...     processar_mensalidades()
        ...     # código aqui
    """
    logger.log(level, f"Iniciando: {description}")
    start_time = time.time()

    try:
        yield
    except Exception as exc:
        duration = time.time() - start_time
        logger.exception(f"Erro em '{description}' após {duration:.2f}s: {exc}")
        raise
    else:
        duration = time.time() - start_time
        logger.log(level, f"Finalizado: {description} em {duration:.2f}s")


@contextmanager
def log_time(logger: logging.Logger, operation: str, level: int = logging.DEBUG):
    """
    Context manager para medir e logar tempo de execução.

    Args:
        logger: Logger a ser usado
        operation: Nome da operação
        level: Nível de log (padrão: DEBUG)

    Exemplo:
        >>> with log_time(logger, "consulta ao banco"):
        ...     resultado = Cliente.objects.all()
    """
    start_time = time.time()
    yield
    duration = time.time() - start_time
    logger.log(level, f"Tempo de {operation}: {duration:.3f}s")


# ==================== FUNÇÕES AUXILIARES ====================

def registrar_log_json_auditoria(
    arquivo_path: str | Path,
    evento: JsonDict,
    auto_timestamp: bool = True,
) -> None:
    """
    Registra evento de auditoria em formato JSON estruturado.

    Args:
        arquivo_path: Caminho do arquivo de log
        evento: Dicionário com dados do evento
        auto_timestamp: Se True, adiciona timestamp automaticamente

    Exemplo:
        >>> registrar_log_json_auditoria("logs/audit.log", {
        ...     "funcao": "enviar_mensagem",
        ...     "status": "sucesso",
        ...     "usuario": "admin",
        ...     "telefone": "+5583999999999"
        ... })
    """
    try:
        path = Path(arquivo_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        registro = dict(evento or {})

        if auto_timestamp and "timestamp" not in registro:
            registro["timestamp"] = localtime().strftime('%d-%m-%Y %H:%M:%S')

        with path.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    except Exception as exc:
        # Fallback: loga no stderr para não perder a informação
        logging.getLogger(__name__).error(
            "Erro ao registrar log de auditoria: %s", exc, exc_info=exc
        )


def registrar_log_arquivo_customizado(
    arquivo_path: str | Path,
    mensagem: str,
    auto_timestamp: bool = False,
) -> None:
    """
    Registra mensagem em arquivo customizado (compatibilidade com sistema antigo).

    Args:
        arquivo_path: Caminho do arquivo de log
        mensagem: Mensagem a ser registrada
        auto_timestamp: Se True, adiciona timestamp na frente

    Exemplo:
        >>> registrar_log_arquivo_customizado(
        ...     "logs/envios.log",
        ...     "[SUCESSO] Mensagem enviada para +5583999999999"
        ... )
    """
    try:
        path = Path(arquivo_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        linha = mensagem
        if auto_timestamp:
            timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
            linha = f"[{timestamp}] {mensagem}"

        with path.open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")

    except Exception as exc:
        logging.getLogger(__name__).error(
            "Erro ao registrar log customizado: %s", exc, exc_info=exc
        )


def format_exception_for_log(exc: Exception, include_traceback: bool = False) -> str:
    """
    Formata exceção para inclusão em log.

    Args:
        exc: Exceção a ser formatada
        include_traceback: Se True, inclui traceback completo

    Returns:
        String formatada da exceção

    Exemplo:
        >>> try:
        ...     1 / 0
        ... except Exception as e:
        ...     logger.error(f"Erro: {format_exception_for_log(e)}")
    """
    exc_type = type(exc).__name__
    exc_msg = str(exc)

    if include_traceback:
        import traceback
        tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return f"{exc_type}: {exc_msg}\n{tb}"

    return f"{exc_type}: {exc_msg}"


def log_dict_pretty(logger: logging.Logger, level: int, title: str, data: dict) -> None:
    """
    Loga dicionário de forma legível (útil para debug).

    Args:
        logger: Logger a ser usado
        level: Nível de log
        title: Título do log
        data: Dicionário a ser logado

    Exemplo:
        >>> log_dict_pretty(logger, logging.DEBUG, "Payload da API", {
        ...     "phone": "+5583999999999",
        ...     "message": "Teste"
        ... })
    """
    formatted = json.dumps(data, ensure_ascii=False, indent=2)
    logger.log(level, f"{title}:\n{formatted}")


def get_current_timestamp(formato: str = "%d-%m-%Y %H:%M:%S") -> str:
    """
    Retorna timestamp atual formatado (usando timezone do Django).

    Args:
        formato: Formato do timestamp (padrão: "%d-%m-%Y %H:%M:%S")

    Returns:
        Timestamp formatado

    Exemplo:
        >>> timestamp = get_current_timestamp()
        >>> print(timestamp)  # "26-10-2025 15:30:45"
    """
    return localtime().strftime(formato)


# ==================== HELPERS ESPECÍFICOS ====================

def log_envio_mensagem(
    logger: logging.Logger,
    sucesso: bool,
    tipo_envio: str,
    usuario: str,
    telefone: str,
    tentativa: Optional[int] = None,
    max_tentativas: Optional[int] = None,
    erro: Optional[str] = None,
) -> None:
    """
    Loga envio de mensagem WhatsApp de forma padronizada.

    Args:
        logger: Logger a ser usado
        sucesso: Se o envio foi bem-sucedido
        tipo_envio: Tipo do envio (vencimentos, atrasos, etc)
        usuario: Usuário que enviou
        telefone: Telefone destinatário
        tentativa: Número da tentativa (opcional)
        max_tentativas: Total de tentativas (opcional)
        erro: Mensagem de erro (se falhou)

    Exemplo:
        >>> log_envio_mensagem(
        ...     logger,
        ...     sucesso=True,
        ...     tipo_envio="vencimentos",
        ...     usuario="admin",
        ...     telefone="+5583999999999"
        ... )
    """
    if sucesso:
        logger.info(
            "Mensagem enviada com sucesso | tipo=%s usuario=%s telefone=%s",
            tipo_envio, usuario, telefone
        )
    else:
        tentativa_info = ""
        if tentativa and max_tentativas:
            tentativa_info = f" tentativa={tentativa}/{max_tentativas}"

        erro_msg = erro or "Erro desconhecido"

        logger.error(
            "Falha ao enviar mensagem | tipo=%s usuario=%s telefone=%s%s erro=%s",
            tipo_envio, usuario, telefone, tentativa_info, erro_msg
        )


def log_sessao_wpp(
    logger: logging.Logger,
    acao: str,
    usuario: str,
    sucesso: bool,
    detalhes: Optional[str] = None,
) -> None:
    """
    Loga ações relacionadas a sessões WhatsApp.

    Args:
        logger: Logger a ser usado
        acao: Ação realizada (iniciar, fechar, verificar, etc)
        usuario: Usuário da sessão
        sucesso: Se a ação foi bem-sucedida
        detalhes: Detalhes adicionais (opcional)

    Exemplo:
        >>> log_sessao_wpp(logger, "verificar", "admin", sucesso=True)
    """
    nivel = logging.INFO if sucesso else logging.WARNING
    msg = f"Sessão WPP - {acao} | usuario={usuario}"

    if detalhes:
        msg += f" | {detalhes}"

    logger.log(nivel, msg)


def log_job_scheduler(
    logger: logging.Logger,
    job_name: str,
    acao: str,
    duracao: Optional[float] = None,
    erro: Optional[Exception] = None,
) -> None:
    """
    Loga ações de jobs do scheduler.

    Args:
        logger: Logger a ser usado
        job_name: Nome do job
        acao: Ação (iniciado, finalizado, erro)
        duracao: Duração em segundos (opcional)
        erro: Exceção se houver erro (opcional)

    Exemplo:
        >>> log_job_scheduler(logger, "backup_db", "iniciado")
        >>> # ... executa job ...
        >>> log_job_scheduler(logger, "backup_db", "finalizado", duracao=5.2)
    """
    if acao == "iniciado":
        logger.info("Job iniciado | nome=%s", job_name)
    elif acao == "finalizado":
        duracao_str = f" duracao={duracao:.2f}s" if duracao else ""
        logger.info("Job finalizado | nome=%s%s", job_name, duracao_str)
    elif acao == "erro":
        erro_msg = format_exception_for_log(erro) if erro else "Erro desconhecido"
        logger.error("Erro no job | nome=%s erro=%s", job_name, erro_msg)


# ==================== COMPATIBILIDADE COM SISTEMA ANTIGO ====================

def criar_registrar_log_compativel(usuario: str, log_directory: str):
    """
    Cria função compatível com o sistema antigo de logs.

    Args:
        usuario: Nome do usuário
        log_directory: Diretório base dos logs

    Returns:
        Função que registra log no formato antigo

    Exemplo:
        >>> registrar_log = criar_registrar_log_compativel("admin", "logs/Envios")
        >>> registrar_log("[SUCESSO] Mensagem enviada")
    """
    def registrar_log(mensagem: str) -> None:
        """Registra log no arquivo do usuário (compatibilidade)."""
        if not log_directory:
            return

        log_filename = Path(log_directory) / f"{usuario}.log"
        registrar_log_arquivo_customizado(log_filename, mensagem)

    return registrar_log
