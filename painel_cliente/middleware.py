"""
Middleware para roteamento de subdominios do Painel do Cliente.

Este middleware identifica requisicoes vindas de *.pagar.cc e
roteia para as views do painel_cliente usando request.urlconf.
"""

from django.http import HttpResponseNotFound
from django.shortcuts import render


class SubdomainRoutingMiddleware:
    """
    Identifica subdominio e roteia para views do painel_cliente.

    Para requisicoes em *.pagar.cc:
    - Extrai o nome do subdominio
    - Busca a configuracao no banco de dados
    - Injeta dados em request.painel_config
    - Define request.urlconf para usar painel_cliente.urls

    Para outras requisicoes:
    - Seta request.is_painel_cliente = False
    - Continua o fluxo normal (nossopainel, jampabet, etc.)
    """

    # Hosts de desenvolvimento que ativam o painel_cliente
    DEV_PAINEL_HOSTS = {
        'localhost:8003',
        '127.0.0.1:8003',
        'local.pagar.cc:8003',
    }

    def __init__(self, get_response):
        self.get_response = get_response
        # Dominio base do painel (pode ser configurado via settings)
        self.dominio_painel = '.pagar.cc'

    def __call__(self, request):
        # Extrai o host completo (com porta) para verificar dev
        host_with_port = request.get_host().lower()
        # Extrai o host da requisicao (sem porta)
        host = host_with_port.split(':')[0].lower()

        # Verifica se e um subdominio do painel (producao)
        if host.endswith(self.dominio_painel):
            print(f"\n{'='*60}")
            print(f"[PainelCliente Routing] Host detectado: {host}")
            print(f"[PainelCliente Routing] Path: {request.path}")
            return self._handle_painel_request(request, host)

        # Verifica se e ambiente de desenvolvimento (porta 8003)
        if host_with_port in self.DEV_PAINEL_HOSTS:
            print(f"\n{'='*60}")
            print(f"[PainelCliente Routing] DEV Host detectado: {host_with_port}")
            print(f"[PainelCliente Routing] Path: {request.path}")
            return self._handle_dev_request(request)

        # Requisicao normal (nossopainel, jampabet, etc.)
        request.is_painel_cliente = False
        request.painel_config = None
        return self.get_response(request)

    def _handle_painel_request(self, request, host):
        """
        Processa requisicao para subdominio do painel.

        Define request.urlconf para usar painel_cliente.urls,
        permitindo que o Django resolva as URLs normalmente.

        Args:
            request: HttpRequest
            host: Nome do host (ex: meunegocio.pagar.cc)

        Returns:
            HttpResponse
        """
        # Importa aqui para evitar importacao circular
        from .models import SubdominioPainelCliente

        # Extrai nome do subdominio
        subdomain = host.replace(self.dominio_painel, '')
        print(f"[PainelCliente Routing] Subdominio extraido: '{subdomain}'")

        # Ignora se for apenas o dominio base (pagar.cc sem subdominio)
        if not subdomain or subdomain == 'www':
            print(f"[PainelCliente Routing] ERRO: Subdominio vazio ou www")
            print(f"{'='*60}\n")
            return self._render_painel_not_found(request)

        try:
            # Busca configuracao do subdominio
            config = SubdominioPainelCliente.objects.select_related(
                'admin_responsavel',
                'conta_bancaria',
                'conta_bancaria__instituicao'
            ).get(
                subdominio=subdomain,
                ativo=True
            )

            print(f"[PainelCliente Routing] Subdominio encontrado: {config.nome_exibicao}")
            print(f"[PainelCliente Routing] Admin: {config.admin_responsavel}")
            print(f"[PainelCliente Routing] Ativo: {config.ativo}")
            print(f"{'='*60}")

            # Injeta dados na requisicao
            request.is_painel_cliente = True
            request.painel_config = config

            # Define urlconf para usar as URLs do painel_cliente
            request.urlconf = 'painel_cliente.urls_root'

            # Continua o fluxo normal (outros middlewares serao executados)
            return self.get_response(request)

        except SubdominioPainelCliente.DoesNotExist:
            print(f"[PainelCliente Routing] ERRO: Subdominio '{subdomain}' nao encontrado ou inativo")
            print(f"{'='*60}\n")
            return self._render_painel_not_found(request)

    def _handle_dev_request(self, request):
        """
        Processa requisicao em ambiente de desenvolvimento (porta 8003).

        Em dev, nao ha subdominio real, entao busca a configuracao de:
        1. Parametro GET ?subdominio=nome
        2. Variavel de ambiente DEV_PAINEL_SUBDOMINIO
        3. Primeiro subdominio ativo no banco

        Args:
            request: HttpRequest

        Returns:
            HttpResponse
        """
        import os
        from .models import SubdominioPainelCliente

        # Tenta obter subdominio do parametro GET
        subdomain = request.GET.get('subdominio', '')

        # Tenta obter da variavel de ambiente
        if not subdomain:
            subdomain = os.getenv('DEV_PAINEL_SUBDOMINIO', '')

        if subdomain:
            # Busca pelo nome especificado
            try:
                config = SubdominioPainelCliente.objects.select_related(
                    'admin_responsavel',
                    'conta_bancaria',
                    'conta_bancaria__instituicao'
                ).get(
                    subdominio=subdomain,
                    ativo=True
                )
                print(f"[PainelCliente Routing] DEV: Usando subdominio '{subdomain}'")
            except SubdominioPainelCliente.DoesNotExist:
                print(f"[PainelCliente Routing] DEV: Subdominio '{subdomain}' nao encontrado")
                return self._render_painel_not_found(
                    request,
                    f"Subdominio de desenvolvimento '{subdomain}' nao encontrado. "
                    f"Crie um subdominio no admin ou use ?subdominio=nome"
                )
        else:
            # Busca o primeiro subdominio ativo
            config = SubdominioPainelCliente.objects.select_related(
                'admin_responsavel',
                'conta_bancaria',
                'conta_bancaria__instituicao'
            ).filter(ativo=True).first()

            if not config:
                print(f"[PainelCliente Routing] DEV: Nenhum subdominio ativo encontrado")
                return self._render_painel_not_found(
                    request,
                    "Nenhum subdominio ativo encontrado. "
                    "Crie um subdominio no admin Django (/painel-configs/) ou "
                    "use ?subdominio=nome na URL."
                )

            print(f"[PainelCliente Routing] DEV: Usando primeiro subdominio ativo: '{config.subdominio}'")

        print(f"[PainelCliente Routing] DEV: Subdominio: {config.nome_exibicao}")
        print(f"[PainelCliente Routing] DEV: Admin: {config.admin_responsavel}")
        print(f"{'='*60}")

        # Injeta dados na requisicao
        request.is_painel_cliente = True
        request.painel_config = config

        # Define urlconf para usar as URLs do painel_cliente
        request.urlconf = 'painel_cliente.urls_root'

        return self.get_response(request)

    def _render_painel_not_found(self, request, mensagem=None):
        """
        Renderiza pagina de painel nao encontrado.

        Em producao, mostra uma pagina amigavel.
        Em debug, mostra erro 404 padrao.
        """
        from django.conf import settings

        if settings.DEBUG:
            msg = mensagem or 'O subdominio solicitado nao esta configurado ou esta inativo.'
            return HttpResponseNotFound(
                f'<h1>Painel nao encontrado</h1>'
                f'<p>{msg}</p>'
            )

        # Em producao, renderiza template customizado
        try:
            return render(
                request,
                'painel_cliente/errors/404_painel.html',
                status=404
            )
        except Exception:
            return HttpResponseNotFound('Painel nao encontrado')


