from django.shortcuts import render
from .models import Cliente, Mensalidade
from django.db.models import Q
from django.shortcuts import redirect
from datetime import datetime
from datetime import date
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Sum, Value
from django.db.models.functions import Cast
from django.db import models
import pytz

def Index(request):
    
    clientes = Cliente.objects.filter(cancelado=False).filter(
        Q(mensalidade__cancelado=False, 
          mensalidade__dt_pagamento=None, 
          mensalidade__pgto=False)).order_by('mensalidade__dt_vencimento').distinct()
    
    hoje = date.today()

    clientes_em_dia = Cliente.objects.filter(
    cancelado=False,
    mensalidade__cancelado=False,
    mensalidade__dt_pagamento=None,
    mensalidade__pgto=False,
    mensalidade__dt_vencimento__lte=hoje).count()
    
    # quantidade total de mensalidades à vencer
    total_mensalidades = clientes.count()

    return render(request, 'index.html', {'clientes': clientes, 'total_mensalidades': total_mensalidades, 'clientes_em_dia': clientes_em_dia})

def pagar_mensalidade(request, mensalidade_id):
    mensalidade = get_object_or_404(Mensalidade, pk=mensalidade_id)

    # realiza as modificações na mensalidade
    mensalidade.dt_pagamento = datetime.now().date()
    mensalidade.pgto = True
    mensalidade.save()

    # redireciona para a página anterior
    return redirect('index')

def cancelar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)

    # realiza as modificações no cliente
    cliente.cancelado = True
    cliente.save()

    # redireciona para a página anterior
    return redirect('index')


