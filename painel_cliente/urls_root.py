"""
URLconf raiz para o Painel do Cliente.

Este arquivo e usado como request.urlconf quando o middleware
detecta um subdominio *.pagar.cc.

Inclui as URLs do painel_cliente com namespace registrado,
permitindo que {% url 'painel_cliente:...' %} funcione nos templates.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path('', include('painel_cliente.urls', namespace='painel_cliente')),
]

# Servir arquivos de mídia em desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