class PainelClienteSessionMiddleware:
    """
    Middleware para gerenciamento de sessao do cliente no painel.

    Verifica o token de sessao no cookie e injeta dados do cliente
    na requisicao se a sessao for valida.
    """

    COOKIE_NAME = 'painel_cliente_session'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Processa apenas requisicoes do painel
        if not getattr(request, 'is_painel_cliente', False):
            request.cliente_sessao = None
            return self.get_response(request)

        # Busca sessao pelo token no cookie
        token = request.COOKIES.get(self.COOKIE_NAME)

        print(f"\n{'='*60}")
        print(f"[PainelCliente Auth] PATH: {request.path} | METHOD: {request.method}")
        print(f"[PainelCliente Auth] Subdominio: {getattr(request, 'painel_config', None)}")
        print(f"[PainelCliente Auth] Todos os cookies: {list(request.COOKIES.keys())}")
        print(f"[PainelCliente Auth] Token no cookie: {token[:20]}..." if token else "[PainelCliente Auth] Token no cookie: NENHUM")

        if token:
            self._load_cliente_session(request, token)
        else:
            request.cliente_sessao = None
            print(f"[PainelCliente Auth] Resultado: SEM SESSAO (cookie vazio)")

        print(f"{'='*60}\n")
        return self.get_response(request)

    def _load_cliente_session(self, request, token):
        """
        Carrega sessao do cliente pelo token.

        Args:
            request: HttpRequest
            token: Token da sessao (string)
        """
        from .models import SessaoCliente

        try:
            sessao = SessaoCliente.objects.select_related(
                'cliente',
                'cliente__plano',
                'subdominio'
            ).get(
                token=token,
                subdominio=request.painel_config,
                ativo=True
            )

            print(f"[PainelCliente Auth] Sessao encontrada: ID={sessao.id}")
            print(f"[PainelCliente Auth] Cliente: {sessao.cliente.nome} (ID={sessao.cliente.id})")
            print(f"[PainelCliente Auth] Expira em: {sessao.expira_em}")

            if sessao.is_valid():
                request.cliente_sessao = sessao
                # Renova sessao a cada acesso
                sessao.renovar()
                print(f"[PainelCliente Auth] Resultado: SESSAO VALIDA - Renovada")
            else:
                request.cliente_sessao = None
                print(f"[PainelCliente Auth] Resultado: SESSAO EXPIRADA")

        except SessaoCliente.DoesNotExist:
            request.cliente_sessao = None
            print(f"[PainelCliente Auth] Resultado: SESSAO NAO ENCONTRADA")
