from .models import (
    Cliente,
    Servidor,
    Dispositivo,
    Aplicativo,
    Tipos_pgto,
    Plano,
    Qtd_tela,
)
from django.shortcuts import get_object_or_404, redirect
from django.views.generic.list import ListView
from babel.numbers import format_currency
from .models import Cliente, Mensalidade
from datetime import datetime, timedelta
from django.shortcuts import redirect
from django.utils.timezone import now
from django.shortcuts import render
from django.db.models import Sum
import locale
import csv


class TabelaDashboard(ListView):
    model = Cliente
    template_name = "dashboard.html"
    paginate_by = 10

    def get_queryset(self):
        query = self.request.GET.get("q")
        queryset = (
            Cliente.objects.filter(cancelado=False)
            .filter(
                mensalidade__cancelado=False,
                mensalidade__dt_pagamento=None,
                mensalidade__pgto=False,
            )
            .order_by("mensalidade__dt_vencimento")
            .distinct()
        )
        if query:
            queryset = queryset.filter(nome__icontains=query)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = now().date()
        clientes_em_atraso = Cliente.objects.filter(
            cancelado=False,
            mensalidade__cancelado=False,
            mensalidade__dt_pagamento=None,
            mensalidade__pgto=False,
            mensalidade__dt_vencimento__lt=hoje,
        ).count()
        total_clientes = self.get_queryset().count()
        ano_atual = now().year
        mes_atual = now().month
        moeda = "BRL"
        valor_total_pago = (
            Mensalidade.objects.filter(
                cancelado=False,
                dt_pagamento__year=ano_atual,
                dt_pagamento__month=mes_atual,
                pgto=True,
            ).aggregate(valor_total=Sum("valor"))["valor_total"]
            or 0
        )
        locale.setlocale(locale.LC_ALL, "")
        valor_total_pago = locale.currency(
            valor_total_pago, grouping=True, symbol=False
        )
        valor_total_pago_qtd = Mensalidade.objects.filter(
            cancelado=False,
            dt_pagamento__year=ano_atual,
            dt_pagamento__month=mes_atual,
            pgto=True,
        ).count()
        valor_total_receber = (
            Mensalidade.objects.filter(
                cancelado=False,
                dt_vencimento__year=ano_atual,
                dt_vencimento__month=mes_atual,
                pgto=False,
            ).aggregate(valor_total=Sum("valor"))["valor_total"]
            or 0
        )
        valor_total_receber = format_currency(valor_total_receber, moeda)
        hoje = now().date()
        proxima_semana = hoje + timedelta(days=7)
        valor_total_receber_qtd = Mensalidade.objects.filter(
            cancelado=False,
            dt_vencimento__gte=hoje,
            dt_vencimento__lt=proxima_semana,
            pgto=False,
        ).count()
        context.update(
            {
                "hoje": hoje,
                "total_clientes": total_clientes,
                "valor_total_pago": valor_total_pago,
                "clientes_em_atraso": clientes_em_atraso,
                "valor_total_receber": valor_total_receber,
                "valor_total_pago_qtd": valor_total_pago_qtd,
                "valor_total_receber_qtd": valor_total_receber_qtd,
            }
        )
        return context


# AÇÃO DE PAGAR MENSALIDADE
def pagar_mensalidade(request, mensalidade_id):
    mensalidade = get_object_or_404(Mensalidade, pk=mensalidade_id)

    # realiza as modificações na mensalidade
    mensalidade.dt_pagamento = datetime.now().date()
    mensalidade.pgto = True
    mensalidade.save()

    # redireciona para a página anterior
    return redirect("dashboard")


# AÇÃO PARA CANCELAMENTO DE CLIENTE
def cancelar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)

    # realiza as modificações no cliente
    cliente.cancelado = True
    cliente.save()

    # redireciona para a página anterior
    return redirect("dashboard")


# PÁGINA DE LOGIN
def Login(request):
    return render(request, "login.html")


def Cadastro(request):
    return render(request, "pages/cadastro.html")


def Teste(request):
    if request.method == "POST" and request.FILES["arquivo"]:
        arquivo_csv = request.FILES["arquivo"].read().decode("utf-8").splitlines()
        
        # Verifica o delimitador utilizado no arquivo
        for delimitador in [',', ';']:
            try:
                leitor_csv = csv.reader(arquivo_csv, delimiter=delimitador)
                primeira_linha = next(leitor_csv)
                if len(primeira_linha) == 11:
                    break
            except csv.Error:
                pass
        
        leitor_csv = csv.reader(arquivo_csv, delimiter=delimitador)
        for x, linha in enumerate(leitor_csv):
            if x == 0:
                continue  # Pula a primeira linha
            
            servidor, created = Servidor.objects.get_or_create(nome=linha[0])
            dispositivo, created = Dispositivo.objects.get_or_create(nome=linha[1])
            sistema, created = Aplicativo.objects.get_or_create(nome=linha[2])
            nome = linha[3].title()
            telefone = linha[4]
            indicado_por = None

            if linha[5]:
                indicado_por = Cliente.objects.filter(nome__iexact=linha[5]).first()

                if indicado_por is None:
                    # Caso o cliente indicado não exista, o campo indicado_por ficará em branco
                    indicado_por = None

            data_pagamento = int(linha[6]) if linha[6] else None
            forma_pgto_nome = linha[7] if linha[7] else "PIX"
            forma_pgto, created = Tipos_pgto.objects.get_or_create(nome=forma_pgto_nome)
            plano = Plano.objects.get(valor=float(linha[8]))
            telas = Qtd_tela.objects.get(telas=int(linha[9]))
            data_adesao = datetime.strptime(linha[10], "%d/%m/%Y").date()

            novo_cliente = Cliente(
                servidor=servidor,
                dispositivo=dispositivo,
                sistema=sistema,
                nome=nome,
                telefone=telefone,
                indicado_por=indicado_por,
                data_pagamento=data_pagamento,
                forma_pgto=forma_pgto,
                plano=plano,
                telas=telas,
                data_adesao=data_adesao,
            )
            novo_cliente.save()
        return render(
            request, "teste.html", {"mensagem": "Arquivo CSV importado com sucesso."}
        )
    return render(request, "teste.html")