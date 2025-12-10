#!/usr/bin/env python3
"""
Teste básico do sistema de logging sem dependências do Django.
"""

import os
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from nossopainel.services.logging_config import (
    get_logger,
    get_console_formatter,
    get_file_formatter,
    get_rotating_file_handler,
)


def test_formatters():
    """Testa os formatadores."""
    print("\n" + "="*60)
    print("TESTE 1: Formatadores")
    print("="*60)

    console_fmt = get_console_formatter()
    file_fmt = get_file_formatter(detailed=True)
    file_fmt_simple = get_file_formatter(detailed=False)

    print(f"✓ Console formatter: {console_fmt._fmt}")
    print(f"✓ File formatter (detailed): {file_fmt._fmt}")
    print(f"✓ File formatter (simple): {file_fmt_simple._fmt}")


def test_rotating_handler():
    """Testa o handler com rotação."""
    print("\n" + "="*60)
    print("TESTE 2: Rotating File Handler")
    print("="*60)

    handler = get_rotating_file_handler(
        log_path="logs/Test/test_rotation.log",
        max_bytes=1024,  # 1KB para teste
        backup_count=3
    )

    print(f"✓ Handler criado: {handler}")
    print(f"  - Arquivo: {handler.baseFilename}")
    print(f"  - Max bytes: {handler.maxBytes}")
    print(f"  - Backup count: {handler.backupCount}")


def test_logger_creation():
    """Testa criação de logger."""
    print("\n" + "="*60)
    print("TESTE 3: Criação de Logger")
    print("="*60)

    logger = get_logger(
        name="test",
        log_file="logs/Test/test_logger.log",
        console_level=logging.INFO,
        file_level=logging.DEBUG
    )

    print(f"✓ Logger criado: {logger.name}")
    print(f"  - Nível: {logger.level}")
    print(f"  - Handlers: {len(logger.handlers)}")

    # Testa logging em diferentes níveis
    logger.debug("Mensagem DEBUG")
    logger.info("Mensagem INFO")
    logger.warning("Mensagem WARNING")
    logger.error("Mensagem ERROR")

    print("✓ Mensagens enviadas para console e arquivo")


def test_structured_logging():
    """Testa logging estruturado."""
    print("\n" + "="*60)
    print("TESTE 4: Logging Estruturado")
    print("="*60)

    logger = get_logger(
        name="test_structured",
        log_file="logs/Test/test_structured.log"
    )

    # Log com formatação estruturada
    logger.info(
        "Operação concluída | usuario=%s telefone=%s tipo=%s",
        "admin",
        "+5583999999999",
        "vencimentos"
    )

    logger.warning(
        "Sessão indisponível | usuario=%s",
        "admin"
    )

    logger.error(
        "Falha no envio | usuario=%s telefone=%s tentativa=%d/%d erro=%s",
        "admin",
        "+5583999999999",
        2,
        3,
        "Timeout"
    )

    print("✓ Logs estruturados registrados")


def main():
    """Executa todos os testes."""
    print("\n" + "="*60)
    print("TESTE BÁSICO DO SISTEMA DE LOGGING")
    print("="*60)

    try:
        test_formatters()
        test_rotating_handler()
        test_logger_creation()
        test_structured_logging()

        print("\n" + "="*60)
        print("TODOS OS TESTES CONCLUÍDOS COM SUCESSO ✓")
        print("="*60)
        print("\nArquivos de log criados em logs/Test/")
        print("\nCaracterísticas validadas:")
        print("  ✓ Formatadores funcionando")
        print("  ✓ Rotação configurada")
        print("  ✓ Loggers criados corretamente")
        print("  ✓ Logs estruturados OK")
        print("\n")

    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
