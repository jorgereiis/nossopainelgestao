"""
Sistema de Autenticação do JampaBet
Completamente isolado do Django Auth
"""
import logging
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from .models import JampabetUser, LoginToken, AuditLog

logger = logging.getLogger(__name__)


class JampabetAuth:
    """
    Sistema de autenticação próprio do JampaBet.
    Não utiliza o Django Auth para garantir isolamento total.
    """

    SESSION_KEY = 'jampabet_user_id'

    @classmethod
    def login(cls, request, user):
        """
        Loga o usuário na sessão do JampaBet.
        Usa uma chave de sessão específica para não conflitar com Django Auth.
        """
        request.session[cls.SESSION_KEY] = user.id
        request.session.modified = True

        # Log de auditoria
        cls._log_action(
            user=user,
            action='login',
            request=request
        )

    @classmethod
    def logout(cls, request):
        """Desloga o usuário"""
        user = cls.get_user(request)

        if cls.SESSION_KEY in request.session:
            del request.session[cls.SESSION_KEY]
            request.session.modified = True

        # Log de auditoria
        if user:
            cls._log_action(
                user=user,
                action='logout',
                request=request
            )

    @classmethod
    def get_user(cls, request):
        """
        Retorna o usuário JampaBet logado ou None.
        Verifica se o usuário existe e está ativo.
        """
        user_id = request.session.get(cls.SESSION_KEY)
        if user_id:
            try:
                return JampabetUser.objects.get(id=user_id, is_active=True)
            except JampabetUser.DoesNotExist:
                # Limpa sessão inválida
                if cls.SESSION_KEY in request.session:
                    del request.session[cls.SESSION_KEY]
        return None

    @classmethod
    def is_authenticated(cls, request):
        """Verifica se há usuário autenticado"""
        return cls.get_user(request) is not None

    @classmethod
    def authenticate(cls, email, password):
        """
        Autentica usuário por email/senha.
        Retorna o usuário se credenciais válidas, None caso contrário.
        """
        try:
            user = JampabetUser.objects.get(email=email.lower(), is_active=True)
            if check_password(password, user.password_hash):
                return user
        except JampabetUser.DoesNotExist:
            # Mesmo tempo de resposta para evitar timing attacks
            check_password(password, make_password('dummy'))
        return None

    @classmethod
    def create_user(cls, name, email, password, request=None):
        """
        Cria um novo usuário JampaBet.
        """
        user = JampabetUser.objects.create(
            name=name.strip(),
            email=email.lower().strip(),
            password_hash=make_password(password)
        )

        # Log de auditoria
        cls._log_action(
            user=user,
            action='register',
            request=request,
            new_value={'email': user.email, 'name': user.name}
        )

        return user

    @classmethod
    def change_password(cls, user, new_password):
        """Altera a senha do usuário"""
        user.password_hash = make_password(new_password)
        user.save(update_fields=['password_hash', 'updated_at'])

    @classmethod
    def send_login_token(cls, user, request=None):
        """
        Gera e envia token de 6 dígitos para 2FA no login.

        Args:
            user: JampabetUser
            request: HttpRequest (para obter IP)

        Returns:
            LoginToken ou None se falhou
        """
        from .email import send_login_token_email

        # Obtém IP do request
        ip_address = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')

        # Gera token (invalida anteriores automaticamente)
        login_token = LoginToken.generate_for_user(user, ip_address)

        # Envia por e-mail
        if send_login_token_email(user, login_token.token):
            logger.info(f"Token 2FA gerado para {user.email}")
            return login_token
        else:
            logger.error(f"Falha ao enviar token 2FA para {user.email}")
            return None

    @classmethod
    def verify_login_token(cls, user, token):
        """
        Verifica token de 2FA.

        Args:
            user: JampabetUser
            token: str - token de 6 dígitos

        Returns:
            bool - True se válido
        """
        try:
            login_token = LoginToken.objects.get(
                user=user,
                token=token,
                used=False,
                expires_at__gt=timezone.now()
            )
            login_token.mark_as_used()
            logger.info(f"Token 2FA validado para {user.email}")
            return True
        except LoginToken.DoesNotExist:
            logger.warning(f"Token 2FA inválido para {user.email}")
            return False

    @classmethod
    def send_activation_email(cls, user, request=None):
        """
        Gera token e envia e-mail de ativação para novo usuário.

        Args:
            user: JampabetUser (deve estar com is_verified=False)
            request: HttpRequest (para construir URL absoluta)

        Returns:
            bool - True se enviou com sucesso
        """
        from .email import send_activation_email

        # Gera token de verificação
        token = user.generate_verification_token()

        # Constrói URL de ativação
        if request:
            scheme = 'https' if request.is_secure() else 'http'
            host = request.get_host()
            # Para JampaBet, a URL real é sem /app/bahia/ pois o middleware reescreve
            if getattr(request, 'is_jampabet', False):
                activation_url = f"{scheme}://{host}/activate/{token}/"
            else:
                activation_url = f"{scheme}://{host}/app/bahia/activate/{token}/"
        else:
            # Fallback para produção
            activation_url = f"https://jampabet.com.br/activate/{token}/"

        # Envia e-mail
        if send_activation_email(user, activation_url):
            logger.info(f"E-mail de ativação enviado para {user.email}")
            return True
        else:
            logger.error(f"Falha ao enviar e-mail de ativação para {user.email}")
            return False

    @classmethod
    def activate_account(cls, token, new_password):
        """
        Ativa conta usando token de verificação.

        Args:
            token: str - token de verificação
            new_password: str - senha definida pelo usuário

        Returns:
            JampabetUser ou None se inválido
        """
        try:
            user = JampabetUser.objects.get(
                verification_token=token,
                is_verified=False
            )

            # Verifica se token não expirou
            if not user.is_verification_token_valid():
                logger.warning(f"Token de ativação expirado para {user.email}")
                return None

            # Ativa conta
            user.is_verified = True
            user.password_hash = make_password(new_password)
            user.verification_token = None
            user.verification_expires = None
            user.save(update_fields=[
                'is_verified',
                'password_hash',
                'verification_token',
                'verification_expires',
                'updated_at'
            ])

            logger.info(f"Conta ativada para {user.email}")
            return user

        except JampabetUser.DoesNotExist:
            logger.warning(f"Token de ativação inválido: {token[:10]}...")
            return None

    @classmethod
    def create_user_by_admin(cls, name, email, request=None):
        """
        Cria usuário pelo admin (sem senha, requer ativação por e-mail).

        Args:
            name: str - nome do usuário
            email: str - e-mail do usuário
            request: HttpRequest

        Returns:
            JampabetUser ou None se falhou
        """
        # Verifica se e-mail já existe
        if JampabetUser.objects.filter(email=email.lower().strip()).exists():
            logger.warning(f"Tentativa de criar usuário com e-mail existente: {email}")
            return None

        user = JampabetUser.objects.create(
            name=name.strip(),
            email=email.lower().strip(),
            password_hash='',  # Vazio até ativação
            is_verified=False,
            is_active=True
        )

        # Log de auditoria
        cls._log_action(
            user=user,
            action='register',
            request=request,
            new_value={'email': user.email, 'name': user.name, 'created_by_admin': True}
        )

        # Envia e-mail de ativação
        cls.send_activation_email(user, request)

        return user

    @classmethod
    def _log_action(cls, user, action, request=None, entity_type='user',
                    entity_id=None, old_value=None, new_value=None):
        """Registra ação no log de auditoria"""
        ip_address = None
        user_agent = ''

        if request:
            # Obtém IP real (considera proxy)
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')

            user_agent = request.META.get('HTTP_USER_AGENT', '')

        AuditLog.objects.create(
            user=user,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id or (user.id if user else None),
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else ''
        )


def jampabet_login_required(view_func):
    """
    Decorator para views que requerem autenticação JampaBet.
    Similar ao login_required do Django, mas para o sistema próprio.
    """
    from functools import wraps
    from django.shortcuts import redirect

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not JampabetAuth.is_authenticated(request):
            return redirect('jampabet:login')
        return view_func(request, *args, **kwargs)

    return wrapper
