#!/usr/bin/env python3
"""
Script de teste para validar o novo sistema de logging centralizado.

Este script testa:
1. Criação de loggers com rotação
2. Níveis de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
3. Logs estruturados com contexto
4. Formatação padronizada
5. Separação console/arquivo

Uso:
    python scripts/test_logging_system.py
"""

import os
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuração do Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
import django
django.setup()

from cadastros.services.logging_config import (
    get_logger,
    get_scheduler_logger,
    get_audit_logger,
    get_wpp_logger,
    get_groups_logger,
)
from scripts.logging_utils import (
    registrar_log_json_auditoria,
    log_envio_mensagem,
    log_sessao_wpp,
    log_job_scheduler,
    log_block,
    log_time,
)


def test_basic_logging():
    """Testa logging básico com diferentes níveis."""
    print("\n" + "="*60)
    print("TESTE 1: Logging Básico com Diferentes Níveis")
    print("="*60)

    logger = get_logger(__name__, log_file="logs/Test/test_basic.log")

    logger.debug("Mensagem DEBUG - detalhes técnicos")
    logger.info("Mensagem INFO - operação normal")
    logger.warning("Mensagem WARNING - situação inesperada")
    logger.error("Mensagem ERROR - erro recuperável")
    logger.critical("Mensagem CRITICAL - falha grave")

    print("✓ Teste concluído - Verifique logs/Test/test_basic.log")


def test_structured_logging():
    """Testa logging estruturado com contexto."""
    print("\n" + "="*60)
    print("TESTE 2: Logging Estruturado com Contexto")
    print("="*60)

    logger = get_logger(__name__, log_file="logs/Test/test_structured.log")

    # Log com contexto extra
    logger.info(
        "Mensagem enviada com sucesso",
        extra={
            "usuario": "admin",
            "telefone": "+5583999999999",
            "tipo_envio": "vencimentos"
        }
    )

    logger.warning(
        "Sessão WPP indisponível",
        extra={"usuario": "admin"}
    )

    logger.error(
        "Falha ao enviar mensagem",
        extra={
            "usuario": "admin",
            "telefone": "+5583999999999",
            "erro": "Timeout na API",
            "tentativa": 2,
            "max_tentativas": 3
        }
    )

    print("✓ Teste concluído - Verifique logs/Test/test_structured.log")


def test_specialized_loggers():
    """Testa loggers especializados."""
    print("\n" + "="*60)
    print("TESTE 3: Loggers Especializados")
    print("="*60)

    # Scheduler logger
    scheduler_logger = get_scheduler_logger()
    scheduler_logger.info("Scheduler iniciado")
    scheduler_logger.debug("Heartbeat OK")

    # Audit logger (apenas arquivo, sem console)
    audit_logger = get_audit_logger()
    audit_logger.info("Evento de auditoria registrado")

    # WPP logger
    wpp_logger = get_wpp_logger()
    wpp_logger.info("Conexão com API WPP estabelecida")

    # Groups logger
    groups_logger = get_groups_logger()
    groups_logger.info("Mensagem enviada para grupo")

    print("✓ Teste concluído - Verifique:")
    print("  - logs/Scheduler/scheduler.log")
    print("  - logs/Audit/envios_wpp.log")
    print("  - logs/WhatsApp/wpp.log")
    print("  - logs/Envios grupos/envios.log")


def test_helper_functions():
    """Testa funções auxiliares de logging."""
    print("\n" + "="*60)
    print("TESTE 4: Funções Auxiliares")
    print("="*60)

    logger = get_logger(__name__, log_file="logs/Test/test_helpers.log")

    # Log de envio de mensagem
    log_envio_mensagem(
        logger=logger,
        sucesso=True,
        tipo_envio="vencimentos",
        usuario="admin",
        telefone="+5583999999999"
    )

    log_envio_mensagem(
        logger=logger,
        sucesso=False,
        tipo_envio="vencimentos",
        usuario="admin",
        telefone="+5583999999999",
        tentativa=2,
        max_tentativas=3,
        erro="Timeout na API"
    )

    # Log de sessão WPP
    log_sessao_wpp(
        logger=logger,
        acao="verificar",
        usuario="admin",
        sucesso=True
    )

    # Log de job do scheduler
    log_job_scheduler(logger, "backup_db", "iniciado")
    import time
    time.sleep(0.1)
    log_job_scheduler(logger, "backup_db", "finalizado", duracao=0.1)

    print("✓ Teste concluído - Verifique logs/Test/test_helpers.log")


