"""Views responsáveis por dashboards, cadastros e integrações do painel."""

import base64
from .email_utils import (
    send_profile_change_notification,
    send_password_change_notification,
    send_login_notification,
    send_2fa_enabled_notification
)
import codecs
import io
import json
import logging
import operator
import os
import random
import re
import requests
import threading
import time
import unicodedata
from pathlib import Path
from django.db.models import Sum, Q, Count, F, ExpressionWrapper, DurationField, Exists, OuterRef, Min, Prefetch
from django.db.models.functions import Upper, Coalesce, ExtractDay, Trim
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.cache import cache_page, never_cache
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models.functions import ExtractMonth, ExtractYear
from django.views.decorators.http import require_http_methods, require_GET
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
from .models import (
    Cliente, Servidor, Dispositivo,
    Aplicativo, Tipos_pgto, Plano,
    Mensalidade, ContaDoAplicativo,
    SessaoWpp, SecretTokenAPI,
    DadosBancarios, MensagemEnviadaWpp,
    DominiosDNS, PlanoIndicacao,
    HorarioEnvios, NotificationRead,
    UserActionLog, ClientePlanoHistorico,
    ContaReseller, TarefaMigracaoDNS,
    DispositivoMigracaoDNS
)
from .utils import (
    envio_apos_novo_cadastro,
    validar_tel_whatsapp,
    criar_mensalidade,
    log_user_action,
    historico_iniciar,
    historico_encerrar_vigente,
    get_client_ip,
    extrair_dominio_de_url,
    calcular_valor_mensalidade,
)
from .wpp_views import (
    cancelar_sessao_wpp,
    check_connection_wpp,
    conectar_wpp,
    desconectar_wpp,
    status_wpp,
    whatsapp,
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
MESES_31_DIAS = [1, 3, 5, 7, 8, 10, 12]

warnings.filterwarnings(
    "ignore", message="errors='ignore' is deprecated", category=FutureWarning
)
logger = logging.getLogger(__name__)
url_api = os.getenv("URL_API_WPP")

class StaffRequiredMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_staff or user.is_superuser)

############################################ AUTH VIEW ############################################

# PÁGINA DE LOGIN
class Login(LoginView):
    template_name = 'login.html'
    form_class = LoginForm
    redirect_authenticated_user = True
    success_url = 'dashboard/'

    def form_valid(self, form):
        """Override to check for 2FA before logging in."""
        from .models import UserProfile
        from django.contrib.auth import authenticate

        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')

        logger.info(f'[LOGIN] Attempting login for user: {username}')

        # Authenticate user (but don't log in yet)
        user = authenticate(self.request, username=username, password=password)

        if user is None:
            logger.warning(f'[LOGIN] Authentication failed for user: {username}')
            return super().form_invalid(form)

        logger.info(f'[LOGIN] Authentication successful for user: {username} (ID: {user.id})')

        # Check if user has 2FA enabled
        try:
            profile = UserProfile.objects.get(user=user)
            logger.info(f'[LOGIN] UserProfile found. 2FA enabled: {profile.two_factor_enabled}, Secret exists: {bool(profile.two_factor_secret)}')

            if profile.two_factor_enabled and profile.two_factor_secret:
                # Store user_id in session for 2FA verification
                self.request.session['pending_2fa_user_id'] = user.id
                self.request.session['pending_2fa_username'] = user.username

                # ✅ SEGURANÇA: Armazenar dados de validação para prevenir session fixation
                from django.utils import timezone
                self.request.session['pending_2fa_timestamp'] = timezone.now().isoformat()
                self.request.session['pending_2fa_ip'] = self.request.META.get('REMOTE_ADDR', '')
                self.request.session['pending_2fa_user_agent'] = self.request.META.get('HTTP_USER_AGENT', '')[:200]

                # Force session save to ensure data persists
                self.request.session.modified = True
                self.request.session.save()

                logger.info(f'[LOGIN] 2FA required for user {user.id}. Session data saved. Redirecting to verify-2fa')
                logger.info(f'[LOGIN] Session key: {self.request.session.session_key}')
                logger.info(f'[LOGIN] Session data: pending_2fa_user_id={user.id}, pending_2fa_username={user.username}')

                return redirect('verify-2fa')
        except UserProfile.DoesNotExist:
            logger.warning(f'[LOGIN] UserProfile not found for user {user.id}. Proceeding without 2FA check.')
            pass

        # No 2FA or not enabled, proceed with normal login
        logger.info(f'[LOGIN] No 2FA required. Proceeding with normal login for user {user.id}')
        return super().form_valid(form)


from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='5/m', method='POST', block=True)
@require_http_methods(["GET", "POST"])
def verify_2fa_code(request):
    """Verify 2FA code and complete login.

    Rate limiting: 5 tentativas por minuto por IP.
    Após 5 tentativas falhadas, o IP é bloqueado por 1 minuto.
    """
    from .models import UserProfile
    from django.contrib.auth import login, get_user_model
    from django_ratelimit.exceptions import Ratelimited

    # Verificar se foi bloqueado por rate limiting
    was_limited = getattr(request, 'limited', False)
    if was_limited:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
        logger.warning(f'[2FA_RATELIMIT] Rate limit exceeded for IP {ip}')
        messages.error(request, 'Muitas tentativas de verificação. Aguarde 1 minuto e tente novamente.')
        return render(request, 'login_2fa.html', {'rate_limited': True})

    logger.info(f'[2FA_VERIFY] Accessed verify_2fa_code view. Method: {request.method}')
    logger.info(f'[2FA_VERIFY] Session key: {request.session.session_key}')
    logger.info(f'[2FA_VERIFY] Session data: {dict(request.session.items())}')

    # Check if there's a pending 2FA verification
    user_id = request.session.get('pending_2fa_user_id')
    username = request.session.get('pending_2fa_username')
    timestamp_str = request.session.get('pending_2fa_timestamp')
    stored_ip = request.session.get('pending_2fa_ip')
    stored_ua = request.session.get('pending_2fa_user_agent')

    logger.info(f'[2FA_VERIFY] Retrieved from session - user_id: {user_id}, username: {username}')

    # ✅ SEGURANÇA: Validação 1 - Dados existem
    if not all([user_id, username, timestamp_str]):
        logger.warning('[2FA_SECURITY] Missing session data (user_id, username, or timestamp)')
        messages.error(request, 'Sessão inválida. Faça login novamente.')
        request.session.flush()
        return redirect('login')

    # ✅ SEGURANÇA: Validação 2 - Timeout de 5 minutos
    from django.utils import timezone
    from datetime import timedelta, datetime
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        if timezone.now() - timestamp > timedelta(minutes=5):
            logger.warning(f'[2FA_SECURITY] Session expired for user {user_id} (timeout > 5 min)')
            # ✅ SEGURANÇA: Mensagem genérica para não revelar motivo específico
            messages.error(request, 'Sessão inválida. Faça login novamente.')
            request.session.flush()
            return redirect('login')
    except (ValueError, TypeError) as e:
        logger.error(f'[2FA_SECURITY] Invalid timestamp format: {timestamp_str} - {e}')
        messages.error(request, 'Sessão inválida. Faça login novamente.')
        request.session.flush()
        return redirect('login')

    # ✅ SEGURANÇA: Validação 3 - IP não mudou
    current_ip = request.META.get('REMOTE_ADDR', '')
    if stored_ip and current_ip != stored_ip:
        logger.warning(f'[2FA_SECURITY] IP mismatch for user {user_id}: {stored_ip} != {current_ip}')
        # ✅ SEGURANÇA: Mensagem genérica para não revelar motivo específico
        messages.error(request, 'Sessão inválida. Faça login novamente.')
        request.session.flush()
        return redirect('login')

    # ✅ SEGURANÇA: Validação 4 - User-Agent não mudou (warning only)
    current_ua = request.META.get('HTTP_USER_AGENT', '')[:200]
    if stored_ua and current_ua != stored_ua:
        logger.warning(f'[2FA_SECURITY] User-Agent mismatch for user {user_id}')
        # Não bloqueia, apenas registra (pode ser legítimo)

    User = get_user_model()

    try:
        user = User.objects.get(id=user_id)
        profile = UserProfile.objects.get(user=user)
        logger.info(f'[2FA_VERIFY] User found: {user.username} (ID: {user.id})')
    except (User.DoesNotExist, UserProfile.DoesNotExist) as e:
        logger.error(f'[2FA_VERIFY] User or profile not found for user_id {user_id}: {str(e)}')
        # ✅ SEGURANÇA: Mensagem genérica para não revelar existência do usuário
        messages.error(request, 'Sessão inválida. Faça login novamente.')
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        logger.info(f'[2FA_VERIFY] POST request - processing 2FA code verification')
        code = request.POST.get('code', '').strip()

        if not code:
            messages.error(request, 'Digite o código de verificação.')
            return render(request, 'login_2fa.html')

        # Verify code
        if profile.verify_2fa_code(code):
            # Code is valid, complete login
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')

            # ✅ SEGURANÇA: Regenerar session ID para prevenir session fixation
            request.session.cycle_key()

            # ✅ SEGURANÇA: Limpar dados temporários de 2FA
            request.session.pop('pending_2fa_user_id', None)
            request.session.pop('pending_2fa_username', None)
            request.session.pop('pending_2fa_timestamp', None)
            request.session.pop('pending_2fa_ip', None)
            request.session.pop('pending_2fa_user_agent', None)

            # Log de segurança para login bem-sucedido
            ip = request.META.get('REMOTE_ADDR', 'unknown')
            security_logger = logging.getLogger('security')
            security_logger.info(
                f'[2FA_SUCCESS] Successful 2FA login | '
                f'User: {user.username} (ID: {user.id}) | '
                f'IP: {ip}'
            )

            # Send login notification if enabled
            try:
                if profile.email_on_login:
                    ip_address = get_client_ip(request) or 'Desconhecido'
                    send_login_notification(user, ip_address=ip_address, user_agent=request.META.get('HTTP_USER_AGENT', 'Desconhecido'))
            except Exception as e:
                logger.warning(f'[2FA_LOGIN] Email notification failed for user {user.id}: {str(e)}')

            messages.success(request, f'Bem-vindo, {user.first_name or user.username}!')
            return redirect('dashboard')
        else:
            # Check if it's a backup code
            if profile.use_backup_code(code):
                # Backup code is valid, complete login
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')

                # ✅ SEGURANÇA: Regenerar session ID para prevenir session fixation
                request.session.cycle_key()

                # Set flag for LoginLog signal to detect backup code usage
                request.session['backup_code_used'] = True

                # ✅ SEGURANÇA: Limpar dados temporários de 2FA
                request.session.pop('pending_2fa_user_id', None)
                request.session.pop('pending_2fa_username', None)
                request.session.pop('pending_2fa_timestamp', None)
                request.session.pop('pending_2fa_ip', None)
                request.session.pop('pending_2fa_user_agent', None)

                # Log de segurança para uso de backup code (importante para auditoria)
                ip = request.META.get('REMOTE_ADDR', 'unknown')
                security_logger = logging.getLogger('security')
                security_logger.warning(
                    f'[2FA_BACKUP_CODE] Backup code used for login | '
                    f'User: {user.username} (ID: {user.id}) | '
                    f'IP: {ip} | '
                    f'Remaining backup codes: {len(profile.two_factor_backup_codes)}'
                )

                # Send login notification if enabled
                try:
                    if profile.email_on_login:
                        ip_address = get_client_ip(request) or 'Desconhecido'
                        send_login_notification(user, ip_address=ip_address, user_agent=request.META.get('HTTP_USER_AGENT', 'Desconhecido'))
                except Exception as e:
                    logger.warning(f'[2FA_LOGIN] Email notification failed for user {user.id}: {str(e)}')

                messages.warning(request, 'Login realizado com código de backup. Considere regenerar seus códigos.')
                return redirect('dashboard')
            else:
                # Log de segurança para tentativa falhada
                ip = request.META.get('REMOTE_ADDR', 'unknown')
                user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
                security_logger = logging.getLogger('security')
                security_logger.warning(
                    f'[2FA_FAILED] Invalid 2FA code attempt | '
                    f'User: {user.username} (ID: {user.id}) | '
                    f'IP: {ip} | '
                    f'User-Agent: {user_agent}'
                )
                messages.error(request, 'Código inválido. Tente novamente.')
                return render(request, 'login_2fa.html')

    # GET request, show 2FA form
    logger.info(f'[2FA_VERIFY] GET request - rendering 2FA form for user: {username}')
    return render(request, 'login_2fa.html')

# PÁGINA DE ERRO 404
def not_found(request, exception):
    """Renderiza a página 404 personalizada utilizada em diversos entrypoints."""
    return render(request, 'pages/404-error.html')

############################################ LIST VIEW ############################################

class CarregarContasDoAplicativo(LoginRequiredMixin, View):
    """Retorna as contas de aplicativo associadas a um cliente para exibição no modal."""

    def get(self, request):
        """Lista contas do cliente autenticado já serializadas para o modal."""
        cliente_id = self.request.GET.get("cliente_id")
        cliente = get_object_or_404(Cliente, id=cliente_id, usuario=self.request.user)
        conta_app = (
            ContaDoAplicativo.objects.filter(cliente=cliente, usuario=self.request.user)
            .select_related('app', 'dispositivo', 'cliente__dispositivo')
        )

        conta_app_json = []

        for conta in conta_app:
            nome_aplicativo = conta.app.nome
            nome_dispositivo = (
                conta.dispositivo.nome if conta.dispositivo
                else (conta.cliente.dispositivo.nome if conta.cliente.dispositivo
                else 'Não especificado')
            )
            conta_json = model_to_dict(conta)
            conta_json['nome_aplicativo'] = nome_aplicativo
            conta_json['nome_dispositivo'] = nome_dispositivo
            conta_json['logo_url'] = conta.app.get_logo_url()
            conta_app_json.append(conta_json)

        conta_app_json = sorted(conta_app_json, key=operator.itemgetter('nome_aplicativo'))

        return JsonResponse({"conta_app": conta_app_json}, safe=False)


