from .models import (Cliente, Servidor, Dispositivo, Aplicativo, Tipos_pgto, Plano, Mensalidade, ContaDoAplicativo, SessaoWpp, SecretTokenAPI, DadosBancarios, MensagemEnviadaWpp)
from django.http import HttpResponseBadRequest, HttpResponseNotFound, HttpResponse, JsonResponse
import requests, operator, logging, codecs, random, base64, json, time, re, os, io
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.views.decorators.clickjacking import xframe_options_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models.functions import ExtractMonth, ExtractYear
from plotly.colors import sample_colorscale, make_colorscale
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models.deletion import ProtectedError
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.views import LoginView
from django.views.generic.list import ListView
from datetime import timedelta, datetime, date
from django.utils.dateparse import parse_date
from django.forms.models import model_to_dict
from django.db.models.functions import Upper
from django.contrib.auth.models import User
from django.db.models import Sum, Q, Count
from .utils import validar_numero_whatsapp
from babel.numbers import format_currency
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
import matplotlib.pyplot as plt
from plotly.offline import plot
from django.views import View
from .forms import LoginForm
from decimal import Decimal
import plotly.express as px
import geopandas as gpd
import pandas as pd
import calendar


from .utils import DDD_UF_MAP

# Constantes
PLANOS_MESES = {
    'mensal': 1,
    'trimestral': 3,
    'semestral': 6,
    'anual': 12
}

MESES_31_DIAS = [1, 3, 5, 7, 8, 10, 12]

logger = logging.getLogger(__name__)
url_api = os.getenv("URL_API")

############################################ WPP VIEW ############################################

def whatsapp(request):
    return render(request, 'pages/whatsapp.html')

############################################ AUTH VIEW ############################################

# PÁGINA DE LOGIN
class Login(LoginView):
    template_name = 'login.html'
    form_class = LoginForm
    redirect_authenticated_user = True
    success_url = 'dashboard/'

# PÁGINA DE ERRO 404
def not_found(request, exception):
    return render(request, 'pages/404-error.html')

############################################ LIST VIEW ############################################

class CarregarContasDoAplicativo(LoginRequiredMixin, View):
    """
    View para carregar as contas dos aplicativos existentes por cliente e exibi-las no modal de informações do cliente.
    """
    def get(self, request):
        """
        Método GET para retornar as contas dos aplicativos existentes por cliente.

        Obtém o ID do cliente da consulta na URL.
        Filtra as contas do aplicativo para o cliente e o usuário atual.
        Cria uma lista para armazenar as contas de aplicativo serializadas.
        Itera sobre as contas de aplicativo.
        - Obtém o nome do aplicativo.
        - Serializa a conta de aplicativo em um dicionário Python.
        - Adiciona o nome do aplicativo ao dicionário.
        - Adiciona a conta de aplicativo serializada à lista.
        Ordena a lista de contas de aplicativo pelo nome do aplicativo.
        Imprime a lista de contas de aplicativo para fins de depuração.
        Retorna a lista de contas de aplicativo como resposta JSON.
        """
        id = self.request.GET.get("cliente_id")
        cliente = Cliente.objects.get(id=id)
        conta_app = ContaDoAplicativo.objects.filter(cliente=cliente, usuario=self.request.user).select_related('app')

        conta_app_json = []

        for conta in conta_app:
            nome_aplicativo = conta.app.nome
            conta_json = model_to_dict(conta)
            conta_json['nome_aplicativo'] = nome_aplicativo
            conta_app_json.append(conta_json)

        conta_app_json = sorted(conta_app_json, key=operator.itemgetter('nome_aplicativo'))

        return JsonResponse({"conta_app": conta_app_json}, safe=False)


class CarregarQuantidadesMensalidades(LoginRequiredMixin, View):
    """
    View para retornar as quantidades de mensalidades pagas, inadimplentes e canceladas existentes para o modal de informações na listagem do cliente.
    """
    def get(self, request):
        """
        Método GET para retornar as quantidades de mensalidades pagas, inadimplentes e canceladas.

        Obtém o ID do cliente da consulta na URL.
        Filtra as mensalidades pagas para o cliente e o usuário atual.
        Filtra as mensalidades pendentes para o cliente e o usuário atual.
        Filtra as mensalidades canceladas para o cliente e o usuário atual.
        Inicializa as variáveis para as quantidades de mensalidades pagas, pendentes e canceladas como zero.
        Itera sobre as mensalidades pagas, incrementando a quantidade de mensalidades pagas para o cliente específico.
        Itera sobre as mensalidades pendentes, incrementando a quantidade de mensalidades pendentes para o cliente específico.
        Itera sobre as mensalidades canceladas, incrementando a quantidade de mensalidades canceladas para o cliente específico.
        Cria um dicionário com os valores de quantidade de mensalidades para cada status.
        Retorna a resposta em formato JSON com os dados de quantidade de mensalidades.
        """
        id = self.request.GET.get("cliente_id")
        cliente = Cliente.objects.get(id=id)
        hoje = timezone.localtime().date()
        mensalidades_totais = Mensalidade.objects.filter(usuario=self.request.user, cliente=cliente).order_by('-id').values()
        mensalidades_pagas = Mensalidade.objects.filter(usuario=self.request.user, pgto=True, cliente=cliente)
        mensalidades_pendentes = Mensalidade.objects.filter(usuario=self.request.user, dt_pagamento=None, pgto=False, cancelado=False, dt_cancelamento=None, dt_vencimento__lt=hoje, cliente=cliente)
        mensalidades_canceladas = Mensalidade.objects.filter(usuario=self.request.user, cancelado=True, cliente=cliente)

        qtd_mensalidades_pagas = 0
        for mensalidade in mensalidades_pagas:
            if mensalidade.cliente.id == cliente.id:
                qtd_mensalidades_pagas += 1

        qtd_mensalidades_pendentes = 0
        for mensalidade in mensalidades_pendentes:
            if mensalidade.cliente.id == cliente.id:
                qtd_mensalidades_pendentes += 1

        qtd_mensalidades_canceladas = 0
        for mensalidade in mensalidades_canceladas:
            if mensalidade.cliente.id == cliente.id:
                qtd_mensalidades_canceladas += 1

        data = {
            'mensalidades_totais': list(mensalidades_totais),
            'qtd_mensalidades_pagas': qtd_mensalidades_pagas,
            'qtd_mensalidades_pendentes': qtd_mensalidades_pendentes,
            'qtd_mensalidades_canceladas': qtd_mensalidades_canceladas
        }

        return JsonResponse(data)
    

class CarregarInidicacoes(LoginRequiredMixin, View):

    def get(self, request):
        id = self.request.GET.get("cliente_id")
        indicados = Cliente.objects.filter(indicado_por=id).order_by('-id').values()

        data = {'indicacoes': list(indicados),}

        return JsonResponse(data)


class ClientesCancelados(LoginRequiredMixin, ListView):
    """
    View para listar clientes, considerando clientes cancelados e ativos.
    """
    model = Cliente
    template_name = "pages/clientes-cancelados.html"
    paginate_by = 15

    def get_queryset(self):
        """
        Retorna a queryset de clientes para a exibição na página.

        Filtra os clientes do usuário atual e os ordena pela data de adesão.
        Se houver uma consulta (q) na URL, filtra os clientes cujo nome contenha o valor da consulta.
        """
        query = self.request.GET.get("q")
        queryset = (
            Cliente.objects.filter(usuario=self.request.user, cancelado=True)
            .order_by("-data_cancelamento")
        )
        
        if query:
            queryset = queryset.filter(nome__icontains=query)
        return queryset
    
    def get_context_data(self, **kwargs):
        """
        Retorna o contexto dos dados para serem exibidos no template.

        Adiciona informações adicionais ao contexto, como objetos relacionados e variáveis de controle de página.
        """
        context = super().get_context_data(**kwargs)
        page_group = 'clientes'
        page = 'lista-clientes'
        range_num = range(1,32)

        context.update(
            {
                "range": range_num,
                "page_group": page_group,
                "page": page,
            }
        )
        return context
    