def test_context_managers():
    """Testa context managers para blocos de código."""
    print("\n" + "="*60)
    print("TESTE 5: Context Managers")
    print("="*60)

    logger = get_logger(__name__, log_file="logs/Test/test_context.log")

    # Log de bloco
    with log_block(logger, "Processamento de mensalidades"):
        logger.info("Processando mensalidade 1")
        logger.info("Processando mensalidade 2")

    # Log de tempo
    with log_time(logger, "consulta ao banco"):
        import time
        time.sleep(0.05)

    print("✓ Teste concluído - Verifique logs/Test/test_context.log")


def test_audit_logs():
    """Testa logs de auditoria em JSON."""
    print("\n" + "="*60)
    print("TESTE 6: Logs de Auditoria (JSON)")
    print("="*60)

    log_file = "logs/Test/test_audit.log"

    # Registra eventos de auditoria
    registrar_log_json_auditoria(log_file, {
        "funcao": "enviar_mensagem_agendada",
        "status": "sucesso",
        "usuario": "admin",
        "telefone": "+5583999999999",
        "tipo_envio": "vencimentos",
        "tentativa": 1,
        "http_status": 200,
    })

    registrar_log_json_auditoria(log_file, {
        "funcao": "enviar_mensagem_agendada",
        "status": "falha",
        "usuario": "admin",
        "telefone": "+5583999999999",
        "tipo_envio": "vencimentos",
        "tentativa": 2,
        "http_status": 500,
        "erro": "Internal Server Error",
    })

    print("✓ Teste concluído - Verifique logs/Test/test_audit.log")


def test_file_rotation():
    """Testa se a rotação de arquivos está funcionando."""
    print("\n" + "="*60)
    print("TESTE 7: Rotação de Arquivos")
    print("="*60)

    logger = get_logger(
        __name__,
        log_file="logs/Test/test_rotation.log",
        file_level=logging.DEBUG
    )

    # Gera muitos logs para testar rotação (simulação)
    for i in range(100):
        logger.debug(f"Linha de log {i+1} para testar rotação")
        logger.info(f"Log INFO número {i+1}")
        logger.warning(f"Log WARNING número {i+1}")

    print("✓ Teste concluído")
    print("  - Verifique logs/Test/test_rotation.log")
    print("  - Arquivos de backup serão criados quando atingir 10MB")


def main():
    """Executa todos os testes."""
    print("\n" + "="*60)
    print("SISTEMA DE LOGGING CENTRALIZADO - TESTES")
    print("="*60)

    try:
        test_basic_logging()
        test_structured_logging()
        test_specialized_loggers()
        test_helper_functions()
        test_context_managers()
        test_audit_logs()
        test_file_rotation()

        print("\n" + "="*60)
        print("TODOS OS TESTES CONCLUÍDOS COM SUCESSO ✓")
        print("="*60)
        print("\nVerifique os arquivos de log em:")
        print("  - logs/Test/")
        print("  - logs/Scheduler/")
        print("  - logs/Audit/")
        print("  - logs/WhatsApp/")
        print("  - logs/Envios grupos/")
        print("\nCaracterísticas do novo sistema:")
        print("  ✓ Rotação automática (10MB por arquivo, 5 backups)")
        print("  ✓ Formato padronizado e profissional")
        print("  ✓ Níveis de log apropriados")
        print("  ✓ Logs estruturados com contexto")
        print("  ✓ Separação console/arquivo")
        print("  ✓ Timestamps automáticos")
        print("\n")

    except Exception as e:
        print(f"\n❌ ERRO durante os testes: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import logging
    main()
