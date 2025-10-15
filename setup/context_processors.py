# setup/context_processors.py
from django.utils import timezone
from django.db.models import F, ExpressionWrapper, DurationField
from cadastros.models import Mensalidade, Tipos_pgto

def notifications(request):
    if not request.user.is_authenticated:
        return {}

    hoje = timezone.localdate()
    read_ids = set(request.session.get("notif_read_ids", []))
    tipos = [Tipos_pgto.CARTAO, Tipos_pgto.BOLETO] # Tipos que geram notificações

    qs = (
        Mensalidade.objects
        .select_related("cliente", "cliente__forma_pgto", "cliente__plano")
        .filter(
            usuario=request.user,
            pgto=False, cancelado=False,
            cliente__cancelado=False,
            cliente__forma_pgto__nome__in=tipos,
            dt_vencimento__lt=hoje,
        )
        .exclude(id__in=read_ids)
        .annotate(dias_atraso=ExpressionWrapper(hoje - F("dt_vencimento"), output_field=DurationField()))
        .order_by("dt_vencimento")
    )

    return {"notif_items": qs[:20], "notif_count": qs.count()}
