from django.conf import settings
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


class CheckUserLoggedInMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._public_paths = None
        self._public_prefixes = None

    def __call__(self, request):
        if request.user.is_authenticated:
            return self.get_response(request)

        path = request.path
        if path in self.public_paths:
            return self.get_response(request)

        for prefix in self.public_prefixes:
            if prefix and path.startswith(prefix):
                return self.get_response(request)

        return redirect("login")

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

        prefixes = {"/static/", "/media/", "/favicon.ico", "/api/internal/"}
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