class CarregarQuantidadesMensalidades(LoginRequiredMixin, View):
    """Expõe um resumo de mensalidades (pagas, pendentes e canceladas) no modal do cliente."""

    def get(self, request):
        """Calcula as contagens por status e devolve um payload JSON para o modal."""
        cliente_id = self.request.GET.get("cliente_id")
        cliente = get_object_or_404(Cliente, id=cliente_id, usuario=self.request.user)
        hoje = timezone.localtime().date()
        mensalidades_totais = Mensalidade.objects.filter(
            usuario=self.request.user,
            cliente=cliente
        ).select_related('cliente__assinatura').order_by('-id').values(
            'id', 'dt_vencimento', 'dt_pagamento', 'valor', 'pgto', 'cancelado',
            'cliente__assinatura__em_campanha',
            # ⭐ FASE 2.5: Novos campos de rastreamento de campanhas
            'gerada_em_campanha',
            'dados_historicos_verificados',
            'valor_base_plano',
            'desconto_campanha',
            'desconto_progressivo',
            'tipo_campanha',
            'numero_mes_campanha'
        )
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
        from cadastros.utils import calcular_desconto_progressivo_total
        from .models import DescontoProgressivoIndicacao

        cliente_id = self.request.GET.get("cliente_id")
        cliente = get_object_or_404(Cliente, id=cliente_id, usuario=self.request.user)
        indicados = Cliente.objects.filter(indicado_por=cliente, usuario=self.request.user).order_by('-id')

        # Calcular informações sobre descontos progressivos
        desconto_info = calcular_desconto_progressivo_total(cliente)

        # Buscar quais indicados geram desconto ativo
        descontos_ativos_ids = set()
        if desconto_info["qtd_descontos_ativos"] > 0:
            descontos_ativos = DescontoProgressivoIndicacao.objects.filter(
                cliente_indicador=cliente,
                ativo=True
            ).values_list('cliente_indicado_id', flat=True)
            descontos_ativos_ids = set(descontos_ativos)

        # Converter indicados para dicionários e adicionar flag de desconto
        indicados_list = []
        for indicado in indicados:
            indicado_dict = {
                'id': indicado.id,
                'nome': indicado.nome,
                'data_adesao': indicado.data_adesao.strftime('%Y-%m-%d') if indicado.data_adesao else None,
                'cancelado': indicado.cancelado,
                'tem_desconto_ativo': indicado.id in descontos_ativos_ids,
            }
            indicados_list.append(indicado_dict)

        data = {
            'indicacoes': indicados_list,
            'desconto_progressivo': {
                'ativo': desconto_info["plano"] is not None and desconto_info["plano"].status,
                'valor_total': float(desconto_info["valor_total"]),
                'qtd_descontos_ativos': desconto_info["qtd_descontos_ativos"],
                'qtd_descontos_aplicados': desconto_info["qtd_descontos_aplicados"],
                'limite_indicacoes': desconto_info["limite_indicacoes"],
            }
        }

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

        # Adiciona dispositivos e aplicativos para o modal de edição
        dispositivos = Dispositivo.objects.all()
        aplicativos = Aplicativo.objects.all()

        # Serializa para JSON (para uso no JavaScript)
        dispositivos_json = [
            {'id': d.id, 'nome': d.nome}
            for d in dispositivos
        ]
        aplicativos_json = [
            {'id': a.id, 'nome': a.nome, 'device_has_mac': a.device_has_mac}
            for a in aplicativos
        ]

        context.update(
            {
                "range": range_num,
                "page_group": page_group,
                "page": page,
                "dispositivos": dispositivos,
                "aplicativos": aplicativos,
                "dispositivos_json": json.dumps(dispositivos_json),
                "aplicativos_json": json.dumps(aplicativos_json),
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
            Cliente.objects
            .select_related('dispositivo', 'sistema', 'servidor', 'forma_pgto', 'plano')
            .annotate(
                contas_count=Count('conta_aplicativo', distinct=True)
            )
            .prefetch_related(
                Prefetch(
                    'conta_aplicativo',
                    queryset=ContaDoAplicativo.objects.select_related('dispositivo', 'app'),
                    to_attr='contas_list'
                ),
                Prefetch(
                    'mensalidade_set',
                    queryset=Mensalidade.objects.filter(
                        cancelado=False,
                        dt_cancelamento=None,
                        dt_pagamento=None,
                        pgto=False
                    )
                )
            )
            .filter(cancelado=False).filter(
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
            Cliente.objects
            .select_related('dispositivo', 'sistema', 'servidor', 'forma_pgto', 'plano')
            .annotate(
                contas_count=Count('conta_aplicativo', distinct=True)
            )
            .prefetch_related(
                Prefetch(
                    'conta_aplicativo',
                    queryset=ContaDoAplicativo.objects.select_related('dispositivo', 'app'),
                    to_attr='contas_list'
                ),
                Prefetch(
                    'mensalidade_set',
                    queryset=Mensalidade.objects.filter(
                        cancelado=False,
                        dt_cancelamento=None,
                        dt_pagamento=None,
                        pgto=False
                    )
                )
            )
            .filter(cancelado=False).filter(
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

        # Serializa dispositivos e aplicativos para JSON (para uso no JavaScript do modal de edição)
        dispositivos_json = [
            {'id': d.id, 'nome': d.nome}
            for d in dispositivos
        ]
        aplicativos_json = [
            {'id': a.id, 'nome': a.nome, 'device_has_mac': a.device_has_mac}
            for a in aplicativos
        ]

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
                "dispositivos_json": json.dumps(dispositivos_json),
                "aplicativos_json": json.dumps(aplicativos_json),
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
    """
    Envia mensagens WhatsApp em massa via WPPConnect API.

    Funcionalidades:
    - Validação robusta via Django Form
    - Sistema de controle via session (pausar/retomar)
    - Mascaramento de telefones nos logs de arquivo
    - Delay incremental (> 200 envios/dia = +10s)
    - Timeout e retry em requests HTTP
    - Registro em UserActionLog
    - Sleep interruptível (parada em ~2s)
    - Constraint UNIQUE previne duplicatas
    - PROCESSAMENTO EM BACKGROUND (threading) para logs em tempo real

    SEGURANÇA:
    - CSRF protected
    - Validação de inputs (XSS, injection, DoS)
    - Path traversal prevention nos logs
    - Rate limiting via constraint UNIQUE
    - Isolamento por sessão (multi-user safe)
    """
    from django.db import IntegrityError
    from .forms import EnvioWhatsAppForm
    from .utils import mask_phone_number, get_envios_hoje
    import threading

    if request.method != 'POST':
        return JsonResponse({'error': 'Método inválido'}, status=400)

    # Previne múltiplas requisições simultâneas do mesmo usuário
    if request.session.get('envio_em_progresso', False):
        return JsonResponse({
            'error': 'Já existe um envio em progresso. Aguarde a conclusão ou pause o envio atual.'
        }, status=409)

    # Validação com Django Form
    form = EnvioWhatsAppForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({'error': form.errors}, status=400)

    # Dados validados
    tipo_envio = form.cleaned_data['options']
    mensagem = form.cleaned_data['mensagem']
    imagem = form.cleaned_data.get('imagem')
    telefones_file = form.cleaned_data.get('telefones')

    # Setup
    usuario = request.user
    sessao = get_object_or_404(SessaoWpp, usuario=usuario)
    token = sessao.token
    BASE_URL = url_api + '/{}/send-{}'

    # Logs
    import re
    safe_username = re.sub(r'[^\w\-]', '', usuario.username)
    log_directory = Path('./logs/Envios manuais/')
    log_directory.mkdir(parents=True, exist_ok=True)
    log_filename = log_directory / f'{safe_username}.log'
    log_result_filename = log_directory / f'{safe_username}_send_result.log'

    # Imagem base64
    imagem_base64 = None
    if imagem:
        imagem_base64 = base64.b64encode(imagem.read()).decode('utf-8')

    # Coleta de telefones (validação inicial)
    telefones = []
    if tipo_envio == 'ativos':
        clientes = Cliente.objects.filter(usuario=usuario, cancelado=False, nao_enviar_msgs=False)
        telefones = [re.sub(r'\s+|\W', '', c.telefone) for c in clientes]
    elif tipo_envio == 'cancelados':
        clientes = Cliente.objects.filter(
            usuario=usuario,
            cancelado=True,
            data_cancelamento__lte=timezone.now() - timedelta(days=40),
            nao_enviar_msgs=False
        )
        telefones = [re.sub(r'\s+|\W', '', c.telefone) for c in clientes]
    elif tipo_envio == 'avulso':
        if telefones_file:
            lines = telefones_file.read().decode('utf-8').splitlines()
            telefones = [re.sub(r'\s+|\W', '', tel) for tel in lines if tel.strip()]

    if not telefones:
        return JsonResponse({'error': 'Nenhum telefone válido encontrado'}, status=400)

    # Marca envio como em progresso
    request.session['envio_em_progresso'] = True
    request.session['stop_envio'] = False
    request.session.save()

    # Prepara dados para a thread
    thread_data = {
        'session_key': request.session.session_key,
        'user_id': usuario.id,
        'tipo_envio': tipo_envio,
        'mensagem': mensagem,
        'imagem_nome': str(imagem) if imagem else None,
        'imagem_base64': imagem_base64,
        'telefones': telefones,
        'token': token,
        'BASE_URL': BASE_URL,
        'log_filename': str(log_filename),
        'log_result_filename': str(log_result_filename),
        'remote_addr': request.META.get('REMOTE_ADDR'),
        'request_path': request.path
    }

    # Função executada em background (thread separada)
    def processar_envios_background(data):
        """
        Processa envios WhatsApp em thread separada para permitir
        que o frontend exiba logs em tempo real via polling.
        """
        from django.contrib.sessions.backends.db import SessionStore
        from django.contrib.auth import get_user_model
        from django.db import IntegrityError
        from .utils import mask_phone_number, get_envios_hoje

        User = get_user_model()

        # Reconstrói objetos necessários
        usuario = User.objects.get(id=data['user_id'])
        session = SessionStore(session_key=data['session_key'])

        tipo_envio = data['tipo_envio']
        mensagem = data['mensagem']
        imagem_nome = data['imagem_nome']
        imagem_base64 = data['imagem_base64']
        telefones = data['telefones']
        token = data['token']
        BASE_URL = data['BASE_URL']
        log_filename = data['log_filename']
        log_result_filename = data['log_result_filename']
        remote_addr = data['remote_addr']
        request_path = data['request_path']

        def log_result(file_path, content):
            """Escreve log em arquivo com timestamp."""
            with codecs.open(file_path, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {content}\n")

        def enviar_mensagem_com_retry(url, telefone, max_retries=3):
            """
            Envia mensagem com retry automático e timeout.
            Cria o registro no BD ANTES de enviar (previne duplicatas).
            """
            hoje = timezone.now().date()

            # Check: já enviou hoje?
            if MensagemEnviadaWpp.objects.filter(
                usuario=usuario,
                telefone=telefone,
                data_envio=hoje
            ).exists():
                log_result(log_result_filename, f"{telefone} - ⚠️ Já enviado hoje (ignorado)")
                return False

            # PASSO 1: Cria registro PRIMEIRO (previne duplicata)
            try:
                registro = MensagemEnviadaWpp.objects.create(usuario=usuario, telefone=telefone)
            except IntegrityError:
                log_result(log_result_filename, f"{telefone} - ⚠️ Já enviado hoje (ignorado)")
                return False

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
            if imagem_nome:
                body.update({
                    'filename': imagem_nome,
                    'caption': mensagem,
                    'base64': f'data:image/png;base64,{imagem_base64}'
                })

            # PASSO 2: Tenta enviar (com rollback se falhar)
            try:
                for attempt in range(max_retries):
                    try:
                        response = requests.post(url, headers=headers, json=body, timeout=30)

                        if response.status_code in [200, 201]:
                            masked_phone = mask_phone_number(telefone)
                            log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{masked_phone}] Mensagem enviada!")
                            log_result(log_result_filename, f"{telefone} - ✅ Mensagem enviada")
                            return True
                        else:
                            try:
                                response_data = response.json()
                                error_message = response_data.get('message', response.text)
                            except json.decoder.JSONDecodeError:
                                error_message = response.text

                            masked_phone = mask_phone_number(telefone)
                            log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{masked_phone}] [CODE][{response.status_code}] - {error_message}")

                            if response.status_code >= 500 and attempt < max_retries - 1:
                                wait_time = 2 ** attempt
                                time.sleep(wait_time)
                                continue
                            else:
                                registro.delete()
                                log_result(log_result_filename, f"{telefone} - ❌ Não enviada (consultar log)")
                                return False

                    except requests.exceptions.Timeout:
                        masked_phone = mask_phone_number(telefone)
                        log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{masked_phone}] [TIMEOUT] Timeout após 30s")
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        else:
                            registro.delete()
                            log_result(log_result_filename, f"{telefone} - ❌ Timeout (consultar log)")
                            return False

                    except requests.exceptions.RequestException as e:
                        registro.delete()
                        masked_phone = mask_phone_number(telefone)
                        log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{masked_phone}] [ERRO] {str(e)}")
                        log_result(log_result_filename, f"{telefone} - ❌ Erro de conexão")
                        return False

            except Exception as e:
                registro.delete()
                masked_phone = mask_phone_number(telefone)
                log_result(log_filename, f"[TIPO][Manual] [USUÁRIO][{usuario}] [TELEFONE][{masked_phone}] [ERRO INESPERADO] {str(e)}")
                log_result(log_result_filename, f"{telefone} - ❌ Erro inesperado")
                return False

            registro.delete()
            return False

        try:
            # UserActionLog: início
            UserActionLog.objects.create(
                usuario=usuario,
                acao='other',
                entidade='envio_whatsapp',
                mensagem='Envio WhatsApp iniciado',
                ip=remote_addr,
                extras={
                    'tipo_envio': tipo_envio,
                    'total_telefones': len(telefones),
                    'com_imagem': bool(imagem_nome),
                    'path': request_path
                }
            )

            # Processamento
            url_envio = BASE_URL.format(usuario, 'image' if imagem_nome else 'message')
            total = len(telefones)
            enviadas = 0
            envios_hoje_inicial = get_envios_hoje(usuario)

            log_result(log_result_filename, f"\n=== INICIANDO ENVIO ===\nTotal: {total} telefones\n")

            for idx, telefone in enumerate(telefones, 1):
                # CHECK: Flag de parada
                if session.get('stop_envio', False):
                    log_result(log_result_filename, f"\n=== ENVIO PARADO PELO USUÁRIO ===\nEnviadas: {enviadas}/{total}\n")
                    UserActionLog.objects.create(
                        usuario=usuario,
                        acao='other',
                        entidade='envio_whatsapp',
                        mensagem='Envio WhatsApp pausado pelo usuário',
                        ip=remote_addr,
                        extras={
                            'tipo_envio': tipo_envio,
                            'enviadas': enviadas,
                            'total': total,
                            'percentual': round((enviadas / total) * 100, 2),
                            'path': request_path
                        }
                    )
                    return

                # Envia mensagem
                if enviar_mensagem_com_retry(url_envio, telefone):
                    enviadas += 1

                # Delay inteligente
                envios_hoje_atual = envios_hoje_inicial + enviadas
                base_delay = random.uniform(5, 12)
                if envios_hoje_atual > 200:
                    extra_delay = 10
                    total_delay = base_delay + extra_delay
                    log_result(log_result_filename, f"⚠️ Limite de 200 envios/dia excedido. Delay aumentado para {total_delay:.1f}s")
                else:
                    total_delay = base_delay

                # Sleep interruptível
                chunks = int(total_delay)
                remainder = total_delay - chunks
                for _ in range(chunks):
                    if session.get('stop_envio', False):
                        log_result(log_result_filename, f"\n=== ENVIO PARADO DURANTE SLEEP ===\n")
                        return
                    time.sleep(1)
                if remainder > 0:
                    time.sleep(remainder)

            # UserActionLog: conclusão
            UserActionLog.objects.create(
                usuario=usuario,
                acao='other',
                entidade='envio_whatsapp',
                mensagem='Envio WhatsApp concluído com sucesso',
                ip=remote_addr,
                extras={
                    'tipo_envio': tipo_envio,
                    'enviadas': enviadas,
                    'total': total,
                    'percentual': round((enviadas / total) * 100, 2) if total > 0 else 0,
                    'path': request_path
                }
            )

            log_result(log_result_filename, f"\n=== ENVIO CONCLUÍDO ===\nEnviadas: {enviadas}/{total}\n")

        except Exception as e:
            log_result(log_result_filename, f"\n=== ERRO INESPERADO ===\n{str(e)}\n")
        finally:
            # Cleanup da sessão
            session['envio_em_progresso'] = False
            session['stop_envio'] = False
            session.save()

    # Inicia thread de processamento
    thread = threading.Thread(target=processar_envios_background, args=(thread_data,), daemon=True)
    thread.start()

    # UserActionLog: início (registro imediato)
    UserActionLog.objects.create(
        usuario=usuario,
        acao='other',
        entidade='envio_whatsapp',
        mensagem='Envio WhatsApp aceito para processamento',
        ip=request.META.get('REMOTE_ADDR'),
        extras={
            'tipo_envio': tipo_envio,
            'total_telefones': len(telefones),
            'com_imagem': bool(imagem),
            'path': request.path
        }
    )

    # Retorna imediatamente (status 202 = Accepted)
    return JsonResponse({
        'success': 'Envio iniciado com sucesso',
        'total': len(telefones),
        'message': 'Os logs serão exibidos em tempo real no console'
    }, status=202)



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
    """
    Retorna logs de envios do usuário atual.

    SEGURANÇA:
    - Valida username contra path traversal (../)
    - Normaliza path para prevenir acesso fora de LOG_DIR
    - Verifica que path final está dentro do diretório esperado
    """
    import re

    # Sanitiza username (previne path traversal)
    username = request.user.username
    # Remove caracteres perigosos: apenas alfanuméricos, underscore, hífen
    safe_username = re.sub(r'[^\w\-]', '', username)

    # Constrói path
    log_dir = Path(LOG_DIR) / "Envios manuais"
    log_path = log_dir / f"{safe_username}_send_result.log"

    # Normaliza e resolve path (previne ../ e symlinks)
    log_path = log_path.resolve()
    log_dir = log_dir.resolve()

    # Verifica se log_path está dentro de log_dir (previne traversal)
    try:
        log_path.relative_to(log_dir)
    except ValueError:
        # Path está fora do diretório permitido
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    if not log_path.exists():
        return JsonResponse({'logs': ''})

    logs = log_path.read_text(encoding='utf-8', errors='ignore')
    return JsonResponse({'logs': logs})


@require_http_methods(["POST"])
@login_required
def parar_envio(request):
    """
    Endpoint para usuário pausar envios WhatsApp em progresso.

    Sistema de controle via session:
    - session['envio_em_progresso']: Boolean indicando se há envio ativo
    - session['stop_envio']: Flag para interromper loop de envios

    Response:
    - 200: Flag setada com sucesso, envio será pausado
    - 409: Nenhum envio em progresso para pausar

    SEGURANÇA:
    - Isolamento por sessão (cada usuário controla apenas seus próprios envios)
    - CSRF protected
    """
    if not request.session.get('envio_em_progresso', False):
        return JsonResponse({
            'error': 'Nenhum envio em progresso'
        }, status=409)

    request.session['stop_envio'] = True
    request.session.save()

    return JsonResponse({
        'success': 'Envio será pausado em breve'
    }, status=200)


@require_http_methods(["GET"])
@login_required
def status_envio(request):
    """
    Retorna status atual do envio para sincronizar UI.

    Used by JavaScript para:
    - Exibir botão correto (Enviar/Parar/Retomar)
    - Polling a cada 5s durante envio ativo
    - Prevenir múltiplas requisições simultâneas

    Response JSON:
        {
            "em_progresso": bool,  # True se há envio rodando
            "pausado": bool,       # True se foi pausado pelo usuário
            "total_hoje": int      # Quantidade de envios realizados hoje
        }
    """
    from .utils import get_envios_hoje

    return JsonResponse({
        'em_progresso': request.session.get('envio_em_progresso', False),
        'pausado': request.session.get('stop_envio', False),
        'total_hoje': get_envios_hoje(request.user)
    })


@require_http_methods(["POST"])
@login_required
def limpar_log_wpp(request):
    """
    Deleta fisicamente o arquivo de log de envios WhatsApp do usuário.

    REGRAS:
    - Só permite limpar se NÃO houver envio em progresso
    - Deleta ambos os arquivos: log principal e log de resultados

    Response:
    - 200: Log deletado com sucesso
    - 409: Não pode limpar durante envio em progresso

    SEGURANÇA:
    - Path traversal prevention (sanitiza username)
    - Isolamento por usuário (cada um limpa apenas seus logs)
    - CSRF protected
    """
    # Verifica se há envio em progresso
    if request.session.get('envio_em_progresso', False):
        return JsonResponse({
            'error': 'Não é possível limpar logs durante um envio em progresso'
        }, status=409)

    # Path dos arquivos de log
    import re
    safe_username = re.sub(r'[^\w\-]', '', request.user.username)
    log_directory = Path('./logs/Envios manuais/')
    log_filename = log_directory / f'{safe_username}.log'
    log_result_filename = log_directory / f'{safe_username}_send_result.log'

    try:
        # Deleta arquivo de log principal (se existir)
        if log_filename.exists():
            log_filename.unlink()

        # Deleta arquivo de log de resultados (se existir)
        if log_result_filename.exists():
            log_result_filename.unlink()

        # Log da ação
        UserActionLog.objects.create(
            usuario=request.user,
            acao='other',
            entidade='log_whatsapp',
            mensagem='Arquivo de log de envios WhatsApp foi limpo',
            ip=request.META.get('REMOTE_ADDR'),
            extras={
                'path': request.path,
                'arquivos_deletados': [str(log_filename), str(log_result_filename)]
            }
        )

        return JsonResponse({
            'success': 'Logs limpos com sucesso'
        }, status=200)

    except Exception as e:
        return JsonResponse({
            'error': f'Erro ao limpar logs: {str(e)}'
        }, status=500)


@login_required
def profile_page(request):
    from .models import UserProfile, UserActionLog

    user = request.user
    dados_bancarios = DadosBancarios.objects.filter(usuario=user).first()

    # Obter ou criar perfil do usuário
    profile, created = UserProfile.objects.get_or_create(user=user)

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

    # ========== ESTATÍSTICAS DO USUÁRIO ==========
    # Total de clientes ativos
    total_clientes = Cliente.objects.filter(usuario=user, cancelado=False).count()

    # Valor de negócio (soma dos valores dos planos dos clientes ativos)
    receita_mensal = Cliente.objects.filter(
        usuario=user,
        cancelado=False
    ).aggregate(
        total=Sum('plano__valor')
    )['total'] or 0

    # Dias no sistema
    dias_sistema = (timezone.now().date() - user.date_joined.date()).days if user.date_joined else 0

    # Última atividade registrada
    ultima_acao = UserActionLog.objects.filter(usuario=user).order_by('-criado_em').first()
    if ultima_acao:
        diff = timezone.now() - ultima_acao.criado_em
        if diff.days > 0:
            ultima_atividade = f"Há {diff.days} dia{'s' if diff.days > 1 else ''}"
        elif diff.seconds // 3600 > 0:
            horas = diff.seconds // 3600
            ultima_atividade = f"Há {horas} hora{'s' if horas > 1 else ''}"
        elif diff.seconds // 60 > 0:
            minutos = diff.seconds // 60
            ultima_atividade = f"Há {minutos} minuto{'s' if minutos > 1 else ''}"
        else:
            ultima_atividade = "Agora mesmo"
    else:
        ultima_atividade = "Nunca"

    # Total de clientes cancelados
    total_cancelados = Cliente.objects.filter(usuario=user, cancelado=True).count()

    # Total de mensalidades recebidas este mês
    mes_atual = timezone.now().month
    ano_atual = timezone.now().year
    mensalidades_mes = Mensalidade.objects.filter(
        usuario=user,
        pgto=True,
        dt_pagamento__month=mes_atual,
        dt_pagamento__year=ano_atual
    ).count()

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
            'avatar_url': profile.get_avatar_url(),
            # Estatísticas
            'total_clientes': total_clientes,
            'receita_mensal': receita_mensal,
            'dias_sistema': dias_sistema,
            'ultima_atividade': ultima_atividade,
            'total_cancelados': total_cancelados,
            'mensalidades_mes': mensalidades_mes,
            # Preferências
            'theme_preference': profile.theme_preference,
            'email_on_profile_change': profile.email_on_profile_change,
            'email_on_password_change': profile.email_on_password_change,
            'email_on_login': profile.email_on_login,
            'profile_public': profile.profile_public,
            'show_email': profile.show_email,
            'show_phone': profile.show_phone,
            'show_statistics': profile.show_statistics,
            # 2FA
            'two_factor_enabled': profile.two_factor_enabled,
            'has_backup_codes': bool(profile.two_factor_backup_codes),
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


def _month_name_pt(month: int) -> str:
    nomes = [
        "",
        "Janeiro",
        "Fevereiro",
        "Mar\u00e7o",
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
    if 1 <= month < len(nomes):
        return nomes[month]
    return str(month)


def _month_abbr_pt(month: int) -> str:
    abreviacoes = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]
    if 1 <= month <= len(abreviacoes):
        return abreviacoes[month - 1]
    return str(month)


def _dataset_adesao_cancelamentos_mensal(usuario, year: int, month: int):
    dados_adesoes = (
        Cliente.objects.filter(
            data_adesao__year=year,
            data_adesao__month=month,
            usuario=usuario,
        )
        .annotate(dia=ExtractDay("data_adesao"))
        .values("dia")
        .annotate(total=Count("id"))
        .order_by("dia")
    )

    dados_cancelamentos = (
        Cliente.objects.filter(
            data_cancelamento__year=year,
            data_cancelamento__month=month,
            usuario=usuario,
        )
        .annotate(dia=ExtractDay("data_cancelamento"))
        .values("dia")
        .annotate(total=Count("id"))
        .order_by("dia")
    )

    adesoes_dict = {item["dia"]: item["total"] for item in dados_adesoes}
    cancelamentos_dict = {item["dia"]: item["total"] for item in dados_cancelamentos}

    categorias = []
    adesoes = []
    cancelamentos = []
    saldo = []

    total_dias = calendar.monthrange(year, month)[1]
    for dia in range(1, total_dias + 1):
        if dia in adesoes_dict or dia in cancelamentos_dict:
            valor_adesao = adesoes_dict.get(dia, 0)
            valor_cancelamento = cancelamentos_dict.get(dia, 0)
            categorias.append(str(dia))
            adesoes.append(valor_adesao)
            cancelamentos.append(valor_cancelamento)
            saldo.append(valor_adesao - valor_cancelamento)

    total_adesoes = sum(adesoes)
    total_cancelamentos = sum(cancelamentos)
    saldo_final = total_adesoes - total_cancelamentos

    return {
        "mode": "monthly",
        "categories": categorias,
        "series": [
            {"key": "adesoes", "name": "Ades\u00f5es", "type": "bar", "data": adesoes},
            {"key": "cancelamentos", "name": "Cancelamentos", "type": "bar", "data": cancelamentos},
            {"key": "saldo", "name": "Saldo", "type": "line", "data": saldo},
        ],
        "summary": {
            "total_adesoes": total_adesoes,
            "total_cancelamentos": total_cancelamentos,
            "saldo": saldo_final,
            "saldo_label": f"{'+' if saldo_final > 0 else ''}{saldo_final}",
        },
        "meta": {
            "mode": "monthly",
            "month": month,
            "month_name": _month_name_pt(month),
            "year": year,
            "range_label": f"{_month_name_pt(month)} {year}",
        },
    }


def _dataset_adesao_cancelamentos_lifetime(usuario):
    dados_adesoes = (
        Cliente.objects.filter(usuario=usuario, data_adesao__isnull=False)
        .annotate(ano=ExtractYear("data_adesao"), mes=ExtractMonth("data_adesao"))
        .values("ano", "mes")
        .annotate(total=Count("id"))
        .order_by("ano", "mes")
    )

    dados_cancelamentos = (
        Cliente.objects.filter(usuario=usuario, data_cancelamento__isnull=False)
        .annotate(ano=ExtractYear("data_cancelamento"), mes=ExtractMonth("data_cancelamento"))
        .values("ano", "mes")
        .annotate(total=Count("id"))
        .order_by("ano", "mes")
    )

    adesoes_dict = {(item["ano"], item["mes"]): item["total"] for item in dados_adesoes}
    cancelamentos_dict = {(item["ano"], item["mes"]): item["total"] for item in dados_cancelamentos}

    todos_periodos = sorted(set(adesoes_dict.keys()) | set(cancelamentos_dict.keys()))

    categorias = []
    adesoes = []
    cancelamentos = []
    saldo = []

    for ano, mes in todos_periodos:
        valor_adesao = adesoes_dict.get((ano, mes), 0)
        valor_cancelamento = cancelamentos_dict.get((ano, mes), 0)
        categorias.append(f"{_month_abbr_pt(mes)} {ano}")
        adesoes.append(valor_adesao)
        cancelamentos.append(valor_cancelamento)
        saldo.append(valor_adesao - valor_cancelamento)

    total_adesoes = sum(adesoes)
    total_cancelamentos = sum(cancelamentos)
    saldo_final = total_adesoes - total_cancelamentos

    meta = {
        "mode": "lifetime",
        "title": "Ades\u00e3o e Cancelamentos - Hist\u00f3rico completo",
    }
    if todos_periodos:
        ano_inicio, mes_inicio = todos_periodos[0]
        ano_fim, mes_fim = todos_periodos[-1]
        meta.update(
            {
                "start_year": ano_inicio,
                "start_month": mes_inicio,
                "end_year": ano_fim,
                "end_month": mes_fim,
                "range_label": f"De {_month_abbr_pt(mes_inicio)} {ano_inicio} a {_month_abbr_pt(mes_fim)} {ano_fim}",
            }
        )

    return {
        "mode": "lifetime",
        "categories": categorias,
        "series": [
            {"key": "adesoes", "name": "Ades\u00f5es", "type": "bar", "data": adesoes},
            {"key": "cancelamentos", "name": "Cancelamentos", "type": "bar", "data": cancelamentos},
            {"key": "saldo", "name": "Saldo", "type": "line", "data": saldo},
        ],
        "summary": {
            "total_adesoes": total_adesoes,
            "total_cancelamentos": total_cancelamentos,
            "saldo": saldo_final,
            "saldo_label": f"{'+' if saldo_final > 0 else ''}{saldo_final}",
        },
        "meta": meta,
    }


def _dataset_adesao_cancelamentos_anual(usuario, year: int):
    dados_adesoes = (
        Cliente.objects.filter(data_adesao__year=year, usuario=usuario)
        .annotate(mes=ExtractMonth("data_adesao"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )

    dados_cancelamentos = (
        Cliente.objects.filter(data_cancelamento__year=year, usuario=usuario)
        .annotate(mes=ExtractMonth("data_cancelamento"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )

    adesoes_dict = {item["mes"]: item["total"] for item in dados_adesoes}
    cancelamentos_dict = {item["mes"]: item["total"] for item in dados_cancelamentos}

    categorias = []
    adesoes = []
    cancelamentos = []
    saldo = []

    for mes in range(1, 13):
        valor_adesao = adesoes_dict.get(mes, 0)
        valor_cancelamento = cancelamentos_dict.get(mes, 0)
        if valor_adesao or valor_cancelamento:
            categorias.append(_month_abbr_pt(mes))
            adesoes.append(valor_adesao)
            cancelamentos.append(valor_cancelamento)
            saldo.append(valor_adesao - valor_cancelamento)

    total_adesoes = sum(adesoes)
    total_cancelamentos = sum(cancelamentos)
    saldo_final = total_adesoes - total_cancelamentos

    return {
        "mode": "annual",
        "categories": categorias,
        "series": [
            {"key": "adesoes", "name": "Ades\u00f5es", "type": "bar", "data": adesoes},
            {"key": "cancelamentos", "name": "Cancelamentos", "type": "bar", "data": cancelamentos},
            {"key": "saldo", "name": "Saldo", "type": "line", "data": saldo},
        ],
        "summary": {
            "total_adesoes": total_adesoes,
            "total_cancelamentos": total_cancelamentos,
            "saldo": saldo_final,
            "saldo_label": f"{'+' if saldo_final > 0 else ''}{saldo_final}",
        },
        "meta": {
            "mode": "annual",
            "year": year,
            "range_label": str(year),
        },
    }


@login_required
@require_GET
def adesoes_cancelamentos_api(request):
    modo = (request.GET.get("mode", "monthly") or "monthly").lower()
    hoje = timezone.localdate()
    usuario = request.user

    try:
        ano = int(request.GET.get("year", hoje.year))
    except (TypeError, ValueError):
        ano = hoje.year

    if modo not in {"monthly", "annual", "lifetime"}:
        modo = "monthly"

    if modo == "annual":
        resultado = _dataset_adesao_cancelamentos_anual(usuario, ano)
        resultado["meta"]["title"] = f"Ades\u00e3o e Cancelamentos por ano - {ano}"
    elif modo == "lifetime":
        resultado = _dataset_adesao_cancelamentos_lifetime(usuario)
    else:
        try:
            mes = int(request.GET.get("month", hoje.month))
        except (TypeError, ValueError):
            mes = hoje.month
        mes = max(1, min(12, mes))
        resultado = _dataset_adesao_cancelamentos_mensal(usuario, ano, mes)
        resultado["meta"]["title"] = f"Ades\u00e3o e Cancelamentos por m\u00eas - {resultado['meta']['month_name']} {ano}"

    return JsonResponse(resultado)


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


@login_required
@cache_page_by_user(60 * 5)
def mapa_clientes_data(request):
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

    for feature in geojson_data.get("features", []):
        props = feature.get("properties", {})
        props["clientes"] = int(props.get("clientes", 0) or 0)
        props["porcentagem"] = float(props.get("porcentagem", 0) or 0)
        feature["properties"] = props

    max_clientes = int(max(mapa["clientes"]) if mapa["clientes"].any() else 0)

    return JsonResponse(
        {
            "features": geojson_data.get("features", []),
            "summary": {
                "total_geral": int(total_geral),
                "fora_pais": int(clientes_internacionais),
                "max_clientes": max_clientes,
            },
        }
    )


@login_required
@cache_page_by_user(60 * 5)
def clientes_servidor_data(request):
    usuario = request.user

    servidores = list(
        Servidor.objects.filter(usuario=usuario)
        .order_by("nome")
        .values_list("nome", flat=True)
    )

    filtro = (request.GET.get("servidor") or "todos").strip()
    selected = filtro if filtro in servidores else "todos"

    base_queryset = Cliente.objects.filter(usuario=usuario, cancelado=False)

    if selected != "todos":
        queryset = base_queryset.filter(servidor__nome=selected)
        agregados = (
            queryset.values("sistema__nome")
            .annotate(total=Count("id"))
            .order_by("-total", "sistema__nome")
        )
        mode = "aplicativo"
    else:
        queryset = base_queryset
        agregados = (
            queryset.values("servidor__nome")
            .annotate(total=Count("id"))
            .order_by("-total", "servidor__nome")
        )
        mode = "servidor"

    total = sum(item["total"] for item in agregados)

    segments = []
    for item in agregados:
        if mode == "servidor":
            label = item["servidor__nome"] or "Sem servidor"
        else:
            label = item["sistema__nome"] or "Sem aplicativo"
        valor = int(item["total"])
        percent = round((valor / total) * 100, 2) if total > 0 else 0.0
        segments.append(
            {
                "label": label,
                "value": valor,
                "percent": percent,
            }
        )

    segments.sort(key=lambda x: (-x["value"], x["label"]))

    options = ["Todos Servidores"] + servidores
    selected_label = selected if selected != "todos" else "Todos os Servidores"

    return JsonResponse(
        {
            "options": options,
            "selected": selected_label,
            "mode": mode,
            "total": int(total),
            "segments": segments,
        }
    )


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
@transaction.atomic
def reactivate_customer(request, cliente_id):
    """
    View para reativar um cliente anteriormente cancelado.
    Avalia a última mensalidade e cria nova se necessário.

    Regras:
    - Se cancelado há menos de 7 dias: reativa mensalidade existente
    - Se cancelado há mais de 7 dias: cria nova mensalidade com vencimento atual
    - Sempre verifica se já existe mensalidade em aberto para evitar duplicação
    """
    try:
        cliente = Cliente.objects.get(pk=cliente_id, usuario=request.user)
    except Cliente.DoesNotExist:
        return JsonResponse({"error_message": "Cliente não encontrado."}, status=404)

    data_hoje = timezone.localdate()
    sete_dias_atras = data_hoje - timedelta(days=7)
    nova_mensalidade_criada = False
    mensalidade_reativada = False

    logger.info('[%s] [USER][%s] Iniciando reativação do cliente ID: %s',
                timezone.localtime(), request.user, cliente_id)

    # Atualiza os campos de reativação
    cliente.cancelado = False
    cliente.data_cancelamento = None
    cliente.data_vencimento = data_hoje
    cliente.save()

    logger.info('[%s] [USER][%s] Cliente ID %s marcado como ativo',
                timezone.localtime(), request.user, cliente_id)

    # histórico: inicia novo período vigente
    try:
        historico_iniciar(cliente, inicio=data_hoje, motivo='reactivate')
    except Exception:
        pass

    # ⭐ FASE 2: Auto-enroll in campaign if eligible
    try:
        from cadastros.utils import enroll_client_in_campaign_if_eligible
        enroll_client_in_campaign_if_eligible(cliente)
    except Exception as e:
        logger.error(f"Erro ao inscrever cliente na campanha durante reativação: {e}", exc_info=True)

    try:
        # ⭐ FASE 2: Calcula valor considerando campanhas promocionais + descontos progressivos
        valor_mensalidade = calcular_valor_mensalidade(cliente)

        logger.info('[%s] [USER][%s] Valor mensalidade calculado para cliente ID %s: R$ %s',
                    timezone.localtime(), request.user, cliente_id, valor_mensalidade)

        # PROTEÇÃO CONTRA DUPLICAÇÃO: Verifica se já existe mensalidade em aberto
        mensalidade_em_aberto = Mensalidade.objects.filter(
            cliente=cliente,
            pgto=False,
            cancelado=False,
            dt_vencimento__gte=data_hoje
        ).first()

        if mensalidade_em_aberto:
            # Já existe mensalidade em aberto, apenas atualiza o valor
            logger.info('[%s] [USER][%s] Cliente ID %s já possui mensalidade em aberto (ID: %s). Atualizando valor.',
                        timezone.localtime(), request.user, cliente_id, mensalidade_em_aberto.id)
            mensalidade_em_aberto.valor = valor_mensalidade
            mensalidade_em_aberto.save()
            mensalidade_reativada = True
        else:
            # Obtém a última mensalidade do cliente
            ultima_mensalidade = Mensalidade.objects.filter(cliente=cliente).order_by('-dt_vencimento').first()

            if ultima_mensalidade:
                # Verifica se a mensalidade foi cancelada há menos de 7 dias
                if sete_dias_atras <= ultima_mensalidade.dt_vencimento <= data_hoje:
                    # CASO 1: Cancelado há menos de 7 dias - Reativa a mensalidade existente
                    logger.info('[%s] [USER][%s] Cliente ID %s cancelado há menos de 7 dias. Reativando mensalidade ID: %s',
                                timezone.localtime(), request.user, cliente_id, ultima_mensalidade.id)

                    ultima_mensalidade.cancelado = False
                    ultima_mensalidade.dt_cancelamento = None
                    ultima_mensalidade.valor = valor_mensalidade
                    ultima_mensalidade.save()
                    mensalidade_reativada = True
                else:
                    # CASO 2: Cancelado há mais de 7 dias - Cria nova mensalidade
                    logger.info('[%s] [USER][%s] Cliente ID %s cancelado há mais de 7 dias. Criando nova mensalidade.',
                                timezone.localtime(), request.user, cliente_id)

                    # Mantém a mensalidade anterior como cancelada
                    ultima_mensalidade.cancelado = True
                    ultima_mensalidade.dt_cancelamento = data_hoje
                    ultima_mensalidade.save()

                    # Cria nova mensalidade com desconto progressivo aplicado
                    nova_mensalidade = Mensalidade.objects.create(
                        cliente=cliente,
                        valor=valor_mensalidade,
                        dt_vencimento=data_hoje,
                        usuario=cliente.usuario
                    )
                    nova_mensalidade_criada = True

                    logger.info('[%s] [USER][%s] Nova mensalidade ID %s criada para cliente ID %s',
                                timezone.localtime(), request.user, nova_mensalidade.id, cliente_id)
            else:
                # CASO 3: Não existe mensalidade anterior - Cria primeira mensalidade
                logger.info('[%s] [USER][%s] Cliente ID %s sem mensalidade anterior. Criando primeira mensalidade.',
                            timezone.localtime(), request.user, cliente_id)

                nova_mensalidade = Mensalidade.objects.create(
                    cliente=cliente,
                    valor=valor_mensalidade,
                    dt_vencimento=data_hoje,
                    usuario=cliente.usuario
                )
                nova_mensalidade_criada = True

                logger.info('[%s] [USER][%s] Primeira mensalidade ID %s criada para cliente ID %s',
                            timezone.localtime(), request.user, nova_mensalidade.id, cliente_id)

    except Exception as erro:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]',
                     timezone.localtime(), request.user,
                     get_client_ip(request) or 'N/A', erro,
                     exc_info=True)
        return JsonResponse({"error_message": "Erro ao processar mensalidade na reativação."}, status=500)

    logger.info('[%s] [USER][%s] Reativação do cliente ID %s concluída. Nova mensalidade: %s | Mensalidade reativada: %s',
                timezone.localtime(), request.user, cliente_id, nova_mensalidade_criada, mensalidade_reativada)

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
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro, exc_info=True)
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
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro, exc_info=True)
            return JsonResponse({"error_message": "Ocorreu um erro ao tentar cancelar esse cliente."}, status=500)

        # Cancelar todas as mensalidades relacionadas ao cliente
        mensalidades = cliente.mensalidade_set.filter(dt_vencimento__gte=timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0), pgto=False, cancelado=False)
        mensalidades_count = mensalidades.count()
        for mensalidade in mensalidades:
            mensalidade.cancelado = True
            mensalidade.dt_cancelamento = timezone.localtime().date()
            mensalidade.save()

        # Encerra histórico vigente na data do cancelamento
        try:
            historico_encerrar_vigente(cliente, timezone.localdate())
        except Exception:
            pass

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
def api_cliente_contas(request, cliente_id):
    """
    API para carregar as contas de aplicativos de um cliente.
    Retorna JSON com todas as contas incluindo dispositivo, app, credenciais e status principal.
    """
    try:
        cliente = Cliente.objects.get(id=cliente_id, usuario=request.user)

        # Busca todas as contas do cliente com relacionamentos
        contas = ContaDoAplicativo.objects.filter(cliente=cliente).select_related(
            'dispositivo', 'app'
        ).order_by('-is_principal', 'id')  # Principal primeiro, depois por ordem de criação

        # Serializa para JSON
        contas_data = []
        for conta in contas:
            conta_dict = {
                'id': conta.id,
                'dispositivo_id': conta.dispositivo.id if conta.dispositivo else None,
                'dispositivo_nome': conta.dispositivo.nome if conta.dispositivo else None,
                'app_id': conta.app.id,
                'app_nome': conta.app.nome,
                'app_device_has_mac': conta.app.device_has_mac,
                'device_id': conta.device_id or '',
                'email': conta.email or '',
                'device_key': conta.device_key or '',
                'is_principal': conta.is_principal,
                'verificado': conta.verificado,
            }
            contas_data.append(conta_dict)

        return JsonResponse({
            'success': True,
            'contas': contas_data,
            'total': len(contas_data)
        })

    except Cliente.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Cliente não encontrado'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


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
            "nao_enviar_msgs": cliente.nao_enviar_msgs,
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
            parts = plano_str.rsplit('-', 2)  # Split into 3 parts: nome - valor - telas
            if len(parts) == 3:
                plano_nome, plano_valor, plano_telas = parts
                plano_nome = plano_nome.strip()
                plano_valor = Decimal(plano_valor.strip().replace(',', '.'))
                plano_telas = int(plano_telas.strip())
                plano = Plano.objects.filter(nome=plano_nome, valor=plano_valor, telas=plano_telas, usuario=user).first()
            else:
                # Fallback for old format (backwards compatibility)
                plano_nome, plano_valor = plano_str.rsplit('-', 1)
                plano_nome = plano_nome.strip()
                plano_valor = Decimal(plano_valor.replace(',', '.'))
                plano = Plano.objects.filter(nome=plano_nome, valor=plano_valor, usuario=user).first()
            if plano and cliente.plano != plano:
                cliente.plano = plano
                mensalidade.valor = calcular_valor_mensalidade(cliente)
                # Atualiza histórico de planos: encerra vigente e inicia novo
                hoje = timezone.localdate()
                try:
                    historico_encerrar_vigente(cliente, fim=hoje - timedelta(days=1))
                    historico_iniciar(cliente, plano=plano, inicio=hoje, motivo='plan_change')
                except Exception:
                    pass

                # ⭐ FASE 2.5: Sync AssinaturaCliente.plano and reset campaign tracking when plan changes
                try:
                    from .models import AssinaturaCliente
                    assinatura = AssinaturaCliente.objects.get(cliente=cliente, ativo=True)

                    # Sincroniza o plano da assinatura com o novo plano do cliente
                    assinatura.plano = plano

                    # Se estava em campanha, reseta os campos de rastreamento
                    if assinatura.em_campanha:
                        assinatura.em_campanha = False
                        assinatura.campanha_data_adesao = None
                        assinatura.campanha_mensalidades_pagas = 0
                        assinatura.campanha_duracao_total = None
                        logger.info(
                            f"[CAMPANHA] Rastreamento de campanha resetado para {cliente.nome} devido a mudança de plano"
                        )

                    # Salva a assinatura (sempre, não só quando em campanha)
                    assinatura.save()

                except AssinaturaCliente.DoesNotExist:
                    pass  # No subscription record

                # ⭐ FASE 2.5: Re-enroll client in new plan's campaign if applicable
                if plano.campanha_ativa:
                    from .utils import enroll_client_in_campaign_if_eligible
                    enroll_result = enroll_client_in_campaign_if_eligible(cliente)
                    if enroll_result:
                        # Recalculate mensalidade value with new campaign
                        mensalidade.valor = calcular_valor_mensalidade(cliente)
                        logger.info(
                            f"[CAMPANHA] Cliente {cliente.nome} inscrito na campanha do novo plano '{plano.nome}'"
                        )

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
                mensalidade.valor = calcular_valor_mensalidade(cliente)

        # Não enviar mensagens automáticas
        nao_enviar_msgs = post.get("nao_enviar_msgs") == "on"
        if cliente.nao_enviar_msgs != nao_enviar_msgs:
            cliente.nao_enviar_msgs = nao_enviar_msgs

        # Notas
        notas = post.get("notas", "").strip()
        if cliente.notas != notas:
            cliente.notas = notas

        # ========== PROCESSAMENTO DE CONTAS DE APLICATIVOS ==========
        # Processa dados de contas do aplicativo enviadas pelo formulário
        conta_principal_id = None
        contas_atualizadas = []

        # Verifica se há contas sendo editadas no formulário
        has_conta_fields = any(key.startswith('conta_') and '_' in key[6:] for key in post.keys())

        # Só desmarca todas as contas se houver contas sendo editadas
        # (evita desmarcar a principal quando apenas outros campos do cliente são alterados)
        if has_conta_fields:
            ContaDoAplicativo.objects.filter(cliente=cliente).update(is_principal=False)

        for key in post.keys():
            # Identifica campos de contas: conta_{id}_campo
            if key.startswith('conta_') and '_' in key[6:]:
                try:
                    # Extrai ID da conta
                    parts = key.split('_')
                    if len(parts) >= 3:
                        conta_id = int(parts[1])
                        campo = '_'.join(parts[2:])  # Pode ser 'is_principal', 'dispositivo_id', 'app_id', etc.

                        # Verifica se esta conta já foi processada neste loop
                        if conta_id not in contas_atualizadas:
                            contas_atualizadas.append(conta_id)

                            # Busca a conta
                            conta = ContaDoAplicativo.objects.filter(
                                id=conta_id,
                                cliente=cliente
                            ).first()

                            if conta:
                                # Atualiza campos da conta
                                dispositivo_id = post.get(f'conta_{conta_id}_dispositivo_id')
                                app_id = post.get(f'conta_{conta_id}_app_id')
                                device_id = post.get(f'conta_{conta_id}_device_id', '').strip()
                                email = post.get(f'conta_{conta_id}_email', '').strip()
                                device_key = post.get(f'conta_{conta_id}_device_key', '').strip()
                                is_principal = post.get(f'conta_{conta_id}_is_principal') == 'on'

                                # Atualiza dispositivo
                                if dispositivo_id:
                                    dispositivo = Dispositivo.objects.filter(id=dispositivo_id, usuario=user).first()
                                    if dispositivo:
                                        conta.dispositivo = dispositivo

                                # Atualiza aplicativo
                                if app_id:
                                    app = Aplicativo.objects.filter(id=app_id, usuario=user).first()
                                    if app:
                                        conta.app = app

                                # Atualiza credenciais
                                conta.device_id = device_id or None
                                conta.email = email or None
                                conta.device_key = device_key or None

                                # Atualiza status de conta principal
                                conta.is_principal = is_principal

                                conta.save()

                                # Log para debug
                                if is_principal:
                                    logger.info(
                                        f"[EDIT_CUSTOMER] Conta {conta_id} marcada como principal para cliente {cliente.nome}"
                                    )

                except (ValueError, IndexError):
                    continue  # Ignora campos mal formatados

        # ========== VALIDAÇÃO: GARANTIR QUE SEMPRE HAJA UMA CONTA PRINCIPAL ==========
        # Se contas foram editadas, garante que ao menos uma seja principal
        if has_conta_fields:
            # Verifica se alguma conta foi marcada como principal
            tem_principal = ContaDoAplicativo.objects.filter(cliente=cliente, is_principal=True).exists()

            if not tem_principal:
                # Se nenhuma conta foi marcada como principal, marca a primeira
                primeira_conta = ContaDoAplicativo.objects.filter(cliente=cliente).order_by('id').first()
                if primeira_conta:
                    primeira_conta.is_principal = True
                    primeira_conta.save()
                    logger.warning(
                        f"[EDIT_CUSTOMER] Nenhuma conta foi marcada como principal para cliente {cliente.nome}. "
                        f"Marcando automaticamente a conta ID {primeira_conta.id} como principal."
                    )

        # A sincronização dos campos Cliente.dispositivo e Cliente.sistema com a conta principal
        # é feita automaticamente pelo signal sincronizar_conta_principal quando conta.save() é chamado
        # Por isso, usamos update_fields para salvar APENAS os campos do formulário,
        # evitando sobrescrever dispositivo/sistema que o signal gerencia
        cliente.save(update_fields=[
            'nome', 'telefone', 'uf', 'indicado_por', 'servidor',
            'forma_pgto', 'plano', 'data_vencimento', 'nao_enviar_msgs', 'notas'
        ])
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
        _add_change("nao_enviar_msgs", original_cliente["nao_enviar_msgs"], cliente.nao_enviar_msgs)
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
                     get_client_ip(request) or 'N/A', e, exc_info=True)
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
        "campanha_ativa": plano_mensal.campanha_ativa,  # ⭐ FASE 2
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

            # ⭐ FASE 2: Update campaign data
            campanha_ativa = request.POST.get('campanha_ativa') == 'on'
            plano_mensal.campanha_ativa = campanha_ativa

            if campanha_ativa:
                plano_mensal.campanha_tipo = request.POST.get('campanha_tipo', 'FIXO')
                plano_mensal.campanha_data_inicio = request.POST.get('campanha_data_inicio') or None
                plano_mensal.campanha_data_fim = request.POST.get('campanha_data_fim') or None
                plano_mensal.campanha_duracao_meses = request.POST.get('campanha_duracao_meses') or None

                if plano_mensal.campanha_tipo == 'FIXO':
                    plano_mensal.campanha_valor_fixo = request.POST.get('campanha_valor_fixo') or None
                else:  # PERSONALIZADO
                    plano_mensal.campanha_valor_mes_1 = request.POST.get('campanha_valor_mes_1') or None
                    plano_mensal.campanha_valor_mes_2 = request.POST.get('campanha_valor_mes_2') or None
                    plano_mensal.campanha_valor_mes_3 = request.POST.get('campanha_valor_mes_3') or None
                    plano_mensal.campanha_valor_mes_4 = request.POST.get('campanha_valor_mes_4') or None
                    plano_mensal.campanha_valor_mes_5 = request.POST.get('campanha_valor_mes_5') or None
                    plano_mensal.campanha_valor_mes_6 = request.POST.get('campanha_valor_mes_6') or None
            else:
                # Clear campaign data if not active
                plano_mensal.campanha_tipo = None
                plano_mensal.campanha_data_inicio = None
                plano_mensal.campanha_data_fim = None
                plano_mensal.campanha_duracao_meses = None
                plano_mensal.campanha_valor_fixo = None
                plano_mensal.campanha_valor_mes_1 = None
                plano_mensal.campanha_valor_mes_2 = None
                plano_mensal.campanha_valor_mes_3 = None
                plano_mensal.campanha_valor_mes_4 = None
                plano_mensal.campanha_valor_mes_5 = None
                plano_mensal.campanha_valor_mes_6 = None

            try:
                plano_mensal.save()
                changes = {}
                if original_plano["nome"] != plano_mensal.nome:
                    changes["nome"] = (original_plano["nome"], plano_mensal.nome)
                if original_plano["telas"] != plano_mensal.telas:
                    changes["telas"] = (original_plano["telas"], plano_mensal.telas)
                if original_plano["valor"] != plano_mensal.valor:
                    changes["valor"] = (original_plano["valor"], plano_mensal.valor)
                # ⭐ FASE 2: Tracking de mudanças da campanha
                if original_plano["campanha_ativa"] != plano_mensal.campanha_ativa:
                    changes["campanha_ativa"] = (
                        original_plano["campanha_ativa"],
                        plano_mensal.campanha_ativa
                    )
                mensagem_plano = "Plano atualizado." if changes else "Plano salvo sem alteracoes."
                log_user_action(
                    request=request,
                    action=UserActionLog.ACTION_UPDATE,
                    instance=plano_mensal,
                    message=mensagem_plano,
                    extra=changes if changes else None,
                )


            except ValidationError as erro1:
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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
        imagem = request.FILES.get("imagem")

        if nome:
            servidor.nome = nome
            try:
                servidor.save()
                changes = {}
                if original_nome != servidor.nome:
                    changes["nome"] = (original_nome, servidor.nome)

                # Atualizar ou criar imagem do servidor
                if imagem:
                    from .models import ServidorImagem
                    servidor_imagem, created = ServidorImagem.objects.get_or_create(
                        servidor=servidor,
                        usuario=request.user
                    )
                    servidor_imagem.imagem = imagem
                    servidor_imagem.save()
                    changes["imagem"] = "atualizada" if not created else "adicionada"

                mensagem = "Servidor atualizado." if changes else "Servidor salvo sem alteracoes."
                log_user_action(
                    request=request,
                    action=UserActionLog.ACTION_UPDATE,
                    instance=servidor,
                    message=mensagem,
                    extra=changes if changes else None,
                )


            except ValidationError as erro1:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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

                # Enviar email de notificação (se habilitado e houve alterações)
                if changes:
                    try:
                        ip_address = get_client_ip(request) or 'Desconhecido'
                        # Formatar mudanças para o email
                        formatted_changes = {}
                        for key, value in changes.items():
                            if isinstance(value, tuple) and len(value) == 2:
                                formatted_changes[key] = {'old': value[0], 'new': value[1]}
                            else:
                                formatted_changes[key] = {'old': '', 'new': str(value)}

                        send_profile_change_notification(
                            request.user,
                            change_type='profile',
                            changes_detail=formatted_changes,
                            ip_address=ip_address
                        )
                    except Exception as e:
                        logger.warning(f'[EDIT_PROFILE] Email notification failed for user {request.user.id}: {str(e)}')

                messages.success(request, 'Perfil editado com sucesso!')
            except Exception as e:
                messages.error(request, 'Ocorreu um erro ao editar o perfil. Verifique o log!')
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', e, exc_info=True)
        else:
            messages.error(request, 'Usuário da requisição não identificado!')
    else:
        messages.error(request, 'Método da requisição não permitido!')

    return redirect('perfil')


