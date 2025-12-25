"""
Sincronização automática de pagamentos PIX pendentes.

Este módulo verifica cobranças PIX pendentes e sincroniza o status
com a API do FastDePix como rede de segurança para casos onde
o webhook falhe.

Execução: A cada 30 minutos via scheduler
"""

import os
import sys
import logging
from datetime import timedelta

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from nossopainel.models import CobrancaPix, ContaBancaria
from nossopainel.services.payment_integrations import get_payment_integration, PaymentStatus

# Logger específico para sincronização PIX
LOG_DIR = "logs/FastDePix"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("sync_pix")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    fh = logging.FileHandler(os.path.join(LOG_DIR, "sync.log"), encoding="utf-8")
    fh.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%d-%m-%Y %H:%M:%S")
    fh.setFormatter(fmt)
    logger.addHandler(fh)


def sincronizar_pagamentos_pix_pendentes():
    """
    Sincroniza pagamentos PIX pendentes com a API do FastDePix.

    Critérios de seleção:
    - Status: pending
    - Criados há mais de 30 minutos (evita conflito com polling)
    - Criados nos últimos 7 dias
    - Ainda não expiraram

    Execução: A cada 30 minutos
    """
    logger.info("[Sync PIX] Iniciando sincronização automática...")

    # Buscar contas FastDePix ativas (campo encriptado é _api_key)
    contas = ContaBancaria.objects.filter(
        instituicao__tipo_integracao='fastdepix',
        _api_key__isnull=False,
        ativo=True
    ).exclude(_api_key='')

    if not contas.exists():
        logger.info("[Sync PIX] Nenhuma conta FastDePix configurada")
        return

    total_verificadas = 0
    total_atualizadas = 0
    total_erros = 0

    for conta in contas:
        integration = get_payment_integration(conta)
        if not integration:
            logger.warning(f"[Sync PIX] Falha ao obter integração para conta {conta.id}")
            continue

        # Cobranças pendentes há mais de 30 min, criadas nos últimos 7 dias
        desde = timezone.now() - timedelta(days=7)
        ate = timezone.now() - timedelta(minutes=30)

        cobrancas = CobrancaPix.objects.filter(
            conta_bancaria=conta,
            status='pending',
            criado_em__gte=desde,
            criado_em__lte=ate,
            expira_em__gt=timezone.now()  # Ainda não expirou
        )

        for cobranca in cobrancas:
            total_verificadas += 1
            try:
                status_api = integration.get_charge_status(cobranca.transaction_id)

                if status_api == PaymentStatus.PAID:
                    # Buscar detalhes para obter data de pagamento
                    try:
                        details = integration.get_charge_details(cobranca.transaction_id)
                        paid_at = None
                        if details.get('paid_at'):
                            paid_at = parse_datetime(details['paid_at'].replace('Z', '+00:00'))

                        payer = details.get('payer', {})
                        cobranca.mark_as_paid(
                            paid_at=paid_at or timezone.now(),
                            payer_name=payer.get('name') if isinstance(payer, dict) else None,
                            payer_document=payer.get('cpf_cnpj') if isinstance(payer, dict) else None,
                            webhook_data={'source': 'sync_automatico', 'data': details}
                        )
                    except Exception:
                        cobranca.mark_as_paid(paid_at=timezone.now())

                    total_atualizadas += 1
                    logger.info(f"[Sync PIX] Cobrança {cobranca.transaction_id} marcada como PAGA")

                elif status_api == PaymentStatus.EXPIRED:
                    cobranca.mark_as_expired()
                    total_atualizadas += 1
                    logger.info(f"[Sync PIX] Cobrança {cobranca.transaction_id} marcada como EXPIRADA")

                elif status_api == PaymentStatus.CANCELLED:
                    cobranca.mark_as_cancelled()
                    total_atualizadas += 1
                    logger.info(f"[Sync PIX] Cobrança {cobranca.transaction_id} marcada como CANCELADA")

            except Exception as e:
                total_erros += 1
                logger.error(f"[Sync PIX] Erro ao sincronizar {cobranca.transaction_id}: {e}")

    logger.info(
        f"[Sync PIX] Concluído - "
        f"Verificadas: {total_verificadas}, "
        f"Atualizadas: {total_atualizadas}, "
        f"Erros: {total_erros}"
    )


if __name__ == "__main__":
    # Execução manual para testes
    sincronizar_pagamentos_pix_pendentes()
