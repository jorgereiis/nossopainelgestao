import os
import sys
import django
from datetime import datetime
from django.utils.timezone import localtime
import traceback

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carregar as configurações do Django
django.setup()

from telethon import TelegramClient, events, sync
from telethon.tl.types import MessageMediaPhoto

# Variáveis de configuração
IMAGES_BASE_DIR = "images/status_wpp/banners_fup/"
MEU_NUM_CLARO = os.getenv('MEU_NUM_CLARO')

api_id = '21357610'
api_hash = '6bb5cdc0797e1f281db5f85986541a0f'
phone = '+5583993329190'
bot_username  = ''
channel_username = 'mybannerscc'

# Data atual
hoje = localtime().strftime('%d-%m-%Y')

# Caminho completo para o diretório do dia
IMAGES_DIR = os.path.join(IMAGES_BASE_DIR, hoje)
os.makedirs(IMAGES_DIR, exist_ok=True)


async def telegram_connection():
    # Inicializa o cliente do Telegram
    client = TelegramClient('telegram_bot', api_id, api_hash)

    try:
        await client.start(phone=phone)
        print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [TELEGRAM] [INIT] Buscando imagens de hoje no canal '{channel_username}'...")
        try:
            entity = await client.get_entity(channel_username)
            print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [TELEGRAM] [OK] Canal encontrado: {entity.title}")
        except Exception as e:
            print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [TELEGRAM] [ERRO] Falha ao obter entidade do canal '{channel_username}': {e}")
            traceback.print_exc()
            return

        count = 0
        imagens_baixadas = 0

        async for message in client.iter_messages(entity, limit=50):
            try:
                # Converte a data da mensagem para o fuso local
                data_msg_local = localtime(message.date).date()
                data_hoje_local = localtime().date()
                if (
                    message.photo
                    and data_msg_local == data_hoje_local
                ):
                    file_name = os.path.join(IMAGES_DIR, f"imagem_{message.id}.jpg")
                    await message.download_media(file_name)
                    print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [TELEGRAM] [OK] Imagem baixada: {file_name}")
                    imagens_baixadas += 1
                count += 1
            except Exception as e:
                print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [TELEGRAM] [ERRO] Erro ao processar mensagem {message.id}: {e}")
                traceback.print_exc()

        print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [TELEGRAM] [SUCCESS] Total de mensagens processadas: {count}")
        print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [TELEGRAM] [SUCCESS] Total de imagens baixadas hoje: {imagens_baixadas}")

    except Exception as e:
        print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [TELEGRAM] [ERRO FATAL] Erro geral no processo: {e}")
        traceback.print_exc()
    finally:
        await client.disconnect()
 