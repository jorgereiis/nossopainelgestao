"""
Views do Painel Administrativo.

Views disponiveis:
- AdminLoginView: Login para administradores
- DashboardAdminView: Visao geral do painel
- SubdominioListView: Lista de subdominios (Admin Superior)
- SubdominioCriarView: Criar subdominio (Admin Superior)
- SubdominioEditarView: Editar subdominio (Admin Superior)
- SubdominioExcluirView: Excluir subdominio (Admin Superior)
- PersonalizacaoView: Personalizar painel (Admin Comum)
- EstatisticasView: Estatisticas de acesso
"""

import logging
import magic

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db.models import Count, Sum
from django.utils import timezone
from django.conf import settings
from datetime import timedelta

from nossopainel.models import Cliente, Mensalidade, ContaBancaria

logger = logging.getLogger(__name__)

# Tipos MIME permitidos para upload de imagens
ALLOWED_IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
# Tamanho maximo de logo: 2MB (pode ser sobrescrito em settings.py)
MAX_LOGO_SIZE = getattr(settings, 'PAINEL_CLIENTE_MAX_LOGO_SIZE', 2 * 1024 * 1024)
from ..models import SubdominioPainelCliente, SessaoCliente
from ..decorators import admin_painel_required, admin_superior_required
from ..utils import validar_recaptcha, get_recaptcha_site_key