@login_required
@require_http_methods(["POST"])
def upload_avatar(request):
    """Processa upload de avatar do usuário com validação e otimização."""
    from .models import UserProfile
    from django.core.files.base import ContentFile
    from django.http import JsonResponse

    try:
        if 'avatar' not in request.FILES:
            return JsonResponse({'error': 'Nenhum arquivo enviado'}, status=400)

        avatar_file = request.FILES['avatar']

        # Validar tamanho (5MB)
        if avatar_file.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'Arquivo muito grande. Máximo: 5MB'}, status=400)

        # Validar tipo
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if avatar_file.content_type not in allowed_types:
            return JsonResponse({'error': 'Formato inválido. Use JPG, PNG, GIF ou WEBP'}, status=400)

        try:
            from PIL import Image

            # Processar imagem
            img = Image.open(avatar_file)

            # Converter RGBA para RGB se necessário
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background

            # Crop para quadrado (se necessário)
            width, height = img.size
            if width != height:
                size = min(width, height)
                left = (width - size) / 2
                top = (height - size) / 2
                right = (width + size) / 2
                bottom = (height + size) / 2
                img = img.crop((left, top, right, bottom))

            # Redimensionar para 500x500
            img = img.resize((500, 500), Image.Resampling.LANCZOS)

            # Salvar em buffer
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85, optimize=True)
            buffer.seek(0)

        except ImportError:
            return JsonResponse({'error': 'Biblioteca Pillow não instalada'}, status=500)
        except Exception as e:
            logger.error(f'[AVATAR_UPLOAD] Erro ao processar imagem: {str(e)}', exc_info=True)
            return JsonResponse({'error': 'Erro ao processar imagem'}, status=500)

        # Obter ou criar perfil
        profile, created = UserProfile.objects.get_or_create(user=request.user)

        # Deletar avatar antigo
        if profile.avatar:
            profile.delete_old_avatar()

        # Salvar novo avatar
        filename = f'avatar_{request.user.id}_{timezone.now().timestamp()}.jpg'
        profile.avatar.save(filename, ContentFile(buffer.read()), save=True)

        # Log da ação
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message='Avatar atualizado',
            extra={'avatar_url': profile.avatar.url}
        )

        # Enviar email de notificação (se habilitado)
        try:
            ip_address = get_client_ip(request) or 'Desconhecido'
            send_profile_change_notification(
                request.user,
                change_type='avatar',
                changes_detail={'avatar': 'Imagem de perfil atualizada'},
                ip_address=ip_address
            )
        except Exception as e:
            logger.warning(f'[UPLOAD_AVATAR] Email notification failed for user {request.user.id}: {str(e)}')

        return JsonResponse({
            'success': True,
            'avatar_url': profile.avatar.url,
            'message': 'Avatar atualizado com sucesso!'
        })

    except Exception as e:
        logger.error(f'[AVATAR_UPLOAD] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao processar avatar'}, status=500)


