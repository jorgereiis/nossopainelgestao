import requests, operator, logging, codecs, random, base64, json, time, re, os, io
import unicodedata
from pathlib import Path
from django.db.models import Sum, Q, Count, F, ExpressionWrapper, DurationField, Exists, OuterRef
from django.db.models.functions import Upper, Coalesce, ExtractDay, Trim
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.cache import cache_page, never_cache
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models.functions import ExtractMonth, ExtractYear
from django.views.decorators.http import require_http_methods
from plotly.colors import sample_colorscale, make_colorscale
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.decorators.vary import vary_on_cookie
from django.views.decorators.http import require_POST
from django.db.models.deletion import ProtectedError
from django.views.decorators.csrf import csrf_exempt
from django.core.validators import validate_email
from django.utils.timezone import localtime, now
from django.contrib.auth.views import LoginView
from django.views.generic.list import ListView
from datetime import timedelta, datetime, date
from django.utils.dateparse import parse_date
from django.forms.models import model_to_dict
from decimal import Decimal, InvalidOperation
from django.views.generic import DetailView
from django.contrib.auth.models import User
from babel.numbers import format_currency
from matplotlib.patches import Patch
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.conf import settings
import matplotlib.pyplot as plt
from plotly.offline import plot
from django.views import View
from .models import DDD_UF_MAP
from .forms import LoginForm
from typing import Optional
import plotly.express as px
import geopandas as gpd
import pandas as pd
import calendar
import warnings
import inspect

from django.http import (
    HttpResponseBadRequest,
    HttpResponseNotFound,
    HttpResponse, JsonResponse,
    Http404
)
from wpp.api_connection import (
    gerar_token, start_session,
    logout_session, status_session,
    check_connection, close_session
)
from .models import (
    Cliente, Servidor, Dispositivo,
    Aplicativo, Tipos_pgto, Plano,
    Mensalidade, ContaDoAplicativo,
    SessaoWpp, SecretTokenAPI,
    DadosBancarios, MensagemEnviadaWpp,
    DominiosDNS, PlanoIndicacao,
    HorarioEnvios, NotificationRead,
    UserActionLog
)
from .utils import (
    envio_apos_novo_cadastro,
    validar_tel_whatsapp,
    criar_mensalidade,
    log_user_action,
)

# Constantes
PLANOS_MESES = {
    'mensal': 1,
    'bimestral': 2,
    'trimestral': 3,
    'semestral': 6,
    'anual': 12
}

LOG_DIR = os.path.join(settings.BASE_DIR, 'logs')
os.getenv("")
MESES_31_DIAS = [1, 3, 5, 7, 8, 10, 12]

warnings.filterwarnings(
    "ignore", message="errors='ignore' is deprecated", category=FutureWarning
)
logger = logging.getLogger(__name__)
url_api = os.getenv("URL_API")

class StaffRequiredMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_staff or user.is_superuser)

############################################ WPP VIEW ############################################

@login_required
def whatsapp(request):
    return render(request, 'pages/whatsapp.html')


@login_required
def conectar_wpp(request):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido."}, status=405)

    usuario = request.user
    session = usuario.username

    try:
        user_admin = User.objects.get(is_superuser=True)
        secret = SecretTokenAPI.objects.get(usuario=user_admin).token
    except (User.DoesNotExist, SecretTokenAPI.DoesNotExist):
        return JsonResponse({"erro": "Token secreto de integração não encontrado."}, status=500)

    # 1. Obtém ou gera token
    sessao_existente = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
    if sessao_existente:
        token = sessao_existente.token
        print(f"[{timestamp}] [INFO] [{func_name}] [{usuario}] Token reutilizado para sessão '{session}'")
    else:
        token_data, token_status = gerar_token(session, secret)
        if token_status != 201:
            return JsonResponse({"erro": "Falha ao gerar token de autenticação."}, status=400)
        token = token_data["token"]
        print(f"[{timestamp}] [INFO] [{func_name}] [{usuario}] Novo token gerado para sessão '{session}'")

    # 2. Inicia a sessão
    init_data, init_status = start_session(session, token)
    print(f"[{timestamp}] [INFO] [{func_name}] [{usuario}] Resposta inicial de start-session: {init_data}")

    # 3. Verifica imediatamente se já está conectado
    status_data, status_code = status_session(session, token)
    status = status_data.get("status")
    if status == "CONNECTED":
        print(f"[{timestamp}] [INFO] [{func_name}] [{usuario}] Sessão '{session}' já está conectada.")
        SessaoWpp.objects.update_or_create(
            usuario=session,
            defaults={
                "token": token,
                "dt_inicio": timezone.now(),
                "is_active": True
            }
        )
        return JsonResponse({
            "status": "CONNECTED",
            "mensagem": "Sessão já está conectada.",
            "session": session
        })

    # 4. Tenta obter o QRCode
    max_tentativas = 5
    intervalo_segundos = 2
    for tentativa in range(max_tentativas):
        status_data, status_code = status_session(session, token)
        status = status_data.get("status")
        print(f"[{timestamp}] [INFO] [{func_name}] [{usuario}] Tentativa {tentativa+1}: status = {status}")
        if status == "QRCODE":
            break
        time.sleep(intervalo_segundos)
    else:
        print(f"[{timestamp}] [{func_name}] [{usuario}] [ERRO] QRCode não gerado após {max_tentativas} tentativas.")
        return JsonResponse({
            "erro": "Não foi possível gerar QRCode. Tente novamente em instantes.",
            "detalhes": status_data
        }, status=400)

    # 5. Salva ou atualiza sessão
    SessaoWpp.objects.update_or_create(
        usuario=session,
        defaults={
            "token": token,
            "dt_inicio": timezone.now(),
            "is_active": True
        }
    )
    print(f"[{timestamp}] [INFO] [{func_name}] [{usuario}] Sessão '{session}' salva com sucesso.")

    # 6. Retorna QRCode
    return JsonResponse({
        "qrcode": status_data.get("qrcode"),
        "status": status_data.get("status"),
        "session": session,
        "token": token
    })



@login_required
def get_token_ativo(usuario) -> Optional[str]:
    sessao = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    return sessao.token if sessao else None


@login_required
def status_wpp(request):
    usuario = request.user
    session = usuario.username

    sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
    if not sessao:
        return JsonResponse({"status": "DISCONNECTED", "message": "Sessão não encontrada"}, status=404)

    token = sessao.token
    dados_status, status_code = status_session(session, token)

    if status_code != 200:
        return JsonResponse({"status": "ERRO", "message": "Falha ao obter status"}, status=500)

    return JsonResponse({
        "status": dados_status.get("status"),
        "qrcode": dados_status.get("qrcode"),
        "session": session,
        "version": dados_status.get("version"),
    })


@login_required
def check_connection_wpp(request):
    usuario = request.user
    session = usuario.username

    sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
    if not sessao:
        return JsonResponse({"status": False, "message": "Sessão não encontrada"}, status=404)

    token = sessao.token
    dados, status_code = check_connection(session, token)

    return JsonResponse(dados, status=status_code)


@login_required
def desconectar_wpp(request):
    if request.method == "POST":
        usuario = request.user
        session = usuario.username

        sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
        if not sessao:
            return JsonResponse({"erro": "Sessão não encontrada"}, status=404)

        token = sessao.token
        resp_data, resp_status = logout_session(session, token)

        if resp_data.get("status") is True:
            sessao.is_active = False
            sessao.save()

        return JsonResponse(resp_data, status=resp_status)
    

@login_required
def cancelar_sessao_wpp(request):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido."}, status=405)

    usuario = request.user
    session = usuario.username

    try:
        sessao = SessaoWpp.objects.filter(usuario=session, is_active=True).first()
    except SessaoWpp.DoesNotExist:
        return JsonResponse({"erro": "Sessão não encontrada"}, status=404)

    token = sessao.token
    try:
        resp_data, resp_status = close_session(session, token)

        # Mesmo que a API retorne 500, se for JSON e tiver estrutura esperada, tratamos com sucesso
        if isinstance(resp_data, dict) and "status" in resp_data:
            print(f"[{timestamp}] [INFO] [{func_name}] [{usuario}] Resposta ao fechar sessão: {resp_data}")

            # Considera a sessão encerrada se a API retornou status 500 com JSON válido
            sessao.is_active = False
            sessao.save()

            return JsonResponse({
                "status": resp_data.get("status", False),
                "message": resp_data.get("message", "Sessão encerrada com falha não crítica."),
                "handled": True
            }, status=200)

        else:
            raise ValueError("Resposta da API não é um JSON válido")

    except Exception as e:
        print(f"[{timestamp}] [{func_name}] [{usuario}] [ERRO] Exceção ao cancelar sessão: {e}")
        return JsonResponse({
            "erro": "Erro interno ao cancelar sessão",
            "detalhes": str(e)
        }, status=500)


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
        cliente_id = self.request.GET.get("cliente_id")
        cliente = get_object_or_404(Cliente, id=cliente_id, usuario=self.request.user)
        conta_app = (
            ContaDoAplicativo.objects.filter(cliente=cliente, usuario=self.request.user)
            .select_related('app')
        )

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
        cliente_id = self.request.GET.get("cliente_id")
        cliente = get_object_or_404(Cliente, id=cliente_id, usuario=self.request.user)
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
        cliente_id = self.request.GET.get("cliente_id")
        cliente = get_object_or_404(Cliente, id=cliente_id, usuario=self.request.user)
        indicados = (
            Cliente.objects.filter(indicado_por=cliente, usuario=self.request.user)
            .order_by('-id')
            .values()
        )

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
            queryset = queryset.filter(
                Q(nome__icontains=query) | Q(telefone__icontains=query)
            )
        
        time.sleep(0.5)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hoje"] = timezone.localtime().date()
        return context
    