@method_decorator(ensure_csrf_cookie, name='get')
class AdminLoginView(View):
    """
    Login para administradores do painel.

    Permite que admins facam login usando credenciais do Django.
    """

    template_name = 'painel_cliente/admin/login.html'

    def get(self, request):
        """Exibe formulario de login."""
        # Se ja esta logado, redireciona para dashboard
        if request.user.is_authenticated:
            return redirect('painel_cliente:admin_dashboard')

        context = {
            'config': getattr(request, 'painel_config', None),
            'next': request.GET.get('next', '/painel-admin/'),
            'recaptcha_site_key': get_recaptcha_site_key(),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Processa login."""
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        next_url = request.POST.get('next', '/painel-admin/')
        config = getattr(request, 'painel_config', None)

        # Valida reCAPTCHA
        recaptcha_response = request.POST.get('g-recaptcha-response', '')
        recaptcha_valido, recaptcha_erro = validar_recaptcha(recaptcha_response)
        if not recaptcha_valido:
            context = {
                'config': config,
                'erro': recaptcha_erro,
                'username': username,
                'next': next_url,
                'recaptcha_site_key': get_recaptcha_site_key(),
            }
            return render(request, self.template_name, context)

        user = authenticate(request, username=username, password=password)

        if user is None:
            context = {
                'config': config,
                'erro': 'Usuario ou senha incorretos',
                'username': username,
                'next': next_url,
                'recaptcha_site_key': get_recaptcha_site_key(),
            }
            return render(request, self.template_name, context)

        # Verifica permissao ANTES de fazer login
        # Admin Superior (superuser) pode acessar qualquer painel
        if user.is_superuser:
            login(request, user)
            return redirect(next_url)

        # Admin Comum so pode acessar seu proprio subdominio
        if config and config.admin_responsavel == user:
            login(request, user)
            return redirect(next_url)

        # Usuario nao tem permissao para este painel
        context = {
            'config': config,
            'erro': 'Voce nao tem permissao para acessar este painel',
            'username': username,
            'next': next_url,
            'recaptcha_site_key': get_recaptcha_site_key(),
        }
        return render(request, self.template_name, context)


def admin_logout_view(request):
    """Logout do admin."""
    logout(request)
    return redirect('painel_cliente:admin_login')


class DashboardAdminView(View):
    """
    Dashboard principal do painel administrativo.

    Exibe:
    - Admin Superior: Todos os subdominios e estatisticas gerais
    - Admin Comum: Apenas seu subdominio e estatisticas
    """

    template_name = 'painel_cliente/admin/dashboard.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return admin_painel_required(view)

    def get(self, request):
        """Exibe dashboard administrativo."""
        config = request.painel_config
        is_superior = request.is_admin_superior

        context = {
            'config': config,
            'is_admin_superior': is_superior,
        }

        if is_superior:
            # Admin Superior ve todos os subdominios
            context['subdominios'] = SubdominioPainelCliente.objects.all()
            context['total_subdominios'] = SubdominioPainelCliente.objects.count()
            context['subdominios_ativos'] = SubdominioPainelCliente.objects.filter(
                ativo=True
            ).count()

            # Estatisticas gerais
            context['total_clientes'] = Cliente.objects.filter(
                usuario__in=User.objects.filter(subdominios_painel__isnull=False)
            ).count()

        else:
            # Admin Comum ve apenas seu subdominio
            admin_user = config.admin_responsavel

            # Estatisticas do subdominio
            context['total_clientes'] = Cliente.objects.filter(
                usuario=admin_user,
                cancelado=False
            ).count()

            context['clientes_ativos'] = Cliente.objects.filter(
                usuario=admin_user,
                cancelado=False,
                dados_atualizados_painel=True
            ).count()

            # Acessos recentes (ultimos 30 dias)
            desde = timezone.now() - timedelta(days=30)
            context['acessos_recentes'] = SessaoCliente.objects.filter(
                subdominio=config,
                criado_em__gte=desde
            ).count()

            # Mensalidades em aberto
            context['mensalidades_abertas'] = Mensalidade.objects.filter(
                cliente__usuario=admin_user,
                pgto=False,
                cancelado=False
            ).count()

        return render(request, self.template_name, context)


class SubdominioListView(View):
    """
    Lista todos os subdominios.

    Apenas Admin Superior pode acessar.
    """

    template_name = 'painel_cliente/admin/subdominios/lista.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return admin_superior_required(view)

    def get(self, request):
        """Lista subdominios."""
        subdominios = SubdominioPainelCliente.objects.select_related(
            'admin_responsavel',
            'criado_por'
        ).all()

        context = {
            'config': request.painel_config,
            'subdominios': subdominios,
            'is_admin_superior': True,
        }
        return render(request, self.template_name, context)


class SubdominioCriarView(View):
    """
    Criar novo subdominio.

    Apenas Admin Superior pode acessar.
    """

    template_name = 'painel_cliente/admin/subdominios/criar.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return admin_superior_required(view)

    def get(self, request):
        """Exibe formulario de criacao."""
        # Lista usuarios disponiveis para vincular
        usuarios = User.objects.filter(is_active=True).order_by('username')

        # Lista contas FastDePix disponiveis
        contas_fastdepix = ContaBancaria.objects.filter(
            instituicao__tipo_integracao='fastdepix'
        ).select_related('instituicao')

        context = {
            'config': request.painel_config,
            'usuarios': usuarios,
            'contas_fastdepix': contas_fastdepix,
            'is_admin_superior': True,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Cria novo subdominio."""
        # Valida dados
        subdominio = request.POST.get('subdominio', '').strip().lower()
        admin_id = request.POST.get('admin_responsavel')
        nome_exibicao = request.POST.get('nome_exibicao', '').strip()
        conta_id = request.POST.get('conta_bancaria')
        ativo = request.POST.get('ativo') == 'on'

        # Validacoes
        errors = []

        if not subdominio:
            errors.append('Subdominio e obrigatorio')
        elif not subdominio.isalnum() or len(subdominio) < 3:
            errors.append('Subdominio deve ter pelo menos 3 caracteres alfanumericos')
        elif SubdominioPainelCliente.objects.filter(subdominio=subdominio).exists():
            errors.append('Este subdominio ja esta em uso')

        if not admin_id:
            errors.append('Admin responsavel e obrigatorio')

        if not nome_exibicao:
            errors.append('Nome de exibicao e obrigatorio')

        if errors:
            usuarios = User.objects.filter(is_active=True).order_by('username')
            contas_fastdepix = ContaBancaria.objects.filter(
                instituicao__tipo_integracao='fastdepix'
            ).select_related('instituicao')

            context = {
                'config': request.painel_config,
                'usuarios': usuarios,
                'contas_fastdepix': contas_fastdepix,
                'is_admin_superior': True,
                'errors': errors,
                'form_data': request.POST,
            }
            return render(request, self.template_name, context)

        # Cria subdominio
        admin_user = get_object_or_404(User, id=admin_id)
        conta = None
        if conta_id:
            conta = get_object_or_404(ContaBancaria, id=conta_id)

        SubdominioPainelCliente.objects.create(
            subdominio=subdominio,
            admin_responsavel=admin_user,
            nome_exibicao=nome_exibicao,
            conta_bancaria=conta,
            ativo=ativo,
            criado_por=request.user
        )

        return redirect('painel_cliente:admin_subdominios')


class SubdominioEditarView(View):
    """
    Editar subdominio existente.

    Apenas Admin Superior pode acessar.
    """

    template_name = 'painel_cliente/admin/subdominios/editar.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return admin_superior_required(view)

    def get(self, request, pk):
        """Exibe formulario de edicao."""
        subdominio_obj = get_object_or_404(SubdominioPainelCliente, pk=pk)
        usuarios = User.objects.filter(is_active=True).order_by('username')
        contas_fastdepix = ContaBancaria.objects.filter(
            instituicao__tipo_integracao='fastdepix'
        ).select_related('instituicao')

        context = {
            'config': request.painel_config,
            'subdominio_obj': subdominio_obj,
            'usuarios': usuarios,
            'contas_fastdepix': contas_fastdepix,
            'is_admin_superior': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Atualiza subdominio."""
        subdominio_obj = get_object_or_404(SubdominioPainelCliente, pk=pk)

        # Atualiza campos
        admin_id = request.POST.get('admin_responsavel')
        if admin_id:
            subdominio_obj.admin_responsavel = get_object_or_404(User, id=admin_id)

        subdominio_obj.nome_exibicao = request.POST.get(
            'nome_exibicao',
            subdominio_obj.nome_exibicao
        ).strip()

        conta_id = request.POST.get('conta_bancaria')
        if conta_id:
            subdominio_obj.conta_bancaria = get_object_or_404(ContaBancaria, id=conta_id)
        else:
            subdominio_obj.conta_bancaria = None

        subdominio_obj.ativo = request.POST.get('ativo') == 'on'

        subdominio_obj.save()

        return redirect('painel_cliente:admin_subdominios')


class SubdominioExcluirView(View):
    """
    Excluir subdominio.

    Apenas Admin Superior pode acessar.
    """

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return admin_superior_required(view)

    def post(self, request, pk):
        """Exclui subdominio."""
        subdominio_obj = get_object_or_404(SubdominioPainelCliente, pk=pk)
        subdominio_obj.delete()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})

        return redirect('painel_cliente:admin_subdominios')


class PersonalizacaoView(View):
    """
    Personalizar visual do painel.

    Admin Comum pode editar apenas seu subdominio.
    Admin Superior pode editar qualquer subdominio.
    """

    template_name = 'painel_cliente/admin/personalizacao.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return admin_painel_required(view)

    def get(self, request):
        """Exibe formulario de personalizacao."""
        config = request.painel_config

        context = {
            'config': config,
            'is_admin_superior': request.is_admin_superior,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Atualiza personalizacao."""
        config = request.painel_config

        # Atualiza campos de personalizacao
        config.nome_exibicao = request.POST.get(
            'nome_exibicao',
            config.nome_exibicao
        ).strip()
        config.cor_primaria = request.POST.get(
            'cor_primaria',
            config.cor_primaria
        ).strip()
        config.cor_secundaria = request.POST.get(
            'cor_secundaria',
            config.cor_secundaria
        ).strip()
        config.whatsapp_suporte = request.POST.get(
            'whatsapp_suporte',
            config.whatsapp_suporte
        ).strip()
        config.mensagem_suporte = request.POST.get(
            'mensagem_suporte',
            config.mensagem_suporte
        ).strip()
        config.texto_boas_vindas = request.POST.get(
            'texto_boas_vindas',
            config.texto_boas_vindas
        ).strip()

        # Processa upload de logo com validacao de seguranca
        if 'logo' in request.FILES:
            logo_file = request.FILES['logo']

            # Valida tamanho do arquivo
            if logo_file.size > MAX_LOGO_SIZE:
                max_size_mb = MAX_LOGO_SIZE // (1024 * 1024)
                messages.error(
                    request,
                    f"Logo muito grande. Tamanho máximo: {max_size_mb}MB"
                )
                context = {
                    'config': config,
                    'is_admin_superior': request.is_admin_superior,
                }
                return render(request, self.template_name, context)

            # Valida tipo MIME real do arquivo
            try:
                # Le os primeiros bytes para detectar o tipo real
                file_mime = magic.from_buffer(logo_file.read(2048), mime=True)
                logo_file.seek(0)  # Retorna ao inicio do arquivo

                if file_mime not in ALLOWED_IMAGE_MIMES:
                    logger.warning(
                        f"[PainelCliente] Upload rejeitado: MIME {file_mime} nao permitido"
                    )
                    messages.error(
                        request,
                        "Tipo de arquivo não permitido. Use apenas: JPG, PNG, GIF ou WebP"
                    )
                    context = {
                        'config': config,
                        'is_admin_superior': request.is_admin_superior,
                    }
                    return render(request, self.template_name, context)

            except Exception as e:
                logger.error(f"[PainelCliente] Erro ao validar MIME: {e}")
                messages.error(request, "Erro ao processar arquivo. Tente novamente.")
                context = {
                    'config': config,
                    'is_admin_superior': request.is_admin_superior,
                }
                return render(request, self.template_name, context)

            # Arquivo validado, pode salvar
            config.logo = logo_file

        config.save()

        context = {
            'config': config,
            'is_admin_superior': request.is_admin_superior,
            'sucesso': True,
        }
        return render(request, self.template_name, context)


@admin_painel_required
def remover_logo_view(request):
    """Remove a logo do subdominio."""
    if request.method != 'POST':
        return redirect('painel_cliente:admin_personalizacao')

    config = request.painel_config

    # Remove o arquivo se existir
    if config.logo:
        config.logo.delete(save=False)
        config.logo = None
        config.save()

    # Resposta JSON para AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    return redirect('painel_cliente:admin_personalizacao')


class EstatisticasView(View):
    """
    Estatisticas de acesso e pagamentos.
    """

    template_name = 'painel_cliente/admin/estatisticas.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return admin_painel_required(view)

    def get(self, request):
        """Exibe estatisticas."""
        config = request.painel_config
        is_superior = request.is_admin_superior

        # Periodo de analise (ultimos 30 dias)
        desde = timezone.now() - timedelta(days=30)

        context = {
            'config': config,
            'is_admin_superior': is_superior,
        }

        if is_superior:
            # Estatisticas gerais de todos os subdominios
            context['sessoes_totais'] = SessaoCliente.objects.filter(
                criado_em__gte=desde
            ).count()

            context['subdominios_stats'] = SubdominioPainelCliente.objects.annotate(
                total_sessoes=Count('sessoes')
            ).order_by('-total_sessoes')[:10]

        else:
            # Estatisticas do subdominio especifico
            admin_user = config.admin_responsavel

            context['sessoes_mes'] = SessaoCliente.objects.filter(
                subdominio=config,
                criado_em__gte=desde
            ).count()

            context['clientes_com_acesso'] = SessaoCliente.objects.filter(
                subdominio=config,
                criado_em__gte=desde
            ).values('cliente').distinct().count()

            context['pagamentos_mes'] = Mensalidade.objects.filter(
                cliente__usuario=admin_user,
                pgto=True,
                dt_pagamento__gte=desde.date()
            ).aggregate(
                total=Count('id'),
                valor=Sum('valor')
            )

        return render(request, self.template_name, context)
