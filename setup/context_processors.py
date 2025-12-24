from django.db.models import DurationField, ExpressionWrapper, F
from django.utils import timezone

from nossopainel.models import Mensalidade, Tipos_pgto, UserProfile, NotificacaoSistema


def notifications(request):
    # Verifica se request.user existe (pode nao existir em middlewares customizados)
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}

    hoje = timezone.localdate()
    tipos = [Tipos_pgto.CARTAO, Tipos_pgto.BOLETO]

    # Mensalidades vencidas
    mensalidades_vencidas = (
        Mensalidade.objects.select_related("cliente", "cliente__forma_pgto", "cliente__plano")
        .filter(
            usuario=request.user,
            pgto=False,
            cancelado=False,
            cliente__cancelado=False,
            cliente__forma_pgto__nome__in=tipos,
            dt_vencimento__lt=hoje,
        )
        .exclude(notifications_read__usuario=request.user)
        .annotate(
            dias_atraso=ExpressionWrapper(
                hoje - F("dt_vencimento"),
                output_field=DurationField(),
            )
        )
        .order_by("dt_vencimento")
    )

    # Notificações do sistema não lidas
    notificacoes_sistema = NotificacaoSistema.objects.filter(
        usuario=request.user,
        lida=False
    )

    # Total = mensalidades vencidas + notificações do sistema
    total_count = mensalidades_vencidas.count() + notificacoes_sistema.count()

    return {
        "notif_items": mensalidades_vencidas[:20],
        "notif_count": total_count,
        "notificacoes_sistema": notificacoes_sistema[:10],
    }


def user_profile(request):
    """
    Disponibiliza o perfil do usuário (UserProfile) em todos os templates.
    Retorna o perfil do usuário autenticado, ou None se não estiver autenticado.
    """
    # Verifica se request.user existe (pode nao existir em middlewares customizados)
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {"user_profile": None}

    try:
        profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        # Criar perfil se não existir
        profile = UserProfile.objects.create(user=request.user)

    return {"user_profile": profile}