class ModalDNSJsonView(LoginRequiredMixin, View):
    def get(self, request):
        dns = DominiosDNS.objects.filter(usuario=request.user).order_by(
            "-status", "-data_online", "-servidor", "dominio"
        )
        data = []
        for d in dns:
            data.append({
                "status": True if d.status == "online" else False,
                "dominio": d.dominio,
                "monitorado": d.monitorado,
                "servidor": str(d.servidor.nome),
                "acesso_canais": d.acesso_canais if d.acesso_canais else "",
                "data_online": d.data_online.strftime('%d/%m/%Y %H:%M') if d.data_online else "",
                "data_offline": d.data_offline.strftime('%d/%m/%Y %H:%M') if d.data_offline else "",
                "data_ultima_verificacao": d.data_ultima_verificacao.strftime('%d/%m/%Y %H:%M') if d.data_ultima_verificacao else "",
            })
        return JsonResponse({"dns": data})


class LogFilesListView(LoginRequiredMixin, StaffRequiredMixin, View):
    def get(self, request):
        base_path = Path(LOG_DIR)
        if not base_path.exists():
            return JsonResponse({"files": []})

        resolved_base = base_path.resolve()
        log_files = []
        for path in resolved_base.rglob("*.log"):
            if not path.is_file():
                continue
            try:
                relative_path = path.relative_to(resolved_base)
            except ValueError:
                continue
            log_files.append(str(relative_path).replace("\\", "/"))

        return JsonResponse({"files": sorted(log_files)})


class LogFileContentView(LoginRequiredMixin, StaffRequiredMixin, View):
    def get(self, request):
        filename = request.GET.get("file", "").strip()
        if not filename:
            return JsonResponse({'error': 'Arquivo não informado.'}, status=400)

        base_path = Path(LOG_DIR)
        if not base_path.exists():
            raise Http404('Arquivo não encontrado.')

        resolved_base = base_path.resolve()
        candidate = (resolved_base / filename).resolve()

        if candidate == resolved_base or resolved_base not in candidate.parents:
            raise Http404('Arquivo não permitido.')

        if candidate.suffix != '.log' or not candidate.is_file():
            raise Http404('Arquivo não encontrado.')

        with candidate.open(encoding='utf-8', errors='replace') as handler:
            lines = handler.readlines()[-2000:]

        return JsonResponse({'content': ''.join(lines)})

class UserActionLogListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            limit = int(request.GET.get('limit', 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 200))

        user_is_staff = request.user.is_staff or request.user.is_superuser
        queryset = UserActionLog.objects.all() if user_is_staff else UserActionLog.objects.filter(usuario=request.user)

        target_user = None
        user_param = request.GET.get('user')
        if user_is_staff and user_param:
            try:
                target_user = User.objects.get(pk=int(user_param))
            except (ValueError, User.DoesNotExist):
                try:
                    target_user = User.objects.get(username=user_param)
                except User.DoesNotExist:
                    target_user = None
        if target_user:
            queryset = queryset.filter(usuario=target_user)

        action_filter = request.GET.get('action')
        valid_actions = {choice for choice, _ in UserActionLog.ACTION_CHOICES}
        if action_filter in valid_actions:
            queryset = queryset.filter(acao=action_filter)

        search_term = request.GET.get('search')
        if search_term:
            queryset = queryset.filter(
                Q(mensagem__icontains=search_term)
                | Q(entidade__icontains=search_term)
                | Q(objeto_repr__icontains=search_term)
            )

        start_date = request.GET.get('since')
        end_date = request.GET.get('until')
        if start_date:
            parsed = parse_date(start_date)
            if parsed:
                queryset = queryset.filter(criado_em__date__gte=parsed)
        if end_date:
            parsed = parse_date(end_date)
            if parsed:
                queryset = queryset.filter(criado_em__date__lte=parsed)

        queryset = queryset.select_related('usuario')
        total_registros = queryset.count()
        queryset = queryset.order_by('-criado_em')[:limit]

        dados = []
        for log in queryset:
            dados.append({
                'id': log.id,
                'timestamp': timezone.localtime(log.criado_em).strftime('%d/%m/%Y %H:%M:%S'),
                'acao': log.acao,
                'acao_label': log.get_acao_display(),
                'entidade': log.entidade,
                'objeto_id': log.objeto_id,
                'objeto_repr': log.objeto_repr,
                'mensagem': log.mensagem,
                'extras': log.extras or {},
                'ip': log.ip,
                'request_path': log.request_path,
                'usuario': {
                    'id': log.usuario_id,
                    'username': log.usuario.get_username(),
                    'nome': log.usuario.get_full_name() or log.usuario.get_username(),
                },
            })

        return JsonResponse({
            'results': dados,
            'actions': [{'value': value, 'label': label} for value, label in UserActionLog.ACTION_CHOICES],
            'total': total_registros,
            'limit': limit,
            'can_view_all': user_is_staff,
            'selected_user': target_user.id if target_user else request.user.id,
            'users': [
                {
                    'id': user.id,
                    'username': user.get_username(),
                    'nome': user.get_full_name() or user.get_username(),
                }
                for user in User.objects.filter(is_active=True).order_by('username')
            ] if user_is_staff else [],
        })

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

        total_pago_qtd = Mensalidade.objects.filter(
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

        total_receber_qtd = Mensalidade.objects.filter(
            cancelado=False,
            dt_vencimento__year=ano_atual,
            dt_vencimento__month=mes_atual,
            dt_vencimento__day__gte=hoje.day,
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

        # Resumo dos planos de adesão
        planos_adesao = (
            Cliente.objects
            .filter(usuario=self.request.user, cancelado=False)
            .annotate(nome_norm=Upper(Trim(F('plano__nome'))))
            .values('nome_norm')
            .annotate(qtd_adesoes=Count('id'))
            .order_by('nome_norm')
        )
        planos_cadastrados_norm = list(
            Plano.objects.filter(usuario=self.request.user)
            .annotate(nome_norm=Upper(Trim(F('nome'))))
            .values_list('nome_norm', flat=True)
            .distinct()
        )
        contagens = {row['nome_norm']: int(row['qtd_adesoes']) for row in planos_adesao}
        ordem_norm = ['MENSAL', 'TRIMESTRAL', 'SEMESTRAL', 'ANUAL']
        planos_ordenados_norm = sorted(
            set(planos_cadastrados_norm),
            key=lambda n: (ordem_norm.index(n) if n in ordem_norm else len(ordem_norm), n)
        )
        def label(n):
            mapa = {'MENSAL': 'Mensal', 'TRIMESTRAL': 'Trimestral', 'SEMESTRAL': 'Semestral', 'ANUAL': 'Anual'}
            return mapa.get(n, n.title())
        total = int(total_clientes) if total_clientes else 0
        planos_resumo = []
        for nome_norm in planos_ordenados_norm:
            qtd = contagens.get(nome_norm, 0)
            pct = (qtd / total * 100) if total else 0
            planos_resumo.append({'nome': label(nome_norm), 'qtd': qtd, 'pct': pct})
        # Fim resumo dos planos de adesão

        lista_meses = [
            (1, 'Jan'), (2, 'Fev'), (3, 'Mar'), (4, 'Abr'), (5, 'Mai'), (6, 'Jun'),
            (7, 'Jul'), (8, 'Ago'), (9, 'Set'), (10, 'Out'), (11, 'Nov'), (12, 'Dez')
        ]

        data_atual = timezone.localtime().date()

        query_telas = (
            Cliente.objects
            .filter(usuario=self.request.user, cancelado=False, plano__usuario=self.request.user)
            .select_related("plano")
            .only("id", "plano__telas", "plano__nome")
        )
        total_telas = query_telas.aggregate(
            total=Coalesce(Sum("plano__telas"), 0)
        )["total"]

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
                "valor_total_pago_qtd": total_pago_qtd,
                "valor_total_receber_qtd": total_receber_qtd,
                "clientes_cancelados_qtd": clientes_cancelados_qtd,
                "total_telas_ativas": int(total_telas),
                'planos_resumo': planos_resumo,
                ## context para modal de edição
                "planos": planos,
                "servidores": servidores,
                "indicadores": indicadores,
                "dispositivos": dispositivos,
                "formas_pgtos": formas_pgtos,
                ## context para o gráfico de adesões e cancelamentos
                "anos_adesao": anos_adesao,
                "lista_meses": lista_meses,
                "anuo_atual": ano_atual,
                "data_atual": data_atual,
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
        if MensagemEnviadaWpp.objects.filter(usuario=usuario, telefone=telefone, data_envio=timezone.now().date()).exists():
            log_result(log_result_filename, f"{telefone} - ⚠️ Já foi feito envio hoje!")
            return

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        body = {
            'phone': telefone,
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
            log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{telefone}] Mensagem enviada!")
            log_result(log_result_filename, f"{telefone} - ✅ Mensagem enviada")
            MensagemEnviadaWpp.objects.create(usuario=usuario, telefone=telefone)
            time.sleep(random.uniform(5, 12))
        else:
            try:
                response_data = response.json()
                error_message = response_data.get('message', response.text)
            except json.decoder.JSONDecodeError:
                error_message = response.text
            log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{telefone}] [CODE][{response.status_code}] - {error_message}")
            log_result(log_result_filename, f"{telefone} - ❌ Não enviada (consultar log)")

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



@require_http_methods(["GET"])
@login_required
def secret_token_api(request):
    """
        Função de view para consultar o Secret Token da API WPP Connect
    """
    if not request.user.is_superuser:
        return JsonResponse({'error_message': 'Permissão negada.'}, status=403)

    token = (
        SecretTokenAPI.objects.filter(usuario=request.user)
        .order_by('-dt_criacao')
        .values_list('token', flat=True)
        .first()
    )

    if not token:
        return JsonResponse({'error_message': 'Token não encontrado.'}, status=404)

    return JsonResponse({'stkn': token}, status=200)

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


@require_http_methods(["GET"])
@login_required
def get_logs_wpp(request):
    log_path = Path(LOG_DIR) / "Envios manuais" / f"{request.user.username}_send_result.log"

    if not log_path.exists():
        return JsonResponse({'logs': ''})

    logs = log_path.read_text(encoding='utf-8', errors='ignore')
    return JsonResponse({'logs': logs})


@login_required
def profile_page(request):
    user = request.user
    dados_bancarios = DadosBancarios.objects.filter(usuario=user).first()

    dt_inicio = user.date_joined.strftime('%d/%m/%Y') if user.date_joined else '--'
    f_name = user.first_name or '--'
    l_name = user.last_name or '--'
    email = user.email or '--'

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
            'username': user.username,
            'email': email,
            'chave': chave,
            'wpp': wpp,
        },
    )


