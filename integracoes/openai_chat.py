"""Integração com o ChatGPT para geração de respostas personalizadas."""

import logging
import os
import sys

import django
import openai
from django.utils.timezone import localtime

# --- Configuração do ambiente Django (executada apenas uma vez) ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

logger = logging.getLogger(__name__)

_openai_client = None


def _get_openai_client() -> openai.OpenAI:
    """Inicializa e mantém uma instância global do cliente OpenAI."""
    global _openai_client  # noqa: PLW0603
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY não encontrado nas variáveis de ambiente.")
        _openai_client = openai.OpenAI(api_key=api_key)
    return _openai_client


def consultar_chatgpt(pergunta: str, user: str) -> str:
    """
    Envia uma pergunta para o ChatGPT (modelo gpt-4o) e retorna a resposta.

    Args:
        pergunta (str): Texto enviado pelo usuário.
        contexto (str): Instrução para o sistema (ex: estilo, área de especialização).

    Returns:
        str: Resposta gerada pelo modelo.
    """
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')

    try:
        response = _get_openai_client().chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Você é um redator profissional. Sempre responda com o texto pronto para envio, sem explicações ou introduções."},
                {"role": "user", "content": pergunta},
            ]
        )
        return response.choices[0].message.content.strip()

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[%s] [ERROR] [%s] Erro ao consultar o ChatGPT: %s",
            timestamp,
            user,
            exc,
            exc_info=exc,
        )
        return f"❌ Erro ao consultar o ChatGPT: {exc}"
