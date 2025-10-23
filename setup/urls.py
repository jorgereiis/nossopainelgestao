"""
URL configuration for setup project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import os
import sys
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("painel-configs/", admin.site.urls),
    path("", include("cadastros.urls"))
]

# ============================================================================
# SERVIR ARQUIVOS DE MEDIA E STATIC - SOLUÇÃO AUTOMÁTICA
# ============================================================================
# Esta configuração detecta automaticamente o ambiente e serve arquivos quando necessário
#
# DESENVOLVIMENTO (runserver):
#   - Serve /media/ e /static/ automaticamente via Django
#   - Não precisa configurar nada
#
# PRODUÇÃO (gunicorn + nginx/apache):
#   - Detecta que está em produção (via variável DJANGO_ENV ou ausência de DEBUG)
#   - NÃO serve arquivos via Django (performance)
#   - Você deve configurar nginx/apache para servir /media/ e /static/
#
# Para forçar serving em produção (NÃO RECOMENDADO), configure:
#   DJANGO_SERVE_MEDIA=true no .env
# ============================================================================

# Detectar ambiente automaticamente
def should_serve_media_files():
    """
    Detecta se deve servir arquivos de media via Django.

    Retorna True se:
    - DEBUG=True (desenvolvimento explícito)
    - Rodando com runserver (python manage.py runserver)
    - Rodando em localhost/127.0.0.1 (desenvolvimento)
    - Variável DJANGO_SERVE_MEDIA=true (override manual)

    Retorna False se:
    - Rodando com gunicorn/uwsgi (produção)
    - Variável DJANGO_ENV=production
    """
    # 1. Se DEBUG=True, sempre serve (desenvolvimento)
    if settings.DEBUG:
        print(f"  [Detecção] DEBUG={settings.DEBUG} → SERVE")
        return True

    # 2. Verificar se está rodando com runserver (development server)
    # runserver passa 'runserver' nos argumentos do sys.argv
    if 'runserver' in sys.argv:
        print(f"  [Detecção] 'runserver' detectado em sys.argv → SERVE")
        return True

    # 3. Verificar se está rodando em localhost (desenvolvimento comum)
    # Mesmo com DEBUG=False, se está em localhost, serve os arquivos
    allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
    localhost_indicators = ['localhost', '127.0.0.1', '0.0.0.0']

    # Se ALLOWED_HOSTS contém localhost e não está em produção explícita
    if allowed_hosts:
        has_localhost = any(
            indicator in str(host).lower()
            for host in allowed_hosts
            for indicator in localhost_indicators
        )
        if has_localhost:
            # Verificar se não está forçando produção
            django_env = os.getenv('DJANGO_ENV', '').lower()
            if django_env != 'production':
                print(f"  [Detecção] localhost detectado em ALLOWED_HOSTS → SERVE")
                return True
            else:
                print(f"  [Detecção] localhost em ALLOWED_HOSTS mas DJANGO_ENV=production → continua verificando...")

    # 4. Variável de ambiente para override manual
    serve_media_env = os.getenv('DJANGO_SERVE_MEDIA', '').lower()
    if serve_media_env in ('true', '1', 'yes'):
        print(f"  [Detecção] DJANGO_SERVE_MEDIA={serve_media_env} → SERVE")
        return True

    # 5. Se DJANGO_ENV=production, NÃO serve (produção explícita)
    django_env = os.getenv('DJANGO_ENV', '').lower()
    if django_env == 'production':
        print(f"  [Detecção] DJANGO_ENV={django_env} → NÃO SERVE")
        return False

    # 6. Detectar servidores WSGI/ASGI (gunicorn, uwsgi, etc)
    # Se qualquer um destes está no comando, é produção
    production_servers = ['gunicorn', 'uwsgi', 'daphne', 'hypercorn', 'waitress']
    for server in production_servers:
        if server in sys.argv[0].lower() or any(server in arg.lower() for arg in sys.argv):
            print(f"  [Detecção] Servidor de produção '{server}' detectado → NÃO SERVE")
            return False

    # 7. Default: SERVE se tiver dúvida (melhor servir em dev que falhar)
    # Só não serve se tiver certeza que é produção
    print(f"  [Detecção] Ambiente incerto, sys.argv={sys.argv[:2]} → SERVE (safe default)")
    return True

# Servir arquivos automaticamente quando apropriado
if should_serve_media_files():
    try:
        from django.views.static import serve as static_serve
        from django.urls import re_path

        # Adicionar pattern de media manualmente (funciona com DEBUG=False)
        urlpatterns += [
            re_path(r'^media/(?P<path>.*)$', static_serve, {
                'document_root': settings.MEDIA_ROOT,
            }),
        ]
        print(f"  [Media] ✓ Pattern adicionado para {settings.MEDIA_URL}")

        # Adicionar pattern de static manualmente (funciona com DEBUG=False)
        urlpatterns += [
            re_path(r'^static/(?P<path>.*)$', static_serve, {
                'document_root': settings.STATIC_ROOT,
            }),
        ]
        print(f"  [Static] ✓ Pattern adicionado para {settings.STATIC_URL}")

        print("📁 [Django] Servindo arquivos de media e static via Django (desenvolvimento)")
    except Exception as e:
        print(f"❌ [ERRO] Falha ao adicionar patterns: {e}")
        import traceback
        traceback.print_exc()
else:
    print("🚀 [Django] Arquivos de media/static devem ser servidos via nginx/apache (produção)")
    print("   Configure seu servidor web para servir:")
    print(f"   - {settings.MEDIA_URL} → {settings.MEDIA_ROOT}")
    print(f"   - {settings.STATIC_URL} → {settings.STATIC_ROOT}")

handler404 = 'cadastros.views.not_found'