@login_required
@require_http_methods(["POST"])
def remove_avatar(request):
    """Remove avatar do usuário e restaura para padrão."""
    from .models import UserProfile
    from django.http import JsonResponse

    try:
        profile = UserProfile.objects.get(user=request.user)

        if profile.avatar:
            profile.delete_old_avatar()
            profile.avatar = None
            profile.save()

            log_user_action(
                request=request,
                action=UserActionLog.ACTION_UPDATE,
                instance=request.user,
                message='Avatar removido'
            )

            return JsonResponse({
                'success': True,
                'avatar_url': '/static/assets/images/avatar/default-avatar.svg',
                'message': 'Avatar removido com sucesso!'
            })

        return JsonResponse({'error': 'Nenhum avatar para remover'}, status=400)

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Perfil não encontrado'}, status=404)
    except Exception as e:
        logger.error(f'[AVATAR_REMOVE] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao remover avatar'}, status=500)


@login_required
def profile_activity_history(request):
    """Retorna histórico de alterações do perfil do usuário."""
    from .models import UserActionLog
    from django.http import JsonResponse
    from django.db.models import Q

    # Buscar logs onde:
    # 1. O usuário fez a ação (usuario=request.user)
    # 2. E a ação foi sobre o próprio perfil (entidade='User' e objeto_id=user.id)
    logs = UserActionLog.objects.filter(
        Q(usuario=request.user) &
        Q(entidade='User') &
        Q(objeto_id=str(request.user.id))
    ).order_by('-criado_em')[:10]

    history = []
    for log in logs:
        history.append({
            'timestamp': log.criado_em.strftime('%d/%m/%Y %H:%M'),
            'action': log.get_acao_display(),
            'message': log.mensagem,
            'ip': log.ip or '--',
        })

    return JsonResponse({'history': history})


