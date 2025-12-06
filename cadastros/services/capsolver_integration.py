"""
Integração com CapSolver API para resolver desafios reCAPTCHA v2.

Esta implementação é baseada no código 100% funcional do projeto de referência.
Usa APENAS a API do CapSolver (sem extensão).

Documentação: https://docs.capsolver.com/pt/guide/captcha/ReCaptchaV2/
"""

import os
import time
from typing import Optional

import requests
from django.conf import settings

from cadastros.services.lib import logger


# Logger para este módulo
log = logger.get_automation_logger()


class CapSolverException(Exception):
    """Erro genérico vindo da API CapSolver."""


class CapSolver:
    """
    Cliente CapSolver para resolução de reCAPTCHA v2

    Baseado na implementação 100% funcional do projeto de referência.
    """

    API_URL = "https://api.capsolver.com"

    def __init__(self, api_key: Optional[str] = None, proxy: Optional[str] = None, timeout: Optional[int] = None):
        """
        Inicializa o cliente CapSolver

        Args:
            api_key: API Key do CapSolver (se None, lê do .env)
            proxy: Proxy HTTP no formato 'http://user:pass@host:port' (opcional)
            timeout: Tempo máximo para aguardar resolução (padrão: 120s)
        """
        self.api_key = api_key or os.getenv('CAPSOLVER_API_KEY')
        if not self.api_key:
            raise CapSolverException(
                "CAPSOLVER_API_KEY não configurada. Defina no arquivo .env"
            )

        self.proxy = proxy or os.getenv('CAPSOLVER_PROXY')
        self.timeout = timeout or int(os.getenv('CAPSOLVER_TIMEOUT', '120'))
        self.max_retries = 3
        self.poll_interval = 5  # Polling a cada 5 segundos

        log.debug(f"CapSolver inicializado (timeout={self.timeout}s, proxy={'Sim' if self.proxy else 'Não'})")

    def create_task(self, website_url: str, website_key: str, task_type: str = 'ReCaptchaV2TaskProxyLess') -> str:
        """
        Cria tarefa de resolução de reCAPTCHA

        Args:
            website_url: URL do site onde o reCAPTCHA está
            website_key: Site key do reCAPTCHA
            task_type: Tipo de task ('ReCaptchaV2TaskProxyLess' ou 'ReCaptchaV2Task')

        Returns:
            ID da tarefa criada
        """
        log.info(f"Criando tarefa CapSolver: {task_type}")
        log.debug(f"Website: {website_url}, SiteKey: {website_key}")
        logger.log_capsolver_event(log, 'task_created', f'Enviando requisição para {self.API_URL}/createTask')

        task_data = {
            'clientKey': self.api_key,
            'task': {
                'type': task_type,
                'websiteURL': website_url,
                'websiteKey': website_key
            }
        }

        # Se tiver proxy, usar versão com proxy
        if self.proxy and task_type == 'ReCaptchaV2Task':
            # Parse proxy: http://user:pass@host:port
            proxy_clean = self.proxy.replace('http://', '').replace('https://', '')
            if '@' in proxy_clean:
                auth, address = proxy_clean.split('@')
                username, password = auth.split(':')
                host, port = address.split(':')

                task_data['task'].update({
                    'type': 'ReCaptchaV2Task',
                    'proxyType': 'http',
                    'proxyAddress': host,
                    'proxyPort': int(port),
                    'proxyLogin': username,
                    'proxyPassword': password
                })
            else:
                # Proxy sem autenticação
                host, port = proxy_clean.split(':')
                task_data['task'].update({
                    'type': 'ReCaptchaV2Task',
                    'proxyType': 'http',
                    'proxyAddress': host,
                    'proxyPort': int(port)
                })

        try:
            response = requests.post(
                f'{self.API_URL}/createTask',
                json=task_data,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            if data.get('errorId') == 0:
                task_id = data.get('taskId')
                log.info(f"Tarefa CapSolver criada com ID: {task_id}")
                logger.log_capsolver_event(log, 'task_created', f'ID={task_id}')
                return task_id
            else:
                error_desc = data.get('errorDescription', 'Erro desconhecido')
                log.error(f"Erro ao criar tarefa CapSolver: {error_desc}")
                logger.log_capsolver_event(log, 'error', error_desc)
                raise CapSolverException(f"CapSolver Error: {error_desc}")

        except requests.RequestException as exc:
            log.error(f"Erro de rede ao criar tarefa CapSolver: {exc}")
            logger.log_exception(log, exc, "create_task")
            raise CapSolverException(f"Erro de rede: {exc}") from exc

    def get_task_result(self, task_id: str) -> dict:
        """
        Verifica resultado da tarefa

        Args:
            task_id: ID da tarefa

        Returns:
            Dict com resultado da API
        """
        payload = {
            'clientKey': self.api_key,
            'taskId': task_id
        }

        try:
            log.debug(f"Consultando resultado da tarefa {task_id}")
            logger.log_capsolver_event(log, 'polling', f'taskId={task_id}')

            response = requests.post(
                f'{self.API_URL}/getTaskResult',
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            log.debug(f"Resultado: status={result.get('status')}")
            return result

        except requests.RequestException as exc:
            log.error(f"Erro ao obter resultado da tarefa {task_id}: {exc}")
            logger.log_exception(log, exc, "get_task_result")
            raise CapSolverException(f"Erro de rede: {exc}") from exc

    def wait_for_result(self, task_id: str, max_wait_time: Optional[int] = None) -> str:
        """
        Aguarda resolução do CAPTCHA com polling

        Args:
            task_id: ID da tarefa
            max_wait_time: Tempo máximo de espera (padrão: self.timeout)

        Returns:
            Token gRecaptchaResponse
        """
        max_wait_time = max_wait_time or self.timeout
        log.info(f"Aguardando resolução da tarefa {task_id} (max: {max_wait_time}s)")

        start_time = time.time()

        while (time.time() - start_time) < max_wait_time:
            result = self.get_task_result(task_id)

            if result.get('status') == 'ready':
                log.info("reCAPTCHA resolvido com sucesso pelo CapSolver")
                logger.log_capsolver_event(log, 'solved', f'taskId={task_id}')
                return result['solution']['gRecaptchaResponse']

            if result.get('status') == 'failed':
                error_msg = result.get('errorDescription', 'Erro desconhecido')
                log.error(f"CapSolver falhou: {error_msg}")
                logger.log_capsolver_event(log, 'error', error_msg)
                raise CapSolverException(f"CapSolver falhou: {error_msg}")

            # Mostrar progresso
            elapsed = int(time.time() - start_time)
            if elapsed % 10 == 0 and elapsed > 0:
                log.debug(f"Aguardando resolução... {elapsed}s decorridos")

            time.sleep(self.poll_interval)

        log.error(f"Timeout ao aguardar resolução da tarefa {task_id}")
        logger.log_capsolver_event(log, 'error', 'Timeout')
        raise CapSolverException(f'Timeout: CapSolver não resolveu em {max_wait_time}s')

    def solve_recaptcha(self, website_url: str, website_key: str) -> str:
        """
        Resolve reCAPTCHA completo (criar tarefa + aguardar resultado)

        Args:
            website_url: URL do site
            website_key: Site key do reCAPTCHA

        Returns:
            Token gRecaptchaResponse
        """
        log.info("Iniciando resolução completa de reCAPTCHA")
        logger.log_capsolver_event(log, 'solve_start', f'url={website_url}, key={website_key}')

        # Determinar tipo de task (com ou sem proxy)
        task_type = 'ReCaptchaV2Task' if self.proxy else 'ReCaptchaV2TaskProxyLess'

        # Criar tarefa
        task_id = self.create_task(website_url, website_key, task_type)

        # Aguardar resultado
        solution = self.wait_for_result(task_id)

        log.info(f"Solução reCAPTCHA obtida: {solution[:50]}...")
        return solution

    def get_balance(self) -> Optional[float]:
        """
        Consulta saldo da conta CapSolver

        Returns:
            Saldo em dólares ou None se erro
        """
        try:
            response = requests.post(
                f"{self.API_URL}/getBalance",
                json={"clientKey": self.api_key},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            balance = data.get("balance")

            if balance is not None:
                log.info(f"Saldo CapSolver: ${balance:.4f}")

            return balance
        except requests.RequestException as exc:
            log.error(f"Erro ao consultar saldo CapSolver: {exc}")
            return None


# Alias para compatibilidade com código existente
CapSolverService = CapSolver
