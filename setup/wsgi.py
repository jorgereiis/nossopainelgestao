import os
from django.core.wsgi import get_wsgi_application
from threading import Thread, Lock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "setup.settings")

application = get_wsgi_application()

# Cria um lock para exclusão mútua
lock = Lock()

# Função para executar enviar_mensagens.py em segundo plano
def executar_enviar_mensagens():
    # Adquira o lock antes de executar o script
    with lock:
        os.system('python3 enviar_mensagens.py')

# Iniciar thread para executar o script enviar_mensagens.py
enviar_mensagens_thread = Thread(target=executar_enviar_mensagens)
enviar_mensagens_thread.start()