"""
Integração com CapSolver API para resolver desafios reCAPTCHA v2.

Suporta envio opcional de proxy próprio, HTML do iframe anchor e
requisições reload, conforme documentação oficial:
https://docs.capsolver.com/pt/guide/captcha/ReCaptchaV2/
"""

from __future__ import annotations

import time
from typing import Optional

import requests
from django.conf import settings

from cadastros.services.logging_config import get_reseller_logger


logger = get_reseller_logger()


class CapSolverException(Exception):
    """Erro genérico vindo da API CapSolver."""


class CapSolverService:
    API_URL = "https://api.capsolver.com"
    STABLE_API_URL = "https://api-stable.capsolver.com"

    def __init__(self, api_key: Optional[str] = None, timeout: Optional[int] = None):
        self.api_key = api_key or getattr(settings, "CAPSOLVER_API_KEY", None)
        if not self.api_key:
            raise CapSolverException(
                "CAPSOLVER_API_KEY não configurada. Defina no .env para habilitar automação."
            )
        self.timeout = timeout or getattr(settings, "CAPSOLVER_TIMEOUT", 120)

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #

    def get_balance(self) -> Optional[float]:
        try:
            response = requests.post(
                f"{self.API_URL}/getBalance",
                json={"clientKey": self.api_key},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("balance")
        except requests.RequestException as exc:
            logger.error(f"Erro ao consultar saldo CapSolver: {exc}")
            return None

    def solve_recaptcha_v2(
        self,
        sitekey: str,
        url: str,
        *,
        proxy: Optional[str] = None,
        anchor: Optional[str] = None,
        reload: Optional[str] = None,
        user_agent: Optional[str] = None,
        cookies: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: int = 3,
    ) -> str:
        """
        Solicita um token reCAPTCHA v2.

        Args:
            sitekey: data-sitekey da página.
            url: URL onde o reCAPTCHA está renderizado.
            proxy: Proxy HTTP/SOCKS no formato protocol://user:pass@host:port
            anchor: HTML Base64 do iframe anchor.
            reload: Requisição reload (fetch) em Base64.
            user_agent: User-Agent atual do navegador.
            cookies: Header Cookie serializado.
            timeout: Tempo máximo para aguardar o token.
            max_retries: Tentativas em caso de erro de proxy.
        """

        timeout = timeout or self.timeout
        task_payload = self._build_task_payload(
            sitekey=sitekey,
            url=url,
            proxy=proxy,
            anchor=anchor,
            reload=reload,
            user_agent=user_agent,
            cookies=cookies,
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                task_id = self._create_task(task_payload)
                logger.info(f"Tarefa CapSolver criada: {task_id}")
                token = self._poll_result(task_id, timeout)
                logger.info("reCAPTCHA resolvido com sucesso!")
                return token
            except CapSolverException as exc:
                last_error = exc
                logger.error(f"Erro CapSolver (tentativa {attempt}/{max_retries}): {exc}")
                if "PROXY" in str(exc).upper() and attempt < max_retries:
                    logger.warning("Tentando novamente com outro proxy do CapSolver...")
                    time.sleep(2)
                    continue
                break

        raise last_error or CapSolverException("Falha ao resolver reCAPTCHA.")

    # ------------------------------------------------------------------ #
    # Internos
    # ------------------------------------------------------------------ #

    def _build_task_payload(
        self,
        *,
        sitekey: str,
        url: str,
        proxy: Optional[str],
        anchor: Optional[str],
        reload: Optional[str],
        user_agent: Optional[str],
        cookies: Optional[str],
    ) -> dict:
        task_type = "ReCaptchaV2Task" if proxy else "ReCaptchaV2TaskProxyLess"
        task = {
            "type": task_type,
            "websiteKey": sitekey,
            "websiteURL": url,
        }
        if proxy:
            task["proxy"] = proxy
        if anchor:
            task["anchor"] = anchor
        if reload:
            task["reload"] = reload
        if user_agent:
            task["userAgent"] = user_agent
        if cookies:
            task["cookies"] = cookies

        return {
            "clientKey": self.api_key,
            "task": task,
        }

    def _create_task(self, payload: dict) -> str:
        try:
            response = requests.post(
                f"{self.API_URL}/createTask",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("errorId", 0) != 0:
                # tenta endpoint estável
                response = requests.post(
                    f"{self.STABLE_API_URL}/createTask",
                    json=payload,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

            if data.get("errorId", 0) != 0:
                raise CapSolverException(
                    f"{data.get('errorCode')}: {data.get('errorDescription')}"
                )
            return data["taskId"]
        except requests.RequestException as exc:
            raise CapSolverException(f"Erro de rede ao criar tarefa: {exc}") from exc

    def _poll_result(self, task_id: str, timeout: int) -> str:
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = requests.post(
                    f"{self.API_URL}/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as exc:
                logger.warning(f"Erro consultando resultado CapSolver: {exc}")
                time.sleep(2)
                continue

            status = data.get("status")
            if status == "processing":
                time.sleep(3)
                continue
            if status == "ready":
                return data["solution"]["gRecaptchaResponse"]
            if status == "failed":
                raise CapSolverException(
                    f"{data.get('errorCode')}: {data.get('errorDescription')}"
                )

        raise CapSolverException(f"Timeout ({timeout}s) aguardando token CapSolver.")

