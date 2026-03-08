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
