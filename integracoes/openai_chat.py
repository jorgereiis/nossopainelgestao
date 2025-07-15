import os
import sys
import openai
import django
import inspect
from django.utils.timezone import localtime

# --- Configuração do ambiente Django (executada apenas uma vez) ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

# --- Inicializa cliente da OpenAI apenas uma vez ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY)


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
    func_name = inspect.currentframe().f_code.co_name

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Você é um redator profissional. Sempre responda com o texto pronto para envio, sem explicações ou introduções."},
                {"role": "user", "content": pergunta},
            ]
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[{timestamp}] [{func_name}] [{user}] [ERROR] Erro ao consultar o ChatGPT: {str(e)}")
        return f"❌ Erro ao consultar o ChatGPT: {str(e)}"
