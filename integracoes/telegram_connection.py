import logging
import os
import sys
import traceback

import django
from django.utils.timezone import localtime
from telethon import TelegramClient

# ======================
# Configuração Django
# ======================
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "setup.settings")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()


def _get_env_setting(name: str, *, cast=str, required: bool = True, default=None):
    value = os.getenv(name)
    if value in (None, ""):
        if required and default is None:
            raise RuntimeError(
                f"Environment variable '{name}' is required for the Telegram integration."
            )
        return default

    try:
        return cast(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Environment variable '{name}' could not be parsed using {cast}."
        ) from exc


# ======================
# Configuração Telegram
# ======================
api_id = _get_env_setting("TELEGRAM_API_ID", cast=int)
api_hash = _get_env_setting("TELEGRAM_API_HASH")
phone = _get_env_setting("TELEGRAM_PHONE_NUMBER")
channel_username = _get_env_setting(
    "TELEGRAM_CHANNEL_USERNAME", required=False, default="mybannerscc"
)
session_name = _get_env_setting(
    "TELEGRAM_SESSION_NAME", required=False, default="telegram_bot"
)

IMAGES_BASE_DIR = "images/telegram_banners/"
LOG_DIR = "logs/TelegramConnection/"
LOG_FILE = os.path.join(LOG_DIR, "telegram_connection.log")

# ======================
# Configuração Logging
# ======================
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("TelegramConnection")
logger.setLevel(logging.DEBUG)

# Log em arquivo
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)

# Log no console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Formato dos logs
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [TELEGRAM] %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S",
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Evitar duplicidade de handlers
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# ======================
# Função principal
# ======================
async def telegram_connection():
    hoje = localtime().strftime("%d-%m-%Y")
    images_dir = os.path.join(IMAGES_BASE_DIR, hoje)
    os.makedirs(images_dir, exist_ok=True)

    client = TelegramClient(session_name, api_id, api_hash)

    try:
        await client.start(phone=phone)
        logger.info("Buscando imagens de hoje no canal '%s'...", channel_username)

        entity = await client.get_entity(channel_username)
        logger.info("Canal encontrado: %s", entity.title)

        count = 0
        imagens_baixadas = 0
        data_hoje_local = localtime().date()

        async for message in client.iter_messages(entity, limit=500):
            try:
                data_msg_local = localtime(message.date).date()
                if message.photo and data_msg_local == data_hoje_local:
                    file_name = os.path.join(images_dir, f"imagem_{message.id}.jpg")
                    if not os.path.exists(file_name):
                        await message.download_media(file_name)
                        logger.info("Imagem baixada: %s", file_name)
                        imagens_baixadas += 1
                    else:
                        logger.debug("Imagem já existente (ignorada): %s", file_name)
                count += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("Erro ao processar mensagem %s: %s", message.id, exc)
                traceback.print_exc()

        logger.info("Total de mensagens processadas: %s", count)
        logger.info("Total de imagens baixadas hoje: %s", imagens_baixadas)

    except Exception as exc:  # noqa: BLE001
        logger.critical("Erro fatal: %s", exc)
        traceback.print_exc()
    finally:
        await client.disconnect()
