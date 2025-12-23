"""
Servico de Integracoes de Pagamento PIX.

Suporta as seguintes integracoes:
- FastDePix (API)
- Mercado Pago (API) - A implementar
- Efi Bank (API) - A implementar

Autor: Sistema Nosso Painel
"""

import logging
import requests
import json
import hashlib
import hmac
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PaymentStatus(Enum):
    """Status possiveis de uma cobranca PIX."""
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    ERROR = "error"


@dataclass
class PixCharge:
    """Representa uma cobranca PIX."""
    transaction_id: str
    amount: Decimal
    qr_code: str  # Codigo para gerar QR Code (EMV)
    qr_code_url: Optional[str]  # URL para visualizar QR Code (pode ser usada como link)
    qr_code_base64: Optional[str]  # Imagem do QR Code em base64
    pix_copy_paste: str  # Codigo copia e cola
    expiration: datetime
    status: PaymentStatus
    external_id: Optional[str] = None  # ID externo (nosso sistema)
    raw_response: Optional[Dict] = None


@dataclass
class PaymentWebhookData:
    """Dados recebidos via webhook de pagamento."""
    transaction_id: str
    status: PaymentStatus
    amount: Decimal
    paid_at: Optional[datetime]
    payer_name: Optional[str]
    payer_document: Optional[str]
    raw_data: Dict


class PaymentIntegrationError(Exception):
    """Excecao base para erros de integracao de pagamento."""
    def __init__(self, message: str, code: str = None, raw_response: Dict = None):
        self.message = message
        self.code = code
        self.raw_response = raw_response
        super().__init__(self.message)


class BasePaymentIntegration(ABC):
    """Classe base abstrata para integracoes de pagamento."""

    def __init__(self, sandbox: bool = True):
        self.sandbox = sandbox

    @abstractmethod
    def create_pix_charge(
        self,
        amount: Decimal,
        description: str,
        external_id: str,
        expiration_minutes: int = 30,
        payer_name: Optional[str] = None,
        payer_document: Optional[str] = None,
    ) -> PixCharge:
        """Cria uma cobranca PIX."""
        pass

    @abstractmethod
    def get_charge_status(self, transaction_id: str) -> PaymentStatus:
        """Consulta o status de uma cobranca."""
        pass

    @abstractmethod
    def cancel_charge(self, transaction_id: str) -> bool:
        """Cancela uma cobranca pendente."""
        pass

    @abstractmethod
    def validate_webhook(self, payload: Dict, signature: str) -> bool:
        """Valida a assinatura de um webhook."""
        pass

    @abstractmethod
    def parse_webhook(self, payload: Dict) -> PaymentWebhookData:
        """Processa os dados de um webhook."""
        pass


# =============================================================================
# FASTDEPIX INTEGRATION
# =============================================================================