@login_required
@require_http_methods(["POST"])
def change_password(request):
    """Processa alteração de senha do usuário com validações."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.contrib.auth import update_session_auth_hash
    from django.http import JsonResponse

    try:
        current_password = request.POST.get('current_password', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        # Validar senha atual
        if not request.user.check_password(current_password):
            return JsonResponse({
                'error': 'Senha atual incorreta',
                'field': 'current_password'
            }, status=400)

        # Validar senhas novas coincidem
        if new_password != confirm_password:
            return JsonResponse({
                'error': 'As senhas não coincidem',
                'field': 'confirm_password'
            }, status=400)

        # Validar que nova senha é diferente da atual
        if current_password == new_password:
            return JsonResponse({
                'error': 'A nova senha deve ser diferente da atual',
                'field': 'new_password'
            }, status=400)

        # Validar força da senha (Django validators)
        try:
            validate_password(new_password, request.user)
        except DjangoValidationError as e:
            return JsonResponse({
                'error': ' '.join(e.messages),
                'field': 'new_password'
            }, status=400)

        # Atualizar senha
        request.user.set_password(new_password)
        request.user.save()

        # Log da ação
        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message='Senha alterada com sucesso',
            extra={'ip': get_client_ip(request) or 'N/A'}
        )

        # Re-autenticar usuário para manter sessão
        update_session_auth_hash(request, request.user)

        # Enviar email de notificação (se habilitado)
        try:
            ip_address = get_client_ip(request) or 'Desconhecido'
            send_password_change_notification(request.user, ip_address=ip_address)
        except Exception as e:
            logger.warning(f'[CHANGE_PASSWORD] Email notification failed for user {request.user.id}: {str(e)}')

        return JsonResponse({
            'success': True,
            'message': 'Senha alterada com sucesso!'
        })

    except Exception as e:
        logger.error(f'[CHANGE_PASSWORD] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({
            'error': 'Erro ao alterar senha. Tente novamente.'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def change_theme(request):
    """Altera tema do usuário (light/dark/auto)."""
    from .models import UserProfile
    from django.http import JsonResponse

    try:
        theme = request.POST.get('theme', '').strip()

        # Validar tema
        valid_themes = ['light', 'dark', 'auto']
        if theme not in valid_themes:
            return JsonResponse({'error': 'Tema inválido'}, status=400)

        profile = UserProfile.objects.get(user=request.user)
        profile.theme_preference = theme
        profile.save()

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message=f'Tema alterado para {theme}',
            extra={'theme': theme}
        )

        return JsonResponse({
            'success': True,
            'theme': theme,
            'message': 'Tema alterado com sucesso!'
        })

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Perfil não encontrado'}, status=404)
    except Exception as e:
        logger.error(f'[CHANGE_THEME] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao alterar tema'}, status=500)


@login_required
@require_http_methods(["POST"])
def update_notification_preferences(request):
    """Atualiza preferências de notificação por email."""
    from .models import UserProfile
    from django.http import JsonResponse

    try:
        profile = UserProfile.objects.get(user=request.user)

        # Atualizar preferências
        profile.email_on_profile_change = request.POST.get('email_on_profile_change') == 'true'
        profile.email_on_password_change = request.POST.get('email_on_password_change') == 'true'
        profile.email_on_login = request.POST.get('email_on_login') == 'true'
        profile.save()

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message='Preferências de notificação atualizadas'
        )

        return JsonResponse({
            'success': True,
            'message': 'Preferências atualizadas com sucesso!'
        })

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Perfil não encontrado'}, status=404)
    except Exception as e:
        logger.error(f'[UPDATE_NOTIF_PREFS] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao atualizar preferências'}, status=500)


@login_required
@require_http_methods(["POST"])
def update_privacy_settings(request):
    """Atualiza configurações de privacidade."""
    from .models import UserProfile
    from django.http import JsonResponse

    try:
        profile = UserProfile.objects.get(user=request.user)

        # Atualizar configurações
        profile.profile_public = request.POST.get('profile_public') == 'true'
        profile.show_email = request.POST.get('show_email') == 'true'
        profile.show_phone = request.POST.get('show_phone') == 'true'
        profile.show_statistics = request.POST.get('show_statistics') == 'true'
        profile.save()

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message='Configurações de privacidade atualizadas'
        )

        return JsonResponse({
            'success': True,
            'message': 'Configurações atualizadas com sucesso!'
        })

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Perfil não encontrado'}, status=404)
    except Exception as e:
        logger.error(f'[UPDATE_PRIVACY] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao atualizar configurações'}, status=500)


@login_required
@require_http_methods(["POST"])
def setup_2fa(request):
    """Inicia configuração de 2FA gerando secret e retornando URL do QR code."""
    from .models import UserProfile
    from django.http import JsonResponse

    try:
        profile = UserProfile.objects.get(user=request.user)

        # Gerar nova chave secreta
        secret = profile.generate_2fa_secret()
        profile.save()

        # Obter URL para QR code
        qr_uri = profile.get_2fa_qr_code()

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message='Iniciou configuração de 2FA'
        )

        return JsonResponse({
            'success': True,
            'secret': secret,
            'qr_uri': qr_uri,
            'message': 'QR Code gerado com sucesso!'
        })

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Perfil não encontrado'}, status=404)
    except Exception as e:
        logger.error(f'[SETUP_2FA] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao configurar 2FA'}, status=500)


@login_required
@require_http_methods(["POST"])
def enable_2fa(request):
    """Ativa 2FA após validar código de verificação."""
    from .models import UserProfile
    from django.http import JsonResponse

    try:
        code = request.POST.get('code', '').strip()

        if not code:
            return JsonResponse({'error': 'Código não fornecido'}, status=400)

        profile = UserProfile.objects.get(user=request.user)

        if not profile.two_factor_secret:
            return JsonResponse({'error': '2FA não foi configurado'}, status=400)

        # Verificar código
        import pyotp
        totp = pyotp.TOTP(profile.two_factor_secret)
        if not totp.verify(code, valid_window=1):
            return JsonResponse({'error': 'Código inválido'}, status=400)

        # Ativar 2FA
        profile.two_factor_enabled = True

        # Gerar códigos de backup
        backup_codes = profile.generate_backup_codes()
        profile.save()

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message='2FA ativado com sucesso'
        )

        # Enviar email de notificação
        try:
            send_2fa_enabled_notification(request.user)
        except Exception as e:
            logger.warning(f'[ENABLE_2FA] Email notification failed for user {request.user.id}: {str(e)}')

        return JsonResponse({
            'success': True,
            'backup_codes': backup_codes,
            'message': '2FA ativado com sucesso!'
        })

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Perfil não encontrado'}, status=404)
    except Exception as e:
        logger.error(f'[ENABLE_2FA] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao ativar 2FA'}, status=500)


@login_required
@require_http_methods(["POST"])
def disable_2fa(request):
    """Desativa 2FA após validar senha do usuário."""
    from .models import UserProfile
    from django.http import JsonResponse
    from django.contrib.auth import authenticate

    try:
        password = request.POST.get('password', '').strip()

        if not password:
            return JsonResponse({'error': 'Senha não fornecida'}, status=400)

        # Verificar senha
        user = authenticate(username=request.user.username, password=password)
        if not user:
            return JsonResponse({'error': 'Senha incorreta'}, status=400)

        profile = UserProfile.objects.get(user=request.user)

        # Desativar 2FA
        profile.two_factor_enabled = False
        profile.two_factor_secret = None
        profile.two_factor_backup_codes = None
        profile.save()

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message='2FA desativado'
        )

        return JsonResponse({
            'success': True,
            'message': '2FA desativado com sucesso!'
        })

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Perfil não encontrado'}, status=404)
    except Exception as e:
        logger.error(f'[DISABLE_2FA] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao desativar 2FA'}, status=500)


@login_required
@require_http_methods(["POST"])
def regenerate_backup_codes(request):
    """Gera novos códigos de backup para 2FA."""
    from .models import UserProfile
    from django.http import JsonResponse

    try:
        password = request.POST.get('password', '').strip()

        if not password:
            return JsonResponse({'error': 'Senha não fornecida'}, status=400)

        # Verificar senha
        from django.contrib.auth import authenticate
        user = authenticate(username=request.user.username, password=password)
        if not user:
            return JsonResponse({'error': 'Senha incorreta'}, status=400)

        profile = UserProfile.objects.get(user=request.user)

        if not profile.two_factor_enabled:
            return JsonResponse({'error': '2FA não está ativado'}, status=400)

        # Gerar novos códigos
        backup_codes = profile.generate_backup_codes()
        profile.save()

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_UPDATE,
            instance=request.user,
            message='Códigos de backup regenerados'
        )

        return JsonResponse({
            'success': True,
            'backup_codes': backup_codes,
            'message': 'Novos códigos de backup gerados!'
        })

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Perfil não encontrado'}, status=404)
    except Exception as e:
        logger.error(f'[REGEN_BACKUP] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Erro ao gerar códigos'}, status=500)


@login_required
@require_http_methods(["GET"])
def get_2fa_qr_code(request):
    """Retorna imagem do QR code para configuração de 2FA."""
    from .models import UserProfile
    from django.http import HttpResponse
    import qrcode
    from io import BytesIO

    try:
        profile = UserProfile.objects.get(user=request.user)

        if not profile.two_factor_secret:
            return HttpResponse('2FA não configurado', status=400)

        # Obter URL do QR code
        qr_uri = profile.get_2fa_qr_code()

        # Gerar QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Salvar em buffer
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        return HttpResponse(buffer, content_type='image/png')

    except UserProfile.DoesNotExist:
        return HttpResponse('Perfil não encontrado', status=404)
    except Exception as e:
        logger.error(f'[GET_QR_CODE] User: {request.user.id}, Error: {str(e)}', exc_info=True)
        return HttpResponse('Erro ao gerar QR code', status=500)


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
        ip_address = get_client_ip(request)
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
        {"tipo_plano": "desconto", "valor": 0.00, "valor_minimo_mensalidade": 5.00, "limite_indicacoes": 0},
        {"tipo_plano": "dinheiro", "valor": 0.00, "valor_minimo_mensalidade": 5.00, "limite_indicacoes": 0},
        {"tipo_plano": "anuidade", "valor": 0.00, "valor_minimo_mensalidade": 5.00, "limite_indicacoes": 0},
        {"tipo_plano": "desconto_progressivo", "valor": 0.00, "valor_minimo_mensalidade": 5.00, "limite_indicacoes": 0},
    ]
    usuario = request.user
    sessao = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    sessao_wpp = bool(sessao)

    if request.method == "GET":
        # Criação automática dos planos se não existirem
        with transaction.atomic():
            for plano_data in PLANOS_OBRIGATORIOS:
                # Define se o plano é ativo por padrão (anuidade é inativo)
                ativo = True if plano_data["tipo_plano"] != "anuidade" else False

                if not PlanoIndicacao.objects.filter(usuario=usuario, tipo_plano=plano_data["tipo_plano"]).exists():
                    novo_plano = PlanoIndicacao.objects.create(
                        usuario=usuario,
                        nome=plano_data["tipo_plano"],
                        tipo_plano=plano_data["tipo_plano"],
                        valor=Decimal(str(plano_data["valor"])),
                        valor_minimo_mensalidade=Decimal(str(plano_data["valor_minimo_mensalidade"])),
                        limite_indicacoes=plano_data.get("limite_indicacoes", 0),
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
                "limite_indicacoes": plano.limite_indicacoes,
                "status": plano.status,
            })

        return JsonResponse({"planos": planos_json, "sessao_wpp": sessao_wpp}, status=200)

    elif request.method == "POST":
        ip_address = get_client_ip(request)
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
            "limite_indicacoes": plano.limite_indicacoes,
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
        if "limite_indicacoes" in data:
            try:
                plano.limite_indicacoes = int(data["limite_indicacoes"])
                if plano.limite_indicacoes < 0:
                    plano.limite_indicacoes = 0
            except (ValueError, TypeError):
                logger.warning(
                    "Limite de indicações inválido recebido para plano %s do usuário %s (ip=%s): %s",
                    plano_id,
                    request.user,
                    ip_address,
                    data.get("limite_indicacoes"),
                )
                return JsonResponse({"error": "Limite de indicações inválido."}, status=400)

        # Validação de modalidades conflitantes
        if plano.status:  # Se está sendo ativado
            modalidades_conflitantes = []

            # Se está ativando "Desconto Progressivo", verificar se "Desconto" ou "Bônus" estão ativos
            if plano.tipo_plano == "desconto_progressivo":
                conflitos = PlanoIndicacao.objects.filter(
                    usuario=usuario,
                    tipo_plano__in=["desconto", "dinheiro"],
                    ativo=True,
                    status=True
                ).exclude(id=plano.id)

                if conflitos.exists():
                    for conflito in conflitos:
                        nome_display = conflito.get_nome_display()
                        modalidades_conflitantes.append(nome_display)

            # Se está ativando "Desconto" ou "Bônus", verificar se "Desconto Progressivo" está ativo
            elif plano.tipo_plano in ["desconto", "dinheiro"]:
                conflito = PlanoIndicacao.objects.filter(
                    usuario=usuario,
                    tipo_plano="desconto_progressivo",
                    ativo=True,
                    status=True
                ).exclude(id=plano.id).first()

                if conflito:
                    modalidades_conflitantes.append(conflito.get_nome_display())

            # Se há conflitos, retornar erro
            if modalidades_conflitantes:
                modalidades_str = ", ".join(modalidades_conflitantes)
                mensagem_erro = (
                    f"Não é possível ativar '{plano.get_nome_display()}' enquanto "
                    f"'{modalidades_str}' estiver(em) ativo(s). "
                    f"Desative a(s) modalidade(s) conflitante(s) primeiro."
                )
                logger.warning(
                    "Tentativa de ativar planos conflitantes (user=%s, ip=%s): %s",
                    request.user,
                    ip_address,
                    mensagem_erro,
                )
                return JsonResponse({"error": mensagem_erro}, status=400)

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
        if original_plano["limite_indicacoes"] != plano.limite_indicacoes:
            changes["limite_indicacoes"] = (original_plano["limite_indicacoes"], plano.limite_indicacoes)

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
                "limite_indicacoes": plano.limite_indicacoes,
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
    dispositivo_id = request.POST.get('dispositivo_id')
    force_create = request.POST.get('force_create') == 'true'  # Prosseguir mesmo com aviso

    app = get_object_or_404(Aplicativo, id=app_id, usuario=request.user)
    cliente = get_object_or_404(Cliente, id=cliente_id, usuario=request.user)
    dispositivo = get_object_or_404(Dispositivo, id=dispositivo_id, usuario=request.user)

    device_id = request.POST.get('device-id') or None
    device_key = request.POST.get('device-key') or None
    app_email = request.POST.get('app-email') or None

    # ⭐ FASE 1: Validação de limite de dispositivos
    try:
        assinatura = cliente.assinatura

        # Verificar limite ANTES de criar (se não for forced)
        if not force_create:
            validacao = assinatura.validar_limite_dispositivos()

            # DEBUG: Log para verificar o estado atual
            logger.info(
                f"[VALIDACAO_LIMITE] Cliente: {cliente.nome} - "
                f"Plano: {assinatura.plano.nome} - "
                f"Telas: {assinatura.plano.telas} - "
                f"Max_dispositivos: {assinatura.plano.max_dispositivos} - "
                f"Dispositivos_usados: {assinatura.dispositivos_usados} - "
                f"No_limite: {validacao['no_limite']} - "
                f"Excedeu: {validacao['excedeu']}"
            )

            # Só exibe aviso se ao adicionar este dispositivo, vai IGUALAR OU EXCEDER o limite
            # Exemplo: Plano com 3 telas, cliente tem 2 dispositivos
            #   -> 2 < 3, não exibe aviso (ainda pode adicionar)
            # Exemplo: Plano com 3 telas, cliente tem 3 dispositivos
            #   -> 3 >= 3, exibe aviso (vai exceder ao adicionar mais um)
            # Exemplo: Plano com 3 telas, cliente tem 4 dispositivos
            #   -> 4 >= 3, exibe aviso (já excedeu)
            if validacao['no_limite'] or validacao['excedeu']:
                return JsonResponse({
                    'warning': True,
                    'dados_aviso': {
                        'plano': {
                            'nome': assinatura.plano.nome,
                            'max_dispositivos': assinatura.plano.max_dispositivos
                        },
                        'usado': {
                            'dispositivos': assinatura.dispositivos_usados
                        }
                    }
                }, status=200)

    except AttributeError:
        # Cliente não tem assinatura - permitir criação mas logar aviso
        logger.warning(
            f"[ASSINATURA] Cliente {cliente.nome} (ID: {cliente.id}) não possui AssinaturaCliente. "
            f"Criando dispositivo sem validação de limite."
        )

    # Verificar se é a primeira conta deste cliente (deve ser principal)
    total_contas_existentes = ContaDoAplicativo.objects.filter(cliente=cliente).count()
    is_primeira_conta = (total_contas_existentes == 0)

    nova_conta_app = ContaDoAplicativo(
        cliente=cliente,
        dispositivo=dispositivo,
        app=app,
        device_id=device_id,
        device_key=device_key,
        email=app_email,
        usuario=request.user,
        is_principal=is_primeira_conta,  # Primeira conta = principal
    )

    try:
        nova_conta_app.save()

        # ⭐ FASE 1: Incrementar contador após criação bem-sucedida
        try:
            assinatura = cliente.assinatura
            assinatura.dispositivos_usados += 1
            assinatura.save(update_fields=['dispositivos_usados'])

            # Logar se excedeu o limite
            validacao = assinatura.validar_limite_dispositivos()
            if validacao['excedeu']:
                logger.warning(
                    f"[LIMITE_EXCEDIDO] Cliente {cliente.nome} - "
                    f"Dispositivos: {assinatura.dispositivos_usados}/{assinatura.plano.max_dispositivos} "
                    f"(Excesso: +{validacao['excesso']})"
                )
        except AttributeError:
            pass  # Cliente sem assinatura, já logado acima

        log_user_action(
            request=request,
            action=UserActionLog.ACTION_CREATE,
            instance=nova_conta_app,
            message="Conta de aplicativo criada.",
            extra={
                "cliente": cliente.nome,
                "dispositivo": dispositivo.nome,
                "app": app.nome,
                "device_id": device_id or '',
                "email": app_email or '',
            },
        )
        return JsonResponse({'success_message_cancel': 'Conta do aplicativo cadastrada com sucesso!'}, status=200)
    except Exception as erro:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro, exc_info=True)
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
        telefone = post.get('telefone', '').strip()
        notas = post.get('notas', '').strip()
        indicador_nome = post.get('indicador_list', '').strip()
        servidor_nome = post.get('servidor', '').strip()
        forma_pgto_nome = post.get('forma_pgto', '').strip()
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
            plano_telas = int(plano_info[2])
        except (IndexError, ValueError):
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": "Plano inválido.",
            })
        plano, _ = Plano.objects.get_or_create(nome=plano_nome, valor=plano_valor, telas=plano_telas, usuario=usuario)

        # Trata relacionados
        servidor, _ = Servidor.objects.get_or_create(nome=servidor_nome, usuario=usuario)
        forma_pgto, _ = Tipos_pgto.objects.get_or_create(nome=forma_pgto_nome, usuario=usuario)

        # Coleta dados de múltiplos dispositivos/apps/contas baseado na quantidade de telas
        telas_data = []
        for i in range(plano_telas):
            dispositivo_nome = post.get(f'dispositivo_{i}', '').strip()
            sistema_nome = post.get(f'sistema_{i}', '').strip()
            device_id = post.get(f'device_id_{i}', '').strip()
            email = post.get(f'email_{i}', '').strip()
            senha = post.get(f'senha_{i}', '').strip()

            if not dispositivo_nome or not sistema_nome:
                return render(request, "pages/cadastro-cliente.html", {
                    "error_message": f"Dispositivo e Aplicativo são obrigatórios para a Tela {i + 1}.",
                    'servidores': servidor_queryset,
                    'dispositivos': dispositivo_queryset,
                    'sistemas': sistema_queryset,
                    'indicadores': indicador_por_queryset,
                    'formas_pgtos': forma_pgto_queryset,
                    'planos': plano_queryset,
                    'page_group': page_group,
                    'page': page,
                })

            # Get or create dispositivo e sistema
            dispositivo, _ = Dispositivo.objects.get_or_create(nome=dispositivo_nome, usuario=usuario)
            sistema, _ = Aplicativo.objects.get_or_create(nome=sistema_nome, usuario=usuario)

            # Valida se conta é obrigatória
            if sistema.device_has_mac and not device_id and not email:
                return render(request, "pages/cadastro-cliente.html", {
                    "error_message": f"Conta do aplicativo é obrigatória para a Tela {i + 1}.",
                    'servidores': servidor_queryset,
                    'dispositivos': dispositivo_queryset,
                    'sistemas': sistema_queryset,
                    'indicadores': indicador_por_queryset,
                    'formas_pgtos': forma_pgto_queryset,
                    'planos': plano_queryset,
                    'page_group': page_group,
                    'page': page,
                })

            telas_data.append({
                'dispositivo': dispositivo,
                'sistema': sistema,
                'device_id': device_id,
                'email': email,
                'senha': senha,
            })

        try:
            with transaction.atomic():
                # SALVAR CLIENTE
                # Define dispositivo e sistema como o primeiro da lista (principal)
                primeiro_dispositivo = telas_data[0]['dispositivo'] if telas_data else None
                primeiro_sistema = telas_data[0]['sistema'] if telas_data else None

                try:
                    cliente = Cliente(
                        nome=nome,
                        telefone=telefone,
                        dispositivo=primeiro_dispositivo,
                        sistema=primeiro_sistema,
                        indicado_por=indicador,
                        servidor=servidor,
                        forma_pgto=forma_pgto,
                        plano=plano,
                        notas=notas,
                        usuario=usuario,
                    )
                    cliente.save()
                except Exception as e:
                    logger.error("Erro ao salvar o cliente: %s", e, exc_info=True)
                    raise Exception("Falha ao salvar os dados do cliente.")

                # CRIAR MÚLTIPLAS CONTAS DO APLICATIVO
                contas_criadas = 0
                try:
                    for idx, tela in enumerate(telas_data):
                        # Primeira conta (idx == 0) deve ser marcada como principal
                        ContaDoAplicativo.objects.create(
                            dispositivo=tela['dispositivo'],
                            app=tela['sistema'],
                            device_id=tela['device_id'] or None,
                            email=tela['email'] or None,
                            device_key=tela['senha'] or None,
                            cliente=cliente,
                            usuario=usuario,
                            is_principal=(idx == 0),  # Primeira conta = principal
                        )
                        contas_criadas += 1

                    # Incrementar contador de dispositivos usados
                    if contas_criadas > 0:
                        try:
                            assinatura = cliente.assinatura
                            assinatura.dispositivos_usados = contas_criadas
                            assinatura.save()
                        except Exception as e:
                            logger.warning(f"Erro ao atualizar contador de dispositivos: {e}")

                except Exception as e:
                    logger.error("Erro ao criar ContaDoAplicativo: %s", e, exc_info=True)
                    raise Exception("Falha ao criar as contas dos aplicativos.<p>Algum dos dados não pôde ser salvo.</p>")

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

                # Histórico de planos (inicial)
                try:
                    inicio_hist = cliente.data_adesao or timezone.localdate()
                    historico_iniciar(cliente, plano=plano, inicio=inicio_hist, motivo='create')
                except Exception:
                    pass

                # ⭐ FASE 2: Auto-enroll in campaign if eligible
                try:
                    from cadastros.utils import enroll_client_in_campaign_if_eligible
                    enroll_client_in_campaign_if_eligible(cliente)
                except Exception as e:
                    logger.error(f"Erro ao inscrever cliente na campanha: {e}", exc_info=True)

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
                        timezone.localtime(), usuario, get_client_ip(request) or 'IP não identificado', e, exc_info=True)
            return render(request, "pages/cadastro-cliente.html", {
                "error_message": str(e),
            })

    # Requisição GET (carrega formulário)

    # Serializar dispositivos e aplicativos para JSON (necessário para JavaScript)
    dispositivos_json = json.dumps([
        {'nome': d.nome}
        for d in dispositivo_queryset
    ])

    sistemas_json = json.dumps([
        {
            'nome': a.nome,
            'device_has_mac': a.device_has_mac
        }
        for a in sistema_queryset
    ])

    return render(request, "pages/cadastro-cliente.html", {
        'servidores': servidor_queryset,
        'dispositivos': dispositivo_queryset,
        'dispositivos_json': dispositivos_json,
        'sistemas': sistema_queryset,
        'sistemas_json': sistemas_json,
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
                # FASE 1: max_dispositivos = telas (automaticamente)
                # FASE 2: Campanhas não diferenciam planos (são atributos mutáveis)
                telas = int(request.POST.get('telas'))

                plano, created = Plano.objects.get_or_create(
                    nome=request.POST.get('nome'),
                    valor=int(request.POST.get('valor')),
                    telas=telas,
                    max_dispositivos=telas,  # ⭐ FASE 1: Dispositivos = Telas
                    usuario=usuario
                )

                # ⭐ FASE 2: Set campaign data (after creation)
                campanha_ativa = request.POST.get('campanha_ativa') == 'on'
                plano.campanha_ativa = campanha_ativa

                if campanha_ativa:
                    plano.campanha_tipo = request.POST.get('campanha_tipo', 'FIXO')
                    plano.campanha_data_inicio = request.POST.get('campanha_data_inicio') or None
                    plano.campanha_data_fim = request.POST.get('campanha_data_fim') or None
                    plano.campanha_duracao_meses = request.POST.get('campanha_duracao_meses') or None

                    if plano.campanha_tipo == 'FIXO':
                        plano.campanha_valor_fixo = request.POST.get('campanha_valor_fixo') or None
                    else:  # PERSONALIZADO
                        plano.campanha_valor_mes_1 = request.POST.get('campanha_valor_mes_1') or None
                        plano.campanha_valor_mes_2 = request.POST.get('campanha_valor_mes_2') or None
                        plano.campanha_valor_mes_3 = request.POST.get('campanha_valor_mes_3') or None
                        plano.campanha_valor_mes_4 = request.POST.get('campanha_valor_mes_4') or None
                        plano.campanha_valor_mes_5 = request.POST.get('campanha_valor_mes_5') or None
                        plano.campanha_valor_mes_6 = request.POST.get('campanha_valor_mes_6') or None
                else:
                    # Clear campaign data if not active
                    plano.campanha_tipo = None
                    plano.campanha_data_inicio = None
                    plano.campanha_data_fim = None
                    plano.campanha_duracao_meses = None
                    plano.campanha_valor_fixo = None
                    plano.campanha_valor_mes_1 = None
                    plano.campanha_valor_mes_2 = None
                    plano.campanha_valor_mes_3 = None
                    plano.campanha_valor_mes_4 = None
                    plano.campanha_valor_mes_5 = None
                    plano.campanha_valor_mes_6 = None

                plano.save()

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
                            "max_dispositivos": plano.max_dispositivos,  # ⭐ FASE 1
                            "campanha_ativa": plano.campanha_ativa,  # ⭐ FASE 2
                            "campanha_tipo": plano.campanha_tipo if plano.campanha_ativa else None,
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', e, exc_info=True)
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
        imagem = request.FILES.get("imagem")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                servidor, created = Servidor.objects.get_or_create(nome=nome, usuario=usuario)

                if created:
                    # Se foi enviada uma imagem, criar ServidorImagem
                    if imagem:
                        from .models import ServidorImagem
                        ServidorImagem.objects.create(
                            servidor=servidor,
                            usuario=usuario,
                            imagem=imagem
                        )

                    log_user_action(
                        request=request,
                        action=UserActionLog.ACTION_CREATE,
                        instance=servidor,
                        message="Servidor criado.",
                        extra={
                            "nome": servidor.nome,
                            "tem_imagem": bool(imagem),
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', e, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', e, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', e, exc_info=True)
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
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', e, exc_info=True)
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

            # ========== VALIDAÇÃO 1: Não pode deletar conta principal ==========
            if conta_app.is_principal:
                logger.warning(
                    f"[DELETE_APP_ACCOUNT] Tentativa de excluir conta principal (ID: {pk}) "
                    f"do cliente {conta_app.cliente.nome} (ID: {conta_app.cliente.id})"
                )
                return JsonResponse({
                    'error_message': 'Não é possível excluir a conta principal. Marque outra conta como principal antes de excluir esta.'
                }, status=400)

            # ========== VALIDAÇÃO 2: Cliente deve ter ao menos 1 conta ==========
            total_contas = ContaDoAplicativo.objects.filter(cliente=conta_app.cliente).count()
            if total_contas <= 1:
                logger.warning(
                    f"[DELETE_APP_ACCOUNT] Tentativa de excluir última conta (ID: {pk}) "
                    f"do cliente {conta_app.cliente.nome} (ID: {conta_app.cliente.id})"
                )
                return JsonResponse({
                    'error_message': 'Não é possível excluir a única conta do cliente. Todo cliente deve ter pelo menos 1 conta de aplicativo.'
                }, status=400)

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
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
            error_msg = 'Você tentou excluir uma conta de aplicativo que não existe.'
            
            return JsonResponse({'error_message': 'erro'}, status=500)
        
        except ProtectedError as erro2:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
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
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, get_client_ip(request) or 'N/A', erro2, exc_info=True)
        error_msg = 'Este Plano não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )

    return redirect('cadastro-plano-adesao')


######################################
############## OUTROS ################
######################################

def get_location_from_ip(ip):
    try:
        response = requests.get(f'https://ipapi.co/{ip}/json/', timeout=5)
        data = response.json()
        cidade = data.get('city', 'Desconhecida')
        pais = data.get('country_name', 'Desconhecido')
        return f"{cidade}, {pais}"
    except Exception:
        return "Localização desconhecida"


############################################
# API: Evolução do Patrimônio (JSON)
############################################

def _last_day_of_month(d: date) -> date:
    _, last = calendar.monthrange(d.year, d.month)
    return date(d.year, d.month, last)


@login_required
@require_GET
def evolucao_patrimonio(request):
    """Retorna patrimonio mensal e evolucao para o periodo solicitado (JSON)."""

    months_param_raw = (request.GET.get('months', '12') or '12').strip().lower()
    max_months = 120

    months_value: Optional[int]
    if months_param_raw == 'all':
        months_value = None
    else:
        try:
            months_value = int(months_param_raw)
        except ValueError:
            months_value = 12
        months_value = max(1, min(months_value, max_months))

    today_month = timezone.localdate().replace(day=1)
    months_list = []

    historico_qs = ClientePlanoHistorico.objects.filter(usuario=request.user)

    if months_value is None:
        first_inicio = historico_qs.aggregate(Min('inicio'))['inicio__min']
        if first_inicio:
            if isinstance(first_inicio, datetime):
                first_inicio = first_inicio.date()
            start_month = date(first_inicio.year, first_inicio.month, 1)
            if start_month > today_month:
                start_month = today_month
            cursor = start_month
            end_month = today_month
            while cursor <= end_month:
                months_list.append(cursor)
                if cursor.month == 12:
                    cursor = date(cursor.year + 1, 1, 1)
                else:
                    cursor = date(cursor.year, cursor.month + 1, 1)
        else:
            months_value = 12

    if months_value is not None and not months_list:
        cursor = today_month
        for _ in range(months_value):
            months_list.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        months_list.reverse()

    if not months_list:
        months_list = [today_month]

    categorias = []
    patrim = []

    for m in months_list:
        ref = _last_day_of_month(m)
        # ativos (sem fim) até a data de referência
        ativos = historico_qs.filter(
            inicio__lte=ref,
            fim__isnull=True,
        ).values_list('valor_plano', flat=True)
        # encerrados mas ainda ativos na data de referência (fim >= ref)
        encerrados = historico_qs.filter(
            inicio__lte=ref,
            fim__gte=ref,
        ).values_list('valor_plano', flat=True)

        total = sum((v or 0) for v in list(ativos) + list(encerrados))
        patrim.append(float(total))
        categorias.append(f"{m.month:02d}/{str(m.year)[2:]}")

    evol = []
    prev = None
    for val in patrim:
        if prev is None:
            evol.append(0.0)
        else:
            evol.append(float(val - prev))
        prev = val

    return JsonResponse({
        'categories': categorias,
        'series': [
            {'name': 'Patrimônio', 'data': patrim},
            {'name': 'Evolução', 'data': evol},
        ],
    })


@csrf_exempt
@require_POST
def internal_send_whatsapp(request):
    """
    Endpoint interno para envio de notificações WhatsApp ao admin.

    Restrito à rede interna (database-network) via InternalAPIMiddleware.
    Usado por scripts cron do servidor MySQL para enviar alertas ao admin.

    O número de destino é fixo (MEU_NUM_TIM do .env).

    Payload JSON esperado:
    {
        "mensagem": "Texto da notificação",
        "tipo": "backup|status|alert|info"  # Opcional, para logging (default: "unknown")
    }

    Segurança:
    - IP-restricted via InternalAPIMiddleware (apenas database-network)
    - CSRF exempt (seguro pois POST-only + IP restrito)
    - Sem autenticação de usuário (não necessária na rede interna)
    - Logging completo de todas as requisições

    Returns:
        JSON: {'success': bool, 'status_code': int, 'response': dict}
    """
    import requests
    from cadastros.services.logging import append_line

    # Diretório de logs
    log_path = Path("logs/MySQL_Triggers/whatsapp_notifications.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Parse do payload JSON
        data = json.loads(request.body.decode('utf-8'))
        mensagem = data.get('mensagem')
        tipo = data.get('tipo', 'unknown')

        # Validação de campo obrigatório
        if not mensagem:
            error_msg = "[ERROR] Campo obrigatório 'mensagem' não fornecido"
            append_line(str(log_path), error_msg)
            return JsonResponse({
                'success': False,
                'error': 'Campo obrigatório: mensagem'
            }, status=400)

        # Busca telefone fixo do admin no .env
        telefone_admin = os.getenv('MEU_NUM_TIM')
        if not telefone_admin:
            error_msg = "[ERROR] Variável MEU_NUM_TIM não configurada no .env"
            append_line(str(log_path), error_msg)
            return JsonResponse({
                'success': False,
                'error': 'Telefone admin não configurado (MEU_NUM_TIM)'
            }, status=500)

        # Busca sessão WhatsApp ativa do usuário admin (id=1)
        try:
            user_admin = User.objects.get(id=1)
            sessao = SessaoWpp.objects.filter(
                usuario=user_admin.username,
                is_active=True
            ).order_by('-dt_inicio').first()

            if not sessao:
                error_msg = f"[ERROR] Nenhuma sessão WhatsApp ativa para usuário {user_admin.username}"
                append_line(str(log_path), error_msg)
                return JsonResponse({
                    'success': False,
                    'error': 'Sessão WhatsApp não encontrada ou inativa'
                }, status=503)

        except User.DoesNotExist:
            error_msg = "[ERROR] Usuário admin (ID=1) não encontrado no banco"
            append_line(str(log_path), error_msg)
            return JsonResponse({
                'success': False,
                'error': 'Usuário admin não encontrado'
            }, status=500)

        # Prepara requisição para WPPConnect API
        url_api_wpp = os.getenv('URL_API_WPP', os.getenv('URL_API', 'http://api.nossopainel.com.br/api'))
        url = f"{url_api_wpp}/{sessao.usuario}/send-message"

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {sessao.token}'
        }

        body = {
            'phone': telefone_admin,
            'message': mensagem,
            'isGroup': False
        }

        # Envia mensagem via WPPConnect
        response = requests.post(url, headers=headers, json=body, timeout=30)

        # Registra resultado no log
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        client_ip = request.META.get('REMOTE_ADDR', 'unknown')

        log_entry = (
            f"[{timestamp}] "
            f"Tipo: {tipo} | "
            f"IP: {client_ip} | "
            f"Telefone: {telefone_admin} | "
            f"Status: {response.status_code} | "
            f"Response: {response.text[:200]}"
        )
        append_line(str(log_path), log_entry)

        # Retorna resposta baseada no status code
        if 200 <= response.status_code < 300:
            return JsonResponse({
                'success': True,
                'status_code': response.status_code,
                'response': response.json() if response.text else {}
            }, status=200)
        else:
            return JsonResponse({
                'success': False,
                'status_code': response.status_code,
                'response': response.json() if response.text else {'error': 'Resposta vazia da API'},
                'error': f'API retornou status {response.status_code}'
            }, status=response.status_code)

    except json.JSONDecodeError as e:
        error_msg = f"[ERROR] JSON inválido no body da requisição: {str(e)}"
        append_line(str(log_path), error_msg)
        return JsonResponse({
            'success': False,
            'error': 'Payload JSON inválido'
        }, status=400)

    except requests.Timeout:
        error_msg = f"[ERROR] Timeout ao conectar com API WhatsApp (tipo: {tipo})"
        append_line(str(log_path), error_msg)
        return JsonResponse({
            'success': False,
            'error': 'Timeout ao conectar com API WhatsApp'
        }, status=504)

    except requests.RequestException as e:
        error_msg = f"[ERROR] Erro na requisição HTTP: {str(e)}"
        append_line(str(log_path), error_msg)
        return JsonResponse({
            'success': False,
            'error': f'Erro na requisição: {str(e)}'
        }, status=500)

    except Exception as e:
        error_msg = f"[ERROR] Erro inesperado: {type(e).__name__} - {str(e)}"
        append_line(str(log_path), error_msg)
        return JsonResponse({
            'success': False,
            'error': f'Erro interno: {str(e)}'
        }, status=500)


########################################
# MIGRAÇÃO DE CLIENTES ENTRE USUÁRIOS #
########################################

class SuperuserRequiredMixin(UserPassesTestMixin):
    """Mixin que permite acesso apenas para superusuários"""
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        return JsonResponse({
            'error': 'Acesso negado. Apenas superusuários podem acessar esta funcionalidade.'
        }, status=403)


class MigrationClientesListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """
    View para listar clientes de um usuário específico para seleção na migração.

    Retorna dados formatados para popular DataTable com informações completas
    dos clientes (nome, servidor, status, plano, telefone, etc.)
    """

    def get(self, request):
        """Retorna lista de clientes do usuário especificado"""
        usuario_origem_id = request.GET.get('usuario_origem_id')

        if not usuario_origem_id:
            return JsonResponse({
                'error': 'ID do usuário de origem não informado.'
            }, status=400)

        try:
            usuario_origem = User.objects.get(id=usuario_origem_id)
        except User.DoesNotExist:
            return JsonResponse({
                'error': 'Usuário de origem não encontrado.'
            }, status=404)

        # Buscar clientes do usuário
        clientes = Cliente.objects.filter(
            usuario=usuario_origem
        ).select_related(
            'servidor', 'dispositivo', 'sistema', 'forma_pgto', 'plano', 'indicado_por'
        ).order_by('-data_adesao')

        # Serializar dados para DataTable
        clientes_data = []
        for cliente in clientes:
            clientes_data.append({
                'id': cliente.id,
                'nome': cliente.nome,
                'telefone': cliente.telefone or '-',
                'servidor': cliente.servidor.nome if cliente.servidor else '-',
                'dispositivo': cliente.dispositivo.nome if cliente.dispositivo else '-',
                'sistema': cliente.sistema.nome if cliente.sistema else '-',
                'plano': cliente.plano.nome if cliente.plano else '-',
                'plano_valor': float(cliente.plano.valor) if cliente.plano else 0,
                'forma_pgto': cliente.forma_pgto.nome if cliente.forma_pgto else '-',
                'status': 'Cancelado' if cliente.cancelado else 'Ativo',
                'status_class': 'danger' if cliente.cancelado else 'success',
                'data_cadastro': cliente.data_adesao.strftime('%d/%m/%Y') if cliente.data_adesao else '-',
                'data_cancelamento': cliente.data_cancelamento.strftime('%d/%m/%Y') if cliente.data_cancelamento else '-',
                'indicado_por': cliente.indicado_por.nome if cliente.indicado_por else '-',
                'uf': cliente.uf or '-',
            })

        return JsonResponse({
            'success': True,
            'clientes': clientes_data,
            'total': len(clientes_data),
            'usuario_origem': {
                'id': usuario_origem.id,
                'username': usuario_origem.username,
                'nome': usuario_origem.get_full_name() or usuario_origem.username,
            }
        })


class MigrationValidationView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """
    View para validar migração de clientes e retornar resumo detalhado.

    Executa todas as validações (indicações, descontos, entidades) e retorna
    estatísticas completas sobre o que será migrado.
    """

    def post(self, request):
        """Valida a migração e retorna resumo"""
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'JSON inválido no corpo da requisição.'
            }, status=400)

        usuario_origem_id = data.get('usuario_origem_id')
        usuario_destino_id = data.get('usuario_destino_id')
        clientes_ids = data.get('clientes_ids', [])

        # Validações básicas
        if not usuario_origem_id or not usuario_destino_id:
            return JsonResponse({
                'error': 'IDs de usuário de origem e destino são obrigatórios.'
            }, status=400)

        if usuario_origem_id == usuario_destino_id:
            return JsonResponse({
                'error': 'Usuário de origem e destino não podem ser iguais.'
            }, status=400)

        if not clientes_ids:
            return JsonResponse({
                'error': 'Nenhum cliente selecionado para migração.'
            }, status=400)

        try:
            usuario_origem = User.objects.get(id=usuario_origem_id)
            usuario_destino = User.objects.get(id=usuario_destino_id)
        except User.DoesNotExist:
            return JsonResponse({
                'error': 'Usuário de origem ou destino não encontrado.'
            }, status=404)

        # Importar serviço de migração
        from cadastros.services.migration_service import (
            ClientMigrationService,
            MigrationValidationError
        )

        # Executar validação
        service = ClientMigrationService(usuario_origem, usuario_destino)

        try:
            validation_result = service.validate_migration(clientes_ids)

            return JsonResponse({
                'success': True,
                'validation': validation_result,
                'usuario_origem': {
                    'id': usuario_origem.id,
                    'username': usuario_origem.username,
                    'nome': usuario_origem.get_full_name() or usuario_origem.username,
                },
                'usuario_destino': {
                    'id': usuario_destino.id,
                    'username': usuario_destino.username,
                    'nome': usuario_destino.get_full_name() or usuario_destino.username,
                }
            })

        except MigrationValidationError as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'validation_errors': service.validation_errors,
            }, status=400)

        except Exception as e:
            logger.exception(
                "Erro inesperado ao validar migração (user=%s, origem=%s, destino=%s)",
                request.user.username,
                usuario_origem_id,
                usuario_destino_id,
            )
            return JsonResponse({
                'success': False,
                'error': f'Erro interno ao validar migração: {str(e)}'
            }, status=500)


class MigrationExecuteView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """
    View para executar a migração de clientes entre usuários.

    Executa a migração de forma transacional (rollback em caso de erro)
    e registra todas as operações em UserActionLog.
    """

    def post(self, request):
        """Executa a migração de clientes"""
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'JSON inválido no corpo da requisição.'
            }, status=400)

        usuario_origem_id = data.get('usuario_origem_id')
        usuario_destino_id = data.get('usuario_destino_id')
        clientes_ids = data.get('clientes_ids', [])

        # Validações básicas
        if not usuario_origem_id or not usuario_destino_id:
            return JsonResponse({
                'error': 'IDs de usuário de origem e destino são obrigatórios.'
            }, status=400)

        if usuario_origem_id == usuario_destino_id:
            return JsonResponse({
                'error': 'Usuário de origem e destino não podem ser iguais.'
            }, status=400)

        if not clientes_ids:
            return JsonResponse({
                'error': 'Nenhum cliente selecionado para migração.'
            }, status=400)

        try:
            usuario_origem = User.objects.get(id=usuario_origem_id)
            usuario_destino = User.objects.get(id=usuario_destino_id)
        except User.DoesNotExist:
            return JsonResponse({
                'error': 'Usuário de origem ou destino não encontrado.'
            }, status=404)

        # Importar serviço de migração
        from cadastros.services.migration_service import (
            ClientMigrationService,
            MigrationValidationError
        )

        # Executar migração
        service = ClientMigrationService(usuario_origem, usuario_destino)

        try:
            # Executar migração (transacional)
            result = service.execute_migration(clientes_ids)

            # Registrar log da operação
            UserActionLog.objects.create(
                usuario=request.user,
                acao='migration',
                entidade='Cliente',
                objeto_id='',  # String vazia ao invés de None
                objeto_repr=f'{result["stats"]["clientes_migrados"]} clientes',
                mensagem=f'Migração de {result["stats"]["clientes_migrados"]} clientes de '
                         f'{usuario_origem.username} para {usuario_destino.username}',
                extras={
                    'usuario_origem_id': usuario_origem.id,
                    'usuario_destino_id': usuario_destino.id,
                    'clientes_ids': clientes_ids,
                    'stats': result['stats'],
                    'entities_created': result['entities_created'],
                },
                ip=get_client_ip(request),
                request_path=request.path,
            )

            logger.info(
                "Migração de clientes concluída com sucesso (admin=%s, origem=%s, destino=%s, clientes=%d)",
                request.user.username,
                usuario_origem.username,
                usuario_destino.username,
                result['stats']['clientes_migrados'],
            )

            return JsonResponse({
                'success': True,
                'result': result,
                'message': f'{result["stats"]["clientes_migrados"]} clientes migrados com sucesso!',
            })

        except MigrationValidationError as e:
            logger.warning(
                "Erro de validação ao executar migração (admin=%s, origem=%s, destino=%s): %s",
                request.user.username,
                usuario_origem_id,
                usuario_destino_id,
                str(e),
            )
            return JsonResponse({
                'success': False,
                'error': str(e),
            }, status=400)

        except Exception as e:
            logger.exception(
                "Erro inesperado ao executar migração (admin=%s, origem=%s, destino=%s)",
                request.user.username,
                usuario_origem_id,
                usuario_destino_id,
            )
            return JsonResponse({
                'success': False,
                'error': f'Erro interno ao executar migração: {str(e)}'
            }, status=500)


# ==================== VIEWS: GESTÃO DE DOMÍNIOS DNS (RESELLER AUTOMATION) ====================

@login_required
def gestao_dns_page(request):
    """
    Página principal de Gestão de Domínios DNS para automação reseller.

    Permite ao usuário:
    - Selecionar aplicativo (apenas os que suportam automação)
    - Fazer login manual no painel reseller (se necessário)
    - Configurar e iniciar migração DNS
    - Visualizar progresso em tempo real
    - Consultar histórico de tarefas

    Template: templates/pages/gestao-dns.html
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Case, When, Value, IntegerField

    # Busca apenas aplicativos que usam MAC e foram cadastrados pelo superuser
    # Ordenação: aplicativos com automação primeiro (DreamTV = 0), depois alfabético
    aplicativos = Aplicativo.objects.filter(
        device_has_mac=True,
        usuario__is_superuser=True
    ).annotate(
        prioridade=Case(
            When(nome__iexact='dreamtv', then=Value(0)),
            default=Value(1),
            output_field=IntegerField()
        )
    ).order_by('prioridade', 'nome')

    # Contas reseller do usuário
    contas = ContaReseller.objects.filter(usuario=request.user).select_related('aplicativo')

    # Verifica se foi solicitada uma tarefa específica
    tarefa_id = request.GET.get('tarefa_id')
    tarefa_selecionada = None
    dispositivos_tarefa = None

    if tarefa_id:
        try:
            tarefa_selecionada = TarefaMigracaoDNS.objects.get(
                id=tarefa_id,
                usuario=request.user
            )
            # Busca dispositivos da tarefa COM PAGINAÇÃO (10 por página)
            dispositivos_list = tarefa_selecionada.dispositivos.all().order_by('id')

            dispositivos_paginator = Paginator(dispositivos_list, 10)
            dispositivos_page = request.GET.get('dispositivos_page', 1)

            try:
                dispositivos_tarefa = dispositivos_paginator.page(dispositivos_page)
            except PageNotAnInteger:
                dispositivos_tarefa = dispositivos_paginator.page(1)
            except EmptyPage:
                dispositivos_tarefa = dispositivos_paginator.page(dispositivos_paginator.num_pages)
        except TarefaMigracaoDNS.DoesNotExist:
            pass

    # Tarefas recentes com paginação (10 por página)
    tarefas_list = TarefaMigracaoDNS.objects.filter(
        usuario=request.user
    ).select_related('aplicativo').order_by('-criada_em')

    paginator = Paginator(tarefas_list, 10)  # 10 tarefas por página
    page = request.GET.get('page', 1)

    try:
        tarefas_recentes = paginator.page(page)
    except PageNotAnInteger:
        tarefas_recentes = paginator.page(1)
    except EmptyPage:
        tarefas_recentes = paginator.page(paginator.num_pages)

    context = {
        'aplicativos': aplicativos,
        'contas': contas,
        'tarefas_recentes': tarefas_recentes,
        'tarefa_selecionada': tarefa_selecionada,
        'dispositivos_tarefa': dispositivos_tarefa,
        'page_title': 'Gestão de Domínios DNS',
    }

    return render(request, 'pages/gestao-dns.html', context)