class TabelaDashboardAjax(LoginRequiredMixin, ListView):
    model = Cliente
    template_name = "partials/table-clients.html"
    paginate_by = 10

    def get_queryset(self):
        """
        Retorna a queryset para a listagem de clientes no dashboard.

        Filtra os clientes que não foram cancelados e possuem mensalidades não canceladas, não pagas e sem data de pagamento definida.
        Ordena a queryset pelo campo de data de vencimento da mensalidade.
        Realiza a operação distinct() para evitar duplicatas na listagem.
        Caso haja um valor de busca na URL (parâmetro 'q'), filtra a queryset pelos clientes cujo nome contém o valor de busca.
        """
        query = self.request.GET.get("q")
        queryset = (
            Cliente.objects.filter(cancelado=False).filter(
                mensalidade__cancelado=False,
                mensalidade__dt_cancelamento=None,
                mensalidade__dt_pagamento=None,
                mensalidade__pgto=False,
                usuario=self.request.user,
            ).order_by("mensalidade__dt_vencimento").distinct()
        )
        if query:
            queryset = queryset.filter(nome__icontains=query)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hoje"] = timezone.localtime().date()
        return context


class TabelaDashboard(LoginRequiredMixin, ListView):
    """
    View para listagem de clientes e outras informações exibidas no dashboard.
    """
    login_url = "login"
    model = Cliente
    template_name = "dashboard.html"
    paginate_by = 10

    def get_queryset(self):

        query = self.request.GET.get("q")
        queryset = (
            Cliente.objects.filter(cancelado=False).filter(
                mensalidade__cancelado=False,
                mensalidade__dt_cancelamento=None,
                mensalidade__dt_pagamento=None,
                mensalidade__pgto=False,
                usuario=self.request.user,
            ).order_by("mensalidade__dt_vencimento").distinct()
        )
        if query:
            queryset = queryset.filter(nome__icontains=query)
        return queryset
    

    def get_context_data(self, **kwargs):
        """
        Retorna o contexto de dados para serem exibidos no dashboard.

        Inicializa as variáveis necessárias, como a moeda utilizada, a data de hoje e o ano atual.
        Calcula o total de clientes baseado na queryset.
        Obtém o mês atual.
        Define a página atual como 'dashboard'.
        Filtra os clientes em atraso.
        Calcula o valor total pago no mês atual.
        Calcula a quantidade de mensalidades pagas no mês atual.
        Calcula o valor total a receber no mês atual.
        Calcula a quantidade de mensalidades a receber na próxima semana.
        Calcula a quantidade de novos clientes no mês atual.
        Calcula a quantidade de clientes cancelados no mês atual.
        Obtém a lista de aplicativos do usuário ordenados por nome.
        Atualiza o contexto com as informações calculadas.
        Retorna o contexto atualizado.
        """
        moeda = "BRL"
        page = 'dashboard'
        hoje = timezone.localtime().date()
        f_name = self.request.user.first_name
        ano_atual = timezone.localtime().year
        proxima_semana = hoje + timedelta(days=7)
        dt_inicio = str(self.request.user.date_joined)
        context = super().get_context_data(**kwargs)
        total_clientes = self.get_queryset().count()
        mes_atual = timezone.localtime().date().month

        # Variáveis para context do modal de edição do cadastro do cliente
        indicadores = Cliente.objects.filter(usuario=self.request.user).order_by('nome')
        servidores = Servidor.objects.filter(usuario=self.request.user).order_by('nome')
        formas_pgtos = Tipos_pgto.objects.filter(usuario=self.request.user)
        planos = Plano.objects.filter(usuario=self.request.user).order_by('nome', 'telas', 'valor')
        dispositivos = Dispositivo.objects.filter(usuario=self.request.user).order_by('nome')
        aplicativos = Aplicativo.objects.filter(usuario=self.request.user).order_by('nome')

        clientes_em_atraso = Cliente.objects.filter(
            cancelado=False,
            mensalidade__cancelado=False,
            mensalidade__dt_pagamento=None,
            mensalidade__pgto=False,
            mensalidade__dt_vencimento__lt=hoje,
            usuario=self.request.user,
        ).count()

        valor_total_pago = (
            Mensalidade.objects.filter(
                cancelado=False,
                dt_pagamento__year=ano_atual,
                dt_pagamento__month=mes_atual,
                usuario=self.request.user,
                pgto=True,
            ).aggregate(valor_total=Sum("valor"))["valor_total"]
            or 0
        )

        valor_total_pago = format_currency(valor_total_pago, moeda)

        valor_total_pago_qtd = Mensalidade.objects.filter(
            cancelado=False,
            dt_pagamento__year=ano_atual,
            dt_pagamento__month=mes_atual,
            usuario=self.request.user,
            pgto=True,
        ).count()

        valor_total_receber = (
            Mensalidade.objects.filter(
                cancelado=False,
                dt_vencimento__year=ano_atual,
                dt_vencimento__month=mes_atual,
                usuario=self.request.user,
                pgto=False,
            ).aggregate(valor_total=Sum("valor"))["valor_total"]
            or 0
        )
        valor_total_receber = format_currency(valor_total_receber, moeda)

        valor_total_receber_qtd = Mensalidade.objects.filter(
            cancelado=False,
            dt_vencimento__gte=hoje,
            dt_vencimento__lt=proxima_semana,
            usuario=self.request.user,
            pgto=False,
        ).count()

        novos_clientes_qtd = (
            Cliente.objects.filter(
                cancelado=False,
                data_adesao__year=ano_atual,
                data_adesao__month=mes_atual,
                usuario=self.request.user,
            )
        ).count()

        clientes_cancelados_qtd = Cliente.objects.filter(
            cancelado=True,
            data_cancelamento__year=ano_atual,
            data_cancelamento__month=mes_atual,
            usuario=self.request.user,
        ).count()

        anos_adesao = (
            Cliente.objects.filter(usuario=self.request.user)
            .annotate(ano=ExtractYear('data_adesao'))
            .values_list('ano', flat=True)
            .distinct()
            .order_by('-ano')
        )

        range_num = range(1,32)

        context.update(
            {
                "hoje": hoje,
                "page": page,
                "range": range_num,
                "nome_user": f_name,
                "aplicativos": aplicativos,
                "data_criacao_user": dt_inicio,
                "total_clientes": total_clientes,
                "valor_total_pago": valor_total_pago,
                "novos_clientes_qtd": novos_clientes_qtd,
                "clientes_em_atraso": clientes_em_atraso,
                "valor_total_receber": valor_total_receber,
                "valor_total_pago_qtd": valor_total_pago_qtd,
                "valor_total_receber_qtd": valor_total_receber_qtd,
                "clientes_cancelados_qtd": clientes_cancelados_qtd,
                ## context para modal de edição
                "planos": planos,
                "servidores": servidores,
                "indicadores": indicadores,
                "dispositivos": dispositivos,
                "formas_pgtos": formas_pgtos,
                ## context para o gráfico de adesões e cancelamentos
                "anos_adesao": anos_adesao,
                "anuo_atual": ano_atual,
            }
        )
        return context


@login_required
def send_message_wpp(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método inválido'}, status=400)

    BASE_URL = url_api + '/{}/send-{}'
    usuario = request.user
    sessao = get_object_or_404(SessaoWpp, usuario=usuario)
    token = sessao.token
    tipo_envio = request.POST.get('options')
    mensagem = request.POST.get('mensagem')
    imagem = request.FILES.get('imagem')

    log_directory = './logs/Envios manuais/'
    log_filename = os.path.join(log_directory, f'{usuario}.log')
    log_result_filename = os.path.join(log_directory, f'{usuario}_send_result.log')
    os.makedirs(log_directory, exist_ok=True)

    imagem_base64 = None
    if imagem:
        imagem_base64 = base64.b64encode(imagem.read()).decode('utf-8')

    def log_result(file_path, content):
        with codecs.open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {content}\n")

    def enviar_mensagem(url, telefone):
        telefone_validado = validar_numero_whatsapp(telefone)
        if MensagemEnviadaWpp.objects.filter(usuario=usuario, telefone=telefone_validado, data_envio=timezone.now().date()).exists():
            log_result(log_result_filename, f"{telefone_validado} - ⚠️ Já foi feito envio hoje!")
            return

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        body = {
            'phone': telefone_validado,
            'isGroup': False,
            'message': mensagem
        }
        if imagem:
            body.update({
                'filename': str(imagem),
                'caption': mensagem,
                'base64': f'data:image/png;base64,{imagem_base64}'
            })

        response = requests.post(url, headers=headers, json=body)

        if response.status_code in [200, 201]:
            log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{telefone_validado}] Mensagem enviada!")
            log_result(log_result_filename, f"{telefone_validado} - ✅ Mensagem enviada")
            MensagemEnviadaWpp.objects.create(usuario=usuario, telefone=telefone_validado)
            time.sleep(random.uniform(5, 12))
        else:
            try:
                response_data = response.json()
                error_message = response_data.get('message', response.text)
            except json.decoder.JSONDecodeError:
                error_message = response.text
            log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{telefone_validado}] [CODE][{response.status_code}] - {error_message}")
            log_result(log_result_filename, f"{telefone_validado} - ❌ Não enviada (consultar log)")

    # Coleta de contatos
    telefones = []
    clientes = []
    if tipo_envio == 'ativos':
        clientes = Cliente.objects.filter(usuario=usuario, cancelado=False, nao_enviar_msgs=False)
        telefones = [re.sub(r'\s+|\W', '', c.telefone) for c in clientes]
    elif tipo_envio == 'cancelados':
        clientes = Cliente.objects.filter(usuario=usuario, cancelado=True, data_cancelamento__lte=timezone.now()-timedelta(days=40), nao_enviar_msgs=False)
        telefones = [re.sub(r'\s+|\W', '', c.telefone) for c in clientes]
    elif tipo_envio == 'avulso':
        telefones_file = request.FILES.get('telefones')
        if telefones_file:
            lines = telefones_file.read().decode('utf-8').splitlines()
            telefones = [re.sub(r'\s+|\W', '', tel) for tel in lines if tel.strip()]

    if not telefones:
        return JsonResponse({'error': 'Nenhum telefone válido encontrado'}, status=400)

    url_envio = BASE_URL.format(usuario, 'image' if imagem else 'message')
    for telefone in telefones:
        enviar_mensagem(url_envio, telefone)

    return JsonResponse({'success': 'Envio concluído'}, status=200)



