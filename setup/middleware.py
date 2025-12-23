from django.conf import settings
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


class DomainRoutingMiddleware:
    """
    Middleware para roteamento baseado em domínio.
    Permite que múltiplos apps Django rodem com domínios diferentes.

    - jampabet.com.br -> reescreve URL para /app/bahia/ (ex: jampabet.com.br/login -> /app/bahia/login)
    - nossopainel.com.br -> URLs normais (padrão)

    Usa URL rewriting ao invés de trocar URLconf, mantendo todos os
    namespaces registrados no setup/urls.py.
    """

    # Mapeamento de domínios do JampaBet
    JAMPABET_DOMAINS = {
        'jampabet.com.br',
        'www.jampabet.com.br',
        'local.jampabet.com.br',
        'localhost:8002',  # Dev JampaBet
        '127.0.0.1:8002',  # Dev JampaBet
        'local.jampabet.com.br:8002',  # Dev JampaBet com domínio local
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower()

        # Verifica se é domínio do JampaBet
        if self._is_jampabet_domain(host):
            request.is_jampabet = True
            # Reescreve a URL para incluir o prefixo /app/bahia/
            # Isso permite que jampabet.com.br/ seja tratado como /app/bahia/
            if not request.path.startswith('/app/bahia/'):
                # Não reescreve paths de static/media/admin
                if not request.path.startswith(('/static/', '/media/', '/painel-configs/')):
                    request.path_info = '/app/bahia' + request.path
                    request.path = '/app/bahia' + request.path
        else:
            request.is_jampabet = False

        return self.get_response(request)

    def _is_jampabet_domain(self, host):
        """Verifica se o host é um domínio do JampaBet"""
        # Verifica match exato
        if host in self.JAMPABET_DOMAINS:
            return True

        # Verifica sem porta
        host_without_port = host.split(':')[0]
        return host_without_port in {'jampabet.com.br', 'www.jampabet.com.br', 'local.jampabet.com.br'}


class CheckUserLoggedInMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._public_paths = None
        self._public_prefixes = None

    def __call__(self, request):
        # Se for JampaBet, usa lógica própria de autenticação
        if getattr(request, 'is_jampabet', False):
            return self._handle_jampabet(request)

        # Se for Painel Cliente, ignora (tem middleware proprio de autenticacao)
        if getattr(request, 'is_painel_cliente', False):
            return self.get_response(request)

        # Lógica original para NossoPainel
        if request.user.is_authenticated:
            return self.get_response(request)

        path = request.path
        if path in self.public_paths:
            return self.get_response(request)

        for prefix in self.public_prefixes:
            if prefix and path.startswith(prefix):
                return self.get_response(request)

        return redirect("login")

    def _handle_jampabet(self, request):
        """
        Tratamento especifico para requisicoes do JampaBet.
        Usa sistema de autenticacao isolado.
        """
        from django.http import JsonResponse
        from jampabet.auth import JampabetAuth

        # Paths publicos do JampaBet (apos rewrite, path comeca com /app/bahia/)
        jampabet_public_paths = {
            '/app/bahia/', '/app/bahia',
            '/app/bahia/login/', '/app/bahia/login',
        }

        # Prefixos publicos (APIs de auth, ativacao, static/media)
        jampabet_public_prefixes = (
            '/static/',
            '/media/',
            '/app/bahia/api/auth/',      # APIs de autenticacao (login step1, step2, resend)
            '/app/bahia/activate/',       # Ativacao de conta
        )

        path = request.path

        # Injeta o usuario JampaBet no request
        request.jampabet_user = JampabetAuth.get_user(request)

        # Verifica se e path publico
        if path in jampabet_public_paths:
            return self.get_response(request)

        for prefix in jampabet_public_prefixes:
            if path.startswith(prefix):
                return self.get_response(request)

        # Se nao esta autenticado no JampaBet
        if not request.jampabet_user:
            # Para APIs, retorna JSON 401 ao inves de redirecionar
            if '/api/' in path:
                return JsonResponse(
                    {'error': 'Nao autenticado', 'redirect': '/app/bahia/login/'},
                    status=401
                )
            # Para paginas, redireciona para login
            return redirect('jampabet:login')

        return self.get_response(request)

    @property
    def public_paths(self):
        if self._public_paths is not None:
            return self._public_paths

        paths = {"/", "/admin/login/"}
        for name in ("login", "logout", "verify-2fa"):
            try:
                paths.add(reverse(name))
            except NoReverseMatch:
                continue
        self._public_paths = paths
        return self._public_paths

    @property
    def public_prefixes(self):
        if self._public_prefixes is not None:
            return self._public_prefixes

        prefixes = {"/static/", "/media/", "/favicon.ico", "/api/internal/", "/webhook/"}
        static_url = getattr(settings, "STATIC_URL", None)
        if static_url:
            prefixes.add(static_url if static_url.endswith("/") else f"{static_url}/")
        media_url = getattr(settings, "MEDIA_URL", None)
        if media_url:
            prefixes.add(media_url if media_url.endswith("/") else f"{media_url}/")

        self._public_prefixes = tuple(prefixes)
        return self._public_prefixes


class InternalAPIMiddleware:
    """
    Middleware para restringir acesso a endpoints internos apenas à rede interna.

    Usado para proteger rotas que devem ser acessadas apenas por containers
    dentro da rede Docker (ex: MySQL triggers enviando notificações).

    Configuração via .env:
        INTERNAL_API_ALLOWED_IPS=172.18.0.0/16,127.0.0.1,::1
    """

    # Endpoints que requerem acesso apenas da rede interna
    INTERNAL_ENDPOINTS = ['/api/internal/']

    def __init__(self, get_response):
        self.get_response = get_response
        self.allowed_networks = self._load_allowed_networks()

    def __call__(self, request):
        # Verifica se a requisição é para um endpoint interno
        if self._is_internal_endpoint(request.path):
            client_ip = self._get_client_ip(request)

            if not self._is_allowed_ip(client_ip):
                from django.http import JsonResponse
                return JsonResponse({
                    'error': 'Access denied - Internal network only',
                    'client_ip': client_ip
                }, status=403)

        return self.get_response(request)

    def _is_internal_endpoint(self, path):
        """Verifica se o path começa com algum endpoint interno"""
        return any(path.startswith(endpoint) for endpoint in self.INTERNAL_ENDPOINTS)

    def _get_client_ip(self, request):
        """
        Extrai o IP real do cliente considerando proxies (Nginx).
        Prioriza X-Forwarded-For quando disponível.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Pega o primeiro IP da lista (cliente original)
            return x_forwarded_for.split(',')[0].strip()

        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip.strip()

        return request.META.get('REMOTE_ADDR', '')

    def _load_allowed_networks(self):
        """Carrega as redes permitidas da configuração"""
        import os
        from ipaddress import ip_network

        # Padrão: redes Docker internas + localhost
        default_networks = [
            '172.18.0.0/16',  # Rede Docker padrão
            '172.17.0.0/16',  # Rede Docker alternativa
            '127.0.0.0/8',    # Localhost IPv4
            '::1/128',        # Localhost IPv6
        ]

        # Tenta carregar do .env
        allowed_ips = os.getenv('INTERNAL_API_ALLOWED_IPS', '')
        if allowed_ips:
            default_networks.extend(allowed_ips.split(','))

        # Converte para objetos ip_network
        networks = []
        for net in default_networks:
            try:
                networks.append(ip_network(net.strip(), strict=False))
            except ValueError:
                # Ignora redes inválidas
                continue

        return networks

    def _is_allowed_ip(self, ip_str):
        """Verifica se o IP está em alguma rede permitida"""
        from ipaddress import ip_address, AddressValueError

        try:
            client_ip = ip_address(ip_str)
            return any(client_ip in network for network in self.allowed_networks)
        except (ValueError, AddressValueError):
            # IP inválido = não permitido
            return False


class WppRateLimitMiddleware:
    """
    Middleware para limitar requisições aos endpoints do WhatsApp.

    Protege contra abuso e ataques de força bruta nos endpoints de conexão.

    Limites por endpoint (por usuário/minuto):
    - /conectar-wpp/: 3
    - /desconectar-wpp/: 5
    - /cancelar-sessao-wpp/: 3
    - /status-wpp/: 30
    """

    # Configuração: (limite_requisições, janela_em_segundos)
    RATE_LIMITS = {
        '/conectar-wpp/': (3, 60),        # 3 req/min
        '/desconectar-wpp/': (5, 60),     # 5 req/min
        '/cancelar-sessao-wpp/': (3, 60), # 3 req/min
        '/status-wpp/': (30, 60),         # 30 req/min
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if path in self.RATE_LIMITS:
            limit, window = self.RATE_LIMITS[path]

            # Identificador único: user_id (se autenticado) ou IP
            if request.user.is_authenticated:
                identifier = f"user_{request.user.id}"
            else:
                identifier = f"ip_{self._get_client_ip(request)}"

            cache_key = f"ratelimit:{identifier}:{path}"

            from django.core.cache import cache
            count = cache.get(cache_key, 0)

            if count >= limit:
                from django.http import JsonResponse
                return JsonResponse({
                    "erro": "Muitas requisições. Aguarde um momento.",
                    "retry_after": window,
                    "limit": f"{limit}/{window}s"
                }, status=429)

            # Incrementa contador com TTL
            cache.set(cache_key, count + 1, window)

        return self.get_response(request)

    def _get_client_ip(self, request):
        """Extrai o IP real do cliente considerando proxies."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip.strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
