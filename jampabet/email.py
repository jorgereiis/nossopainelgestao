"""
Funcoes de envio de e-mail para o JampaBet
"""
import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def send_login_token_email(user, token):
    """
    Envia e-mail com token de verificacao 2FA para login.

    Args:
        user: JampabetUser - usuario que esta fazendo login
        token: str - token de 6 digitos

    Returns:
        bool - True se enviou com sucesso
    """
    # Em modo DEBUG, exibe o token no console e retorna sucesso
    if settings.DEBUG:
        print("\n" + "=" * 60)
        print("   JAMPABET - TOKEN DE VERIFICACAO (MODO DEBUG)")
        print("=" * 60)
        print(f"   Usuario: {user.name} ({user.email})")
        print(f"   TOKEN:   {token}")
        print("=" * 60 + "\n")
        logger.info(f"[DEBUG] Token 2FA para {user.email}: {token}")
        return True

    subject = f'JampaBet - Codigo de Verificacao: {token}'

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #0a0a1a; color: #ffffff; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; padding: 40px; }}
            .logo {{ text-align: center; margin-bottom: 30px; }}
            .logo h1 {{ color: #00ff88; font-size: 28px; margin: 0; }}
            .token-box {{ background: rgba(0, 255, 136, 0.1); border: 2px solid #00ff88; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0; }}
            .token {{ font-size: 36px; font-weight: bold; color: #00ff88; letter-spacing: 8px; }}
            .message {{ color: #b0b0b0; line-height: 1.6; }}
            .warning {{ color: #ff6b6b; font-size: 12px; margin-top: 20px; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">
                <h1>JampaBet</h1>
            </div>
            <p class="message">Olá, <strong>{user.name}</strong>!</p>
            <p class="message">Você solicitou acesso ao JampaBet. Use o código abaixo para confirmar seu login:</p>
            <div class="token-box">
                <div class="token">{token}</div>
            </div>
            <p class="message">Este código expira em <strong>5 minutos</strong>.</p>
            <p class="warning">Se você não solicitou este código, ignore este e-mail. Sua conta está segura.</p>
            <div class="footer">
                <p>JampaBet - Palpites do Bahia</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_message = f"""
JampaBet - Código de Verificação

Olá, {user.name}!

Você solicitou acesso ao JampaBet. Use o código abaixo para confirmar seu login:

{token}

Este código expira em 5 minutos.

Se você não solicitou este código, ignore este e-mail. Sua conta está segura.

--
JampaBet - Palpites do Bahia
    """

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Token 2FA enviado para {user.email}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar token 2FA para {user.email}: {e}")
        return False


def send_activation_email(user, activation_url):
    """
    Envia e-mail de ativacao de conta para novo usuario.

    Args:
        user: JampabetUser - usuario recem-criado
        activation_url: str - URL completa para ativacao

    Returns:
        bool - True se enviou com sucesso
    """
    # Em modo DEBUG, exibe a URL no console e retorna sucesso
    if settings.DEBUG:
        print("\n" + "=" * 60)
        print("   JAMPABET - LINK DE ATIVACAO (MODO DEBUG)")
        print("=" * 60)
        print(f"   Usuario: {user.name} ({user.email})")
        print(f"   URL: {activation_url}")
        print("=" * 60 + "\n")
        logger.info(f"[DEBUG] Link de ativacao para {user.email}: {activation_url}")
        return True

    subject = 'JampaBet - Ative sua conta'

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #0a0a1a; color: #ffffff; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; padding: 40px; }}
            .logo {{ text-align: center; margin-bottom: 30px; }}
            .logo h1 {{ color: #00ff88; font-size: 28px; margin: 0; }}
            .message {{ color: #b0b0b0; line-height: 1.6; }}
            .btn {{ display: inline-block; background: linear-gradient(135deg, #00ff88, #00cc6a); color: #000; padding: 15px 40px; border-radius: 8px; text-decoration: none; font-weight: bold; margin: 20px 0; }}
            .link-box {{ background: rgba(255,255,255,0.05); border-radius: 8px; padding: 15px; word-break: break-all; font-size: 12px; color: #888; margin-top: 20px; }}
            .warning {{ color: #ff6b6b; font-size: 12px; margin-top: 20px; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">
                <h1>JampaBet</h1>
            </div>
            <p class="message">Olá, <strong>{user.name}</strong>!</p>
            <p class="message">Sua conta foi criada no JampaBet! Para ativá-la, clique no botão abaixo e defina sua senha:</p>
            <p style="text-align: center;">
                <a href="{activation_url}" class="btn">Ativar Minha Conta</a>
            </p>
            <p class="message">Ou copie e cole o link abaixo no seu navegador:</p>
            <div class="link-box">{activation_url}</div>
            <p class="warning">Este link expira em <strong>24 horas</strong>. Se expirar, entre em contato com o administrador.</p>
            <div class="footer">
                <p>JampaBet - Palpites do Bahia</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_message = f"""
JampaBet - Ative sua conta

Olá, {user.name}!

Sua conta foi criada no JampaBet! Para ativá-la, acesse o link abaixo e defina sua senha:

{activation_url}

Este link expira em 24 horas. Se expirar, entre em contato com o administrador.

--
JampaBet - Palpites do Bahia
    """

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"E-mail de ativação enviado para {user.email}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail de ativação para {user.email}: {e}")
        return False


def send_password_reset_email(user, reset_url):
    """
    Envia e-mail de redefinição de senha.

    Args:
        user: JampabetUser - usuário que solicitou reset
        reset_url: str - URL completa para redefinição

    Returns:
        bool - True se enviou com sucesso
    """
    subject = 'JampaBet - Redefinição de Senha'

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #0a0a1a; color: #ffffff; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; padding: 40px; }}
            .logo {{ text-align: center; margin-bottom: 30px; }}
            .logo h1 {{ color: #00ff88; font-size: 28px; margin: 0; }}
            .message {{ color: #b0b0b0; line-height: 1.6; }}
            .btn {{ display: inline-block; background: linear-gradient(135deg, #00ff88, #00cc6a); color: #000; padding: 15px 40px; border-radius: 8px; text-decoration: none; font-weight: bold; margin: 20px 0; }}
            .link-box {{ background: rgba(255,255,255,0.05); border-radius: 8px; padding: 15px; word-break: break-all; font-size: 12px; color: #888; margin-top: 20px; }}
            .warning {{ color: #ff6b6b; font-size: 12px; margin-top: 20px; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">
                <h1>JampaBet</h1>
            </div>
            <p class="message">Olá, <strong>{user.name}</strong>!</p>
            <p class="message">Você solicitou a redefinição de senha da sua conta JampaBet. Clique no botão abaixo para criar uma nova senha:</p>
            <p style="text-align: center;">
                <a href="{reset_url}" class="btn">Redefinir Senha</a>
            </p>
            <p class="message">Ou copie e cole o link abaixo no seu navegador:</p>
            <div class="link-box">{reset_url}</div>
            <p class="warning">Este link expira em <strong>1 hora</strong>. Se você não solicitou esta redefinição, ignore este e-mail.</p>
            <div class="footer">
                <p>JampaBet - Palpites do Bahia</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_message = f"""
JampaBet - Redefinição de Senha

Olá, {user.name}!

Você solicitou a redefinição de senha da sua conta JampaBet. Acesse o link abaixo para criar uma nova senha:

{reset_url}

Este link expira em 1 hora. Se você não solicitou esta redefinição, ignore este e-mail.

--
JampaBet - Palpites do Bahia
    """

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"E-mail de redefinição de senha enviado para {user.email}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail de redefinição para {user.email}: {e}")
        return False
