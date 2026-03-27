"""Middleware do app nossopainel."""


class AtendenteContextMiddleware:
    """
    Detecta se o usuário autenticado é um atendente e injeta no request:
      - request.is_atendente (bool)
      - request.data_owner   (User: owner se atendente, próprio usuário caso contrário)
      - request.atendente_permissoes (PermissoesAtendente | None)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, 'user', None) and request.user.is_authenticated:
            try:
                perfil = request.user.perfil_atendente
                request.is_atendente = True
                request.data_owner = perfil.owner
                request.atendente_permissoes = perfil.permissoes
            except Exception:
                request.is_atendente = False
                request.data_owner = request.user
                request.atendente_permissoes = None
        else:
            request.is_atendente = False
            request.data_owner = getattr(request, 'user', None)
            request.atendente_permissoes = None

        return self.get_response(request)


class SubscricaoMiddleware:
    """
    Verifica se o usuário autenticado possui assinatura de plataforma válida.
    Em caso negativo, redireciona para /minha-assinatura/ (ou retorna 402 para AJAX).
    - Superusers: sempre liberados.
    - Atendentes: herdam o acesso do owner (data_owner).
    - Caminhos públicos (static, webhook, etc.) são liberados sem verificação.
    """

    PATHS_EXATAS_LIBERADAS = frozenset([
        '/minha-assinatura/',
        '/logout/',
        '/verify-2fa/',
        '/perfil/',
        '/perfil/2fa/setup/',
        '/perfil/2fa/enable/',
        '/perfil/2fa/disable/',
        '/perfil/2fa/qr-code/',
        '/perfil/2fa/regenerate-codes/',
        '/api/assinatura/cobranca/',  # prefixo — tratado abaixo
    ])

    PREFIXOS_LIBERADOS = (
        '/static/',
        '/media/',
        '/webhook/',
        '/api/assinatura/cobranca/',
        '/minha-assinatura/assinar/',
        '/api/push/',
        '/painel-configs/',
        '/favicon',
        '/robots',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return self.get_response(request)

        # Superusers são sempre liberados
        if user.is_superuser:
            return self.get_response(request)

        # Atendentes herdam o acesso do owner
        user_verificar = getattr(request, 'data_owner', user)
        if user_verificar.is_superuser:
            return self.get_response(request)

        path = request.path

        # Liberar caminhos públicos
        if path in self.PATHS_EXATAS_LIBERADAS:
            return self.get_response(request)
        for prefixo in self.PREFIXOS_LIBERADOS:
            if path.startswith(prefixo):
                return self.get_response(request)

        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('Accept', '')
            or request.content_type == 'application/json'
        )

        # Verificar assinatura
        try:
            from nossopainel.utils import get_ou_criar_assinatura_plataforma, usuario_tem_funcionalidade
            assinatura = get_ou_criar_assinatura_plataforma(user_verificar)
            if assinatura.is_acesso_valido:
                # Bloquear atendente cujo owner não possui atendentes_gestao no plano
                if getattr(request, 'is_atendente', False) and not usuario_tem_funcionalidade(user_verificar, 'atendentes_gestao'):
                    from django.contrib.auth import logout as auth_logout
                    auth_logout(request)
                    if is_ajax:
                        from django.http import JsonResponse
                        return JsonResponse(
                            {'error': 'Acesso de atendente não disponível no plano atual.', 'redirect': '/login/'},
                            status=403,
                        )
                    from django.shortcuts import redirect
                    return redirect('/login/')
                return self.get_response(request)
        except Exception:
            pass

        # Acesso inválido (assinatura expirada)
        if is_ajax:
            from django.http import JsonResponse
            return JsonResponse(
                {'error': 'Assinatura expirada.', 'redirect': '/minha-assinatura/'},
                status=402,
            )
        from django.shortcuts import redirect
        return redirect('/minha-assinatura/')
