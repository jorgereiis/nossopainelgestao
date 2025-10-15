# core/context_processors.py
from django.utils import timezone
from django.db.models import F, ExpressionWrapper, DurationField
from cadastros.models import Mensalidade, Tipos_pgto

def notifications(request):
    if not request.user.is_authenticated:
        return {}

    hoje = timezone.localdate()

    qs = (
        Mensalidade.objects
        .select_related("cliente", "cliente__forma_pgto")
        .filter(
            usuario=request.user,
            pgto=False,
            cancelado=False,
            cliente__cancelado=False,
            cliente__forma_pgto__nome=Tipos_pgto.CARTAO,
            dt_vencimento__lt=hoje,
        )
        .annotate(
            dias_atraso=ExpressionWrapper(
                hoje - F("dt_vencimento"),
                output_field=DurationField()
            )
        )
        .order_by("dt_vencimento")
    )

    # Limite leve para o dropdown; “ver tudo” pode ter paginação
    notif_items = qs[:20]
    notif_count = qs.count()

    return {
        "notif_count": notif_count,
        "notif_items": notif_items,
    }
