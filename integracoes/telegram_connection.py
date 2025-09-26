import os
import sys
import django
from django.utils.timezone import localtime
import traceback
import logging
from telethon import TelegramClient

# ======================
# Configuração Django
# ======================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

# ======================
# Configuração Telegram
# ======================
api_id = '21357610'
api_hash = '6bb5cdc0797e1f281db5f85986541a0f'
phone = '+5583993329190'
channel_username = 'mybannerscc'

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
    datefmt="%d-%m-%Y %H:%M:%S"
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
    hoje = localtime().strftime('%d-%m-%Y')
    IMAGES_DIR = os.path.join(IMAGES_BASE_DIR, hoje)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    client = TelegramClient('telegram_bot', api_id, api_hash)

    try:
        await client.start(phone=phone)
        logger.info(f"Buscando imagens de hoje no canal '{channel_username}'...")

        entity = await client.get_entity(channel_username)
        logger.info(f"Canal encontrado: {entity.title}")

        count = 0
        imagens_baixadas = 0
        data_hoje_local = localtime().date()

        async for message in client.iter_messages(entity, limit=500):
            try:
                data_msg_local = localtime(message.date).date()
                if message.photo and data_msg_local == data_hoje_local:
                    file_name = os.path.join(IMAGES_DIR, f"imagem_{message.id}.jpg")
                    if not os.path.exists(file_name):
                        await message.download_media(file_name)
                        logger.info(f"Imagem baixada: {file_name}")
                        imagens_baixadas += 1
                    else:
                        logger.debug(f"Imagem já existente (ignorada): {file_name}")
                count += 1
            except Exception as e:
                logger.error(f"Erro ao processar mensagem {message.id}: {e}")
                traceback.print_exc()

        logger.info(f"Total de mensagens processadas: {count}")
        logger.info(f"Total de imagens baixadas hoje: {imagens_baixadas}")

    except Exception as e:
        logger.critical(f"Erro fatal: {e}")
        traceback.print_exc()
    finally:
        await client.disconnect()
