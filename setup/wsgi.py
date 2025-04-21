import os
import sys
from django.core.wsgi import get_wsgi_application
from threading import Thread, Lock

# Configuração do ambiente Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "setup.settings")

application = get_wsgi_application()

# Definindo um lock para evitar execução simultânea de threads no mesmo processo
lock = Lock()

# Função para inicializar os scripts do sistema
def inicializar_scripts():
    try:
        with lock:
            print("[WSGI] INICIANDO SCRIPT 'agendamentos.py'...")
            os.system('python3 scripts/agendamentos.py')

    except Exception as e:
        print(f"[WSGI] Erro ao iniciar scripts: {e}", file=sys.stderr)

# Inicia a thread para executar os scripts
inicializar_scripts_thread = Thread(target=inicializar_scripts)
inicializar_scripts_thread.start()
