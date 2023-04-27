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
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum
from django.db.models import Q
import locale
import json
import csv


class TabelaDashboard(ListView):
    model = Cliente
    template_name = "dashboard.html"
    paginate_by = 15

    # QUERY PARA O CAMPO DE PESQUISA DO DASHBOARD
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

    # FUNÇÃO PARA RETORNAR RESULTADOS DAS QUERY UTILIZADAS NO DASHBOARD
    def get_context_data(self, **kwargs):
        moeda = "BRL"
        hoje = timezone.localtime().date()
        ano_atual = timezone.localtime().year
        proxima_semana = hoje + timedelta(days=7)
        context = super().get_context_data(**kwargs)
        total_clientes = self.get_queryset().count()
        mes_atual = timezone.localtime().date().month

        clientes_em_atraso = Cliente.objects.filter(
            cancelado=False,
            mensalidade__cancelado=False,
            mensalidade__dt_pagamento=None,
            mensalidade__pgto=False,
            mensalidade__dt_vencimento__lt=hoje,
        ).count()

        valor_total_pago = (
            Mensalidade.objects.filter(
                cancelado=False,
                dt_pagamento__year=ano_atual,
                dt_pagamento__month=mes_atual,
                pgto=True,
            ).aggregate(valor_total=Sum("valor"))["valor_total"]
            or 0
        )

        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
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

        valor_total_receber_qtd = Mensalidade.objects.filter(
            cancelado=False,
            dt_vencimento__gte=hoje,
            dt_vencimento__lt=proxima_semana,
            pgto=False,
        ).count()

        novos_clientes_qtd = (
            Cliente.objects.filter(
                cancelado=False,
                data_adesao__year=ano_atual,
                data_adesao__month=mes_atual,
            )
        ).count()

        clientes_cancelados_qtd = Cliente.objects.filter(
            cancelado=True,
            data_adesao__year=ano_atual,
            data_adesao__month=mes_atual,
        ).count()

        context.update(
            {
                "hoje": hoje,
                "total_clientes": total_clientes,
                "valor_total_pago": valor_total_pago,
                "novos_clientes_qtd": novos_clientes_qtd,
                "clientes_em_atraso": clientes_em_atraso,
                "valor_total_receber": valor_total_receber,
                "valor_total_pago_qtd": valor_total_pago_qtd,
                "valor_total_receber_qtd": valor_total_receber_qtd,
                "clientes_cancelados_qtd": clientes_cancelados_qtd,
            }
        )
        return context


# AÇÃO DE PAGAR MENSALIDADE
def pagar_mensalidade(request, mensalidade_id):
    mensalidade = get_object_or_404(Mensalidade, pk=mensalidade_id)

    # realiza as modificações na mensalidade
    mensalidade.dt_pagamento = timezone.localtime().date()
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


