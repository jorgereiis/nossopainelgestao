"""
Serviço para sincronização segura de LIDs do WhatsApp.

Este serviço escuta mensagens recebidas via webhook e, quando detecta um @lid,
busca o número de telefone correspondente e atualiza o campo whatsapp_lid
do cliente no banco de dados.

Características:
- Processamento em fila (queue) para evitar sobrecarga
- Rate limiting: máximo 5 requisições por minuto à API
- Timeout para database lock (20 segundos)
- Worker em thread separada para não bloquear o webhook
- Singleton para garantir uma única instância

Configurações:
- MAX_QUEUE_SIZE: 50 itens
- RATE_LIMIT: 5 requisições por minuto
- DB_LOCK_TIMEOUT: 20 segundos
- Sem persistência de fila em caso de restart
- Sem cache em memória (usa índice do banco)
"""

import logging
import threading
import time
from collections import deque
from typing import Optional

from django.db import OperationalError, transaction
from django.db.models.signals import post_save

from nossopainel.services.logging_config import get_logger

# Logger dedicado para o serviço
logger = get_logger(__name__, log_file="logs/WhatsApp/lid_sync.log")


class LidSyncService:
    """
    Serviço singleton para sincronização de LIDs do WhatsApp.

    Uso:
        service = LidSyncService()
        service.enqueue(lid="277742767599622@lid", session="jrg", token="...")
    """

    _instance = None
    _lock = threading.Lock()

    # ==================== CONFIGURAÇÕES ====================
    MAX_QUEUE_SIZE = 50         # Limite máximo da fila
    RATE_LIMIT = 5              # Requisições por minuto
    RATE_WINDOW = 60            # Janela de tempo em segundos
    DB_LOCK_TIMEOUT = 20        # Timeout para lock do banco em segundos
    PROCESS_INTERVAL = 1        # Intervalo entre processamentos em segundos
    # ========================================================

    def __new__(cls):
        """Implementação do padrão Singleton thread-safe."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def _initialize(self):
        """Inicializa as estruturas internas (chamado apenas uma vez)."""
        if self._initialized:
            return

        self.queue = deque(maxlen=self.MAX_QUEUE_SIZE)
        self.request_times = deque()  # Timestamps das requisições para rate limiting
        self.worker_thread: Optional[threading.Thread] = None
        self.running = False
        self._initialized = True

        logger.info(
            "[LidSyncService] Serviço inicializado | "
            f"max_queue={self.MAX_QUEUE_SIZE} rate_limit={self.RATE_LIMIT}/min "
            f"db_timeout={self.DB_LOCK_TIMEOUT}s"
        )

    def enqueue(self, lid: str, session: str, token: str) -> bool:
        """
        Adiciona um LID à fila para processamento.

        Args:
            lid: O LID completo (ex: "277742767599622@lid")
            session: Nome da sessão WhatsApp
            token: Token de autenticação da sessão

        Returns:
            True se adicionado à fila, False se fila cheia ou LID inválido
        """
        self._initialize()

        # Validar LID
        if not lid or '@lid' not in lid:
            logger.debug(f"[LidSyncService] LID inválido ignorado: {lid}")
            return False

        # Verificar se já está no banco (evita requisição desnecessária)
        if self._lid_exists_in_db(lid):
            logger.debug(f"[LidSyncService] LID já existe no banco: {lid}")
            return False

        # Verificar se já está na fila
        for item in self.queue:
            if item['lid'] == lid:
                logger.debug(f"[LidSyncService] LID já está na fila: {lid}")
                return False

        # Adicionar à fila
        item = {
            'lid': lid,
            'session': session,
            'token': token,
            'enqueued_at': time.time()
        }

        try:
            self.queue.append(item)
            logger.info(
                f"[LidSyncService] LID enfileirado | lid={lid} "
                f"queue_size={len(self.queue)}/{self.MAX_QUEUE_SIZE}"
            )
        except Exception as e:
            logger.error(f"[LidSyncService] Erro ao enfileirar LID {lid}: {e}")
            return False

        # Iniciar worker se não estiver rodando
        self._ensure_worker_running()

        return True

    def _lid_exists_in_db(self, lid: str) -> bool:
        """Verifica se o LID já existe no banco de dados (usa índice)."""
        try:
            from nossopainel.models import Cliente
            return Cliente.objects.filter(whatsapp_lid=lid).exists()
        except Exception as e:
            logger.error(f"[LidSyncService] Erro ao verificar LID no banco: {e}")
            return False

    def _ensure_worker_running(self):
        """Garante que o worker thread está rodando."""
        with self._lock:
            if self.worker_thread is None or not self.worker_thread.is_alive():
                self.running = True
                self.worker_thread = threading.Thread(
                    target=self._worker_loop,
                    daemon=True,
                    name="LidSyncWorker"
                )
                self.worker_thread.start()
                logger.info("[LidSyncService] Worker thread iniciado")

    def _worker_loop(self):
        """Loop principal do worker que processa a fila."""
        logger.info("[LidSyncService] Worker loop iniciado")

        while self.running:
            try:
                # Verificar se há itens na fila
                if not self.queue:
                    # Fila vazia - aguardar e verificar novamente
                    time.sleep(self.PROCESS_INTERVAL)

                    # Se fila continua vazia por 30 segundos, encerrar worker
                    empty_count = 0
                    while not self.queue and empty_count < 30:
                        time.sleep(1)
                        empty_count += 1

                    if not self.queue:
                        logger.info("[LidSyncService] Fila vazia por 30s, encerrando worker")
                        break

                    continue

                # Verificar rate limit
                if not self._check_rate_limit():
                    wait_time = self._get_wait_time()
                    logger.debug(
                        f"[LidSyncService] Rate limit atingido, aguardando {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                    continue

                # Pegar próximo item da fila
                try:
                    item = self.queue.popleft()
                except IndexError:
                    continue

                # Processar o item
                self._process_item(item)

                # Intervalo entre processamentos
                time.sleep(self.PROCESS_INTERVAL)

            except Exception as e:
                logger.error(f"[LidSyncService] Erro no worker loop: {e}", exc_info=True)
                time.sleep(5)  # Aguardar antes de continuar após erro

        self.running = False
        logger.info("[LidSyncService] Worker loop encerrado")

    def _check_rate_limit(self) -> bool:
        """
        Verifica se podemos fazer uma nova requisição (rate limiting).

        Returns:
            True se podemos fazer requisição, False se limite atingido
        """
        now = time.time()
        window_start = now - self.RATE_WINDOW

        # Remover timestamps antigos
        while self.request_times and self.request_times[0] < window_start:
            self.request_times.popleft()

        # Verificar se está dentro do limite
        return len(self.request_times) < self.RATE_LIMIT

    def _get_wait_time(self) -> float:
        """Calcula quanto tempo aguardar até poder fazer nova requisição."""
        if not self.request_times:
            return 0

        oldest_request = self.request_times[0]
        wait_until = oldest_request + self.RATE_WINDOW
        return max(0, wait_until - time.time())

    def _record_request(self):
        """Registra uma requisição para o rate limiting."""
        self.request_times.append(time.time())

    def _process_item(self, item: dict):
        """
        Processa um item da fila: busca telefone do LID e atualiza o cliente.

        Args:
            item: Dicionário com 'lid', 'session', 'token'
        """
        lid = item['lid']
        session = item['session']
        token = item['token']

        logger.info(f"[LidSyncService] Processando LID: {lid}")

        try:
            # 1. Buscar número de telefone do LID via API
            from wpp.api_connection import get_phone_from_pn_lid

            self._record_request()
            phone, status = get_phone_from_pn_lid(session, token, lid)

            if status != 200 or not phone:
                logger.warning(
                    f"[LidSyncService] Falha ao obter telefone do LID | "
                    f"lid={lid} status={status} phone={phone}"
                )
                return

            logger.debug(f"[LidSyncService] Telefone obtido: {lid} -> {phone}")

            # 2. Buscar cliente pelo telefone no banco
            self._update_client_lid(phone, lid)

        except Exception as e:
            logger.error(
                f"[LidSyncService] Erro ao processar LID {lid}: {e}",
                exc_info=True
            )

    def _update_client_lid(self, phone: str, lid: str):
        """
        Atualiza o campo whatsapp_lid do cliente.

        Implementa retry com timeout para lidar com database lock.
        OTIMIZAÇÃO: Desconecta o signal cliente_post_save durante o save
        para evitar sincronização de labels desnecessária.

        Args:
            phone: Número de telefone do cliente
            lid: LID a ser salvo
        """
        from nossopainel.models import Cliente
        from nossopainel.signals import cliente_post_save

        # Normalizar telefone para busca (remover + e @c.us se houver)
        phone_normalized = phone.replace('+', '').replace('@c.us', '').strip()

        # Tentar diferentes formatos de telefone
        phone_variants = [
            phone_normalized,                    # 554588334558
            f"+{phone_normalized}",              # +554588334558
            phone_normalized[2:] if phone_normalized.startswith('55') else phone_normalized,  # 4588334558
        ]

        start_time = time.time()
        retry_count = 0
        max_retries = 5

        while time.time() - start_time < self.DB_LOCK_TIMEOUT:
            try:
                with transaction.atomic():
                    # Tentar encontrar cliente com diferentes formatos de telefone
                    cliente = None
                    for phone_variant in phone_variants:
                        cliente = Cliente.objects.filter(telefone__endswith=phone_variant[-10:]).first()
                        if cliente:
                            break

                    if not cliente:
                        logger.debug(
                            f"[LidSyncService] Cliente não encontrado para telefone: {phone_normalized}"
                        )
                        return

                    # Verificar se já tem o LID correto
                    if cliente.whatsapp_lid == lid:
                        logger.debug(
                            f"[LidSyncService] Cliente {cliente.nome} já possui este LID"
                        )
                        return

                    # Atualizar o LID
                    old_lid = cliente.whatsapp_lid
                    cliente.whatsapp_lid = lid

                    # OTIMIZAÇÃO: Desconectar signal para evitar sincronização de labels
                    # A atualização de whatsapp_lid não deve disparar labels sync
                    post_save.disconnect(cliente_post_save, sender=Cliente)
                    try:
                        cliente.save(update_fields=['whatsapp_lid'])
                    finally:
                        # Sempre reconectar o signal, mesmo em caso de erro
                        post_save.connect(cliente_post_save, sender=Cliente)

                    logger.info(
                        f"[LidSyncService] LID atualizado com sucesso | "
                        f"cliente={cliente.nome} (ID={cliente.pk}) | "
                        f"telefone={cliente.telefone} | "
                        f"old_lid={old_lid} -> new_lid={lid}"
                    )
                    return

            except OperationalError as e:
                if "database is locked" in str(e).lower():
                    retry_count += 1
                    wait_time = min(2 ** retry_count, 5)  # Exponential backoff, max 5s
                    logger.warning(
                        f"[LidSyncService] Database locked, tentativa {retry_count}/{max_retries} | "
                        f"aguardando {wait_time}s..."
                    )
                    time.sleep(wait_time)

                    if retry_count >= max_retries:
                        logger.error(
                            f"[LidSyncService] Timeout ao atualizar LID após {max_retries} tentativas | "
                            f"phone={phone_normalized} lid={lid}"
                        )
                        return
                else:
                    raise

            except Exception as e:
                logger.error(
                    f"[LidSyncService] Erro ao atualizar cliente: {e}",
                    exc_info=True
                )
                return

        logger.error(
            f"[LidSyncService] Timeout geral ({self.DB_LOCK_TIMEOUT}s) ao atualizar LID | "
            f"phone={phone_normalized} lid={lid}"
        )

    def get_stats(self) -> dict:
        """Retorna estatísticas do serviço para monitoramento."""
        return {
            'queue_size': len(self.queue),
            'max_queue_size': self.MAX_QUEUE_SIZE,
            'rate_limit': self.RATE_LIMIT,
            'requests_in_window': len(self.request_times),
            'worker_running': self.worker_thread.is_alive() if self.worker_thread else False,
        }

    def stop(self):
        """Para o worker thread graciosamente."""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
            logger.info("[LidSyncService] Worker thread parado")


# Instância global (singleton)
lid_sync_service = LidSyncService()
