"""
Serviço de Web Push Notifications.

Envia notificações push para navegadores de usuários usando a Web Push API.
Requer a biblioteca pywebpush e configuração de chaves VAPID.

Instalação:
    pip install pywebpush

Configuração no .env:
    VAPID_PUBLIC_KEY=<chave_publica>
    VAPID_PRIVATE_KEY=<chave_privada>
    VAPID_EMAIL=contato@seudominio.com

Para gerar chaves VAPID:
    from pywebpush import webpush
    import base64
    import os
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    # Gerar par de chaves
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    # Exportar chave privada
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
    vapid_private = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')

    # Exportar chave pública
    public_bytes = public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint
    )
    vapid_public = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')

    print(f"VAPID_PUBLIC_KEY={vapid_public}")
    print(f"VAPID_PRIVATE_KEY={vapid_private}")
"""

import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def enviar_push_pagamento(usuario, titulo, mensagem, dados=None):
    """
    Envia push notification para todas as subscriptions ativas de um usuário.

    Args:
        usuario: Instância do User
        titulo: Título da notificação
        mensagem: Corpo da notificação
        dados: Dict com dados extras (ex: url para navegar ao clicar)

    Returns:
        dict: {enviados: int, falhas: int, detalhes: list}
    """
    from nossopainel.models import PushSubscription

    # Verificar se VAPID está configurado
    vapid_private = getattr(settings, 'VAPID_PRIVATE_KEY', None)
    vapid_email = getattr(settings, 'VAPID_EMAIL', None)

    if not vapid_private or not vapid_email:
        logger.warning('[Push] VAPID keys não configuradas. Ignorando push notification.')
        return {'enviados': 0, 'falhas': 0, 'detalhes': ['VAPID não configurado']}

    # Buscar subscriptions ativas do usuário
    subscriptions = PushSubscription.objects.filter(usuario=usuario, ativo=True)

    if not subscriptions.exists():
        logger.debug(f'[Push] Nenhuma subscription ativa para usuário {usuario.id}')
        return {'enviados': 0, 'falhas': 0, 'detalhes': ['Sem subscriptions']}

    # Preparar payload
    payload = json.dumps({
        'title': titulo,
        'body': mensagem,
        'icon': '/static/images/icon-192.png',
        'badge': '/static/images/badge-72.png',
        'vibrate': [100, 50, 100],
        'data': dados or {},
        'actions': [
            {'action': 'open', 'title': 'Abrir'},
            {'action': 'close', 'title': 'Fechar'}
        ]
    })

    resultados = {
        'enviados': 0,
        'falhas': 0,
        'detalhes': []
    }

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning('[Push] pywebpush não instalado. Execute: pip install pywebpush')
        return {'enviados': 0, 'falhas': 0, 'detalhes': ['pywebpush não instalado']}

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {
                        'p256dh': sub.p256dh,
                        'auth': sub.auth
                    }
                },
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={
                    'sub': f'mailto:{vapid_email}'
                }
            )
            resultados['enviados'] += 1
            logger.info(f'[Push] Enviado para subscription {sub.id}')

        except WebPushException as e:
            resultados['falhas'] += 1
            resultados['detalhes'].append(f'Subscription {sub.id}: {str(e)}')

            # Se subscription expirou (410 Gone) ou não é mais válida (404), desativar
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code in (404, 410):
                    sub.ativo = False
                    sub.save(update_fields=['ativo'])
                    logger.info(f'[Push] Subscription {sub.id} marcada como inativa (status {e.response.status_code})')

            logger.error(f'[Push] Erro ao enviar para subscription {sub.id}: {e}')

        except Exception as e:
            resultados['falhas'] += 1
            resultados['detalhes'].append(f'Subscription {sub.id}: {str(e)}')
            logger.error(f'[Push] Erro inesperado: {e}')

    return resultados


def enviar_push_para_todos(usuarios_ids, titulo, mensagem, dados=None):
    """
    Envia push notification para múltiplos usuários.

    Args:
        usuarios_ids: Lista de IDs de usuários
        titulo: Título da notificação
        mensagem: Corpo da notificação
        dados: Dict com dados extras

    Returns:
        dict: Estatísticas totais de envio
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    total_enviados = 0
    total_falhas = 0

    for user_id in usuarios_ids:
        try:
            usuario = User.objects.get(id=user_id)
            resultado = enviar_push_pagamento(usuario, titulo, mensagem, dados)
            total_enviados += resultado['enviados']
            total_falhas += resultado['falhas']
        except User.DoesNotExist:
            logger.warning(f'[Push] Usuário {user_id} não encontrado')
            total_falhas += 1

    return {
        'total_enviados': total_enviados,
        'total_falhas': total_falhas
    }


def gerar_chaves_vapid():
    """
    Gera um novo par de chaves VAPID.

    Returns:
        dict: {'public_key': str, 'private_key': str}

    Uso:
        from nossopainel.services.push_notifications import gerar_chaves_vapid
        chaves = gerar_chaves_vapid()
        print(f"VAPID_PUBLIC_KEY={chaves['public_key']}")
        print(f"VAPID_PRIVATE_KEY={chaves['private_key']}")
    """
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    # Gerar par de chaves EC P-256
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    # Exportar chave privada (formato raw de 32 bytes)
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
    vapid_private = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')

    # Exportar chave pública (formato uncompressed point)
    public_bytes = public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint
    )
    vapid_public = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')

    return {
        'public_key': vapid_public,
        'private_key': vapid_private
    }
