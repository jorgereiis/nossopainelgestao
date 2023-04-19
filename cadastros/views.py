from django.shortcuts import render
from .models import Cliente, Mensalidade
from django.db.models import Q
from django.shortcuts import redirect
from datetime import datetime
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
import pytz

def Index(request):
    clientes = Cliente.objects.filter(cancelado=False).filter(
        Q(mensalidade__cancelado=False, 
          mensalidade__dt_pagamento=None, 
          mensalidade__pgto=False)).order_by('mensalidade__dt_vencimento').distinct()
    return render(request, 'index.html', {'clientes': clientes})

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