def ImportarClientes(request):
    if (
        request.method == "POST"
        and 'importar' in request.POST
        and request.FILES["arquivo"]
    ):
        arquivo_csv = request.FILES["arquivo"].read().decode("utf-8").splitlines()

        # Verifica o delimitador utilizado no arquivo .csv
        for delimitador in [',', ';']:
            try:
                leitor_csv = csv.reader(arquivo_csv, delimiter=delimitador)
                primeira_linha = next(leitor_csv)
                if len(primeira_linha) == 12:
                    break
            except csv.Error:
                pass

        leitor_csv = csv.reader(arquivo_csv, delimiter=delimitador)
        for x, linha in enumerate(leitor_csv):
            if x == 0:
                continue  # Pula a primeira linha do arquivo .csv e considera os dados a partir da segunda

            nome = linha[3].title()
            telefone = linha[4]

            # Verifica se já existe um cliente com esse nome ou telefone
            cliente_existente = Cliente.objects.filter(
                Q(nome__iexact=nome) | Q(telefone=telefone)
            ).exists()
            if cliente_existente:
                continue  # Pula essa linha do arquivo e vai para a próxima

            servidor, created = Servidor.objects.get_or_create(nome=linha[0])
            dispositivo, created = Dispositivo.objects.get_or_create(nome=linha[1])
            sistema, created = Aplicativo.objects.get_or_create(nome=linha[2])

            indicado_por = None
            if linha[5]:
                indicado_por = Cliente.objects.filter(nome__iexact=linha[5]).first()

                if indicado_por is None:
                    # Caso o cliente indicado não exista, o campo indicado_por ficará em branco
                    indicado_por = None

            data_pagamento = int(linha[6]) if linha[6] else None
            forma_pgto_nome = linha[7] if linha[7] else "PIX"
            forma_pgto, created = Tipos_pgto.objects.get_or_create(nome=forma_pgto_nome)
            tipo_plano = linha[9].capitalize() if linha[9] != None else None

            if tipo_plano == '' or tipo_plano == None:
                plano_queryset = Plano.objects.filter(
                    valor=int(linha[8]), nome='Mensal'
                )
            else:
                plano_queryset = Plano.objects.filter(
                    valor=int(linha[8]), nome=tipo_plano
                )

            plano = plano_queryset.first()
            telas = Qtd_tela.objects.get(telas=int(linha[10]))
            data_adesao = datetime.strptime(linha[11], "%d/%m/%Y").date()

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
        request,
        "pages/importar-cliente.html",
        {"mensagem": "Arquivo CSV importado com sucesso."},
    )


def CadastroCliente(request):
    # Recebendo os dados da requisição para criar um novo cliente
    if request.method == 'POST' and 'cadastrar' in request.POST:
        indicador = None
        nome = request.POST.get('nome')
        sobrenome = request.POST.get('sobrenome')
        dispositivo = request.POST.get('dispositivo')
        sistema = request.POST.get('sistema')
        indicador_nome = request.POST.get('indicador_list')
        if indicador_nome == None or indicador_nome == "" or indicador_nome == " ":
            indicador_nome = None
        else:
            indicador = Cliente.objects.get(nome=indicador_nome)
        servidor = request.POST.get('servidor')
        forma_pgto = request.POST.get('forma_pgto')
        plano = request.POST.get('plano')
        lista = plano.split("-")
        nome_do_plano = lista[0]
        valor_do_plano = float(lista[1].replace(',', '.'))
        telas = request.POST.get('telas')
        data_pagamento = (
            int(request.POST.get('data_pagamento'))
            if request.POST.get('data_pagamento')
            else None
        )

        cliente = Cliente(
            nome=(nome + " " + sobrenome),
            dispositivo=Dispositivo.objects.get(nome=dispositivo),
            sistema=Aplicativo.objects.get(nome=sistema),
            indicado_por=indicador,
            servidor=Servidor.objects.get(nome=servidor),
            forma_pgto=Tipos_pgto.objects.get(nome=forma_pgto),
            plano=Plano.objects.get(nome=nome_do_plano, valor=valor_do_plano),
            telas=Qtd_tela.objects.get(telas=telas),
            data_pagamento=data_pagamento,
        )
        cliente.save()

        return redirect('cadastro-cliente')

    # Criando os queryset para exibir os dados nos campos do fomulário
    servidor_queryset = Servidor.objects.all()
    dispositivo_queryset = Dispositivo.objects.all()
    sistema_queryset = Aplicativo.objects.all()
    indicador_por_queryset = Cliente.objects.all()
    forma_pgto_queryset = Tipos_pgto.objects.all()
    plano_queryset = Plano.objects.all()
    telas_queryset = Qtd_tela.objects.all()

    return render(
        request,
        'pages/cadastro-cliente.html',
        {
            'servidores': servidor_queryset,
            'dispositivos': dispositivo_queryset,
            'sistemas': sistema_queryset,
            'indicadores': indicador_por_queryset,
            'formas_pgtos': forma_pgto_queryset,
            'planos': plano_queryset,
            'telas': telas_queryset,
        },
    )


def Teste(request):
    clientes = Cliente.objects.all()

    return render(
        request,
        'teste.html',
        {
            'clientes': clientes,
        },
    )