@login_required
def secret_token_api(request):
    """
        Função de view para consultar o Secret Token da API WPP Connect
    """
    if request.method == 'GET':
        if request.user:
            query = SecretTokenAPI.objects.get(id=1)
            token = query.token
        else:
            return JsonResponse({"error_message": "Usuário da requisição não identificado."}, status=500)
    else:
        return JsonResponse({"error_message": "Método da requisição não permitido."}, status=500)
    
    return JsonResponse({"stkn": token}, status=200)


@login_required
def get_session_wpp(request):
    """
        Função de view para consultar o Token da sessão WhatsApp do usuário da requisição.
    """
    if request.method == 'GET':
        if request.user:
            sessao = get_object_or_404(SessaoWpp, usuario=request.user)
            token = sessao.token
        else:
            return JsonResponse({"error_message": "Usuário da requisição não identificado."}, status=500)
    else:
        return JsonResponse({"error_message": "Método da requisição não permitido."}, status=500)

    return JsonResponse({"token": token}, status=200)


@login_required
def get_logs_wpp(request):
    if request.method == 'POST':

        file_path = './logs/Envios manuais/{}_send_result.log'.format(request.user)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            logs = file.read()

    return JsonResponse({'logs': logs})


def profile_page(request):
    user = User.objects.get(username=request.user)
    dados_bancarios = DadosBancarios.objects.filter(usuario=user.id).first()

    dt_inicio = user.date_joined.strftime('%d/%m/%Y') if user.date_joined else '--'
    f_name = user.first_name if user.first_name else '--'
    l_name = user.last_name if user.last_name else '--'
    email = user.email if user.email else '--'

    beneficiario = dados_bancarios.beneficiario if dados_bancarios else '--'
    instituicao = dados_bancarios.instituicao if dados_bancarios else '--'
    tipo_chave = dados_bancarios.tipo_chave if dados_bancarios else '--'
    chave = dados_bancarios.chave if dados_bancarios else '--'
    wpp = dados_bancarios.wpp if dados_bancarios else '--'

    ip = get_client_ip(request)
    localizacao = get_location_from_ip(ip)

    return render(
        request,
        'pages/perfil.html',
        {
            'beneficiario': beneficiario,
            'localizacao': localizacao,
            'instituicao': instituicao,
            'tipo_chave': tipo_chave,
            'sobrenome_user': l_name,
            'dt_inicio': dt_inicio,
            'nome_user': f_name,
            'username': user,
            'email': email,
            'chave': chave,
            'wpp': wpp,
        },
    )


def generate_graphic_columns(request):
    # Obtendo o ano escolhido (se não for informado, pega o atual)
    ano = request.GET.get("ano", timezone.now().year)
    usuario = request.user

    # Filtrando os dados do banco com base no ano escolhido
    dados_adesoes = Cliente.objects.filter(data_adesao__year=ano, usuario=usuario) \
        .annotate(mes=ExtractMonth("data_adesao")) \
        .values("mes") \
        .annotate(total=Count("id")) \
        .order_by("mes")

    dados_cancelamentos = Cliente.objects.filter(data_cancelamento__year=ano, usuario=usuario) \
        .annotate(mes=ExtractMonth("data_cancelamento")) \
        .values("mes") \
        .annotate(total=Count("id")) \
        .order_by("mes")

    # Criando listas dinâmicas de meses, adesões e cancelamentos
    meses = []
    adesoes = []
    cancelamentos = []

    # Criando dicionários auxiliares
    adesoes_dict = {dado["mes"]: dado["total"] for dado in dados_adesoes}
    cancelamentos_dict = {dado["mes"]: dado["total"] for dado in dados_cancelamentos}

    # Preenchendo os dados de acordo com os meses existentes no banco
    for mes in range(1, 13):
        if mes in adesoes_dict or mes in cancelamentos_dict:
            meses.append(calendar.month_abbr[mes])  # Ex: "Jan", "Feb", ...
            adesoes.append(adesoes_dict.get(mes, 0))
            cancelamentos.append(cancelamentos_dict.get(mes, 0))

    # Cálculo do saldo final
    total_adesoes = sum(adesoes)
    total_cancelamentos = sum(cancelamentos)
    saldo_final = total_adesoes - total_cancelamentos

    # Criando o gráfico de colunas
    plt.figure(figsize=(7, 3))
    
    plt.bar(meses, adesoes, color="#4CAF50", width=0.4, label="Adesões")  # Verde
    plt.bar(meses, cancelamentos, color="#F44336", width=0.4, bottom=adesoes, label="Cancelamentos")  # Vermelho

    # Adicionando rótulos nas barras
    for i, v in enumerate(adesoes):
        if v > 0:
            plt.text(i, v / 2, str(v), ha='center', va='center', fontsize=10, color='white', fontweight='bold')

    for i, v in enumerate(cancelamentos):
        if v > 0:
            plt.text(i, adesoes[i] + v / 2, str(v), ha='center', va='center', fontsize=10, color='white', fontweight='bold')

    # Melhorando a estética do gráfico
    plt.xlabel('Mês', fontsize=12)
    plt.ylabel('Quantidade', fontsize=12)
    plt.title(f'Adesão e Cancelamentos por ano - {ano}', fontsize=14)
    plt.xticks(fontsize=10, fontweight='bold')
    plt.yticks(fontsize=10)

    # Definição da cor do saldo na legenda
    cor_saldo = "#624BFF" if saldo_final >= 0 else "#F44336"
    texto_saldo = f"Saldo {ano}: {'+' if saldo_final > 0 else ''}{saldo_final}"

    # Criando um proxy para adicionar o saldo na legenda
    from matplotlib.patches import Patch
    saldo_patch = Patch(color=cor_saldo, label=texto_saldo)

    # Adicionando a legenda com "Saldo" personalizado
    plt.legend(handles=[Patch(color="#4CAF50", label="Adesões"), 
                        Patch(color="#F44336", label="Cancelamentos"), 
                        saldo_patch])

    # Removendo bordas superiores e laterais para um design mais limpo
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)

    # Salvando o gráfico como imagem
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches="tight", dpi=100)
    buffer.seek(0)
    plt.close()

    return HttpResponse(buffer.getvalue(), content_type="image/png")