class FastDePixIntegration(BasePaymentIntegration):
    """
    Integracao com a API do FastDePix.

    Documentacao: https://fastdepix.space/api/docs.php

    Autenticacao: Bearer Token (API Key no formato fdpx_...)
    """

    PRODUCTION_URL = "https://fastdepix.space/api/v1"
    SANDBOX_URL = "https://fastdepix.space/api/v1"  # Mesmo endpoint, modo sandbox via config

    def __init__(self, api_key: str, sandbox: bool = True, webhook_secret: str = None):
        """
        Inicializa a integracao FastDePix.

        Args:
            api_key: Token de autenticacao (formato: fdpx_...)
            sandbox: Se True, usa ambiente de testes
            webhook_secret: Chave para validar webhooks (HMAC-SHA256)
        """
        super().__init__(sandbox)
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.base_url = self.SANDBOX_URL if sandbox else self.PRODUCTION_URL

    def _get_headers(self) -> Dict[str, str]:
        """Retorna os headers para requisicoes."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None,
    ) -> Dict:
        """
        Faz uma requisicao para a API.

        Args:
            method: GET, POST, PUT, DELETE
            endpoint: Endpoint da API (ex: /transactions)
            data: Dados para enviar no body (JSON)
            params: Query parameters

        Returns:
            Dict com a resposta da API

        Raises:
            PaymentIntegrationError: Se ocorrer erro na requisicao
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        try:
            logger.info(f"[FastDePix] {method} {url}")

            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=30,
            )

            response_data = response.json() if response.text else {}

            logger.info(f"[FastDePix] Response status: {response.status_code}")

            if response.status_code >= 400:
                error_msg = response_data.get("message", "Erro desconhecido")
                logger.error(f"[FastDePix] Erro: {error_msg}")
                raise PaymentIntegrationError(
                    message=error_msg,
                    code=str(response.status_code),
                    raw_response=response_data,
                )

            return response_data

        except requests.exceptions.Timeout:
            logger.error("[FastDePix] Timeout na requisicao")
            raise PaymentIntegrationError(
                message="Timeout na comunicacao com FastDePix",
                code="TIMEOUT",
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"[FastDePix] Erro de conexao: {e}")
            raise PaymentIntegrationError(
                message=f"Erro de conexao: {str(e)}",
                code="CONNECTION_ERROR",
            )
        except json.JSONDecodeError:
            logger.error("[FastDePix] Resposta invalida (nao e JSON)")
            raise PaymentIntegrationError(
                message="Resposta invalida da API",
                code="INVALID_RESPONSE",
            )

    def create_pix_charge(
        self,
        amount: Decimal,
        description: str,
        external_id: str,
        expiration_minutes: int = 30,
        payer_name: Optional[str] = None,
        payer_document: Optional[str] = None,
    ) -> PixCharge:
        """
        Cria uma cobranca PIX no FastDePix.

        Args:
            amount: Valor em reais (minimo R$ 10.00)
            description: Descricao da cobranca
            external_id: ID externo para referencia
            expiration_minutes: Tempo de expiracao em minutos
            payer_name: Nome do pagador (obrigatorio para valores >= R$ 500)
            payer_document: CPF/CNPJ do pagador (obrigatorio para valores >= R$ 500)

        Returns:
            PixCharge com dados da cobranca

        Raises:
            PaymentIntegrationError: Se ocorrer erro
        """
        # Validar valor minimo
        if amount < Decimal("10.00"):
            raise PaymentIntegrationError(
                message="Valor minimo para cobranca PIX e R$ 10,00",
                code="MIN_AMOUNT",
            )

        # Preparar dados da requisicao
        payload = {
            "amount": float(amount),
            "description": description,
            "external_id": external_id,
            "expiration_minutes": expiration_minutes,
        }

        # Dados do pagador (obrigatorio para valores >= R$ 500)
        if amount >= Decimal("500.00") or payer_name:
            if payer_name and payer_document:
                # Determinar tipo de usuario
                doc_clean = "".join(filter(str.isdigit, payer_document))
                user_type = "company" if len(doc_clean) == 14 else "individual"

                payload["user"] = {
                    "name": payer_name,
                    "cpf_cnpj": doc_clean,
                    "user_type": user_type,
                }

        # Criar transacao
        response = self._make_request("POST", "/transactions", data=payload)

        # Processar resposta
        data = response.get("data", response)

        # Calcular expiracao
        # Tentar usar qr_code_expires_at da resposta, senao usar o tempo padrao
        expiration = datetime.now() + timedelta(minutes=expiration_minutes)
        if data.get("qr_code_expires_at"):
            try:
                expiration = datetime.fromisoformat(
                    data["qr_code_expires_at"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except (ValueError, AttributeError):
                pass

        # FastDePix retorna:
        # - qr_code: URL para visualizar o QR Code
        # - qr_code_text: Codigo copia e cola (EMV)
        qr_code_url = data.get("qr_code", "")
        qr_code_text = data.get("qr_code_text", "")

        return PixCharge(
            transaction_id=str(data.get("id", data.get("transaction_id", ""))),
            amount=Decimal(str(data.get("amount", amount))),
            qr_code=qr_code_text,  # Codigo EMV (copia e cola)
            qr_code_url=qr_code_url,  # URL para visualizar QR Code
            qr_code_base64=data.get("qr_code_base64"),
            pix_copy_paste=qr_code_text,  # Codigo copia e cola
            expiration=expiration,
            status=PaymentStatus.PENDING,
            external_id=external_id,
            raw_response=response,
        )

    def get_charge_status(self, transaction_id: str) -> PaymentStatus:
        """
        Consulta o status de uma cobranca.

        Args:
            transaction_id: ID da transacao no FastDePix

        Returns:
            PaymentStatus atual da cobranca
        """
        response = self._make_request("GET", f"/transactions/{transaction_id}")

        data = response.get("data", response)
        status_str = data.get("status", "pending").lower()

        status_map = {
            "pending": PaymentStatus.PENDING,
            "paid": PaymentStatus.PAID,
            "expired": PaymentStatus.EXPIRED,
            "cancelled": PaymentStatus.CANCELLED,
            "canceled": PaymentStatus.CANCELLED,
            "refunded": PaymentStatus.REFUNDED,
        }

        return status_map.get(status_str, PaymentStatus.ERROR)

    def get_charge_details(self, transaction_id: str) -> Dict:
        """
        Obtem detalhes completos de uma cobranca.

        Args:
            transaction_id: ID da transacao

        Returns:
            Dict com todos os dados da cobranca
        """
        response = self._make_request("GET", f"/transactions/{transaction_id}")
        return response.get("data", response)

    def cancel_charge(self, transaction_id: str) -> bool:
        """
        Cancela uma cobranca pendente.

        Args:
            transaction_id: ID da transacao

        Returns:
            True se cancelada com sucesso
        """
        try:
            self._make_request("DELETE", f"/transactions/{transaction_id}")
            return True
        except PaymentIntegrationError as e:
            logger.warning(f"[FastDePix] Erro ao cancelar cobranca: {e.message}")
            return False

    def list_transactions(
        self,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict:
        """
        Lista transacoes com filtros.

        Args:
            status: Filtrar por status (pending, paid, expired, cancelled)
            start_date: Data inicial
            end_date: Data final
            page: Pagina atual
            per_page: Itens por pagina

        Returns:
            Dict com lista de transacoes e metadados de paginacao
        """
        params = {
            "page": page,
            "per_page": per_page,
        }

        if status:
            params["status"] = status
        if start_date:
            params["start_date"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["end_date"] = end_date.strftime("%Y-%m-%d")

        return self._make_request("GET", "/transactions", params=params)

    def validate_webhook(self, payload: Dict, signature: str) -> bool:
        """
        Valida a assinatura HMAC-SHA256 de um webhook.

        Args:
            payload: Dados do webhook
            signature: Assinatura recebida no header X-Webhook-Signature

        Returns:
            True se a assinatura for valida
        """
        if not self.webhook_secret:
            logger.warning("[FastDePix] webhook_secret nao configurado, pulando validacao")
            return True

        try:
            payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                payload_str.encode(),
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"[FastDePix] Erro ao validar webhook: {e}")
            return False

    def parse_webhook(self, payload: Dict) -> PaymentWebhookData:
        """
        Processa os dados de um webhook de pagamento.

        Args:
            payload: Dados recebidos no webhook

        Returns:
            PaymentWebhookData com dados estruturados
        """
        data = payload.get("data", payload)
        event_type = payload.get("event", "")

        # Mapear status
        status_str = data.get("status", "").lower()
        if event_type == "transaction.paid":
            status = PaymentStatus.PAID
        elif event_type == "transaction.expired":
            status = PaymentStatus.EXPIRED
        else:
            status_map = {
                "pending": PaymentStatus.PENDING,
                "paid": PaymentStatus.PAID,
                "expired": PaymentStatus.EXPIRED,
                "cancelled": PaymentStatus.CANCELLED,
            }
            status = status_map.get(status_str, PaymentStatus.PENDING)

        # Extrair data de pagamento
        paid_at = None
        if data.get("paid_at"):
            try:
                paid_at = datetime.fromisoformat(data["paid_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return PaymentWebhookData(
            transaction_id=str(data.get("id", data.get("transaction_id", ""))),
            status=status,
            amount=Decimal(str(data.get("amount", 0))),
            paid_at=paid_at,
            payer_name=data.get("payer", {}).get("name") if isinstance(data.get("payer"), dict) else None,
            payer_document=data.get("payer", {}).get("cpf_cnpj") if isinstance(data.get("payer"), dict) else None,
            raw_data=payload,
        )

    # =========================================================================
    # WEBHOOK MANAGEMENT
    # =========================================================================

    def register_webhook(
        self,
        url: str,
        events: list = None,
    ) -> Dict:
        """
        Registra URL de webhook na API FastDePix.

        Args:
            url: URL HTTPS do endpoint de webhook
            events: Lista de eventos (default: transaction.paid, transaction.expired)

        Returns:
            Dict com dados do webhook registrado (id, secret, etc)

        Raises:
            PaymentIntegrationError: Se ocorrer erro
        """
        if events is None:
            events = ["transaction.paid", "transaction.expired"]

        payload = {
            "url": url,
            "events": events,
        }

        logger.info(f"[FastDePix] Registrando webhook: {url}")
        response = self._make_request("POST", "/webhooks/register", data=payload)

        data = response.get("data", response)
        logger.info(f"[FastDePix] Webhook registrado com sucesso. ID: {data.get('id')}")

        return data

    def update_webhook(
        self,
        webhook_id: str,
        url: str = None,
        events: list = None,
    ) -> Dict:
        """
        Atualiza um webhook existente.

        Args:
            webhook_id: ID do webhook a atualizar
            url: Nova URL (opcional)
            events: Nova lista de eventos (opcional)

        Returns:
            Dict com dados atualizados do webhook
        """
        payload = {}
        if url:
            payload["url"] = url
        if events:
            payload["events"] = events

        logger.info(f"[FastDePix] Atualizando webhook {webhook_id}")
        response = self._make_request("PUT", f"/webhooks/{webhook_id}", data=payload)

        return response.get("data", response)

    def delete_webhook(self, webhook_id: str) -> bool:
        """
        Remove um webhook registrado.

        Args:
            webhook_id: ID do webhook a remover

        Returns:
            True se removido com sucesso
        """
        try:
            logger.info(f"[FastDePix] Removendo webhook {webhook_id}")
            self._make_request("DELETE", f"/webhooks/{webhook_id}")
            return True
        except PaymentIntegrationError as e:
            logger.warning(f"[FastDePix] Erro ao remover webhook: {e.message}")
            return False

    def list_webhooks(self) -> list:
        """
        Lista todos os webhooks registrados.

        Returns:
            Lista de webhooks configurados
        """
        response = self._make_request("GET", "/webhooks")
        data = response.get("data", response)

        # Pode retornar lista direta ou em campo 'webhooks'
        if isinstance(data, list):
            return data
        return data.get("webhooks", [])

    # =========================================================================
    # CONNECTION TEST
    # =========================================================================

    def test_connection(self) -> Tuple[bool, str]:
        """
        Testa a conexao com a API FastDePix.

        Verifica se a API key e valida fazendo uma requisicao simples.

        Returns:
            Tuple (sucesso: bool, mensagem: str)
        """
        try:
            # Tenta listar transacoes (limite 1) para verificar conexao
            response = self._make_request("GET", "/transactions", params={"per_page": 1})

            if response.get("success", True):
                return True, "Conexao estabelecida com sucesso"
            else:
                return False, response.get("message", "Erro desconhecido")

        except PaymentIntegrationError as e:
            if e.code == "401":
                return False, "API Key invalida ou expirada"
            elif e.code == "TIMEOUT":
                return False, "Timeout ao conectar com FastDePix"
            elif e.code == "CONNECTION_ERROR":
                return False, "Erro de conexao com FastDePix"
            else:
                return False, f"Erro: {e.message}"
        except Exception as e:
            logger.error(f"[FastDePix] Erro inesperado no teste de conexao: {e}")
            return False, f"Erro inesperado: {str(e)}"


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_payment_integration(conta_bancaria) -> Optional[BasePaymentIntegration]:
    """
    Factory function para obter a integracao de pagamento correta
    baseada na conta bancaria.

    Args:
        conta_bancaria: Instancia de ContaBancaria

    Returns:
        Instancia da integracao correspondente ou None
    """
    if not conta_bancaria or not conta_bancaria.instituicao:
        return None

    tipo = conta_bancaria.instituicao.tipo_integracao

    if tipo == "fastdepix":
        if not conta_bancaria.api_key:
            logger.warning("FastDePix: api_key nao configurada")
            return None

        return FastDePixIntegration(
            api_key=conta_bancaria.api_key,
            sandbox=conta_bancaria.ambiente_sandbox,
            webhook_secret=conta_bancaria.webhook_secret or None,
        )

    elif tipo == "mercado_pago":
        # TODO: Implementar MercadoPagoIntegration
        logger.info("Mercado Pago: integracao ainda nao implementada")
        return None

    elif tipo == "efi_bank":
        # TODO: Implementar EfiBankIntegration
        logger.info("Efi Bank: integracao ainda nao implementada")
        return None

    return None