@login_required
def obter_dispositivos_paginados_api(request):
    """
    API para obter dispositivos de uma tarefa de migração com paginação AJAX.

    GET Params:
        tarefa_id: ID da tarefa (obrigatório)
        page: Número da página (default: 1)
        status_filter: Filtro de status ('all', 'sucesso', 'erro', 'pulado') (default: 'all')

    Returns:
        JSON:
            - success: Boolean
            - dispositivos: Lista de dispositivos (dict)
            - pagination: Informações de paginação
            - estatisticas: Estatísticas da tarefa
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    try:
        tarefa_id = request.GET.get('tarefa_id')
        page = request.GET.get('page', 1)
        status_filter = request.GET.get('status_filter', 'all')

        if not tarefa_id:
            return JsonResponse({
                'success': False,
                'error': 'tarefa_id é obrigatório'
            }, status=400)

        # Busca tarefa (apenas do usuário logado)
        try:
            tarefa = TarefaMigracaoDNS.objects.get(
                id=tarefa_id,
                usuario=request.user
            )
        except TarefaMigracaoDNS.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Tarefa não encontrada'
            }, status=404)

        # Filtra dispositivos por status (se não for 'all')
        dispositivos_queryset = tarefa.dispositivos.all().order_by('id')

        if status_filter != 'all':
            dispositivos_queryset = dispositivos_queryset.filter(status=status_filter)

        # Paginação (10 por página)
        paginator = Paginator(dispositivos_queryset, 10)

        try:
            dispositivos_page = paginator.page(page)
        except PageNotAnInteger:
            dispositivos_page = paginator.page(1)
        except EmptyPage:
            dispositivos_page = paginator.page(paginator.num_pages)

        # Serializa dispositivos
        dispositivos_data = []
        for dispositivo in dispositivos_page:
            dispositivos_data.append({
                'device_id': dispositivo.device_id,
                'nome_dispositivo': dispositivo.nome_dispositivo or '-',
                'status': dispositivo.status,
                'dns_encontrado': extrair_dominio_de_url(dispositivo.dns_encontrado) if dispositivo.dns_encontrado else '-',
                'dns_atualizado': extrair_dominio_de_url(dispositivo.dns_atualizado) if dispositivo.dns_atualizado else '-',
                'mensagem_erro': dispositivo.mensagem_erro or ''
            })

        # Informações de paginação
        pagination_data = {
            'current_page': dispositivos_page.number,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count,
            'has_previous': dispositivos_page.has_previous(),
            'has_next': dispositivos_page.has_next(),
            'previous_page': dispositivos_page.previous_page_number() if dispositivos_page.has_previous() else None,
            'next_page': dispositivos_page.next_page_number() if dispositivos_page.has_next() else None,
            'page_range': list(paginator.page_range)
        }

        # Estatísticas da tarefa (sempre baseadas no total, não no filtro)
        estatisticas = {
            'total': tarefa.total_dispositivos,
            'sucessos': tarefa.sucessos,
            'falhas': tarefa.falhas,
            'pulados': tarefa.pulados,
            'processados': tarefa.processados
        }

        return JsonResponse({
            'success': True,
            'dispositivos': dispositivos_data,
            'pagination': pagination_data,
            'estatisticas': estatisticas,
            'status_filter_ativo': status_filter
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erro interno: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(['GET', 'POST'])
def verificar_conta_reseller_api(request):
    """
    API para verificar se usuário possui conta reseller válida para o aplicativo.

    GET/POST Params:
        aplicativo_id: ID do aplicativo

    Returns:
        JSON:
            - status: 'sem_conta' | 'sessao_expirada' | 'ok'
            - email: Email da conta (se existir)
            - ultimo_login: Data/hora do último login (se existir)
            - sessao_valida: Boolean
            - mensagem: Mensagem descritiva
    """
    try:
        # Aceita tanto GET quanto POST (GET usado no polling de login)
        aplicativo_id = request.POST.get('aplicativo_id') or request.GET.get('aplicativo_id')

        if not aplicativo_id:
            return JsonResponse({
                'success': False,
                'error': 'aplicativo_id é obrigatório'
            }, status=400)

        # Busca aplicativo
        try:
            aplicativo = Aplicativo.objects.get(id=aplicativo_id)
        except Aplicativo.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Aplicativo não encontrado'
            }, status=404)

        # Verifica se aplicativo tem automação implementada
        # NOTA: Por enquanto, apenas DreamTV tem automação
        if aplicativo.nome.lower() != 'dreamtv':
            return JsonResponse({
                'status': 'nao_implementado',
                'mensagem': f'Automação ainda não implementada para {aplicativo.nome}.'
            })

        # Busca conta reseller
        try:
            conta = ContaReseller.objects.get(
                usuario=request.user,
                aplicativo=aplicativo
            )
        except ContaReseller.DoesNotExist:
            return JsonResponse({
                'status': 'sem_conta',
                'mensagem': 'Você ainda não possui credenciais salvas para este aplicativo.'
            })

        # Verifica se sessão ainda é válida
        from cadastros.services.reseller_automation import DreamTVSeleniumAutomation

        service = DreamTVSeleniumAutomation(user=request.user, aplicativo=aplicativo)
        sessao_valida = service.verificar_sessao_valida()

        if not sessao_valida:
            return JsonResponse({
                'status': 'sessao_expirada',
                'email': conta.email_login,
                'ultimo_login': conta.ultimo_login.isoformat() if conta.ultimo_login else None,
                'sessao_valida': False,
                'login_progresso': conta.login_progresso,  # Progresso do login em andamento
                'mensagem': 'Sua sessão expirou. Faça login novamente.'
            })

        return JsonResponse({
            'status': 'ok',
            'email': conta.email_login,
            'ultimo_login': conta.ultimo_login.isoformat() if conta.ultimo_login else None,
            'sessao_valida': True,
            'login_progresso': conta.login_progresso,  # Progresso do login
            'mensagem': 'Conta autenticada e sessão válida.'
        })

    except Exception as e:
        logger.exception(f"Erro ao verificar conta reseller: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Erro interno: {str(e)}'
        }, status=500)


@login_required
@require_POST
def iniciar_login_manual_api(request):
    """
    API para iniciar processo de login automático no painel reseller.

    Utiliza CapSolver para resolver reCAPTCHA automaticamente.
    O navegador pode ser visível ou headless dependendo da configuração de debug.

    POST Params:
        aplicativo_id: ID do aplicativo
        email: Email/usuário para login
        senha: Senha para login

    Returns:
        JSON:
            - status: 'login_iniciado' | 'erro'
            - mensagem: Mensagem descritiva
    """
    try:
        aplicativo_id = request.POST.get('aplicativo_id')
        email = request.POST.get('email')
        senha = request.POST.get('senha')

        # Validações
        if not all([aplicativo_id, email, senha]):
            return JsonResponse({
                'success': False,
                'error': 'Campos obrigatórios: aplicativo_id, email, senha'
            }, status=400)

        # Busca aplicativo
        try:
            aplicativo = Aplicativo.objects.get(id=aplicativo_id)
        except Aplicativo.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Aplicativo não encontrado'
            }, status=404)

        # Verifica se aplicativo tem automação
        if aplicativo.nome.lower() != 'dreamtv':
            return JsonResponse({
                'success': False,
                'error': f'Automação não implementada para {aplicativo.nome}'
            }, status=400)

        # Salva ou atualiza credenciais (senha será criptografada)
        from cadastros.utils import encrypt_password

        conta, created = ContaReseller.objects.update_or_create(
            usuario=request.user,
            aplicativo=aplicativo,
            defaults={
                'email_login': email,
                'senha_login': encrypt_password(senha),
                'sessao_valida': False,  # Ainda não logou
            }
        )

        logger.info(
            f"[USER:{request.user.username}] Credenciais salvas para {aplicativo.nome} "
            f"({'criadas' if created else 'atualizadas'})"
        )

        # Inicia login automático em thread separada
        def fazer_login_thread():
            try:
                from cadastros.services.reseller_automation import DreamTVSeleniumAutomation

                service = DreamTVSeleniumAutomation(user=request.user, aplicativo=aplicativo)

                logger.info(
                    f"[USER:{request.user.username}] Iniciando login AUTOMÁTICO com CapSolver"
                )
                sucesso = service.fazer_login_automatico()

                if sucesso:
                    logger.info(
                        f"[USER:{request.user.username}] Login automático concluído com sucesso"
                    )
                else:
                    logger.warning(
                        f"[USER:{request.user.username}] Login automático falhou (timeout ou erro)"
                    )

            except Exception as e:
                logger.exception(
                    f"[USER:{request.user.username}] Erro na thread de login automático: {e}"
                )

        thread = threading.Thread(target=fazer_login_thread, daemon=True)
        thread.start()

        return JsonResponse({
            'status': 'login_iniciado',
            'mensagem': 'Automação iniciada. O sistema resolverá o reCAPTCHA automaticamente.',
        })

    except Exception as e:
        logger.exception(f"Erro ao iniciar login automático: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Erro interno: {str(e)}'
        }, status=500)


@login_required
@require_POST
def iniciar_migracao_dns_api(request):
    """
    API para iniciar tarefa de migração DNS em background.

    Valida inputs, cria tarefa no banco e inicia execução em thread separada.

    POST Params:
        aplicativo_id: ID do aplicativo
        tipo_migracao: 'todos' | 'especifico'
        mac_alvo: MAC Address (obrigatório se tipo='especifico')
        dominio_origem: Domínio DNS atual (protocolo+host+porta, ex: http://dominio.com:8080)
        dominio_destino: Novo domínio DNS (protocolo+host+porta)

    Returns:
        JSON:
            - status: 'iniciado' | 'erro'
            - tarefa_id: ID da tarefa criada (para polling)
            - mensagem: Mensagem descritiva
    """
    from cadastros.utils import validar_formato_dominio, extrair_dominio_de_url

    try:
        # Parse dados
        aplicativo_id = request.POST.get('aplicativo_id')
        tipo_migracao = request.POST.get('tipo_migracao')
        mac_alvo = request.POST.get('mac_alvo', '').strip()
        dominio_origem = request.POST.get('dominio_origem', '').strip()
        dominio_destino = request.POST.get('dominio_destino', '').strip()

        # Validações básicas
        if not all([aplicativo_id, tipo_migracao, dominio_origem, dominio_destino]):
            return JsonResponse({
                'success': False,
                'error': 'Campos obrigatórios: aplicativo_id, tipo_migracao, dominio_origem, dominio_destino'
            }, status=400)

        # Validação de formato de domínio
        if not validar_formato_dominio(dominio_origem):
            return JsonResponse({
                'success': False,
                'error': 'Domínio origem inválido. Formato esperado: http://dominio.com ou http://dominio.com:8080'
            }, status=400)

        if not validar_formato_dominio(dominio_destino):
            return JsonResponse({
                'success': False,
                'error': 'Domínio destino inválido. Formato esperado: http://dominio.com ou http://dominio.com:8080'
            }, status=400)

        if tipo_migracao not in [TarefaMigracaoDNS.TIPO_TODOS, TarefaMigracaoDNS.TIPO_ESPECIFICO]:
            return JsonResponse({
                'success': False,
                'error': 'tipo_migracao deve ser "todos" ou "especifico"'
            }, status=400)

        if tipo_migracao == TarefaMigracaoDNS.TIPO_ESPECIFICO and not mac_alvo:
            return JsonResponse({
                'success': False,
                'error': 'mac_alvo é obrigatório quando tipo_migracao="especifico"'
            }, status=400)

        # Busca aplicativo
        try:
            aplicativo = Aplicativo.objects.get(id=aplicativo_id)
        except Aplicativo.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Aplicativo não encontrado'
            }, status=404)

        # Busca conta reseller
        try:
            conta = ContaReseller.objects.get(
                usuario=request.user,
                aplicativo=aplicativo
            )
        except ContaReseller.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Conta reseller não encontrada. Faça login primeiro.'
            }, status=400)

        # Verifica se sessão é válida
        if not conta.sessao_valida:
            return JsonResponse({
                'success': False,
                'error': 'Sessão expirada. Faça login novamente.'
            }, status=400)

        # Validação específica: se tipo='especifico', validar se dispositivo existe
        if tipo_migracao == TarefaMigracaoDNS.TIPO_ESPECIFICO:
            # NOTA: Esta validação assume que você tem ContaDoAplicativo vinculado ao usuário
            # Ajuste conforme seu modelo de dados
            try:
                device = ContaDoAplicativo.objects.get(
                    usuario=request.user,
                    device_id=mac_alvo
                )

                # VALIDAÇÃO CRÍTICA: Extrai domínio da URL do dispositivo e compara
                if device.url_lista:
                    dominio_device = extrair_dominio_de_url(device.url_lista)

                    if dominio_device and dominio_device != dominio_origem:
                        return JsonResponse({
                            'success': False,
                            'error': f'Domínio atual do dispositivo ({dominio_device}) não corresponde ao domínio origem informado ({dominio_origem}).'
                        }, status=400)

            except ContaDoAplicativo.DoesNotExist:
                # Dispositivo não encontrado no banco local
                # Isso não é necessariamente um erro, pois pode existir apenas no painel reseller
                # Vamos permitir e deixar a validação para o momento da execução
                logger.warning(
                    f"[USER:{request.user.username}] Dispositivo {mac_alvo} não encontrado no banco local. "
                    "Migração será tentada mesmo assim."
                )

        # ===== OTIMIZAÇÃO v2.0: Receber cache de devices do frontend =====
        cached_devices_json = request.POST.get('cached_devices')

        # Cria tarefa
        tarefa = TarefaMigracaoDNS.objects.create(
            usuario=request.user,
            aplicativo=aplicativo,
            conta_reseller=conta,
            tipo_migracao=tipo_migracao,
            mac_alvo=mac_alvo if tipo_migracao == TarefaMigracaoDNS.TIPO_ESPECIFICO else '',
            dominio_origem=dominio_origem,
            dominio_destino=dominio_destino,
            status=TarefaMigracaoDNS.STATUS_INICIANDO,
            cached_devices=cached_devices_json if cached_devices_json else None,  # NOVO: cache temporário
        )

        logger.info(
            f"[USER:{request.user.username}] Tarefa de migração DNS criada: #{tarefa.id} "
            f"(tipo={tipo_migracao}, origem={dominio_origem}, destino={dominio_destino})"
        )

        # Inicia execução em thread
        def executar_migracao_thread():
            """Thread que executa a migração DNS."""
            try:
                from cadastros.services.reseller_automation import DreamTVSeleniumAutomation

                service = DreamTVSeleniumAutomation(user=request.user, aplicativo=aplicativo)
                service.executar_migracao(tarefa_id=tarefa.id)

            except Exception as e:
                logger.exception(
                    f"[TAREFA:{tarefa.id}] Erro na thread de migração: {e}"
                )

        thread = threading.Thread(target=executar_migracao_thread, daemon=True)
        thread.start()

        return JsonResponse({
            'status': 'iniciado',
            'tarefa_id': tarefa.id,
            'mensagem': 'Migração DNS iniciada. Aguarde o progresso.'
        })

    except Exception as e:
        logger.exception(f"Erro ao iniciar migração DNS: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Erro interno: {str(e)}'
        }, status=500)


@login_required
@require_GET
def consultar_progresso_migracao_api(request, tarefa_id):
    """
    API para consultar progresso de uma tarefa de migração DNS (polling).

    URL: /api/gestao-dns/progresso/<tarefa_id>/
    Method: GET

    Returns:
        JSON:
            - status: Status da tarefa
            - total_dispositivos: Total a serem migrados
            - processados: Quantidade já processada
            - sucessos: Quantidade com sucesso
            - falhas: Quantidade com erro
            - erro_geral: Mensagem de erro geral (se houver)
            - concluida: Boolean indicando se tarefa finalizou
            - dispositivos: Lista com status de cada dispositivo
    """
    try:
        # Busca tarefa (apenas do usuário logado - segurança)
        try:
            tarefa = TarefaMigracaoDNS.objects.get(
                id=tarefa_id,
                usuario=request.user
            )
        except TarefaMigracaoDNS.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Tarefa não encontrada ou você não tem permissão para acessá-la.'
            }, status=404)

        # Busca dispositivos processados
        dispositivos = tarefa.dispositivos.all().values(
            'device_id',
            'nome_dispositivo',
            'status',
            'dns_encontrado',
            'dns_atualizado',
            'mensagem_erro',
            'processado_em'
        )

        # Serializa processado_em para ISO format e extrai domínios
        from cadastros.utils import extrair_dominio_de_url

        dispositivos_list = []
        for disp in dispositivos:
            disp_dict = dict(disp)
            if disp_dict['processado_em']:
                disp_dict['processado_em'] = disp_dict['processado_em'].isoformat()

            # Extrair apenas domínio (não URL completa) para DNS encontrado e atualizado
            if disp_dict['dns_encontrado']:
                disp_dict['dns_encontrado'] = extrair_dominio_de_url(disp_dict['dns_encontrado'])
            if disp_dict['dns_atualizado']:
                disp_dict['dns_atualizado'] = extrair_dominio_de_url(disp_dict['dns_atualizado'])

            dispositivos_list.append(disp_dict)

        return JsonResponse({
            'status': tarefa.status,
            'etapa_atual': tarefa.etapa_atual,  # NEW: Etapa atual (iniciando, analisando, processando, concluida, cancelada)
            'mensagem_progresso': tarefa.mensagem_progresso,  # NEW: Mensagem dinâmica de progresso
            'progresso_percentual': tarefa.progresso_percentual,  # UPDATED: Usa valor direto do banco (0-100)
            'total_dispositivos': tarefa.total_dispositivos,
            'processados': tarefa.processados,
            'sucessos': tarefa.sucessos,
            'falhas': tarefa.falhas,
            'pulados': tarefa.pulados,
            'erro_geral': tarefa.erro_geral,
            'dominio_origem': tarefa.dominio_origem,  # Domínio DNS de origem (para cache update)
            'dominio_destino': tarefa.dominio_destino,  # Domínio DNS de destino (para cache update)
            'concluida': tarefa.esta_concluida(),
            'criada_em': tarefa.criada_em.isoformat(),
            'iniciada_em': tarefa.iniciada_em.isoformat() if tarefa.iniciada_em else None,
            'concluida_em': tarefa.concluida_em.isoformat() if tarefa.concluida_em else None,
            'dispositivos': dispositivos_list
        })

    except Exception as e:
        logger.exception(f"Erro ao consultar progresso da tarefa {tarefa_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Erro interno: {str(e)}'
        }, status=500)


@login_required
def listar_dominios_api(request):
    """
    API para listar domínios únicos de todos os dispositivos do reseller account.

    GET Params:
        aplicativo_id: ID do aplicativo

    Returns:
        JSON:
            - success: bool
            - dominios: List[{'dominio': str, 'count': int}]
            - error: str (se houver erro)
    """
    try:
        aplicativo_id = request.GET.get('aplicativo_id')

        if not aplicativo_id:
            return JsonResponse({'success': False, 'error': 'aplicativo_id é obrigatório'}, status=400)

        try:
            aplicativo = Aplicativo.objects.get(id=aplicativo_id)
        except Aplicativo.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Aplicativo não encontrado'}, status=404)

        # Obter conta reseller
        conta_reseller = ContaReseller.objects.filter(
            usuario=request.user,
            aplicativo=aplicativo
        ).first()

        if not conta_reseller or not conta_reseller.session_data:
            return JsonResponse({
                'success': False,
                'error': 'Conta reseller não encontrada ou sem sessão válida'
            }, status=400)

        # Extrair JWT do session_data
        try:
            session_data = json.loads(conta_reseller.session_data)
            jwt = session_data.get('jwt') or session_data.get('token')
        except:
            jwt = None

        if not jwt:
            return JsonResponse({
                'success': False,
                'error': 'JWT não encontrado na sessão. Faça login novamente.'
            }, status=400)

        # Inicializar API client
        from cadastros.services.lib.dream_tv_api import DreamTVAPI
        from cadastros.utils import extrair_dominio_de_url
        from cadastros.services.api_raw_logger import get_api_raw_logger
        from collections import Counter
        import time

        api = DreamTVAPI(jwt=jwt)

        # Inicializar logger RAW para registrar dados completos da API
        api_raw_logger = get_api_raw_logger()
        collection_start_time = time.time()

        # Log RAW: Início da coleta
        api_raw_logger.log_collection_start(
            user=request.user.username,
            app_name=aplicativo.nome,
            total_devices=0  # Será atualizado conforme dispositivos são processados
        )

        # v2.0: Coletar devices completos + domínios
        dominios_counter = Counter()
        devices_completos = []  # NOVO: armazena devices com playlists
        page = 1
        limit = 100

        logger.info(f"[listar_dominios_api] Iniciando coleta de devices completos para user={request.user.username}, app={aplicativo.nome}")

        while True:
            try:
                # Listar dispositivos
                devices_data = api.list_devices(page=page, limit=limit)
                devices = devices_data.get('rows', [])

                if not devices:
                    break  # Sem mais dispositivos

                logger.debug(f"[listar_dominios_api] Página {page}: {len(devices)} dispositivos")

                # Para cada dispositivo, listar playlists
                for device in devices:
                    device_id = device.get('id')  # ID numérico (usado para API)
                    device_mac = device.get('mac')  # MAC address real (usado no cache)

                    # Extrair nome do dispositivo (campo pode variar: comment, name, id)
                    nome_dispositivo = (
                        device.get('reseller_activation', {}).get('comment') or
                        device.get('comment') or
                        device.get('name') or
                        device_mac or
                        str(device_id)
                    )

                    # Log RAW: Device completo
                    api_raw_logger.log_device_raw(
                        device_id=device_id,
                        device_mac=device_mac or str(device_id),
                        device_name=nome_dispositivo,
                        raw_data=device  # JSON completo do device
                    )

                    try:
                        playlists = api.list_playlists(device_id=device_id)

                        # NOVO: Estruturar playlists com domínio extraído
                        playlists_estruturadas = []
                        for playlist in playlists:
                            url = playlist.get('url', '')
                            dominio = extrair_dominio_de_url(url) if url else None

                            # Log RAW: Playlist completa
                            api_raw_logger.log_playlist_raw(
                                device_id=device_id,
                                playlist_id=playlist.get('id'),
                                playlist_name=playlist.get('name', 'Sem nome'),
                                raw_data=playlist  # JSON completo da playlist
                            )

                            playlists_estruturadas.append({
                                'id': playlist.get('id'),
                                'name': playlist.get('name', 'Sem nome'),
                                'url': url,
                                'dominio': dominio,
                                'is_selected': playlist.get('is_selected', False),
                                'deviceId': playlist.get('deviceId')  # Preservar deviceId numérico para updates
                            })

                            # Contar domínios para lista de domínios únicos
                            if dominio:
                                dominios_counter[dominio] += 1

                        # NOVO: Adicionar device completo ao array
                        devices_completos.append({
                            'device_id': device_mac,  # MAC real (ex: 00:1A:79:XX:XX:XX)
                            'nome_dispositivo': nome_dispositivo,
                            'playlists': playlists_estruturadas
                        })

                    except Exception as e:
                        logger.warning(f"[listar_dominios_api] Erro ao buscar playlists do device {device_mac}: {e}")
                        # NOVO: Mesmo com erro, adicionar device sem playlists
                        devices_completos.append({
                            'device_id': device_mac,  # MAC real (ex: 00:1A:79:XX:XX:XX)
                            'nome_dispositivo': nome_dispositivo,
                            'playlists': []
                        })
                        continue

                    # Delay para evitar rate limiting da API (429) - reduzido de 0.2 para 0.05
                    import time
                    time.sleep(0.05)  # 50ms entre cada requisição (economia de ~26s para 175 devices)

                # Verificar se há mais páginas
                total = devices_data.get('count', 0)
                if page * limit >= total:
                    break

                page += 1

            except Exception as e:
                logger.error(f"[listar_dominios_api] Erro ao listar devices na página {page}: {e}")
                break

        # Formatar resultado (ordenar por count DESC)
        dominios_list = [
            {'dominio': dominio, 'count': count}
            for dominio, count in dominios_counter.most_common()
        ]

        logger.info(f"[listar_dominios_api] Coleta finalizada: {len(devices_completos)} dispositivos, {len(dominios_list)} domínios únicos")

        # Log RAW: Fim da coleta (sucesso)
        collection_duration = time.time() - collection_start_time
        total_playlists = sum(len(d['playlists']) for d in devices_completos)
        api_raw_logger.log_collection_end(
            user=request.user.username,
            app_name=aplicativo.nome,
            status="success",
            duration_seconds=collection_duration,
            devices_processed=len(devices_completos),
            playlists_total=total_playlists
        )

        return JsonResponse({
            'success': True,
            'devices': devices_completos,  # NOVO: devices completos
            'dominios': dominios_list,      # mantém para compatibilidade
            'total_dispositivos': len(devices_completos),
            'total_dominios': len(dominios_list)
        })

    except Exception as e:
        # Log RAW: Fim da coleta (erro)
        try:
            collection_duration = time.time() - collection_start_time
            total_playlists = sum(len(d['playlists']) for d in devices_completos) if devices_completos else 0
            api_raw_logger.log_collection_end(
                user=request.user.username,
                app_name=aplicativo.nome,
                status="error",
                duration_seconds=collection_duration,
                devices_processed=len(devices_completos),
                playlists_total=total_playlists,
                error=str(e)
            )
        except:
            pass  # Se log falhar, não impedir o erro original

        logger.exception(f"[listar_dominios_api] Erro geral: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def buscar_dispositivo_api(request):
    """
    API para buscar dispositivo por MAC e listar suas playlists.

    POST Body:
        aplicativo_id: ID do aplicativo
        mac_address: MAC address do dispositivo

    Returns:
        JSON:
            - success: bool
            - device: Dict com dados do dispositivo
            - playlists: List[Dict] com playlists e domínios extraídos
            - error: str (se houver erro)
    """
    try:
        data = json.loads(request.body)
        aplicativo_id = data.get('aplicativo_id')
        mac_address = data.get('mac_address', '').strip().upper()

        if not aplicativo_id or not mac_address:
            return JsonResponse({
                'success': False,
                'error': 'aplicativo_id e mac_address são obrigatórios'
            }, status=400)

        try:
            aplicativo = Aplicativo.objects.get(id=aplicativo_id)
        except Aplicativo.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Aplicativo não encontrado'}, status=404)

        # Obter conta reseller
        conta_reseller = ContaReseller.objects.filter(
            usuario=request.user,
            aplicativo=aplicativo
        ).first()

        if not conta_reseller or not conta_reseller.session_data:
            return JsonResponse({
                'success': False,
                'error': 'Conta reseller não encontrada ou sem sessão válida'
            }, status=400)

        # Extrair JWT
        try:
            session_data = json.loads(conta_reseller.session_data)
            jwt = session_data.get('jwt') or session_data.get('token')
        except:
            jwt = None

        if not jwt:
            return JsonResponse({
                'success': False,
                'error': 'JWT não encontrado na sessão. Faça login novamente.'
            }, status=400)

        # Inicializar API client
        from cadastros.services.lib.dream_tv_api import DreamTVAPI
        from cadastros.utils import extrair_dominio_de_url

        api = DreamTVAPI(jwt=jwt)

        # Buscar dispositivo por MAC
        logger.info(f"[buscar_dispositivo_api] Buscando dispositivo MAC={mac_address} para user={request.user.username}")

        devices_data = api.list_devices(page=1, limit=10, search={'mac': mac_address})
        devices = devices_data.get('rows', [])

        if not devices:
            return JsonResponse({
                'success': False,
                'error': f'Dispositivo com MAC {mac_address} não encontrado'
            }, status=404)

        device = devices[0]  # Primeiro resultado (MAC é único)
        device_id = device.get('id')

        # Extrair comment do reseller_activation
        reseller_activation = device.get('reseller_activation', {})
        comment = reseller_activation.get('comment', '')

        logger.debug(f"[buscar_dispositivo_api] Dispositivo encontrado: id={device_id}, comment={comment}")

        # Buscar playlists do dispositivo
        playlists_raw = api.list_playlists(device_id=device_id)

        # Extrair domínio de cada playlist
        playlists_formatted = []
        for playlist in playlists_raw:
            url = playlist.get('url', '')
            dominio = extrair_dominio_de_url(url) if url else ''

            playlists_formatted.append({
                'id': playlist.get('id'),
                'name': playlist.get('name', 'Sem nome'),
                'url': url,
                'dominio': dominio,
                'is_selected': playlist.get('is_selected', False)
            })

        logger.info(f"[buscar_dispositivo_api] Dispositivo {mac_address} possui {len(playlists_formatted)} playlist(s)")

        return JsonResponse({
            'success': True,
            'device': {
                'id': device.get('id'),
                'mac': device.get('mac'),
                'comment': comment,
                'activation_expired': device.get('activation_expired')
            },
            'playlists': playlists_formatted
        })

    except Exception as e:
        logger.exception(f"[buscar_dispositivo_api] Erro geral: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================================================================
# API - CONFIGURAÇÃO DEBUG HEADLESS (ADMIN)
# =====================================================================

@login_required
@require_http_methods(["POST"])
def toggle_debug_headless(request):
    """
    Toggle do modo debug headless (apenas admin).
    Quando ativado, o navegador Playwright fica visível durante automação.
    """
    from cadastros.models import ConfiguracaoAutomacao

    # Apenas admins podem ativar debug mode
    if not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'erro': 'Permissão negada. Apenas administradores podem alterar o modo debug.'
        }, status=403)

    try:
        # Pega ou cria config para o usuário
        config, created = ConfiguracaoAutomacao.objects.get_or_create(user=request.user)

        # Inverte o estado
        config.debug_headless_mode = not config.debug_headless_mode
        config.save()

        status_msg = "ATIVADO" if config.debug_headless_mode else "DESATIVADO"
        logger.info(
            f"[ADMIN:{request.user.username}] Modo debug headless {status_msg}"
        )

        return JsonResponse({
            'success': True,
            'debug_mode': config.debug_headless_mode,
            'mensagem': f"Modo debug {status_msg}. "
                       f"{'Navegador ficará VISÍVEL durante próximas automações.' if config.debug_headless_mode else 'Navegador voltará a ser OCULTO (headless).'}"
        })

    except Exception as e:
        logger.exception(f"Erro ao toggle debug headless: {e}")
        return JsonResponse({
            'success': False,
            'erro': f'Erro ao alterar configuração: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_debug_status(request):
    """
    Retorna o status atual do modo debug headless.
    Usado para inicializar o estado do botão na interface.
    """
    from cadastros.models import ConfiguracaoAutomacao

    try:
        config = ConfiguracaoAutomacao.objects.filter(user=request.user).first()

        return JsonResponse({
            'success': True,
            'debug_mode': config.debug_headless_mode if config else False,
            'is_admin': request.user.is_staff
        })

    except Exception as e:
        logger.exception(f"Erro ao consultar status de debug: {e}")
        return JsonResponse({
            'success': False,
            'erro': f'Erro ao consultar status: {str(e)}'
        }, status=500)
