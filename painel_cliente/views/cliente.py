"""
Views do Cliente Final no Painel do Cliente.

Views disponiveis:
- LoginView: Autenticacao por telefone
- PerfilView: Atualizacao de dados cadastrais
- DashboardView: Visao geral de mensalidades
- PagamentoView: Pagamento via PIX
- HistoricoView: Historico de mensalidades
"""

import logging
import time
import random
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from ipware import get_client_ip

from nossopainel.models import Cliente, Mensalidade, CobrancaPix
from nossopainel.services.payment_integrations import (
    get_payment_integration,
    PaymentIntegrationError,
    PaymentStatus
)
from ..models import SessaoCliente, TentativaLogin
from ..utils import validar_recaptcha, get_recaptcha_site_key

logger = logging.getLogger(__name__)
from ..decorators import (
    cliente_login_required,
    cliente_login_required_ajax,
    cliente_dados_atualizados_required,
    painel_config_required
)
from ..middleware import PainelClienteSessionMiddleware


@method_decorator(ensure_csrf_cookie, name='get')
class LoginView(View):
    """
    View de login do cliente.

    GET: Exibe formulario de login
    POST: Processa autenticacao
    """

    template_name = 'painel_cliente/cliente/login.html'

    def get(self, request):
        """Exibe pagina de login."""
        # Se ja estiver logado, redireciona
        if getattr(request, 'cliente_sessao', None):
            cliente = request.cliente_sessao.cliente
            if cliente.dados_atualizados_painel:
                return redirect('painel_cliente:dashboard')
            return redirect('painel_cliente:perfil')

        context = {
            'config': request.painel_config,
            'recaptcha_site_key': get_recaptcha_site_key(),
        }
        return render(request, self.template_name, context)

    # Mensagem generica para evitar user enumeration
    MENSAGEM_LOGIN_FALHA = "Credenciais inválidas. Verifique o telefone ou fale com o suporte."

    def post(self, request):
        """Processa tentativa de login."""
        config = request.painel_config
        telefone = request.POST.get('telefone', '').strip()

        logger.debug(f"[PainelCliente LOGIN] Tentativa de login - Subdominio: {config.subdominio}")

        # Valida reCAPTCHA
        recaptcha_response = request.POST.get('g-recaptcha-response', '')
        recaptcha_valido, recaptcha_erro = validar_recaptcha(
            recaptcha_response,
            remote_ip=self._get_client_ip(request)
        )
        if not recaptcha_valido:
            logger.debug("[PainelCliente LOGIN] reCAPTCHA invalido")
            return self._render_error(request, recaptcha_erro)

        # Validacao basica
        if not telefone:
            logger.debug("[PainelCliente LOGIN] Telefone vazio")
            return self._render_error(
                request,
                'Por favor, informe seu telefone.'
            )

        # Verifica rate limiting
        ip_address = self._get_client_ip(request)
        logger.debug(f"[PainelCliente LOGIN] IP: {ip_address}")
        bloqueado, tentativas_restantes = TentativaLogin.verificar_bloqueio(
            ip_address, config
        )

        if bloqueado:
            logger.debug("[PainelCliente LOGIN] Rate limit atingido")
            return self._render_error(
                request,
                'Muitas tentativas de login. Aguarde 15 minutos.'
            )

        # Busca cliente pelo telefone
        cliente = self._buscar_cliente(telefone, config)

        # Delay aleatorio para evitar timing attacks (entre 0.1 e 0.3 segundos)
        time.sleep(random.uniform(0.1, 0.3))

        if not cliente:
            # Registra tentativa falha
            TentativaLogin.registrar(
                ip_address=ip_address,
                subdominio=config,
                identificador=telefone,
                sucesso=False
            )
            logger.debug("[PainelCliente LOGIN] Cliente nao encontrado")
            # Mensagem generica para evitar user enumeration
            return self._render_error(
                request,
                self.MENSAGEM_LOGIN_FALHA,
                tentativas_restantes=tentativas_restantes - 1
            )

        logger.debug(f"[PainelCliente LOGIN] Cliente encontrado: ID={cliente.id}")

        # Registra tentativa bem-sucedida
        TentativaLogin.registrar(
            ip_address=ip_address,
            subdominio=config,
            identificador=telefone,
            sucesso=True
        )

        # Cria sessao
        sessao = SessaoCliente.criar_sessao(
            cliente=cliente,
            subdominio=config,
            ip_address=ip_address,
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        logger.debug(f"[PainelCliente LOGIN] SUCESSO: Sessao criada para cliente ID={cliente.id}")

        # Atualiza ultimo acesso
        cliente.ultimo_acesso_painel = timezone.now()
        cliente.save(update_fields=['ultimo_acesso_painel'])

        # Redireciona
        if cliente.dados_atualizados_painel:
            response = redirect('painel_cliente:dashboard')
            logger.debug("[PainelCliente LOGIN] Redirecionando para: dashboard")
        else:
            response = redirect('painel_cliente:perfil')
            logger.debug("[PainelCliente LOGIN] Redirecionando para: perfil (primeiro acesso)")

        # Seta cookie de sessao
        # Em desenvolvimento (HTTP), nao usar Secure
        # Em producao (HTTPS), usar Secure
        is_secure = request.is_secure()
        host = request.META.get('HTTP_HOST', '').split(':')[0]  # Remove porta
        is_development = ':8003' in request.META.get('HTTP_HOST', '') or 'localhost' in host or '127.0.0.1' in host

        response.set_cookie(
            PainelClienteSessionMiddleware.COOKIE_NAME,
            sessao.token,
            max_age=24 * 60 * 60,  # 24 horas
            httponly=True,
            secure=False if is_development else is_secure,
            samesite='Lax',  # Lax permite cookies em redirecionamentos
            path='/',
        )

        return response

    def _buscar_cliente(self, telefone, config):
        """
        Busca cliente por telefone.

        Para telefones brasileiros (+55), tenta com e sem o 9 adicional.
        O cliente deve pertencer ao admin_responsavel do subdominio.

        IMPORTANTE: O telefone deve vir com DDI do frontend (intl-tel-input).
        """
        # Normaliza: mantém + e dígitos
        telefone_normalizado = ''.join(c for c in telefone if c.isdigit() or c == '+')

        # Garante que tenha o prefixo +
        if not telefone_normalizado.startswith('+'):
            telefone_normalizado = '+' + telefone_normalizado

        logger.debug(f"[PainelCliente LOGIN] Telefone normalizado: {telefone_normalizado}")

        # Primeira tentativa: busca exata
        cliente = Cliente.objects.select_related('plano').filter(
            telefone=telefone_normalizado,
            usuario=config.admin_responsavel
        ).first()

        if cliente:
            logger.debug("[PainelCliente LOGIN] Cliente encontrado na busca exata")
            return cliente

        # Se for brasileiro (+55), tenta variação com/sem 9
        if telefone_normalizado.startswith('+55'):
            variacao = self._gerar_variacao_brasileira(telefone_normalizado)
            if variacao:
                logger.debug(f"[PainelCliente LOGIN] Tentando variacao brasileira")
                cliente = Cliente.objects.select_related('plano').filter(
                    telefone=variacao,
                    usuario=config.admin_responsavel
                ).first()
                if cliente:
                    logger.debug("[PainelCliente LOGIN] Cliente encontrado com variacao")

        return cliente

    def _gerar_variacao_brasileira(self, telefone):
        """
        Gera variação do telefone brasileiro com/sem o 9 adicional.

        +5511999999999 (13 dígitos) -> +551199999999 (12 dígitos) sem o 9
        +551199999999 (12 dígitos) -> +5511999999999 (13 dígitos) com o 9

        Retorna None se não for possível gerar variação.
        """
        digitos = telefone.replace('+', '')  # Remove +

        # Formato: 55 (DDI) + DDD (2) + número (8 ou 9)
        if len(digitos) == 13:  # Com 9: 55 + 11 + 999999999
            # Remove o 9 (5º dígito após 55, que é o primeiro do número)
            ddd = digitos[2:4]
            primeiro_digito_numero = digitos[4]
            # Só remove se o 5º dígito for 9
            if primeiro_digito_numero == '9':
                numero_sem_9 = digitos[5:]
                return '+55' + ddd + numero_sem_9

        elif len(digitos) == 12:  # Sem 9: 55 + 11 + 99999999
            # Adiciona o 9 após DDD
            ddd = digitos[2:4]
            numero = digitos[4:]
            return '+55' + ddd + '9' + numero

        return None

    def _get_client_ip(self, request):
        """
        Retorna IP do cliente usando django-ipware.

        Usa configuracao de proxy para evitar IP spoofing via X-Forwarded-For.
        """
        client_ip, is_routable = get_client_ip(
            request,
            request_header_order=['HTTP_X_FORWARDED_FOR', 'HTTP_X_REAL_IP', 'REMOTE_ADDR'],
            proxy_count=1  # Ajustar conforme infraestrutura (numero de proxies reversos)
        )
        return client_ip or '0.0.0.0'

    def _render_error(self, request, mensagem, tentativas_restantes=None):
        """Renderiza pagina de login com erro."""
        context = {
            'config': request.painel_config,
            'erro': mensagem,
            'tentativas_restantes': tentativas_restantes,
            'recaptcha_site_key': get_recaptcha_site_key(),
        }
        return render(request, self.template_name, context)

    def _render_cancelado(self, request, cliente):
        """Renderiza pagina de cliente cancelado."""
        context = {
            'config': request.painel_config,
            'cliente': cliente,
        }
        return render(request, 'painel_cliente/cliente/cancelado.html', context)


def logout_view(request):
    """Encerra sessao do cliente."""
    sessao = getattr(request, 'cliente_sessao', None)
    if sessao:
        sessao.encerrar()

    response = redirect('painel_cliente:login')
    response.delete_cookie(PainelClienteSessionMiddleware.COOKIE_NAME)
    return response


class PerfilView(View):
    """
    View de perfil do cliente.

    Permite atualizar dados cadastrais.
    Obrigatorio na primeira vez que o cliente acessa.
    """

    template_name = 'painel_cliente/cliente/perfil.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return cliente_login_required(view)

    def get(self, request):
        """Exibe formulario de perfil."""
        cliente = request.cliente_sessao.cliente

        context = {
            'config': request.painel_config,
            'cliente': cliente,
            'primeiro_acesso': not cliente.dados_atualizados_painel,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Atualiza dados do cliente."""
        from django.contrib import messages

        cliente = request.cliente_sessao.cliente

        # Coleta dados do formulario
        nome = request.POST.get('nome', cliente.nome).strip()
        email = request.POST.get('email', '').strip()
        cpf = request.POST.get('cpf', '').strip()

        # Validacoes
        erros = []

        if len(nome) < 3:
            erros.append('Nome deve ter pelo menos 3 caracteres.')

        if not email:
            erros.append('Email é obrigatório.')
        else:
            try:
                validate_email(email)
            except DjangoValidationError:
                erros.append('Email inválido. Verifique o formato.')

        if not cpf:
            erros.append('CPF é obrigatório.')
        elif not self._validar_cpf(cpf):
            erros.append('CPF inválido.')

        if erros:
            for erro in erros:
                messages.error(request, erro)
            context = {
                'config': request.painel_config,
                'cliente': cliente,
                'primeiro_acesso': not cliente.dados_atualizados_painel,
            }
            return render(request, self.template_name, context)

        # Atualiza dados
        cliente.nome = nome
        cliente.email = email
        cliente.cpf = cpf

        # Telefone nao pode ser alterado (usado para login)

        # Marca como atualizado
        cliente.dados_atualizados_painel = True
        cliente.save()

        messages.success(request, 'Dados atualizados com sucesso!')
        return redirect('painel_cliente:dashboard')

    def _validar_cpf(self, cpf):
        """Valida CPF usando algoritmo padrao."""
        cpf = ''.join(filter(str.isdigit, cpf))

        if len(cpf) != 11:
            return False

        # Verifica se todos os digitos sao iguais
        if cpf == cpf[0] * 11:
            return False

        # Calcula primeiro digito verificador
        soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
        resto = (soma * 10) % 11
        if resto in (10, 11):
            resto = 0
        if resto != int(cpf[9]):
            return False

        # Calcula segundo digito verificador
        soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
        resto = (soma * 10) % 11
        if resto in (10, 11):
            resto = 0
        if resto != int(cpf[10]):
            return False

        return True


class DashboardView(View):
    """
    Dashboard principal do cliente.

    Exibe:
    - Mensalidades em aberto
    - Historico recente
    - Informacoes do plano
    """

    template_name = 'painel_cliente/cliente/dashboard.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return cliente_login_required(cliente_dados_atualizados_required(view))

    def get(self, request):
        """Exibe dashboard."""
        from datetime import date

        cliente = request.cliente_sessao.cliente
        today = date.today()

        # Se cliente cancelado, não exibe mensalidades abertas
        if cliente.cancelado:
            mensalidades_abertas = []
        else:
            # Mensalidades em aberto (nao pagas, nao canceladas)
            mensalidades_abertas = Mensalidade.objects.filter(
                cliente=cliente,
                pgto=False,
                cancelado=False
            ).order_by('dt_vencimento')[:5]

        # Historico recente (ultimas 12 mensalidades)
        historico_recente = Mensalidade.objects.filter(
            cliente=cliente
        ).order_by('-dt_vencimento')[:12]

        context = {
            'config': request.painel_config,
            'cliente': cliente,
            'mensalidades_abertas': mensalidades_abertas,
            'historico_recente': historico_recente,
            'today': today,
        }
        return render(request, self.template_name, context)


class PagamentoView(View):
    """
    View de pagamento de mensalidade.

    Exibe QR Code PIX e copia/cola.
    """

    template_name = 'painel_cliente/cliente/pagamento.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return cliente_login_required(cliente_dados_atualizados_required(view))

    def get(self, request, mensalidade_id):
        """Exibe pagina de pagamento."""
        from django.contrib import messages

        cliente = request.cliente_sessao.cliente
        config = request.painel_config

        # Bloqueia acesso se cliente cancelado
        if cliente.cancelado:
            messages.error(request, 'Seu plano está cancelado. Entre em contato com o suporte.')
            return redirect('painel_cliente:dashboard')

        # Busca mensalidade validando ownership (sem filtrar por status)
        mensalidade = get_object_or_404(
            Mensalidade,
            id=mensalidade_id,
            cliente=cliente,
            cliente__usuario=config.admin_responsavel
        )

        # Valida status da mensalidade
        if mensalidade.pgto:
            messages.success(
                request,
                'Esta mensalidade já foi paga! Obrigado pelo pagamento.'
            )
            return redirect('painel_cliente:dashboard')

        if mensalidade.cancelado:
            messages.warning(
                request,
                'Esta mensalidade foi cancelada e não pode ser paga.'
            )
            return redirect('painel_cliente:dashboard')

        # Data atual para comparação de vencimento
        from datetime import date
        today = date.today()

        context = {
            'config': config,
            'cliente': cliente,
            'mensalidade': mensalidade,
            'today': today,
        }
        return render(request, self.template_name, context)


@require_POST
@cliente_login_required_ajax
def gerar_pix(request, mensalidade_id):
    """
    Gera QR Code PIX para pagamento.

    Retorna JSON com:
    - qr_code_base64: Imagem do QR Code
    - pix_copia_cola: Codigo para copiar
    - expira_em: Data/hora de expiracao
    """
    cliente = request.cliente_sessao.cliente
    config = request.painel_config

    # Bloqueia geração de PIX para clientes cancelados
    if cliente.cancelado:
        return JsonResponse({
            'success': False,
            'error': 'Seu plano está cancelado. Entre em contato com o suporte.'
        }, status=403)

    # Valida mensalidade
    try:
        mensalidade = Mensalidade.objects.get(
            id=mensalidade_id,
            cliente=cliente,
            cliente__usuario=config.admin_responsavel,
            pgto=False,
            cancelado=False
        )
    except Mensalidade.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Mensalidade não encontrada ou já paga'
        }, status=404)

    # Verifica se tem conta FastDePix configurada
    if not config.conta_bancaria:
        return JsonResponse({
            'success': False,
            'error': 'Conta de pagamento não configurada. Fale com o suporte.'
        }, status=400)

    # Verifica se ja existe cobranca pendente para esta mensalidade
    cobranca_existente = CobrancaPix.objects.filter(
        mensalidade=mensalidade,
        status='pending',
        expira_em__gt=timezone.now()
    ).first()

    if cobranca_existente:
        # Retorna cobranca existente
        return JsonResponse({
            'success': True,
            'cobranca_id': str(cobranca_existente.id),
            'qr_code_url': cobranca_existente.qr_code_url,
            'qr_code_base64': cobranca_existente.qr_code_base64,
            'pix_copia_cola': cobranca_existente.pix_copia_cola,
            'valor': float(cobranca_existente.valor),
            'expira_em': cobranca_existente.expira_em.isoformat()
        })

    # Obtem integracao de pagamento
    integracao = get_payment_integration(config.conta_bancaria)
    if not integracao:
        logger.error(f"[PainelCliente] Integracao nao disponivel para conta {config.conta_bancaria.id}")
        return JsonResponse({
            'success': False,
            'error': 'Serviço de pagamento indisponivel. Tente novamente mais tarde.'
        }, status=503)

    try:
        # Gera cobranca PIX
        descricao = f"Mensalidade {mensalidade.dt_vencimento.strftime('%m/%Y')} - {config.nome_exibicao}"
        external_id = f"painel_{mensalidade.id}"

        pix_charge = integracao.create_pix_charge(
            amount=Decimal(str(mensalidade.valor)),
            description=descricao,
            external_id=external_id,
            expiration_minutes=20,
            payer_name=cliente.nome,
            payer_document=cliente.cpf if cliente.cpf else None
        )

        # Salva cobranca no banco
        cobranca = CobrancaPix.objects.create(
            transaction_id=pix_charge.transaction_id,
            usuario=config.admin_responsavel,
            conta_bancaria=config.conta_bancaria,
            mensalidade=mensalidade,
            cliente=cliente,
            valor=pix_charge.amount,
            descricao=descricao,
            status='pending',
            qr_code=pix_charge.qr_code,
            qr_code_url=pix_charge.qr_code_url or '',
            qr_code_base64=pix_charge.qr_code_base64 or '',
            pix_copia_cola=pix_charge.pix_copy_paste,
            expira_em=pix_charge.expiration,
            integracao='fastdepix',
            raw_response=pix_charge.raw_response or {}
        )

        logger.info(f"[PainelCliente] Cobrança {cobranca.id} criada para mensalidade {mensalidade.id}")

        return JsonResponse({
            'success': True,
            'cobranca_id': str(cobranca.id),
            'qr_code_url': cobranca.qr_code_url,
            'qr_code_base64': cobranca.qr_code_base64,
            'pix_copia_cola': cobranca.pix_copia_cola,
            'valor': float(cobranca.valor),
            'expira_em': cobranca.expira_em.isoformat()
        })

    except PaymentIntegrationError as e:
        logger.error(f"[PainelCliente] Erro ao gerar PIX: {e.message}")
        return JsonResponse({
            'success': False,
            'error': f'Erro ao gerar PIX: {e.message}'
        }, status=500)
    except Exception as e:
        logger.exception(f"[PainelCliente] Erro inesperado ao gerar PIX: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Erro inesperado. Tente novamente mais tarde.'
        }, status=500)


@require_GET
@cliente_login_required_ajax
def status_pix(request, cobranca_id):
    """
    Verifica status de uma cobranca PIX.

    Retorna JSON com status atual.
    """
    cliente = request.cliente_sessao.cliente
    config = request.painel_config

    # Busca cobranca validando ownership
    try:
        cobranca = CobrancaPix.objects.select_related(
            'mensalidade', 'conta_bancaria'
        ).get(
            id=cobranca_id,
            cliente=cliente,
            usuario=config.admin_responsavel
        )
    except CobrancaPix.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Cobranca nao encontrada'
        }, status=404)

    # Se ja esta pago ou expirado no banco, retorna direto
    if cobranca.status in ['paid', 'expired', 'cancelled']:
        return JsonResponse({
            'success': True,
            'status': cobranca.status,
            'pago_em': cobranca.pago_em.isoformat() if cobranca.pago_em else None
        })

    # Verifica se expirou localmente
    if cobranca.expira_em < timezone.now():
        cobranca.status = 'expired'
        cobranca.save(update_fields=['status', 'atualizado_em'])
        return JsonResponse({
            'success': True,
            'status': 'expired',
            'pago_em': None
        })

    # Consulta status na API
    integracao = get_payment_integration(cobranca.conta_bancaria)
    if not integracao:
        # Se nao tiver integracao, retorna status do banco
        return JsonResponse({
            'success': True,
            'status': cobranca.status,
            'pago_em': None
        })

    try:
        status_api = integracao.get_charge_status(cobranca.transaction_id)

        # Mapeia status da API para nosso status
        status_map = {
            PaymentStatus.PENDING: 'pending',
            PaymentStatus.PAID: 'paid',
            PaymentStatus.EXPIRED: 'expired',
            PaymentStatus.CANCELLED: 'cancelled',
            PaymentStatus.REFUNDED: 'refunded',
            PaymentStatus.ERROR: 'error',
        }
        novo_status = status_map.get(status_api, 'pending')

        # Atualiza status se mudou
        if novo_status != cobranca.status:
            if novo_status == 'paid':
                # Buscar detalhes completos da transação para obter dados de taxa
                paid_at = timezone.now()
                payer_name = None
                payer_doc = None
                valor_recebido = None
                valor_taxa = None

                try:
                    details = integracao.get_charge_details(cobranca.transaction_id)
                    logger.info(f"[PainelCliente] Detalhes da API para {cobranca.id}: {details}")

                    # Extrair data de pagamento
                    if details.get('paid_at'):
                        try:
                            paid_at = timezone.datetime.fromisoformat(
                                details['paid_at'].replace('Z', '+00:00')
                            )
                        except (ValueError, AttributeError):
                            pass

                    # Extrair dados do pagador
                    payer = details.get('payer', {})
                    if isinstance(payer, dict):
                        payer_name = payer.get('name')
                        payer_doc = payer.get('cpf_cnpj')

                    # Extrair valores financeiros
                    from decimal import Decimal
                    amount_received = (
                        details.get('commission_amount') or
                        details.get('amount_received') or
                        details.get('net_amount')
                    )
                    fee = details.get('fee') or details.get('tax')

                    if amount_received:
                        try:
                            valor_recebido = Decimal(str(amount_received))
                        except (ValueError, TypeError):
                            pass

                    if fee:
                        try:
                            valor_taxa = Decimal(str(fee))
                        except (ValueError, TypeError):
                            pass

                    # Se não veio taxa, calcular a partir do valor bruto
                    if valor_taxa is None and details.get('amount') and valor_recebido:
                        try:
                            valor_taxa = Decimal(str(details['amount'])) - valor_recebido
                        except (ValueError, TypeError):
                            pass

                    logger.info(f"[PainelCliente] Valores extraídos - Recebido: {valor_recebido}, Taxa: {valor_taxa}")

                except Exception as e:
                    logger.warning(f"[PainelCliente] Erro ao buscar detalhes da cobrança {cobranca.id}: {e}")

                # Usar mark_as_paid que já atualiza mensalidade e dispara signals
                # (criar_nova_mensalidade, atualiza_ultimo_pagamento)
                cobranca.mark_as_paid(
                    paid_at=paid_at,
                    payer_name=payer_name,
                    payer_document=payer_doc,
                    valor_recebido=valor_recebido,
                    valor_taxa=valor_taxa,
                )
                logger.info(f"[PainelCliente] Cobrança {cobranca.id} marcada como paga via polling")
            else:
                cobranca.status = novo_status
                cobranca.save(update_fields=['status', 'atualizado_em'])

        return JsonResponse({
            'success': True,
            'status': novo_status,
            'pago_em': cobranca.pago_em.isoformat() if cobranca.pago_em else None
        })

    except PaymentIntegrationError as e:
        logger.warning(f"[PainelCliente] Erro ao consultar status: {e.message}")
        # Em caso de erro, retorna status atual do banco
        return JsonResponse({
            'success': True,
            'status': cobranca.status,
            'pago_em': cobranca.pago_em.isoformat() if cobranca.pago_em else None
        })
    except Exception as e:
        logger.exception(f"[PainelCliente] Erro inesperado ao consultar status: {e}")
        return JsonResponse({
            'success': True,
            'status': cobranca.status,
            'pago_em': cobranca.pago_em.isoformat() if cobranca.pago_em else None
        })


class HistoricoView(View):
    """
    Historico completo de mensalidades.
    """

    template_name = 'painel_cliente/cliente/historico.html'

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return cliente_login_required(cliente_dados_atualizados_required(view))

    def get(self, request):
        """Exibe historico de mensalidades."""
        cliente = request.cliente_sessao.cliente

        mensalidades = Mensalidade.objects.filter(
            cliente=cliente
        ).order_by('-dt_vencimento')

        context = {
            'config': request.painel_config,
            'cliente': cliente,
            'mensalidades': mensalidades,
        }
        return render(request, self.template_name, context)
