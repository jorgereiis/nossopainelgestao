"""
Decorators para controle de acesso no Painel do Cliente.

Decorators disponiveis:
- @cliente_login_required: Requer sessao de cliente ativa
- @admin_painel_required: Requer usuario admin do subdominio
- @admin_superior_required: Requer superuser (Admin Superior)
"""

from functools import wraps

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required


def cliente_login_required(view_func):
    """
    Decorator que requer sessao de cliente ativa.

    Verifica se o cliente esta autenticado no painel.
    Se nao estiver, redireciona para a pagina de login.

    Uso:
        @cliente_login_required
        def minha_view(request):
            # request.cliente_sessao esta disponivel
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Verifica se e requisicao do painel
        if not getattr(request, 'is_painel_cliente', False):
            return HttpResponseForbidden('Acesso nao permitido')

        # Verifica se tem sessao ativa
        if not getattr(request, 'cliente_sessao', None):
            # Redireciona para login mantendo o subdominio
            return redirect('painel_cliente:login')

        return view_func(request, *args, **kwargs)

    return wrapper


def cliente_login_required_ajax(view_func):
    """
    Decorator para endpoints AJAX que requerem sessao de cliente.

    Similar ao cliente_login_required, mas retorna JSON em vez de redirect.

    Uso:
        @cliente_login_required_ajax
        def minha_api(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not getattr(request, 'is_painel_cliente', False):
            return JsonResponse({'error': 'Acesso nao permitido'}, status=403)

        if not getattr(request, 'cliente_sessao', None):
            return JsonResponse({'error': 'Sessao expirada'}, status=401)

        return view_func(request, *args, **kwargs)

    return wrapper


def admin_painel_required(view_func):
    """
    Decorator que requer usuario admin do subdominio.

    Verifica se o usuario logado e:
    1. Admin Superior (superuser) - pode acessar qualquer painel
    2. Admin Comum - pode acessar apenas seu proprio subdominio

    Adiciona request.is_admin_superior (bool) para identificar o tipo.

    Uso:
        @admin_painel_required
        def admin_view(request):
            if request.is_admin_superior:
                # Pode ver todos os subdominios
            else:
                # Pode ver apenas seu subdominio
    """
    @wraps(view_func)
    @login_required(login_url='/painel-admin/login/')
    def wrapper(request, *args, **kwargs):
        # Verifica se e requisicao do painel
        if not getattr(request, 'is_painel_cliente', False):
            return HttpResponseForbidden('Acesso nao permitido')

        config = request.painel_config

        # Admin Superior (superuser) pode acessar qualquer painel
        if request.user.is_superuser:
            request.is_admin_superior = True
            return view_func(request, *args, **kwargs)

        # Admin Comum so pode acessar seu proprio subdominio
        if config and config.admin_responsavel == request.user:
            request.is_admin_superior = False
            return view_func(request, *args, **kwargs)

        return HttpResponseForbidden('Voce nao tem permissao para acessar este painel')

    return wrapper


def admin_superior_required(view_func):
    """
    Decorator que requer superuser (Admin Superior).

    Usado para funcoes que apenas o Admin Superior pode executar,
    como criar/editar/excluir subdominios.

    Uso:
        @admin_superior_required
        def criar_subdominio(request):
            ...
    """
    @wraps(view_func)
    @login_required(login_url='/painel-admin/login/')
    def wrapper(request, *args, **kwargs):
        if not getattr(request, 'is_painel_cliente', False):
            return HttpResponseForbidden('Acesso nao permitido')

        if not request.user.is_superuser:
            return HttpResponseForbidden(
                'Apenas o administrador superior pode realizar esta acao'
            )

        request.is_admin_superior = True
        return view_func(request, *args, **kwargs)

    return wrapper


def cliente_dados_atualizados_required(view_func):
    """
    Decorator que requer que o cliente tenha atualizado seus dados.

    Usado em views que so podem ser acessadas apos o cliente
    completar seu perfil (dados_atualizados_painel = True).

    Se os dados nao estiverem atualizados, redireciona para /perfil.

    Uso:
        @cliente_login_required
        @cliente_dados_atualizados_required
        def dashboard(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        sessao = getattr(request, 'cliente_sessao', None)

        if not sessao:
            return redirect('painel_cliente:login')

        cliente = sessao.cliente

        if not cliente.dados_atualizados_painel:
            return redirect('painel_cliente:perfil')

        return view_func(request, *args, **kwargs)

    return wrapper


def painel_config_required(view_func):
    """
    Decorator basico que apenas verifica se a requisicao e do painel.

    Util para views que precisam de painel_config mas nao requerem login.

    Uso:
        @painel_config_required
        def pagina_publica(request):
            config = request.painel_config
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not getattr(request, 'is_painel_cliente', False):
            return HttpResponseForbidden('Acesso nao permitido')

        if not getattr(request, 'painel_config', None):
            return HttpResponseForbidden('Painel nao configurado')

        return view_func(request, *args, **kwargs)

    return wrapper
