from django.db.models import DurationField, ExpressionWrapper, F
from django.utils import timezone

from nossopainel.models import Mensalidade, Tipos_pgto, UserProfile


def notifications(request):
    if not request.user.is_authenticated:
        return {}

    hoje = timezone.localdate()
    tipos = [Tipos_pgto.CARTAO, Tipos_pgto.BOLETO]

    qs = (
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

    return {"notif_items": qs[:20], "notif_count": qs.count()}


def user_profile(request):
    """
    Disponibiliza o perfil do usuário (UserProfile) em todos os templates.
    Retorna o perfil do usuário autenticado, ou None se não estiver autenticado.
    """
    if not request.user.is_authenticated:
        return {"user_profile": None}

    try:
        profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        # Criar perfil se não existir
        profile = UserProfile.objects.create(user=request.user)

    return {"user_profile": profile}