@cache_page(60 * 120)  # cache por 2 hora
@xframe_options_exempt  # permite ser exibido em iframe
def generate_graphic_map_customers(request):
    usuario = request.user

    # Consulta os clientes ativos por estado (uf)
    dados = dict(
        Cliente.objects.filter(cancelado=False, usuario=usuario)
        .values('uf')
        .annotate(total=Count('id'))
        .values_list('uf', 'total')
    )
    total_geral = sum(dados.values())

    # Carrega o arquivo GeoJSON local
    mapa = gpd.read_file("archives/brasil_estados.geojson")

    # Mapeia os nomes dos estados para siglas
    siglas = {
        "Acre": "AC", "Alagoas": "AL", "Amapá": "AP", "Amazonas": "AM",
        "Bahia": "BA", "Ceará": "CE", "Distrito Federal": "DF", "Espírito Santo": "ES",
        "Goiás": "GO", "Maranhão": "MA", "Mato Grosso": "MT", "Mato Grosso do Sul": "MS",
        "Minas Gerais": "MG", "Pará": "PA", "Paraíba": "PB", "Paraná": "PR",
        "Pernambuco": "PE", "Piauí": "PI", "Rio de Janeiro": "RJ", "Rio Grande do Norte": "RN",
        "Rio Grande do Sul": "RS", "Rondônia": "RO", "Roraima": "RR", "Santa Catarina": "SC",
        "São Paulo": "SP", "Sergipe": "SE", "Tocantins": "TO"
    }

    # Adiciona a sigla e clientes ao GeoDataFrame
    mapa["sigla"] = mapa["name"].map(siglas)
    mapa["clientes"] = mapa["sigla"].apply(lambda uf: dados.get(uf, 0))
    mapa["porcentagem"] = mapa["clientes"].apply(
        lambda x: round((x / total_geral) * 100, 1) if total_geral > 0 else 0
    )

    # Remove colunas com Timestamp (não serializáveis)
    mapa = mapa.drop(columns=["created_at", "updated_at"], errors="ignore")

    # Converte para GeoJSON
    geojson_data = json.loads(mapa.to_json())

    # Definindo a  escala de 1 ao máximo
    max_clientes = max(mapa["clientes"]) if mapa["clientes"].any() else 1

    mapa["clientes_cor"] = mapa["clientes"].apply(lambda x: x if x > 0 else None)

    # Gera o gráfico interativo
    fig = px.choropleth_mapbox(
        mapa,
        geojson=geojson_data,
        locations="sigla",
        color="clientes",
        color_continuous_scale=[
            [0.0, "#FFFFFF"],   # clientes = 0
            [0.01, "#cdbfff"],  # mínimo relevante
            [1.0, "#624BFF"]    # máximo
        ],
        range_color=[0, max_clientes],
        labels={
            "clientes": "Clientes Ativos",
            "porcentagem": "% do Total"
        },
        featureidkey="properties.sigla",
        hover_name="name",
        hover_data={
            "clientes": True,
            "sigla": False,
            "clientes_cor": False,
            "porcentagem": True
        },
        mapbox_style="white-bg",
        center={"lat": -19.29285, "lon": -49.35954},
        zoom=2.6,
        opacity=0.6,
    )

    fig.update_traces(
        hoverlabel=dict(
            bgcolor="#fff",
            bordercolor="#724BFF",
            font=dict(size=14, color="black", family="Arial")
        ),
        marker_line_color="#ABA5D9",
        marker_line_width=0.5
    )

    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        title_text="Clientes Ativos por Estado",
        title_x=0.5,
        title_y=0.95,
        title_font=dict(size=25),
        title_font_color="black",
        title_font_family="Arial",
        title_xanchor="center",
        coloraxis_showscale=False
    )

    # Gera o HTML do gráfico
    grafico_html = plot(fig, output_type="div", include_plotlyjs="cdn")

    # Envolve com estrutura HTML e CSS responsivo
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Mapa Interativo</title>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                height: 100%;
                max-width: 100%;
                overflow: hidden;
            }}
            .plotly-graph-div {{
                height: 100% !important;
                width: 100% !important;
            }}
            @media (max-width: 576px) {{
                .plotly-graph-div {{
                    height: 400px !important;
                }}
            }}
        </style>
    </head>
    <body>
        {grafico_html}
    </body>
    </html>
    """

    return HttpResponse(html, content_type="text/html")

############################################ UPDATE VIEW ############################################

from django.views.decorators.http import require_POST

@require_POST
@login_required
def HorarioEnvio(request):
    usuario = request.user
    horario = request.POST.get('horario')

    try:
        obj_existente = HorarioEnvio.objects.get(usuario=usuario)
    except HorarioEnvio.DoesNotExist:
        obj_existente = None

    if request.POST.get('ativar'):
        if not obj_existente:
            obj = HorarioEnvio.objects.create(usuario=usuario, horario=horario, ativo=True)
            obj.save()
        else:
            obj_existente.horario = horario
            obj_existente.ativo = True
            obj_existente.save()

    elif request.POST.get('desativar'):
        if not obj_existente:
            obj = HorarioEnvio.objects.create(usuario=usuario, horario=None, ativo=False)
            obj.save()
        else:
            obj_existente.horario = None
            obj_existente.ativo = False
            obj_existente.save()

    return JsonResponse({"success_message": "Horário de envio atualizado com sucesso."}, status=200)


@login_required
def session_wpp(request):
    """
    Função de view para criar ou deletar uma sessão do WhatsApp
    """
    if request.method == 'DELETE':
        try:
            sessao = SessaoWpp.objects.filter(usuario=request.user)
            sessao.delete()
            # Realizar outras ações necessárias após a exclusão, se houver
            return JsonResponse({"success_message_session": "Sessão deletada com sucesso."}, status=200)
        except ObjectDoesNotExist:
            return JsonResponse({"error_message": "A sessão não existe."}, status=404)
        except Exception as e:
            return JsonResponse({"error_message": str(e)}, status=500)

    elif request.method in ['PUT', 'PATCH']:
        body = json.loads(request.body)
        token = body.get('token')
        try:
            sessao, created = SessaoWpp.objects.update_or_create(
                usuario=request.user,
                token=token,
                dt_inicio=timezone.localtime()
            )
            # Realizar outras ações necessárias após salvar/atualizar, se houver
            return JsonResponse({"success_message_session": "Sessão salva/atualizada com sucesso."}, status=200)
        except Exception as e:
            return JsonResponse({"error_message": str(e)}, status=500)

    else:
        return JsonResponse({"error_message": "Método da requisição não permitido."}, status=405)



@login_required
def reactivate_customer(request, cliente_id):
    """
    View para reativar um cliente anteriormente cancelado.
    Avalia a última mensalidade e cria nova se necessário.
    """
    try:
        cliente = Cliente.objects.get(pk=cliente_id, usuario=request.user)
    except Cliente.DoesNotExist:
        return JsonResponse({"error_message": "Cliente não encontrado."}, status=404)

    data_hoje = timezone.localdate()
    sete_dias_atras = data_hoje - timedelta(days=7)

    # Atualiza os campos de reativação
    cliente.cancelado = False
    cliente.data_cancelamento = None
    cliente.data_vencimento = data_hoje
    cliente.save()

    try:
        # Obtém a última mensalidade do cliente
        ultima_mensalidade = Mensalidade.objects.filter(cliente=cliente).order_by('-dt_vencimento').first()

        if ultima_mensalidade:
            if sete_dias_atras <= ultima_mensalidade.dt_vencimento <= data_hoje:
                # Apenas remove o cancelamento da mensalidade
                ultima_mensalidade.cancelado = False
                ultima_mensalidade.dt_cancelamento = None
                ultima_mensalidade.save()
            else:
                # Mantém a mensalidade anterior como cancelada
                ultima_mensalidade.cancelado = True
                ultima_mensalidade.dt_cancelamento = data_hoje
                ultima_mensalidade.save()

                # Cria nova mensalidade
                Mensalidade.objects.create(
                    cliente=cliente,
                    valor=cliente.plano.valor,
                    dt_vencimento=data_hoje,
                    usuario=cliente.usuario
                )
        else:
            # Caso não exista mensalidade anterior, cria uma nova
            Mensalidade.objects.create(
                cliente=cliente,
                valor=cliente.plano.valor,
                dt_vencimento=data_hoje,
                usuario=cliente.usuario
            )

    except Exception as erro:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]',
                     timezone.localtime(), request.user,
                     request.META.get('REMOTE_ADDR', ''), erro,
                     exc_info=True)
        return JsonResponse({"error_message": "Erro ao processar mensalidade na reativação."}, status=500)

    return JsonResponse({"success_message_activate": "Reativação feita com sucesso!"})


# AÇÃO DE PAGAR MENSALIDADE
@login_required
def pay_monthly_fee(request, mensalidade_id):
    """
    Função de view para pagar uma mensalidade.
    """
    hoje = timezone.localtime().date()
    mensalidade = Mensalidade.objects.get(pk=mensalidade_id, usuario=request.user)

    # Verifica se a mensalidade está atrasada por mais de 7 dias
    if mensalidade.dt_vencimento < hoje - timedelta(days=7):
        return JsonResponse({"error_message": "erro"})
    
    # Realiza as modificações na mensalidade paga
    mensalidade.dt_pagamento = timezone.localtime().date()
    mensalidade.pgto = True
    try:
        mensalidade.save()
    except Exception as erro:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
        return JsonResponse({"error_message": "Ocorreu um erro ao tentar pagar essa mensalidade."}, status=500)

    # Retorna uma resposta JSON indicando que a mensalidade foi paga com sucesso
    return JsonResponse({"success_message_invoice": "Mensalidade paga!"}, status=200)


# AÇÃO PARA CANCELAMENTO DE CLIENTE
@login_required
def cancel_customer(request, cliente_id):
    if request.user.is_authenticated:
        cliente = Cliente.objects.get(pk=cliente_id, usuario=request.user)

        # Realiza as modificações no cliente
        cliente.cancelado = True
        cliente.data_cancelamento = timezone.localtime().date()
        try:
            cliente.save()
        except Exception as erro:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
            return JsonResponse({"error_message": "Ocorreu um erro ao tentar cancelar esse cliente."}, status=500)

        # Cancelar todas as mensalidades relacionadas ao cliente
        mensalidades = cliente.mensalidade_set.filter(dt_vencimento__gte=timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0), pgto=False, cancelado=False)
        for mensalidade in mensalidades:
            mensalidade.cancelado = True
            mensalidade.dt_cancelamento = timezone.localtime().date()
            mensalidade.save()

        # Retorna uma resposta JSON indicando que o cliente foi cancelado com sucesso
        return JsonResponse({"success_message_cancel": "Eita! mais um cliente cancelado?! "})
    else:
        return redirect("login")


# Função para extrair UF pelo DDD
def extrair_uf_do_telefone(telefone):
    telefone_digits = re.sub(r'\D+', '', telefone)
    if telefone_digits.startswith('55'):
        telefone_digits = telefone_digits[2:]
    ddd = telefone_digits[:2]
    return DDD_UF_MAP.get(ddd, '')

# Função ajustada para calcular a nova data de vencimento com base no plano e data base
def calcular_nova_data_vencimento(plano_nome, data_base):
    meses = PLANOS_MESES.get(plano_nome.lower(), 0)
    mes = data_base.month + meses
    ano = data_base.year

    if mes > 12:
        mes -= 12
        ano += 1

    dia = data_base.day
    if dia == 31 and mes not in MESES_31_DIAS:
        dia = 1
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1

    try:
        return date(year=ano, month=mes, day=dia)
    except ValueError:
        return date(year=ano, month=mes, day=1)

@login_required
@transaction.atomic
def edit_customer(request, cliente_id):
    if request.method != "POST":
        return redirect("dashboard")

    try:
        post = request.POST
        user = request.user
        cliente = get_object_or_404(Cliente, pk=cliente_id, usuario=user)
        mensalidade = get_object_or_404(Mensalidade, cliente=cliente, pgto=False, cancelado=False, usuario=user)

        # Nome
        nome = post.get("nome", "").strip()
        if cliente.nome != nome:
            cliente.nome = nome

        # Telefone + UF
        telefone = post.get("telefone", "").strip()
        if cliente.telefone != telefone:
            if not Cliente.objects.filter(telefone=telefone, usuario=user).exclude(pk=cliente.pk).exists():
                cliente.telefone = telefone
                cliente.uf = extrair_uf_do_telefone(telefone)
            else:
                return render(request, "dashboard.html", {
                    "error_message_edit": "Já existe um cliente com este telefone informado."
                }, status=400)

        # Indicação
        indicado_nome = post.get("indicado_por")
        if indicado_nome:
            indicado = Cliente.objects.filter(nome=indicado_nome, usuario=user).first()
            if indicado and cliente.indicado_por != indicado:
                cliente.indicado_por = indicado

        # Servidor
        servidor = get_object_or_404(Servidor, nome=post.get("servidor"), usuario=user)
        if cliente.servidor != servidor:
            cliente.servidor = servidor

        # Forma de pagamento
        forma_pgto = Tipos_pgto.objects.filter(nome=post.get("forma_pgto"), usuario=user).first()
        if forma_pgto and cliente.forma_pgto != forma_pgto:
            cliente.forma_pgto = forma_pgto

        # Plano
        plano_nome, plano_valor = post.get("plano", "").replace(' ', '').split('-')
        plano_valor = Decimal(plano_valor.replace(',', '.'))
        plano = Plano.objects.filter(nome=plano_nome, valor=plano_valor, usuario=user).first()
        if plano and cliente.plano != plano:
            cliente.plano = plano
            mensalidade.valor = plano.valor

        # Data de vencimento
        data_vencimento_str = post.get("dt_pgto", "").strip()
        data_base = None

        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                data_base = datetime.strptime(data_vencimento_str, fmt).date()
                break
            except ValueError:
                continue

        if not data_base:
            return render(request, "dashboard.html", {
                "error_message_edit": "Data de vencimento inválida. Use o formato DD/MM/AAAA ou AAAA-MM-DD."
            }, status=400)

        #nova_data_vencimento = calcular_nova_data_vencimento(plano.nome, data_base)
        nova_data_vencimento = data_base

        if cliente.data_vencimento != nova_data_vencimento:
            cliente.data_vencimento = nova_data_vencimento
            mensalidade.dt_vencimento = nova_data_vencimento
            mensalidade.valor = plano.valor

        # Dispositivo
        dispositivo = get_object_or_404(Dispositivo, nome=post.get("dispositivo"), usuario=user)
        if cliente.dispositivo != dispositivo:
            cliente.dispositivo = dispositivo

        # Aplicativo
        aplicativo = get_object_or_404(Aplicativo, nome=post.get("aplicativo"), usuario=user)
        if cliente.sistema != aplicativo:
            cliente.sistema = aplicativo

        # Notas
        notas = post.get("notas", "").strip()
        if cliente.notas != notas:
            cliente.notas = notas

        cliente.save()
        mensalidade.save()

        return render(request, "dashboard.html", {
            "success_message_edit": f"{cliente.nome} foi atualizado com sucesso."
        }, status=200)

    except Exception as e:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]',
                     timezone.localtime(), request.user,
                     request.META.get('REMOTE_ADDR'), e, exc_info=True)
        return render(request, "dashboard.html", {
            "error_message_edit": "Ocorreu um erro ao tentar atualizar esse cliente."
        }, status=500)


# AÇÃO PARA EDITAR O OBJETO PLANO MENSAL
@login_required
def edit_payment_plan(request, plano_id):
    """
    Função de view para editar um plano de adesão mensal.
    """
    plano_mensal = get_object_or_404(Plano, pk=plano_id, usuario=request.user)

    planos_mensalidades = Plano.objects.all().order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")
        telas = request.POST.get("telas")
        valor = request.POST.get("valor")

        if nome and valor:
            plano_mensal.nome = nome
            plano_mensal.telas = telas
            plano_mensal.valor = valor

            try:
                plano_mensal.save()

            except ValidationError as erro1:
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                # Capturando a exceção ValidationError e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-plano-adesao.html",
                    {
                        'planos_mensalidades': planos_mensalidades,
                        "error_message": "Já existe um plano com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o plano e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-plano-adesao.html",
                    {
                        'planos_mensalidades': planos_mensalidades,
                        "error_message": "Ocorreu um erro ao salvar o plano. Verifique o log!",
                    },
                )
            
            # Em caso de sucesso, renderiza a página novamente com a mensagem de sucesso
            return render(
                request,
                "pages/cadastro-plano-adesao.html",
                {"planos_mensalidades": planos_mensalidades, "success_update": True},
            )

        else:
            return render(
                request,
                "pages/cadastro-plano-adesao.html",
                {
                    "planos_mensalidades": planos_mensalidades,
                    "error_message": "O campo do valor não pode estar em branco.",
                },
            )

    # Redireciona para a página de cadastro de plano de adesão se o método HTTP não for POST
    return redirect("cadastro-plano-adesao")


# AÇÃO PARA EDITAR O OBJETO SERVIDOR
@login_required
def edit_server(request, servidor_id):
    servidor = get_object_or_404(Servidor, pk=servidor_id, usuario=request.user)

    servidores = Servidor.objects.filter(usuario=request.user).order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:         
            servidor.nome = nome
            try:
                servidor.save()

            except ValidationError as erro1:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-servidor.html",
                    {
                        'servidores': servidores,
                        "error_message": "Já existe um servidor com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o servidor
                return render(
                    request,
                    "pages/cadastro-servidor.html",
                    {
                        'servidores': servidores,
                        "error_message": "Ocorreu um erro ao salvar o servidor. Verifique o log!",
                    },
                )
            
            return render(
                request,
                "pages/cadastro-servidor.html",
                {"servidores": servidores, "success_update": True},
            )

    return redirect("cadastro-servidor")


# AÇÃO PARA EDITAR O OBJETO DISPOSITIVO
@login_required
def edit_device(request, dispositivo_id):
    dispositivo = get_object_or_404(Dispositivo, pk=dispositivo_id, usuario=request.user)

    dispositivos = Dispositivo.objects.filter(usuario=request.user).order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:         
            dispositivo.nome = nome
            try:
                dispositivo.save()

            except ValidationError as erro1:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-dispositivo.html",
                    {
                        'dispositivos': dispositivos,
                        "error_message": "Já existe um dispositivo com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o dispositivo
                return render(
                    request,
                    "pages/cadastro-dispositivo.html",
                    {
                        'dispositivos': dispositivos,
                        "error_message": "Ocorreu um erro ao salvar o dispositivo. Verifique o log!",
                    },
                )
            
            return render(
                request,
                "pages/cadastro-dispositivo.html",
                {"dispositivos": dispositivos, "success_update": True},
            )

    return redirect("cadastro-dispositivo")


# AÇÃO PARA EDITAR O OBJETO APLICATIVO
@login_required
def editar_app(request, aplicativo_id):
    aplicativo = get_object_or_404(Aplicativo, pk=aplicativo_id, usuario=request.user)

    aplicativos = Aplicativo.objects.filter(usuario=request.user).order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")
        mac = request.POST.get("mac")

        if nome and mac:
            aplicativo.nome = nome
            aplicativo.device_has_mac = True if mac == "true" else False

            try:
                aplicativo.save()

            except ValidationError as erro1:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-aplicativo.html",
                    {
                        'aplicativos': aplicativos,
                        "error_message": "Já existe um aplicativo com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o aplicativo
                return render(
                    request,
                    "pages/cadastro-aplicativo.html",
                    {
                        'aplicativos': aplicativos,
                        "error_message": "Ocorreu um erro ao salvar o aplicativo. Verifique o log!",
                    },
                )
            
            return render(
                request,
                "pages/cadastro-aplicativo.html",
                {"aplicativos": aplicativos, "success_update": True},
            )

    return redirect("cadastro-aplicativo")


@login_required
def edit_profile(request):
    if request.method == "POST":
        if request.user.is_authenticated:
            try:
                user = request.user
                dados_usuario = user
                dados_usuario.last_name = request.POST.get('sobrenome', '')
                dados_usuario.first_name = request.POST.get('nome', '')
                dados_usuario.email = request.POST.get('email', '')
                dados_usuario.save()

                dados_bancarios = DadosBancarios.objects.filter(usuario=user).first()
                beneficiario = request.POST.get('beneficiario', '')
                instituicao = request.POST.get('instituicao', '')
                tipo_chave = request.POST.get('tipo_chave', '')
                chave = request.POST.get('chave', '')
                wpp = request.POST.get('wpp', '')

                if not dados_bancarios:
                    dados_bancarios = DadosBancarios(usuario=user)

                dados_bancarios.beneficiario = beneficiario
                dados_bancarios.instituicao = instituicao
                dados_bancarios.tipo_chave = tipo_chave
                dados_bancarios.chave = chave
                dados_bancarios.wpp = wpp
                dados_bancarios.save()

                messages.success(request, 'Perfil editado com sucesso!')
            except Exception as e:
                messages.error(request, 'Ocorreu um erro ao editar o perfil. Verifique o log!')
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
        else:
            messages.error(request, 'Usuário da requisição não identificado!')
    else:
        messages.error(request, 'Método da requisição não permitido!')

    return redirect('perfil')


def test(request):
    clientes = Cliente.objects.all()

    return render(
        request,
        'teste.html',
        {
            'clientes': clientes,
        },
    )


############################################ CREATE VIEW ############################################

@login_required
def create_app_account(request):

    if request.method == "POST":
        app_id = request.POST.get('app_id')
        app = Aplicativo.objects.get(id=app_id, usuario=request.user)
        cliente = Cliente.objects.get(id=request.POST.get('cliente-id'))
        device_id = request.POST.get('device-id') or None
        device_key = request.POST.get('device-key') or None
        app_email = request.POST.get('app-email') or None
    
        nova_conta_app = ContaDoAplicativo(
            cliente=cliente,
            app=app,
            device_id=device_id,
            device_key=device_key,
            email=app_email,
            usuario=request.user
        )

        try:
            nova_conta_app.save()
            
            # retorna a mensagem de sucesso como resposta JSON
            return JsonResponse({"success_message_cancel": "Conta do aplicativo cadastrada com sucesso!"}, status=200)

        except Exception as erro:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
        
        return JsonResponse({"error_message": "Ocorreu um erro ao tentar realizar o cadastro."}, status=500)
    else:
        return JsonResponse({"error_message": "Ocorreu um erro ao tentar realizar o cadastro."}, status=500)


@login_required
def import_customers(request):

    num_linhas_importadas = 0  # Inicializa o contador de linhas importadas
    num_linhas_nao_importadas = 0  # Inicializa o contador de linhas não importadas
    nomes_clientes_existentes = []  # Inicializa a lista de nomes de clientes existentes não importados
    nomes_clientes_erro_importacao = [] # Inicializa a lista de nomes de clientes que tiveram erro na importação
    usuario_request = request.user # Usuário que fez a requisição
    page_group = 'clientes'
    page = 'importar-clientes'

    if request.method == "POST" and 'importar' in request.POST:
        if not str(request.FILES['arquivo']).endswith('.xls') and not str(request.FILES['arquivo']).endswith('.xlsx'):
            # se o arquivo não possui a extensão esperada (.xls/.xlsx), retorna erro ao usuário.
            return render(request, "pages/importar-cliente.html",
                {"error_message": "O arquivo não é uma planilha válida (.xls, .xlsx)."},)

        try:
            # realiza a leitura dos dados da planilha.
            dados = pd.read_excel(request.FILES['arquivo'], engine='openpyxl')
        
        except Exception as erro1:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
            return render(request, "pages/importar-cliente.html",
                {"error_message": "Erro ao tentar ler planilha. Verifique o arquivo e tente novamente."},)
        
        # transforma cada linha dos dados lidos da planilha em um dicionário para que seja iterado no loop FOR.
        lista_de_objetos = dados.to_dict('records')

        with transaction.atomic(): # Adicionando a transação atomica
            i=0
            for dado in lista_de_objetos:
                i+=1

                servidor_import = str(dado['servidor']).replace(" ", "") if not pd.isna(dado['servidor']) else None
                dispositivo_import = str(dado['dispositivo']) if not pd.isna(dado['dispositivo']) else None
                sistema_import = str(dado['sistema']) if not pd.isna(dado['sistema']) else None
                device_id_import = str(dado['device_id']).replace(" ", "") if not pd.isna(dado['device_id']) else None
                email_import = str(dado['email']).replace(" ", "") if not pd.isna(dado['email']) else None
                device_key_import = str(dado['device_key']).replace(" ", "") if not pd.isna(dado['device_key']) else None
                nome_import = str(dado['nome']).title() if not pd.isna(dado['nome']) else None
                telefone_import = str(dado['telefone']).replace(" ", "") if not pd.isna(dado['telefone']) else None
                indicado_por_import = str(dado['indicado_por']) if not pd.isna(dado['indicado_por']) else None
                data_vencimento_import = str(dado['data_vencimento']) if not pd.isna(dado['data_vencimento']) else None
                forma_pgto_import = str(dado['forma_pgto']) if not pd.isna(dado['forma_pgto']) else 'PIX'
                tipo_plano_import = str(dado['tipo_plano']).replace(" ", "").title() if not pd.isna(dado['tipo_plano']) else None
                plano_valor_import = int(dado['plano_valor']) if not pd.isna(dado['plano_valor']) else None
                data_adesao_import = dado['data_adesao'] if not pd.isna(dado['data_adesao']) else None

                if (servidor_import is None) or (dispositivo_import is None) or (sistema_import is None) or (nome_import is None) or (telefone_import is None) or (data_adesao_import is None) or (forma_pgto_import is None) or (plano_valor_import is None) or (tipo_plano_import is None):
                    num_linhas_nao_importadas += 1
                    nomes_clientes_erro_importacao.append('Linha {} da planilha - (há campos obrigatórios em branco)'.format(i))
                    continue
                
                try:
                    with transaction.atomic(): # Nova transação atomica para cada cliente importado
                        
                        # Verifica se já existe um cliente com esse nome ou telefone
                        cliente_existente = Cliente.objects.filter(Q(nome__iexact=nome_import) | Q(telefone=telefone_import), usuario=usuario_request).exists()
                        if cliente_existente:
                            num_linhas_nao_importadas += 1 # incrementa mais 1 a contagem
                            nomes_clientes_existentes.append('Linha {} da planilha - {}'.format(i, nome_import.title()))  # Adiciona o nome do cliente já existente
                            continue # pula a inserção desse cliente
                        
                        servidor, created = Servidor.objects.get_or_create(nome=servidor_import, usuario=usuario_request)
                        dispositivo, created = Dispositivo.objects.get_or_create(nome=dispositivo_import, usuario=usuario_request)
                        sistema, created = Aplicativo.objects.get_or_create(nome=sistema_import, usuario=usuario_request)
                        indicado_por = None
                        if indicado_por_import:
                            indicado_por = Cliente.objects.filter(nome__iexact=nome_import, usuario=usuario_request).first()
                        data_vencimento = data_vencimento_import
                        forma_pgto, created = Tipos_pgto.objects.get_or_create(nome=forma_pgto_import, usuario=usuario_request)
                        plano, created = Plano.objects.get_or_create(nome=tipo_plano_import, valor=plano_valor_import, usuario=usuario_request)
                        data_adesao = data_adesao_import

                        novo_cliente = Cliente(
                            servidor=servidor,
                            dispositivo=dispositivo,
                            sistema=sistema,
                            nome=nome_import,
                            telefone=telefone_import,
                            indicado_por=indicado_por,
                            data_vencimento=data_vencimento,
                            forma_pgto=forma_pgto,
                            plano=plano,
                            data_adesao=data_adesao,
                            usuario=usuario_request,
                        )
                        novo_cliente.save()
                        
                        check_sistema = sistema_import.lower().replace(" ", "")
                        if check_sistema == "clouddy" or check_sistema == "duplexplay" or check_sistema == "duplecast" or check_sistema == "metaplayer":
                            device_id = device_id_import
                            email = email_import
                            device_key = device_key_import.split('.')[0]
                            dados_do_app = ContaDoAplicativo(
                                device_id=device_id,
                                email=email,
                                device_key=device_key,
                                app=Aplicativo.objects.filter(nome__iexact=check_sistema, usuario=usuario_request).first(),
                                cliente=novo_cliente,
                                usuario=usuario_request,
                            )
                            dados_do_app.save()

                        num_linhas_importadas += 1  # Incrementa o contador de linhas importadas com sucesso
                except Exception as erro2:
                    logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                    # Se ocorrer um erro, apenas incrementa 1 a contagem e adiciona o nome do cliente a lista dos não importados, e continua para o próximo cliente.
                    num_linhas_nao_importadas += 1
                    nomes_clientes_erro_importacao.append('Linha {} da planilha - {}'.format(i, nome_import.title()))
                    continue

            time.sleep(2)
            return render(
                    request,
                    "pages/importar-cliente.html",
                    {
                        "success_message": "Importação concluída!",
                        "num_linhas_importadas": num_linhas_importadas,
                        "num_linhas_nao_importadas": num_linhas_nao_importadas,
                        "nomes_clientes_existentes": nomes_clientes_existentes,
                        "nomes_clientes_erro_importacao": nomes_clientes_erro_importacao,
                        "page_group": page_group,
                        "page": page,
                        },
            )
    
    return render(request, "pages/importar-cliente.html", {"page_group": page_group,"page": page,})


# AÇÃO PARA CRIAR NOVO CLIENTE ATRAVÉS DO FORMULÁRIO
@login_required
def create_customer(request):
    usuario = request.user
    page_group = "clientes"
    page = "cadastro-cliente"

    # Querysets para preencher os selects do formulário
    plano_queryset = Plano.objects.filter(usuario=usuario).order_by('nome', 'telas', 'valor')
    forma_pgto_queryset = Tipos_pgto.objects.filter(usuario=usuario)
    servidor_queryset = Servidor.objects.filter(usuario=usuario).order_by('nome')
    sistema_queryset = Aplicativo.objects.filter(usuario=usuario).order_by('nome')
    indicador_por_queryset = Cliente.objects.filter(usuario=usuario, cancelado=False).order_by('nome')
    dispositivo_queryset = Dispositivo.objects.filter(usuario=usuario).order_by('nome')

    # Processa requisição POST (cadastro)
    if request.method == 'POST' and 'cadastrar' in request.POST:
        post = request.POST

        # Coleta e sanitiza dados do formulário
        nome = post.get('nome', '').strip()
        sobrenome = post.get('sobrenome', '').strip()
        telefone = post.get('telefone', '').strip()
        notas = post.get('notas', '').strip()
        indicador_nome = post.get('indicador_list', '').strip()
        sistema_nome = post.get('sistema', '').strip()
        servidor_nome = post.get('servidor', '').strip()
        forma_pgto_nome = post.get('forma_pgto', '').strip()
        dispositivo_nome = post.get('dispositivo', '').strip()
        plano_info = post.get('plano', '').replace(' ', '').split('-')

        if not telefone:
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": "O campo telefone não pode estar em branco.",
            })

        # Verifica se já existe cliente com o mesmo telefone
        if Cliente.objects.filter(telefone=telefone, usuario=usuario).exists():
            cliente_existente = Cliente.objects.get(telefone=telefone, usuario=usuario)
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": f"Há um cliente cadastrado com o telefone informado! <br><br><strong>Nome:</strong> {cliente_existente.nome} <br> <strong>Telefone:</strong> {cliente_existente.telefone}",
            })

        # Trata indicador (pode ser nulo)
        indicador = None
        if indicador_nome:
            indicador = Cliente.objects.filter(nome=indicador_nome, usuario=usuario).first()

        # Trata plano
        try:
            plano_nome = plano_info[0]
            plano_valor = float(plano_info[1].replace(',', '.'))
        except (IndexError, ValueError):
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": "Plano inválido.",
            })
        plano, _ = Plano.objects.get_or_create(nome=plano_nome, valor=plano_valor, usuario=usuario)

        # Trata relacionados
        sistema, _ = Aplicativo.objects.get_or_create(nome=sistema_nome, usuario=usuario)
        servidor, _ = Servidor.objects.get_or_create(nome=servidor_nome, usuario=usuario)
        forma_pgto, _ = Tipos_pgto.objects.get_or_create(nome=forma_pgto_nome, usuario=usuario)
        dispositivo, _ = Dispositivo.objects.get_or_create(nome=dispositivo_nome, usuario=usuario)

        # Trata data de vencimento
        data_vencimento = None
        data_vencimento_str = post.get('data_vencimento', '').strip()
        if data_vencimento_str:
            try:
                data_vencimento = datetime.strptime(data_vencimento_str, "%Y-%m-%d").date()
            except ValueError:
                return render(request, "pages/cadastro-cliente.html", {
                    "error_message": "Data de vencimento inválida.",
                })

        # Cria cliente
        cliente = Cliente(
            nome=f"{nome} {sobrenome}",
            telefone=telefone,
            dispositivo=dispositivo,
            sistema=sistema,
            indicado_por=indicador,
            servidor=servidor,
            forma_pgto=forma_pgto,
            plano=plano,
            data_vencimento=data_vencimento,
            notas=notas,
            usuario=usuario,
        )

        try:
            cliente.save()
        except ValidationError as e:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]',
                         timezone.localtime(), usuario, request.META['REMOTE_ADDR'], e, exc_info=True)
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": "Não foi possível cadastrar cliente!"
            })
        except Exception as e:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]',
                         timezone.localtime(), usuario, request.META['REMOTE_ADDR'], e, exc_info=True)
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": "Não foi possível cadastrar cliente!",
            })

        # Se o sistema exige ID de dispositivo, cria ContaDoAplicativo
        if sistema.device_has_mac:
            ContaDoAplicativo.objects.create(
                device_id=post.get('id'),
                email=post.get('email'),
                device_key=post.get('senha'),
                app=sistema,
                cliente=cliente,
                usuario=usuario,
            )

        return render(request, "pages/cadastro-cliente.html", {
            "success_message": "Novo cliente cadastrado com sucesso!",
        })

    # Requisição GET (carrega formulário)
    return render(request, "pages/cadastro-cliente.html", {
        'servidores': servidor_queryset,
        'dispositivos': dispositivo_queryset,
        'sistemas': sistema_queryset,
        'indicadores': indicador_por_queryset,
        'formas_pgtos': forma_pgto_queryset,
        'planos': plano_queryset,
        'page_group': page_group,
        'page': page,
    })



# AÇÃO PARA CRIAR NOVO OBJETO PLANO MENSAL
@login_required
def create_payment_plan(request):
    planos_mensalidades = Plano.objects.filter(usuario=request.user).order_by('nome', 'telas', 'valor')
    usuario = request.user
    page_group = "cadastros"
    page = "plano_adesao"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                plano, created = Plano.objects.get_or_create(nome=request.POST.get('nome'), valor=int(request.POST.get('valor')), usuario=usuario)

                if created:
                    return render(
                            request,
                        'pages/cadastro-plano-adesao.html',
                        {
                            'planos_mensalidades': planos_mensalidades,
                            "success_message": "Novo Plano cadastrado com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        'pages/cadastro-plano-adesao.html',
                        {
                            'planos_mensalidades': planos_mensalidades,
                            "error_message": "Já existe um Plano com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-plano-adesao.html",
                    {
                        'planos_mensalidades': planos_mensalidades,
                        "error_message": "Não foi possível cadastrar este novo Plano. Verifique os logs!",
                    },
                )

    return render(
        request, 'pages/cadastro-plano-adesao.html', {'planos_mensalidades': planos_mensalidades, "page_group": page_group, "page": page}
    )

# AÇÃO PARA CRIAR NOVO OBJETO SERVIDOR
@login_required
def create_server(request):
    servidores = Servidor.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "servidor"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                servidor, created = Servidor.objects.get_or_create(nome=nome, usuario=usuario)

                if created:
                    return render(
                            request,
                        'pages/cadastro-servidor.html',
                        {
                            'servidores': servidores,
                            "success_message": "Novo Servidor cadastrado com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        'pages/cadastro-servidor.html',
                        {
                            'servidores': servidores,
                            "error_message": "Já existe um Servidor com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "'pages/cadastro-servidor.html",
                    {
                        'servidores': servidores,
                        "error_message": "Não foi possível cadastrar este novo Servidor. Verifique os logs!",
                    },
                )

    return render(
        request, 'pages/cadastro-servidor.html', {'servidores': servidores, "page_group": page_group, "page": page}
    )


# AÇÃO PARA CRIAR NOVO OBJETO FORMA DE PAGAMENTO (TIPOS_PGTO)
@login_required
def create_payment_method(request):
    formas_pgto = Tipos_pgto.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "forma_pgto"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                formapgto, created = Tipos_pgto.objects.get_or_create(nome=nome, usuario=usuario)

                if created:
                    return render(
                            request,
                        'pages/cadastro-forma-pagamento.html',
                        {
                            'formas_pgto': formas_pgto,
                            "success_message": "Nova Forma de Pagamento cadastrada com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        'pages/cadastro-forma-pagamento.html',
                        {
                            'formas_pgto': formas_pgto,
                            "error_message": "Já existe uma Forma de Pagamento com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-forma-pagamento.html",
                    {
                        'formas_pgto': formas_pgto,
                        "error_message": "Não foi possível cadastrar esta nova Forma de Pagamento. Verifique os logs!",
                    },
                )

    return render(
        request, 'pages/cadastro-forma-pagamento.html', {'formas_pgto': formas_pgto, "page_group": page_group, "page": page}
    )


# AÇÃO PARA CRIAR NOVO OBJETO DISPOSITIVO
@login_required
def create_device(request):
    dispositivos = Dispositivo.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "dispositivo"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                dispositivo, created = Dispositivo.objects.get_or_create(nome=nome, usuario=usuario)

                if created:
                    return render(
                            request,
                        "pages/cadastro-dispositivo.html",
                        {
                            'dispositivos': dispositivos,
                            "success_message": "Novo Dispositivo cadastrado com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        "pages/cadastro-dispositivo.html",
                        {
                            'dispositivos': dispositivos,
                            "error_message": "Já existe um Dispositivo com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-dispositivo.html",
                    {
                        'dispositivos': dispositivos,
                        "error_message": "Não foi possível cadastrar este novo Dispositivo. Verifique os logs!",
                    },
                )

    return render(
        request, "pages/cadastro-dispositivo.html", {'dispositivos': dispositivos, "page_group": page_group, "page": page}
    )


# AÇÃO PARA CRIAR NOVO OBJETO APLICATIVO
@login_required
def create_app(request):
    aplicativos = Aplicativo.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "aplicativo"

    if request.method == "POST":
        nome = request.POST.get("name")
        have_mac = request.POST.get("mac")

        if nome and have_mac:
            # Verifica se o campo "mac" foi preenchido e atribui o valor correspondente
            if have_mac == "true":
                have_mac = True
            else:
                have_mac = False

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                aplicativo, created = Aplicativo.objects.get_or_create(nome=nome, device_has_mac=have_mac , usuario=usuario)

                if created:
                    return render(
                            request,
                        "pages/cadastro-aplicativo.html",
                        {
                            'aplicativos': aplicativos,
                            "success_message": "Novo Aplicativo cadastrado com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        "pages/cadastro-aplicativo.html",
                        {
                            'aplicativos': aplicativos,
                            "error_message": "Já existe um Aplicativo com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-aplicativo.html",
                    {
                        'aplicativos': aplicativos,
                        "error_message": "Não foi possível cadastrar este novo Aplicativo. Verifique os logs!",
                    },
                )

    return render(
        request, "pages/cadastro-aplicativo.html", {'aplicativos': aplicativos, "page_group": page_group, "page": page}
    )


############################################ DELETE VIEW ############################################

@login_required
def delete_app_account(request, pk):
    if request.method == "DELETE":
        try:
            conta_app = ContaDoAplicativo.objects.get(pk=pk, usuario=request.user)
            conta_app.delete()

            return JsonResponse({'success_message': 'deu bom'}, status=200)
        
        except Aplicativo.DoesNotExist as erro1:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
            error_msg = 'Você tentou excluir uma conta de aplicativo que não existe.'
            
            return JsonResponse({'error_message': 'erro'}, status=500)
        
        except ProtectedError as erro2:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
            error_msg = 'Essa conta de aplicativo não pôde ser excluída.'

            return JsonResponse(status=500)
    else:
        return JsonResponse({'error_message': 'erro'}, status=500)
    

@login_required
def delete_app(request, pk):
    try:
        aplicativo = Aplicativo.objects.get(pk=pk, usuario=request.user)
        aplicativo.delete()
    except Aplicativo.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Aplicativo não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    else:
        return redirect('cadastro-aplicativo')
    

@login_required
def delete_device(request, pk):
    try:
        dispositivo = Dispositivo.objects.get(pk=pk, usuario=request.user)
        dispositivo.delete()
    except Dispositivo.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Dispositivo não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    else:
        return redirect('cadastro-dispositivo')
    

@login_required
def delete_payment_method(request, pk):
    try:
        formapgto = Tipos_pgto.objects.get(pk=pk, usuario=request.user)
        formapgto.delete()
    except Tipos_pgto.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Servidor não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    else:
        return redirect('cadastro-forma-pagamento')
    

@login_required
def delete_server(request, pk):
    try:
        servidor = Servidor.objects.get(pk=pk, usuario=request.user)
        servidor.delete()
    except Servidor.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Servidor não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    else:
        return redirect('cadastro-servidor')
    

@login_required
def delete_payment_plan(request, pk):
    try:
        plano_mensal = Plano.objects.get(pk=pk, usuario=request.user)
        plano_mensal.delete()
    except Plano.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Plano não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )

    return redirect('cadastro-plano-adesao')


######################################
############## OUTROS ################
######################################

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_location_from_ip(ip):
    try:
        response = requests.get(f'https://ipapi.co/{ip}/json/')
        data = response.json()
        cidade = data.get('city', 'Desconhecida')
        pais = data.get('country_name', 'Desconhecido')
        return f"{cidade}, {pais}"
    except Exception:
        return "Localização desconhecida"


