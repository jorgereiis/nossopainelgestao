"""
Utilidades para envio de emails de notificação do sistema.
Centraliza toda lógica de envio de emails relacionados ao perfil do usuário.
"""

import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_profile_change_notification(user, change_type, changes_detail=None, ip_address=None):
    """
    Envia email notificando alteração no perfil do usuário.

    Args:
        user: Instância do User
        change_type: Tipo de alteração ('profile', 'password', 'avatar', 'security')
        changes_detail: Dict com detalhes das alterações
        ip_address: IP de onde foi feita a alteração
    """
    try:
        profile = user.profile

        # Verificar se o usuário quer receber notificações
        if not profile.email_on_profile_change:
            return False

        # Preparar contexto para o template
        site_url = settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000'
        context = {
            'user': user,
            'change_type': change_type,
            'changes': changes_detail or {},
            'ip_address': ip_address or 'Desconhecido',
            'timestamp': timezone.now(),
            'site_name': 'Nosso Painel - Gestão IPTV',
            'site_url': site_url,
        }

        # Definir assunto e template baseado no tipo de alteração
        subject_map = {
            'profile': 'Alteração no seu perfil',
            'password': 'Senha alterada com sucesso',
            'avatar': 'Avatar atualizado',
            'security': 'Configurações de segurança alteradas',
        }

        subject = f'{subject_map.get(change_type, "Alteração no perfil")} - Nosso Painel'

        # Renderizar email em HTML
        html_message = render_to_string('emails/profile_change.html', context)

        # Renderizar email em texto puro (fallback)
        text_message = render_to_string('emails/profile_change.txt', context)

        # Enviar email
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@nossopainel.com')
        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )

        logger.info(f'[EMAIL] Notificação de {change_type} enviada para {user.email}')
        return True

    except Exception as e:
        logger.error(f'[EMAIL] Erro ao enviar notificação para {user.email}: {str(e)}', exc_info=True)
        return False


def send_password_change_notification(user, ip_address=None):
    """
    Envia email específico para alteração de senha.
    """
    try:
        profile = user.profile

        if not profile.email_on_password_change:
            return False

        site_url = settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000'
        context = {
            'user': user,
            'ip_address': ip_address or 'Desconhecido',
            'timestamp': timezone.now(),
            'site_name': 'Nosso Painel - Gestão IPTV',
            'site_url': site_url,
        }

        subject = 'Sua senha foi alterada - Nosso Painel'
        html_message = render_to_string('emails/password_changed.html', context)
        text_message = render_to_string('emails/password_changed.txt', context)

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@nossopainel.com')
        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )

        logger.info(f'[EMAIL] Notificação de alteração de senha enviada para {user.email}')
        return True

    except Exception as e:
        logger.error(f'[EMAIL] Erro ao enviar notificação de senha para {user.email}: {str(e)}', exc_info=True)
        return False


def send_login_notification(user, ip_address=None, user_agent=None, location=None):
    """
    Envia email notificando novo login (se habilitado).
    """
    try:
        profile = user.profile

        if not profile.email_on_login:
            return False

        site_url = settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000'
        context = {
            'user': user,
            'ip_address': ip_address or 'Desconhecido',
            'user_agent': user_agent or 'Desconhecido',
            'location': location or 'Localização não disponível',
            'timestamp': timezone.now(),
            'site_name': 'Nosso Painel - Gestão IPTV',
            'site_url': site_url,
        }

        subject = 'Novo login detectado - Nosso Painel'
        html_message = render_to_string('emails/new_login.html', context)
        text_message = render_to_string('emails/new_login.txt', context)

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@nossopainel.com')
        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )

        logger.info(f'[EMAIL] Notificação de login enviada para {user.email}')
        return True

    except Exception as e:
        logger.error(f'[EMAIL] Erro ao enviar notificação de login para {user.email}: {str(e)}', exc_info=True)
        return False


def send_2fa_enabled_notification(user):
    """
    Envia email notificando que 2FA foi ativado.
    """
    try:
        site_url = settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000'
        context = {
            'user': user,
            'timestamp': timezone.now(),
            'site_name': 'Nosso Painel - Gestão IPTV',
            'site_url': site_url,
        }

        subject = 'Autenticação em Dois Fatores Ativada - Nosso Painel'
        html_message = render_to_string('emails/2fa_enabled.html', context)
        text_message = render_to_string('emails/2fa_enabled.txt', context)

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@nossopainel.com')
        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )

        logger.info(f'[EMAIL] Notificação de 2FA ativado enviada para {user.email}')
        return True

    except Exception as e:
        logger.error(f'[EMAIL] Erro ao enviar notificação de 2FA para {user.email}: {str(e)}', exc_info=True)
        return False