@login_required
def generate_graphic_columns_per_month(request):
    ano_atual = now().year
    mes = int(request.GET.get("mes", now().month))
    usuario = request.user

    if not (1 <= mes <= 12):
        return HttpResponse("Mês inválido", status=400)

    dados_adesoes = (
        Cliente.objects.filter(
            data_adesao__year=ano_atual,
            data_adesao__month=mes,
            usuario=usuario,
        )
        .annotate(dia=ExtractDay("data_adesao"))
        .values("dia")
        .annotate(total=Count("id"))
        .order_by("dia")
    )

    dados_cancelamentos = (
        Cliente.objects.filter(
            data_cancelamento__year=ano_atual,
            data_cancelamento__month=mes,
            usuario=usuario,
        )
        .annotate(dia=ExtractDay("data_cancelamento"))
        .values("dia")
        .annotate(total=Count("id"))
        .order_by("dia")
    )

    adesoes_dict = {dado["dia"]: dado["total"] for dado in dados_adesoes}
    cancelamentos_dict = {dado["dia"]: dado["total"] for dado in dados_cancelamentos}

    dias = []
    adesoes = []
    cancelamentos = []

    total_dias_mes = calendar.monthrange(ano_atual, mes)[1]

    for dia in range(1, total_dias_mes + 1):
        if dia in adesoes_dict or dia in cancelamentos_dict:
            dias.append(str(dia))
            adesoes.append(adesoes_dict.get(dia, 0))
            cancelamentos.append(cancelamentos_dict.get(dia, 0))

    total_adesoes = sum(adesoes)
    total_cancelamentos = sum(cancelamentos)
    saldo_final = total_adesoes - total_cancelamentos

    plt.figure(figsize=(7, 3))
    plt.bar(dias, adesoes, color="#4CAF50", width=0.4, label="Adesões")
    plt.bar(dias, cancelamentos, color="#F44336", width=0.4, bottom=adesoes, label="Cancelamentos")

    for i, valor in enumerate(adesoes):
        if valor > 0:
            plt.text(i, valor / 2, str(valor), ha='center', va='center', fontsize=10, color='white', fontweight='bold')

    for i, valor in enumerate(cancelamentos):
        if valor > 0:
            plt.text(
                i,
                adesoes[i] + valor / 2,
                str(valor),
                ha='center',
                va='center',
                fontsize=10,
                color='white',
                fontweight='bold',
            )

    nomes_pt = [
        "",
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]
    nome_mes = nomes_pt[mes]
    plt.title(f"Adesões e Cancelamentos por mês - {nome_mes} {ano_atual}", fontsize=14)
    plt.xlabel("Dia", fontsize=12)
    plt.ylabel("Quantidade", fontsize=12)
    plt.xticks(fontsize=10, fontweight='bold')
    plt.yticks(fontsize=10)

    cor_saldo = "#624BFF" if saldo_final >= 0 else "#F44336"
    texto_saldo = f"Saldo {nome_mes}: {'+' if saldo_final > 0 else ''}{saldo_final}"

    saldo_patch = Patch(color=cor_saldo, label=texto_saldo)
    plt.legend(
        handles=[
            Patch(color="#4CAF50", label=f"Adesões: {total_adesoes}"),
            Patch(color="#F44336", label=f"Cancelamentos: {total_cancelamentos}"),
            saldo_patch,
        ]
    )

    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)

    buffer = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buffer, format='png', bbox_inches="tight", dpi=100)
    buffer.seek(0)
    plt.close()

    return HttpResponse(buffer.getvalue(), content_type="image/png")


@login_required
def generate_graphic_columns_per_year(request):
    ano = request.GET.get("ano", timezone.now().year)
    usuario = request.user

    dados_adesoes = (
        Cliente.objects.filter(data_adesao__year=ano, usuario=usuario)
        .annotate(mes=ExtractMonth("data_adesao"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )

    dados_cancelamentos = (
        Cliente.objects.filter(data_cancelamento__year=ano, usuario=usuario)
        .annotate(mes=ExtractMonth("data_cancelamento"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )

    meses = []
    adesoes = []
    cancelamentos = []

    adesoes_dict = {dado["mes"]: dado["total"] for dado in dados_adesoes}
    cancelamentos_dict = {dado["mes"]: dado["total"] for dado in dados_cancelamentos}

    for mes in range(1, 13):
        if mes in adesoes_dict or mes in cancelamentos_dict:
            meses.append(calendar.month_abbr[mes])
            adesoes.append(adesoes_dict.get(mes, 0))
            cancelamentos.append(cancelamentos_dict.get(mes, 0))

    total_adesoes = sum(adesoes)
    total_cancelamentos = sum(cancelamentos)
    saldo_final = total_adesoes - total_cancelamentos

    plt.figure(figsize=(7, 3))
    plt.bar(meses, adesoes, color="#4CAF50", width=0.4, label="Adesões")
    plt.bar(meses, cancelamentos, color="#F44336", width=0.4, bottom=adesoes, label="Cancelamentos")

    for i, valor in enumerate(adesoes):
        if valor > 0:
            plt.text(i, valor / 2, str(valor), ha='center', va='center', fontsize=10, color='white', fontweight='bold')

    for i, valor in enumerate(cancelamentos):
        if valor > 0:
            plt.text(
                i,
                adesoes[i] + valor / 2,
                str(valor),
                ha='center',
                va='center',
                fontsize=10,
                color='white',
                fontweight='bold',
            )

    plt.title(f'Adesão e Cancelamentos por ano - {ano}', fontsize=14)
    plt.xlabel('Mês', fontsize=12)
    plt.ylabel('Quantidade', fontsize=12)
    plt.xticks(fontsize=10, fontweight='bold')
    plt.yticks(fontsize=10)

    cor_saldo = "#624BFF" if saldo_final >= 0 else "#F44336"
    texto_saldo = f"Saldo {ano}: {'+' if saldo_final > 0 else ''}{saldo_final}"

    saldo_patch = Patch(color=cor_saldo, label=texto_saldo)
    plt.legend(
        handles=[
            Patch(color="#4CAF50", label=f"Adesões: {total_adesoes}"),
            Patch(color="#F44336", label=f"Cancelamentos: {total_cancelamentos}"),
            saldo_patch,
        ]
    )

    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches="tight", dpi=100)
    buffer.seek(0)
    plt.close()

    return HttpResponse(buffer.getvalue(), content_type="image/png")


def user_cache_key(request):
    return f"user-{request.user.id}" if request.user.is_authenticated else "anonymous"


def cache_page_by_user(timeout):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            return cache_page(timeout, key_prefix=user_cache_key(request))(view_func)(request, *args, **kwargs)

        return _wrapped_view

    return decorator


@xframe_options_exempt
@login_required
@cache_page_by_user(60 * 120)
def generate_graphic_map_customers(request):
    usuario = request.user

    dados = dict(
        Cliente.objects.filter(cancelado=False, usuario=usuario)
        .values("uf")
        .annotate(total=Count("id"))
        .values_list("uf", "total")
    )
    total_geral = sum(dados.values())
    clientes_internacionais = Cliente.objects.filter(cancelado=False, usuario=usuario, uf__isnull=True).count()

    mapa = gpd.read_file("archives/brasil_estados.geojson")

    def _normalizar_estado(nome):
        if not isinstance(nome, str):
            return ""
        return unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii").lower()

    siglas = {
        "acre": "AC",
        "alagoas": "AL",
        "amapa": "AP",
        "amazonas": "AM",
        "bahia": "BA",
        "ceara": "CE",
        "distrito federal": "DF",
        "espirito santo": "ES",
        "goias": "GO",
        "maranhao": "MA",
        "mato grosso": "MT",
        "mato grosso do sul": "MS",
        "minas gerais": "MG",
        "para": "PA",
        "paraiba": "PB",
        "parana": "PR",
        "pernambuco": "PE",
        "piaui": "PI",
        "rio de janeiro": "RJ",
        "rio grande do norte": "RN",
        "rio grande do sul": "RS",
        "rondonia": "RO",
        "roraima": "RR",
        "santa catarina": "SC",
        "sao paulo": "SP",
        "sergipe": "SE",
        "tocantins": "TO",
    }

    mapa["sigla"] = mapa["name"].apply(lambda nome: siglas.get(_normalizar_estado(nome)))
    mapa = mapa.dropna(subset=["sigla"])
    mapa["clientes"] = mapa["sigla"].apply(lambda uf: dados.get(uf, 0))
    mapa["porcentagem"] = mapa["clientes"].apply(
        lambda x: round((x / total_geral) * 100, 1) if total_geral > 0 else 0
    )

    mapa = mapa.drop(columns=["created_at", "updated_at"], errors="ignore")
    geojson_data = json.loads(mapa.to_json())

    max_clientes = max(mapa["clientes"]) if mapa["clientes"].any() else 1
    mapa["clientes_cor"] = mapa["clientes"].apply(lambda x: x if x > 0 else None)

    fig = px.choropleth_mapbox(
        mapa,
        geojson=geojson_data,
        locations="sigla",
        color="clientes",
        color_continuous_scale=[
            [0.0, "#FFFFFF"],
            [0.01, "#cdbfff"],
            [1.0, "#624BFF"]
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
        center={"lat": -19.68828, "lon": -54.72019},
        zoom=2.2,
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

    grafico_html = plot(fig, output_type="div", include_plotlyjs="cdn")

    info_adicional = f"""
    <div style='text-align:center; font-family:Arial; font-size:12px; color: #333; margin-top: 8px;'>
        Qtd. fora do pa\u00eds: {clientes_internacionais}
    </div>
    """
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
        {info_adicional}
        {grafico_html}
    </body>
    </html>
    """

    return HttpResponse(html, content_type="text/html")

@login_required
@never_cache
def notifications_dropdown(request):
    hoje = timezone.localdate()
    tipos = [Tipos_pgto.CARTAO, Tipos_pgto.BOLETO]

    queryset = (
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
                hoje - F("dt_vencimento"), output_field=DurationField()
            )
        )
        .order_by("dt_vencimento")
    )

    itens = list(queryset[:20])
    context = {
        "notif_items": itens,
        "notif_count": queryset.count(),
    }
    return render(request, "notificacoes/dropdown.html", context)

@login_required
@require_POST
def notifications_mark_all_read(request):
    hoje = timezone.localdate()
    tipos = [Tipos_pgto.CARTAO, Tipos_pgto.BOLETO]
    ids = list(
        Mensalidade.objects.filter(
            usuario=request.user,
            pgto=False, cancelado=False,
            cliente__cancelado=False,
            cliente__forma_pgto__nome__in=tipos,
            dt_vencimento__lt=hoje,
        ).values_list("id", flat=True)
    )

    objetos = [
        NotificationRead(usuario=request.user, mensalidade_id=mensalidade_id)
        for mensalidade_id in ids
    ]
    NotificationRead.objects.bulk_create(objetos, ignore_conflicts=True)

    request.session.pop("notif_read_ids", None)

    return JsonResponse({"ok": True, "cleared": len(ids)})

class NotificationsModalView(LoginRequiredMixin, ListView):
    model = Mensalidade
    template_name = "notificacoes/_lista_modal.html"
    context_object_name = "mensalidades"
    paginate_by = 15

    def get_queryset(self):
        hoje = timezone.localdate()
        return (
            Mensalidade.objects
            .select_related("cliente", "cliente__forma_pgto", "cliente__plano")
            .filter(
                usuario=self.request.user,
                pgto=False,
                cancelado=False,
                cliente__cancelado=False,
                cliente__forma_pgto__nome__in=[Tipos_pgto.CARTAO, Tipos_pgto.BOLETO],
                dt_vencimento__lt=hoje,
            )
            .annotate(
                ja_lida=Exists(
                    NotificationRead.objects.filter(
                        usuario=self.request.user,
                        mensalidade=OuterRef("pk"),
                    )
                ),
                dias_atraso=ExpressionWrapper(
                    hoje - F("dt_vencimento"), output_field=DurationField()
                ),
            )
            .order_by("ja_lida", "dt_vencimento")
        )

@login_required
def notifications_count(request):
    hoje = timezone.localdate()
    tipos = [Tipos_pgto.CARTAO, Tipos_pgto.BOLETO]

    count = (
        Mensalidade.objects
        .filter(
            usuario=request.user,
            pgto=False, cancelado=False,
            cliente__cancelado=False,
            cliente__forma_pgto__nome__in=tipos,
            dt_vencimento__lt=hoje,
        )
        .exclude(notifications_read__usuario=request.user)
        .count()
    )
    return JsonResponse({"count": count})

class MensalidadeDetailView(LoginRequiredMixin, DetailView):
    model = Mensalidade
    template_name = "mensalidades/detalhe.html"

    def get_queryset(self):
        # Restringe ao usuário logado
        return Mensalidade.objects.select_related("cliente", "cliente__plano", "cliente__forma_pgto").filter(
            usuario=self.request.user
        )

############################################ UPDATE VIEW ############################################

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
    nova_mensalidade_criada = False
    mensalidade_reativada = False

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
                mensalidade_reativada = True
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
                nova_mensalidade_criada = True
        else:
            # Caso não exista mensalidade anterior, cria uma nova
            Mensalidade.objects.create(
                cliente=cliente,
                valor=cliente.plano.valor,
                dt_vencimento=data_hoje,
                usuario=cliente.usuario
            )
            nova_mensalidade_criada = True

    except Exception as erro:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]',
                     timezone.localtime(), request.user,
                     request.META.get('REMOTE_ADDR', ''), erro,
                     exc_info=True)
        return JsonResponse({"error_message": "Erro ao processar mensalidade na reativação."}, status=500)

    log_user_action(
        request=request,
        action=UserActionLog.ACTION_REACTIVATE,
        instance=cliente,
        message="Cliente reativado.",
        extra={
            "nova_mensalidade_criada": nova_mensalidade_criada,
            "mensalidade_reativada": mensalidade_reativada,
        },
    )
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
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_PAYMENT,
            instance=mensalidade,
            message="Mensalidade marcada como paga.",
            extra={
                "cliente": mensalidade.cliente_id,
                "valor": str(mensalidade.valor),
                "dt_pagamento": mensalidade.dt_pagamento.strftime('%Y-%m-%d') if mensalidade.dt_pagamento else '',
            },
        )

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
        mensalidades_count = mensalidades.count()
        for mensalidade in mensalidades:
            mensalidade.cancelado = True
            mensalidade.dt_cancelamento = timezone.localtime().date()
            mensalidade.save()

        # Retorna uma resposta JSON indicando que o cliente foi cancelado com sucesso
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_CANCEL,
            instance=cliente,
            message="Cliente cancelado.",
            extra={
                "mensalidades_canceladas": mensalidades_count,
            },
        )
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
        token = SessaoWpp.objects.filter(usuario=user, is_active=True).first()
        cliente = get_object_or_404(Cliente, pk=cliente_id, usuario=user)
        mensalidade = get_object_or_404(Mensalidade, cliente=cliente, pgto=False, cancelado=False, usuario=user)

        original_cliente = {
            "nome": cliente.nome,
            "telefone": cliente.telefone,
            "uf": cliente.uf,
            "indicado_por": cliente.indicado_por,
            "servidor": cliente.servidor,
            "forma_pgto": cliente.forma_pgto,
            "plano": cliente.plano,
            "data_vencimento": cliente.data_vencimento,
            "dispositivo": cliente.dispositivo,
            "sistema": cliente.sistema,
            "notas": cliente.notas,
        }
        original_mensalidade = {
            "dt_vencimento": mensalidade.dt_vencimento,
            "valor": mensalidade.valor,
        }

        # Nome
        nome = post.get("nome", "").strip()
        if cliente.nome != nome:
            cliente.nome = nome

        # Telefone
        telefone_novo = post.get("telefone", "").strip()
        if cliente.telefone != telefone_novo:

            # Valida o novo telefone
            resultado_wpp = validar_tel_whatsapp(telefone_novo, token.token, user)
            cliente_existe_telefone = resultado_wpp.get("cliente_existe_telefone")
            telefone_novo = resultado_wpp.get("telefone_validado_wpp")

            if not resultado_wpp.get("wpp"):
                logger.warning(
                    f"[WARN][EDITAR CLIENTE] O número {telefone_novo} não possui um WhatsApp."
                )
                return JsonResponse({
                    "error": True,
                    "error_message_edit": (
                        f"O número {telefone_novo} não possui um WhatsApp.<br>"
                        "O cadastro do cliente precisa ter um número ativo no WhatsApp."
                    ),
                }, status=500)

            # Se o novo número existe para outro cliente cadastrado
            if cliente_existe_telefone:
                # Garante que não é o próprio cliente que está editando
                cliente_existente = Cliente.objects.filter(
                    telefone=cliente_existe_telefone,
                    usuario=user
                ).exclude(pk=cliente_id).first()
                if cliente_existente:
                    logger.warning(
                        f"[WARN][EDITAR CLIENTE] Já existe cliente para telefone {cliente_existente.telefone} (ID: {cliente_existente.id})"
                    )
                    return JsonResponse({
                        "error": True,
                        "error_message_edit": (
                            "Há um cliente cadastrado com o telefone informado! <br><br>"
                            f"<strong>Nome:</strong> {cliente_existente.nome} <br>"
                            f"<strong>Telefone:</strong> {cliente_existente.telefone}"
                        ),
                    }, status=500)
                # Se chegou aqui, está tudo certo (ou é ele mesmo)
            # Atualiza telefone e UF
            cliente.telefone = telefone_novo
            cliente.uf = extrair_uf_do_telefone(telefone_novo)

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
        plano_str = post.get("plano", "")
        if '-' in plano_str:
            plano_nome, plano_valor = plano_str.rsplit('-', 1)
            plano_nome = plano_nome.strip()
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
            return JsonResponse({
                "error": True,
                "error_message_edit": "Data de vencimento inválida. Use o formato DD/MM/AAAA ou AAAA-MM-DD."
            }, status=400)

        nova_data_vencimento = data_base

        if cliente.data_vencimento != nova_data_vencimento:
            cliente.data_vencimento = nova_data_vencimento
            mensalidade.dt_vencimento = nova_data_vencimento
            if plano:
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

        changes = {}

        def _add_change(key, old, new):
            if old != new:
                changes[key] = (old, new)

        _add_change("nome", original_cliente["nome"], cliente.nome)
        _add_change("telefone", original_cliente["telefone"], cliente.telefone)
        _add_change("uf", original_cliente["uf"], cliente.uf)
        _add_change("indicado_por", original_cliente["indicado_por"], cliente.indicado_por)
        _add_change("servidor", original_cliente["servidor"], cliente.servidor)
        _add_change("forma_pgto", original_cliente["forma_pgto"], cliente.forma_pgto)
        _add_change("plano", original_cliente["plano"], cliente.plano)
        _add_change("data_vencimento", original_cliente["data_vencimento"], cliente.data_vencimento)
        _add_change("dispositivo", original_cliente["dispositivo"], cliente.dispositivo)
        _add_change("sistema", original_cliente["sistema"], cliente.sistema)
        _add_change("notas", original_cliente["notas"], cliente.notas)
        _add_change("mensalidade.dt_vencimento", original_mensalidade["dt_vencimento"], mensalidade.dt_vencimento)
        _add_change("mensalidade.valor", original_mensalidade["valor"], mensalidade.valor)

        mensagem_log = "Cliente atualizado." if changes else "Cliente salvo sem alteracoes."
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=cliente,
            message=mensagem_log,
            extra=changes if changes else None,
        )

        return JsonResponse({
            "success": True,
            "success_message": f"<strong>{cliente.nome}</strong> foi atualizado com sucesso."
        }, status=200)

    except Exception as e:
        logger.error('[%s] [ERROR][EDITAR CLIENTE] [USER][%s] [IP][%s] [%s]',
                     timezone.localtime(), request.user,
                     request.META.get('REMOTE_ADDR'), e, exc_info=True)
        return JsonResponse({
            "error": True,
            "error_message": "Ocorreu um erro ao tentar atualizar esse cliente."
        }, status=500)



# AÇÃO PARA EDITAR O OBJETO PLANO MENSAL
@login_required
def edit_payment_plan(request, plano_id):
    """
    Função de view para editar um plano de adesão mensal.
    """
    plano_mensal = get_object_or_404(Plano, pk=plano_id, usuario=request.user)

    original_plano = {
        "nome": plano_mensal.nome,
        "telas": plano_mensal.telas,
        "valor": plano_mensal.valor,
    }

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
                changes = {}
                if original_plano["nome"] != plano_mensal.nome:
                    changes["nome"] = (original_plano["nome"], plano_mensal.nome)
                if original_plano["telas"] != plano_mensal.telas:
                    changes["telas"] = (original_plano["telas"], plano_mensal.telas)
                if original_plano["valor"] != plano_mensal.valor:
                    changes["valor"] = (original_plano["valor"], plano_mensal.valor)
                mensagem_plano = "Plano atualizado." if changes else "Plano salvo sem alteracoes."
                log_user_action(
                    request=request,
                    action=UserActionLog.ACTION_UPDATE,
                    instance=plano_mensal,
                    message=mensagem_plano,
                    extra=changes if changes else None,
                )


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
    original_nome = servidor.nome

    servidores = Servidor.objects.filter(usuario=request.user).order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:         
            servidor.nome = nome
            try:
                servidor.save()
                changes = {}
                if original_nome != servidor.nome:
                    changes["nome"] = (original_nome, servidor.nome)
                mensagem = "Servidor atualizado." if changes else "Servidor salvo sem alteracoes."
                log_user_action(
                    request=request,
                    action=UserActionLog.ACTION_UPDATE,
                    instance=servidor,
                    message=mensagem,
                    extra=changes if changes else None,
                )


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
    original_nome = dispositivo.nome

    dispositivos = Dispositivo.objects.filter(usuario=request.user).order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:         
            dispositivo.nome = nome
            try:
                dispositivo.save()
                changes = {}
                if original_nome != dispositivo.nome:
                    changes["nome"] = (original_nome, dispositivo.nome)
                mensagem = "Dispositivo atualizado." if changes else "Dispositivo salvo sem alteracoes."
                log_user_action(
                    request=request,
                    action=UserActionLog.ACTION_UPDATE,
                    instance=dispositivo,
                    message=mensagem,
                    extra=changes if changes else None,
                )


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
                original_usuario = {
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "email": user.email or "",
                }
                dados_usuario = user
                dados_usuario.last_name = request.POST.get('sobrenome', '').strip()
                dados_usuario.first_name = request.POST.get('nome', '').strip()
                dados_usuario.email = request.POST.get('email', '').strip()
                dados_usuario.save()

                dados_bancarios = DadosBancarios.objects.filter(usuario=user).first()
                dados_bancarios_criado = False
                original_bancarios = None
                if dados_bancarios:
                    original_bancarios = {
                        "beneficiario": dados_bancarios.beneficiario or "",
                        "instituicao": dados_bancarios.instituicao or "",
                        "tipo_chave": dados_bancarios.tipo_chave or "",
                        "chave": dados_bancarios.chave or "",
                        "wpp": dados_bancarios.wpp or "",
                    }
                else:
                    dados_bancarios = DadosBancarios(usuario=user)
                    dados_bancarios_criado = True

                beneficiario = request.POST.get('beneficiario', '').strip()
                instituicao = request.POST.get('instituicao', '').strip()
                tipo_chave = request.POST.get('tipo_chave', '').strip()
                chave = request.POST.get('chave', '').strip()
                wpp = request.POST.get('wpp', '').strip()

                dados_bancarios.beneficiario = beneficiario
                dados_bancarios.instituicao = instituicao
                dados_bancarios.tipo_chave = tipo_chave
                dados_bancarios.chave = chave
                dados_bancarios.wpp = wpp
                dados_bancarios.save()

                changes = {}
                if original_usuario["first_name"] != dados_usuario.first_name:
                    changes["usuario.first_name"] = (original_usuario["first_name"], dados_usuario.first_name)
                if original_usuario["last_name"] != dados_usuario.last_name:
                    changes["usuario.last_name"] = (original_usuario["last_name"], dados_usuario.last_name)
                if original_usuario["email"] != dados_usuario.email:
                    changes["usuario.email"] = (original_usuario["email"], dados_usuario.email)

                if dados_bancarios_criado:
                    changes["dados_bancarios"] = {
                        "created": True,
                        "beneficiario": beneficiario,
                        "instituicao": instituicao,
                        "tipo_chave": tipo_chave,
                        "chave": chave,
                        "wpp": wpp,
                    }
                else:
                    updated_bancarios = {
                        "beneficiario": beneficiario,
                        "instituicao": instituicao,
                        "tipo_chave": tipo_chave,
                        "chave": chave,
                        "wpp": wpp,
                    }
                    for campo, antigo_valor in original_bancarios.items():
                        novo_valor = updated_bancarios.get(campo, "")
                        if antigo_valor != novo_valor:
                            changes[f"dados_bancarios.{campo}"] = (antigo_valor, novo_valor)

                mensagem = "Perfil atualizado." if changes else "Perfil salvo sem alterações."
                log_user_action(
                    request=request,
                    action=UserActionLog.ACTION_UPDATE,
                    instance=request.user,
                    message=mensagem,
                    extra=changes if changes else None,
                )

                messages.success(request, 'Perfil editado com sucesso!')
            except Exception as e:
                messages.error(request, 'Ocorreu um erro ao editar o perfil. Verifique o log!')
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
        else:
            messages.error(request, 'Usuário da requisição não identificado!')
    else:
        messages.error(request, 'Método da requisição não permitido!')

    return redirect('perfil')


@login_required
@require_http_methods(["GET", "POST"])
def edit_horario_envios(request):
    HORARIOS_OBRIGATORIOS = [
        {
            "nome": "mensalidades_a_vencer",
            "tipo_envio": "mensalidades_a_vencer",
            "horario": None,
            "status": False,
            "ativo": True,
        },
        {
            "nome": "obter_mensalidades_vencidas",
            "tipo_envio": "obter_mensalidades_vencidas",
            "horario": None,
            "status": False,
            "ativo": True,
        },
    ]
    usuario = request.user
    sessao = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    sessao_wpp = bool(sessao)

    if request.method == "GET":
        # Criação automática dos horários obrigatórios, se não existirem
        with transaction.atomic():
            for horario_data in HORARIOS_OBRIGATORIOS:
                if not HorarioEnvios.objects.filter(usuario=usuario, tipo_envio=horario_data["tipo_envio"]).exists():
                    novo_horario = HorarioEnvios.objects.create(
                        usuario=usuario,
                        nome=horario_data["nome"],
                        tipo_envio=horario_data["tipo_envio"],
                        horario=horario_data["horario"],
                        status=horario_data["status"],
                        ativo=horario_data["ativo"],
                    )
                    log_user_action(
                        request=request,
                        action=UserActionLog.ACTION_CREATE,
                        instance=novo_horario,
                        message="Horário de envio criado automaticamente.",
                        extra={
                            "tipo_envio": novo_horario.tipo_envio,
                            "status": novo_horario.status,
                            "ativo": novo_horario.ativo,
                        },
                    )
        horarios = HorarioEnvios.objects.filter(usuario=usuario)
        horarios_json = []
        for h in horarios:
            horarios_json.append({
                "id": h.id,
                "nome": h.nome,
                "nome_display": dict(HorarioEnvios.TITULO).get(h.nome, h.nome),
                "tipo_envio": h.tipo_envio,
                "descricao": dict(HorarioEnvios.DESCRICOES).get(h.tipo_envio, ""),
                "exemplo": dict(HorarioEnvios.EXEMPLOS).get(h.tipo_envio, ""),
                "horario": h.horario.strftime("%H:%M") if h.horario else "",
                "status": h.status,
                "ativo": h.ativo,
            })
        return JsonResponse({"horarios": horarios_json, "sessao_wpp": sessao_wpp}, status=200)

    elif request.method == "POST":
        ip_address = request.META.get("REMOTE_ADDR")
        try:
            data = json.loads(request.body)
        except Exception as e:
            logger.exception(
                "JSON inválido ao atualizar horário de envio (user=%s, ip=%s)",
                request.user,
                ip_address,
            )
            return JsonResponse({"error": f"JSON inválido. Detalhe: {e}"}, status=400)

        horario_id = data.get("id")
        if not horario_id:
            logger.warning(
                "Requisição para editar horário sem ID (user=%s, ip=%s)",
                request.user,
                ip_address,
            )
            return JsonResponse({"error": "ID do horário não informado."}, status=400)

        try:
            horario_envio = HorarioEnvios.objects.get(id=horario_id, usuario=usuario)
        except HorarioEnvios.DoesNotExist:
            logger.warning(
                "Horário de envio %s não encontrado para usuário %s (ip=%s)",
                horario_id,
                request.user,
                ip_address,
            )
            return JsonResponse({"error": "Horário não encontrado."}, status=404)

        original_horario = {
            "horario": horario_envio.horario.strftime("%H:%M") if horario_envio.horario else "",
            "status": horario_envio.status,
        }

        # Atualiza campos permitidos
        if "horario" in data:
            horario_str = data["horario"]
            from datetime import time
            try:
                if horario_str:
                    h, m = [int(x) for x in horario_str.split(":")]
                    horario_envio.horario = time(hour=h, minute=m)
                else:
                    horario_envio.horario = None
            except Exception:
                logger.warning(
                    "Formato de horário inválido recebido: %s (user=%s, horario_id=%s, ip=%s)",
                    horario_str,
                    request.user,
                    horario_id,
                    ip_address,
                )
                return JsonResponse({"error": "Horário inválido (use HH:MM)."}, status=400)
        if "status" in data:
            status = data["status"]
            if isinstance(status, str):
                horario_envio.status = status.lower() in ("1", "true", "on")
            else:
                horario_envio.status = bool(status)

        try:
            horario_envio.save()
        except ValidationError as e:
            logger.warning(
                "Erro de validação ao salvar horário %s do usuário %s (ip=%s): %s",
                horario_id,
                request.user,
                ip_address,
                e,
            )
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            logger.exception(
                "Erro inesperado ao salvar horário %s do usuário %s (ip=%s)",
                horario_id,
                request.user,
                ip_address,
            )
            return JsonResponse({"error": "Erro interno ao atualizar horário."}, status=500)

        changes = {}
        novo_horario = horario_envio.horario.strftime("%H:%M") if horario_envio.horario else ""
        if original_horario["horario"] != novo_horario:
            changes["horario"] = (original_horario["horario"], novo_horario)
        if original_horario["status"] != horario_envio.status:
            changes["status"] = (original_horario["status"], horario_envio.status)

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=horario_envio,
            message="Horário de envio atualizado.",
            extra=changes if changes else None,
        )

        return JsonResponse({
            "success": True,
            "message": "Horário atualizado com sucesso.",
            "horario": {
                "id": horario_envio.id,
                "nome": horario_envio.nome,
                "nome_display": dict(HorarioEnvios.TITULO).get(horario_envio.nome, horario_envio.nome),
                "tipo_envio": horario_envio.tipo_envio,
                "descricao": dict(HorarioEnvios.DESCRICOES).get(horario_envio.tipo_envio, ""),
                "exemplo": dict(HorarioEnvios.EXEMPLOS).get(horario_envio.tipo_envio, ""),
                "horario": horario_envio.horario.strftime("%H:%M") if horario_envio.horario else "",
                "status": horario_envio.status,
                "sessao_wpp": sessao_wpp,
            }
        }, status=200)


@login_required
@require_http_methods(["GET", "POST"])
def edit_referral_plan(request):
    PLANOS_OBRIGATORIOS = [
        {"tipo_plano": "desconto", "valor": 0.00, "valor_minimo_mensalidade": 5.00},
        {"tipo_plano": "dinheiro", "valor": 0.00, "valor_minimo_mensalidade": 5.00},
        {"tipo_plano": "anuidade", "valor": 0.00, "valor_minimo_mensalidade": 5.00},
    ]
    usuario = request.user
    sessao = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    sessao_wpp = bool(sessao)

    if request.method == "GET":
        # Criação automática dos planos se não existirem
        ativo = True
        with transaction.atomic():
            for plano_data in PLANOS_OBRIGATORIOS:
                if plano_data["tipo_plano"] == "anuidade":
                    ativo = False
                if not PlanoIndicacao.objects.filter(usuario=usuario, tipo_plano=plano_data["tipo_plano"]).exists():
                    novo_plano = PlanoIndicacao.objects.create(
                        usuario=usuario,
                        nome=plano_data["tipo_plano"],
                        tipo_plano=plano_data["tipo_plano"],
                        valor=Decimal(str(plano_data["valor"])),
                        valor_minimo_mensalidade=Decimal(str(plano_data["valor_minimo_mensalidade"])),
                        status=False,
                        ativo=ativo,
                    )
                    log_user_action(
                        request=request,
                        action=UserActionLog.ACTION_CREATE,
                        instance=novo_plano,
                        message="Plano de indicação criado automaticamente.",
                        extra={
                            "tipo_plano": novo_plano.tipo_plano,
                            "valor": str(novo_plano.valor),
                            "valor_minimo_mensalidade": str(novo_plano.valor_minimo_mensalidade),
                            "status": novo_plano.status,
                            "ativo": novo_plano.ativo,
                        },
                    )

        planos = PlanoIndicacao.objects.filter(usuario=request.user, ativo=True)
        planos_json = []
        for plano in planos:
            planos_json.append({
                "id": plano.id,
                "nome": plano.nome,
                "nome_display": plano.get_nome_display(),
                "tipo_plano": plano.tipo_plano,
                "descricao": plano.descricao,
                "exemplo": plano.exemplo,
                "valor": float(plano.valor),
                "valor_minimo_mensalidade": float(plano.valor_minimo_mensalidade),
                "status": plano.status,
            })

        return JsonResponse({"planos": planos_json, "sessao_wpp": sessao_wpp}, status=200)

    elif request.method == "POST":
        ip_address = request.META.get("REMOTE_ADDR")
        try:
            data = json.loads(request.body)
        except Exception as e:
            logger.exception(
                "JSON inválido ao atualizar plano de indicação (user=%s, ip=%s)",
                request.user,
                ip_address,
            )
            return JsonResponse({"error": f"JSON inválido. Detalhe: {e}"}, status=400)

        plano_id = data.get("id")
        if not plano_id:
            logger.warning(
                "Requisição para editar plano sem ID (user=%s, ip=%s)",
                request.user,
                ip_address,
            )
            return JsonResponse({"error": "ID do plano não informado."}, status=400)

        try:
            plano = PlanoIndicacao.objects.get(id=plano_id, usuario=usuario)
        except PlanoIndicacao.DoesNotExist:
            logger.warning(
                "Plano de indicação %s não encontrado para usuário %s (ip=%s)",
                plano_id,
                request.user,
                ip_address,
            )
            return JsonResponse({"error": "Plano não encontrado."}, status=404)

        original_plano = {
            "valor": str(plano.valor),
            "status": plano.status,
        }

        # Atualiza os campos permitidos
        if "valor" in data:
            try:
                plano.valor = Decimal(str(data["valor"]))
            except (InvalidOperation, ValueError):
                logger.warning(
                    "Valor inválido recebido para plano %s do usuário %s (ip=%s): %s",
                    plano_id,
                    request.user,
                    ip_address,
                    data.get("valor"),
                )
                return JsonResponse({"error": "Valor inválido."}, status=400)
        if "status" in data:
            status = data["status"]
            if isinstance(status, str):
                plano.status = status.lower() in ("1", "true", "on")
            else:
                plano.status = bool(status)

        try:
            plano.save()
        except ValidationError as e:
            logger.warning(
                "Erro de validação ao salvar plano %s do usuário %s (ip=%s): %s",
                plano_id,
                request.user,
                ip_address,
                e,
            )
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            logger.exception(
                "Erro inesperado ao salvar plano %s do usuário %s (ip=%s)",
                plano_id,
                request.user,
                ip_address,
            )
            return JsonResponse({"error": "Erro interno ao atualizar plano."}, status=500)

        changes = {}
        if original_plano["valor"] != str(plano.valor):
            changes["valor"] = (original_plano["valor"], str(plano.valor))
        if original_plano["status"] != plano.status:
            changes["status"] = (original_plano["status"], plano.status)

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=plano,
            message="Plano de indicação atualizado.",
            extra=changes if changes else None,
        )

        return JsonResponse({
            "success": True,
            "message": "Plano atualizado com sucesso.",
            "plano": {
                "id": plano.id,
                "nome": plano.nome,
                "nome_display": plano.get_nome_display(),
                "tipo_plano": plano.tipo_plano,
                "descricao": plano.descricao,
                "exemplo": plano.exemplo,
                "valor": float(plano.valor),
                "valor_minimo_mensalidade": float(plano.valor_minimo_mensalidade),
                "status": plano.status,
                "ativo": plano.ativo,
                "sessao_wpp": sessao_wpp,
            }
        }, status=200)


@login_required
def test(request):
    clientes = Cliente.objects.filter(usuario=request.user)

    return render(
        request,
        'teste.html',
        {
            'clientes': clientes,
        },
    )


############################################ CREATE VIEW ############################################

@require_POST
@login_required
def create_app_account(request):
    app_id = request.POST.get('app_id')
    cliente_id = request.POST.get('cliente-id')

    app = get_object_or_404(Aplicativo, id=app_id, usuario=request.user)
    cliente = get_object_or_404(Cliente, id=cliente_id, usuario=request.user)

    device_id = request.POST.get('device-id') or None
    device_key = request.POST.get('device-key') or None
    app_email = request.POST.get('app-email') or None

    nova_conta_app = ContaDoAplicativo(
        cliente=cliente,
        app=app,
        device_id=device_id,
        device_key=device_key,
        email=app_email,
        usuario=request.user,
    )

    try:
        nova_conta_app.save()
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_CREATE,
            instance=nova_conta_app,
            message="Conta de aplicativo criada.",
            extra={
                "cliente": cliente.nome,
                "app": app.nome,
                "device_id": device_id or '',
                "email": app_email or '',
            },
        )
        return JsonResponse({'success_message_cancel': 'Conta do aplicativo cadastrada com sucesso!'}, status=200)
    except Exception as erro:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META.get('REMOTE_ADDR'), erro, exc_info=True)
        return JsonResponse({'error_message': 'Ocorreu um erro ao tentar realizar o cadastro.'}, status=500)


@login_required
def import_customers(request):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name
    usuario = request.user
    token = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    page_group = 'clientes'
    page = 'importar-clientes'
    success, fail, clientes_existentes, clientes_invalidos_whatsapp, erros_importacao, clientes_criados = 0, 0, [], [], [], {}
    error_message = None

    def clean_cell(row, key):
        valor = row.get(key, None)
        return "" if pd.isnull(valor) or valor is None else str(valor).strip()

    if request.method == "POST" and 'importar' in request.POST:
        arquivo = request.FILES.get('arquivo')
        if not arquivo:
            error_message = "Nenhum arquivo enviado."
        else:
            ext = os.path.splitext(arquivo.name)[1].lower()
            if ext != '.xlsx':
                error_message = "Apenas arquivos .xlsx são suportados."
            else:
                try:
                    dados = pd.read_excel(
                        arquivo,
                        engine='openpyxl',
                        header=2,
                        dtype={
                            "servidor": str,
                            "dispositivo": str,
                            "sistema": str,
                            "device_id": str,
                            "email": str,
                            "device_key": str,
                            "nome": str,
                            "telefone": str,
                            "indicado_por": str,
                            "data_vencimento": str,
                            "forma_pgto": str,
                            "tipo_plano": str,
                            "plano_valor": float,
                            "telas": int,
                            "data_adesao": str
                        }
                    )
                    if "data_adesao" in dados.columns:
                        dados["data_adesao"] = pd.to_datetime(dados["data_adesao"], errors="coerce")
                        dados = dados.sort_values("data_adesao", ascending=True)
                except Exception as e:
                    logger.error("Erro lendo planilha: %s", e, exc_info=True)
                    error_message = "Erro ao ler a planilha. Verifique o arquivo."

        if error_message:
            return render(request, "pages/importar-cliente.html", {
                "error_message": error_message,
                "page_group": page_group, "page": page
            })

        registros = dados.to_dict('records')
        with transaction.atomic():

            # Verifica se o usuário tem uma sessão ativa do WhatsApp
            if not token:
                error_message = (
                    "Você precisa conectar sua conta ao WhatsApp antes de importar clientes. "
                    "Vá até a tela de integração com o WhatsApp e faça a conexão para prosseguir."
                )
                return render(request, "pages/importar-cliente.html", {
                    "error_message": error_message,
                    "page_group": page_group,
                    "page": page,
                })
            
            # 1º loop: salva todos os clientes sem indicado_por
            for idx, row in enumerate(registros, 1):
                try:
                    print(f"[{timestamp}] [{func_name}] [{usuario}] [IMPORT] Processando linha {idx} - dados: {row}")
                    servidor_nome = clean_cell(row, 'servidor')
                    dispositivo_nome = clean_cell(row, 'dispositivo')
                    sistema_nome = clean_cell(row, 'sistema')
                    device_id = clean_cell(row, 'device_id')
                    email = clean_cell(row, 'email')
                    senha = clean_cell(row, 'device_key')
                    nome = clean_cell(row, 'nome')
                    telefone = clean_cell(row, 'telefone')
                    data_vencimento_str = clean_cell(row, 'data_vencimento')
                    forma_pgto_nome = clean_cell(row, 'forma_pgto')
                    plano_nome = clean_cell(row, 'tipo_plano')
                    plano_valor = clean_cell(row, 'plano_valor')
                    plano_telas = clean_cell(row, 'telas')
                    data_adesao_str = clean_cell(row, 'data_adesao')

                    # Valida obrigatórios
                    if not all([servidor_nome, dispositivo_nome, sistema_nome, nome, telefone, data_vencimento_str, forma_pgto_nome, plano_nome, plano_valor, plano_telas, data_adesao_str]):
                        fail += 1
                        erros_importacao.append(f"Linha {idx}: campos obrigatórios em branco")
                        continue

                    # 1. Validação de telefone
                    resultado_telefone = validar_tel_whatsapp(telefone, token.token, request.user)
                    if not resultado_telefone.get("wpp"):
                        fail += 1
                        clientes_invalidos_whatsapp.append(f"Linha {idx}: {telefone} (número não existe no WhatsApp)")
                        continue
                    if not resultado_telefone.get("telefone_validado_wpp"):
                        fail += 1
                        clientes_invalidos_whatsapp.append(f"Linha {idx}: {telefone} (não foi possível validar o telefone para WhatsApp)")
                        continue
                    if resultado_telefone.get("cliente_existe_telefone"):
                        fail += 1
                        clientes_existentes.append(f"Linha {idx}: {telefone} (já existe cliente com esse telefone)")
                        continue
                    if resultado_telefone.get("telefone_validado_wpp"):
                        telefone = resultado_telefone.get("telefone_validado_wpp")

                    # Valida se o plano informado é um dos permitidos
                    planos_validos = [plano[0] for plano in Plano.CHOICES]
                    if plano_nome not in planos_validos:
                        fail += 1
                        erros_importacao.append(f"Linha {idx}: plano '{plano_nome}' inválido. Deve ser um dos: {', '.join(planos_validos)}.")
                        continue

                    # Parse plano_valor
                    try:
                        plano_valor = float(str(plano_valor).replace(",", "."))
                    except Exception:
                        fail += 1
                        erros_importacao.append(f"Linha {idx}: valor do plano inválido.")
                        continue

                    # Parse de plano_telas
                    try:
                        plano_telas = int(plano_telas)
                    except Exception:
                        fail += 1
                        erros_importacao.append(f"Linha {idx}: quantidade de telas inválida.")
                        continue

                    # Parse datas
                    data_vencimento = None
                    if data_vencimento_str:
                        try:
                            if len(data_vencimento_str) > 10:
                                data_vencimento = datetime.strptime(data_vencimento_str, "%Y-%m-%d %H:%M:%S").date()
                            else:
                                data_vencimento = datetime.strptime(data_vencimento_str, "%Y-%m-%d").date()
                        except Exception:
                            fail += 1
                            erros_importacao.append(f"Linha {idx}: data de vencimento inválida.")
                            continue
                    try:
                        if len(data_adesao_str) > 10:
                            data_adesao = datetime.strptime(data_adesao_str, "%Y-%m-%d %H:%M:%S").date()
                        else:
                            data_adesao = datetime.strptime(data_adesao_str, "%Y-%m-%d").date()
                    except Exception:
                        fail += 1
                        erros_importacao.append(f"Linha {idx}: data de adesão inválida.")
                        continue

                    # Validar e-mail
                    try:
                        if email:
                            validate_email(email)
                    except ValidationError:
                        erros_importacao.append(f"Linha {idx}: E-mail inválido.")
                        continue

                    # Objetos relacionados
                    plano, _ = Plano.objects.get_or_create(nome=plano_nome, telas=plano_telas, valor=plano_valor, usuario=usuario)
                    sistema, _ = Aplicativo.objects.get_or_create(nome=sistema_nome, usuario=usuario)
                    servidor, _ = Servidor.objects.get_or_create(nome=servidor_nome, usuario=usuario)
                    forma_pgto, _ = Tipos_pgto.objects.get_or_create(nome=forma_pgto_nome, usuario=usuario)
                    dispositivo, _ = Dispositivo.objects.get_or_create(nome=dispositivo_nome, usuario=usuario)

                    # Salva cliente sem indicado_por
                    cliente = Cliente(
                        nome=nome,
                        telefone=telefone,
                        dispositivo=dispositivo,
                        sistema=sistema,
                        servidor=servidor,
                        forma_pgto=forma_pgto,
                        plano=plano,
                        data_vencimento=data_vencimento,
                        data_adesao=data_adesao,
                        usuario=usuario,
                    )
                    cliente.save()
                    clientes_criados[telefone] = cliente

                    # Conta do App se aplicável
                    if device_id or email:
                        device_id = re.sub(r'[^A-Fa-f0-9]', '', device_id or '')
                        if all(device_id):
                            ContaDoAplicativo.objects.create(
                                device_id=device_id,
                                email=email,
                                device_key=senha,
                                app=sistema,
                                cliente=cliente,
                                usuario=usuario,
                            )

                    try:
                        Mensalidade.objects.create(
                            cliente=cliente,
                            valor=plano_valor,
                            dt_vencimento = data_vencimento,
                            usuario=usuario
                        )
                    except Exception as e:
                        logger.error(f"Erro ao criar mensalidade: {e}", exc_info=True)

                    success += 1
                except Exception as e:
                    fail += 1
                    logger.error(f"Falha ao importar linha {idx}: {e}", exc_info=True)
                    erros_importacao.append(f"Linha {idx}: {e}")

            # 2º loop: associa indicador
            for idx, row in enumerate(registros, 1):
                telefone = clean_cell(row, 'telefone')
                indicador_raw = clean_cell(row, 'indicado_por')
                try:
                    if indicador_raw:
                        indicador = clientes_criados.get(indicador_raw) or Cliente.objects.filter(telefone='+' + indicador_raw, usuario=usuario).first()
                        if indicador:
                            Cliente.objects.filter(telefone='+' + telefone, usuario=usuario).update(indicado_por=indicador)
                except Exception as e:
                    fail += 1
                    erros_importacao.append(f"Linha {idx}: Não foi possível fazer associado do Indicador ({telefone}) com o Cliente ({indicador_raw}).")
                    continue
                
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_IMPORT,
            entity="Cliente",
            message="Importação de clientes concluída.",
            extra={
                "sucesso": success,
                "falhas": fail,
                "clientes_existentes": len(clientes_existentes),
                "clientes_invalidos_whatsapp": len(clientes_invalidos_whatsapp),
                "erros_registrados": len(erros_importacao),
            },
        )
        return render(request, "pages/importar-cliente.html", {
            "success_message": "Importação concluída!",
            "num_linhas_importadas": success,
            "num_linhas_nao_importadas": fail,
            "nomes_clientes_existentes": clientes_existentes,
            "nomes_clientes_erro_importacao": erros_importacao,
            "clientes_invalidos_whatsapp": clientes_invalidos_whatsapp,
            "page_group": page_group,
            "page": page,
        })

    return render(request, "pages/importar-cliente.html", {"page_group": page_group, "page": page})


# AÇÃO PARA CRIAR NOVO CLIENTE ATRAVÉS DO FORMULÁRIO
@login_required
def create_customer(request):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name
    usuario = request.user
    token = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
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
        
        # Verifica se o usuário tem uma sessão ativa do WhatsApp
        if not token:
            return render(request, "pages/cadastro-cliente.html", {
                'error_message': (
                    "Você precisa conectar sua conta ao WhatsApp antes de cadastrar um cliente.<br>"
                    "Vá até a tela de integração com o WhatsApp e faça a conexão para prosseguir."
                ),
                'servidores': servidor_queryset,
                'dispositivos': dispositivo_queryset,
                'sistemas': sistema_queryset,
                'indicadores': indicador_por_queryset,
                'formas_pgtos': forma_pgto_queryset,
                'planos': plano_queryset,
                'page_group': page_group,
                'page': page,
            })

        # Coleta e sanitiza dados do formulário
        post = request.POST
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

        print(f"[{timestamp}] [INFO] [{func_name}] [{usuario}] Iniciando cadastro de Novo Cliente.")
        resultado_wpp = validar_tel_whatsapp(telefone, token.token, user=usuario)
        # Verifica se o número possui WhatsApp (antes de qualquer validação de duplicidade)
        if not resultado_wpp.get("wpp"):
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": (
                    "O telefone informado não possui um WhatsApp.<br>"
                    "Cada novo cliente precisa estar cadastrado no WhatsApp."
                ),
            })

        # Se cliente existe com o telefone recebido, retorna os erros conforme cada possibilidade
        if resultado_wpp.get("cliente_existe_telefone"):
            telefone = resultado_wpp.get("cliente_existe_telefone")
            cliente_existente = None

            try:
                cliente_existente = Cliente.objects.filter(telefone=telefone, usuario=usuario).first()
                if cliente_existente:
                    logger.warning(
                        f"[ERRO][CADASTRO CLIENTE] Já existe cliente para telefone {cliente_existente.telefone} (ID: {cliente_existente.id})"
                    )
                    return render(request, "pages/cadastro-cliente.html", {
                        "error_message": (
                            "Há um cliente cadastrado com o telefone informado! <br><br>"
                            f"<strong>Nome:</strong> {cliente_existente.nome} <br>"
                            f"<strong>Telefone:</strong> {cliente_existente.telefone}"
                        ),
                    })
                else:
                    logger.error(
                        f"[ERRO][CADASTRO CLIENTE] resultado_wpp apontou cliente_existe=True, mas nenhum cliente foi localizado no banco para telefone {telefone}"
                    )
                    return render(request, "pages/cadastro-cliente.html", {
                        "error_message": (
                            "Erro inesperado ao validar telefone existente.<br>"
                            "Por favor, tente novamente em poucos instantes ou contate o suporte."
                        ),
                    })
            except Exception as e:
                logger.exception(
                    f"[ERRO][CADASTRO CLIENTE] Erro ao buscar cliente existente para telefone(s) {telefone}: {e}"
                )
                return render(request, "pages/cadastro-cliente.html", {
                    "error_message": (
                        "Ocorreu um erro inesperado ao tentar verificar o número de telefone.<br>"
                        "Por favor, tente novamente ou contate o suporte."
                    ),
                })
            
        # Obtém o telefone validado com WhatsApp
        if resultado_wpp.get("telefone_validado_wpp"):
            telefone = resultado_wpp.get("telefone_validado_wpp")

        # Trata indicador (pode ser nulo)
        indicador = None
        if indicador_nome:
            indicador = Cliente.objects.filter(nome=indicador_nome, usuario=usuario).first()

        # Trata plano
        try:
            plano_nome = plano_info[0]
            plano_valor = float(plano_info[1].replace(',', '.'))
            plano_telas = plano_info[2]
        except (IndexError, ValueError):
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": "Plano inválido.",
            })
        plano, _ = Plano.objects.get_or_create(nome=plano_nome, valor=plano_valor, telas=plano_telas, usuario=usuario)

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

        try:
            with transaction.atomic():
                # SALVAR CLIENTE
                try:
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
                    cliente.save()
                except Exception as e:
                    logger.error("Erro ao salvar o cliente: %s", e, exc_info=True)
                    raise Exception("Falha ao salvar os dados do cliente.")

                # CRIAR CONTA DO APLICATIVO
                if sistema.device_has_mac:
                    try:
                        device_id = post.get('id', '')
                        email = post.get('email', '')
                        senha = post.get('senha', '')

                        ContaDoAplicativo.objects.create(
                            device_id=device_id,
                            email=email,
                            device_key=senha,
                            app=sistema,
                            cliente=cliente,
                            usuario=usuario,
                        )
                    except Exception as e:
                        logger.error("Erro ao criar ContaDoAplicativo: %s", e, exc_info=True)
                        raise Exception("Falha ao criar a conta do aplicativo.<p>Algum dos dados não pôde ser salvo.</p>")

                # ENVIO DE MENSAGEM
                try:
                    envio_apos_novo_cadastro(cliente)
                except Exception as e:
                    logger.error("Erro ao enviar mensagem para o cliente: %s", e, exc_info=True)
                    raise Exception("Erro ao realizar cadastro!<p>Talvez você ainda não tenha conectado a sessão do WhatsApp.</p>")

                # CRIAÇÃO DE MENSALIDADE
                try:
                    criar_mensalidade(cliente)
                except Exception as e:
                    logger.error("Erro ao criar a mensalidade: %s", e, exc_info=True)
                    raise Exception("Falha ao criar a mensalidade do cliente.")

            print(f"[{timestamp}] [SUCCESS] [{func_name}] [{usuario}] Cliente {cliente.nome} ({cliente.telefone}) cadastrado com sucesso!")
            log_user_action(
                request=request,
                action=UserActionLog.ACTION_CREATE,
                instance=cliente,
                message="Cliente criado.",
                extra={
                    "telefone": cliente.telefone,
                    "plano": getattr(cliente.plano, 'nome', ''),
                    "servidor": getattr(cliente.servidor, 'nome', ''),
                    "forma_pgto": getattr(cliente.forma_pgto, 'nome', ''),
                    "data_vencimento": cliente.data_vencimento.strftime('%Y-%m-%d') if cliente.data_vencimento else '',
                },
            )
            return render(request, "pages/cadastro-cliente.html", {
                "success_message": "Novo cliente cadastrado com sucesso!",
            })

        except Exception as e:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]',
                        timezone.localtime(), usuario, request.META.get('REMOTE_ADDR', 'IP não identificado'), e, exc_info=True)
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": str(e),
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
                    log_user_action(
                        request=request,
                        action=UserActionLog.ACTION_CREATE,
                        instance=plano,
                        message="Plano de adesao criado.",
                        extra={
                            "nome": plano.nome,
                            "valor": str(plano.valor),
                            "telas": plano.telas,
                        },
                    )
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
                    log_user_action(
                        request=request,
                        action=UserActionLog.ACTION_CREATE,
                        instance=servidor,
                        message="Servidor criado.",
                        extra={
                            "nome": servidor.nome,
                        },
                    )
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
                    log_user_action(
                        request=request,
                        action=UserActionLog.ACTION_CREATE,
                        instance=formapgto,
                        message="Forma de pagamento criada.",
                        extra={
                            "nome": formapgto.nome,
                        },
                    )
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
                    log_user_action(
                        request=request,
                        action=UserActionLog.ACTION_CREATE,
                        instance=dispositivo,
                        message="Dispositivo criado.",
                        extra={
                            "nome": dispositivo.nome,
                        },
                    )
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
                    log_user_action(
                        request=request,
                        action=UserActionLog.ACTION_CREATE,
                        instance=aplicativo,
                        message="Aplicativo criado.",
                        extra={
                            "nome": aplicativo.nome,
                            "device_has_mac": aplicativo.device_has_mac,
                        },
                    )
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
            log_extra = {
                "id": conta_app.id,
                "cliente": conta_app.cliente_id,
                "app": conta_app.app_id,
                "device_id": conta_app.device_id or "",
                "email": conta_app.email or "",
            }
            conta_app.delete()
            log_user_action(
                request=request,
                action=UserActionLog.ACTION_DELETE,
                instance=conta_app,
                message="Conta de aplicativo removida.",
                extra=log_extra,
            )

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
        log_extra = {"id": aplicativo.id, "nome": aplicativo.nome}
        aplicativo.delete()
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_DELETE,
            instance=aplicativo,
            message="Aplicativo removido.",
            extra=log_extra,
        )
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
        log_extra = {"id": dispositivo.id, "nome": dispositivo.nome}
        dispositivo.delete()
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_DELETE,
            instance=dispositivo,
            message="Dispositivo removido.",
            extra=log_extra,
        )
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
        log_extra = {"id": formapgto.id, "nome": formapgto.nome}
        formapgto.delete()
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_DELETE,
            instance=formapgto,
            message="Forma de pagamento removida.",
            extra=log_extra,
        )
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
        log_extra = {"id": servidor.id, "nome": servidor.nome}
        servidor.delete()
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_DELETE,
            instance=servidor,
            message="Servidor removido.",
            extra=log_extra,
        )
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
        log_extra = {"id": plano_mensal.id, "nome": plano_mensal.nome}
        plano_mensal.delete()
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_DELETE,
            instance=plano_mensal,
            message="Plano removido.",
            extra=log_extra,
        )
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
        response = requests.get(f'https://ipapi.co/{ip}/json/', timeout=5)
        data = response.json()
        cidade = data.get('city', 'Desconhecida')
        pais = data.get('country_name', 'Desconhecido')
        return f"{cidade}, {pais}"
    except Exception:
        return "Localização desconhecida"
















