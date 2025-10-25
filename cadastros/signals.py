"""Signals responsáveis por garantir consistência interna e integrações externas.

Centraliza regras de atualização automática vinculadas a clientes e mensalidades,
além de orquestrar a sincronização de labels do WhatsApp após alterações.
"""

import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Cliente, Mensalidade, SessaoWpp, UserProfile
from wpp.api_connection import add_or_remove_label_contact, criar_label_se_nao_existir, get_label_contact

logger = logging.getLogger(__name__)


def _log_event(level, instance, func_name, message, exc_info=None):
    """Centraliza a formatação dos registros de log para este módulo."""
    logger.log(level, "[%s] [%s] %s", func_name, instance.usuario, message, exc_info=exc_info)

@receiver(post_save, sender=Mensalidade)
def atualiza_ultimo_pagamento(sender, instance, **kwargs):
    """Atualiza o campo `ultimo_pagamento` do cliente ao registrar um pagamento válido."""
    cliente = instance.cliente

    if instance.dt_pagamento and instance.pgto:
        if not cliente.ultimo_pagamento or instance.dt_pagamento > cliente.ultimo_pagamento:
            cliente.ultimo_pagamento = instance.dt_pagamento
            cliente.save()


@receiver(pre_save, sender=Mensalidade)
def criar_nova_mensalidade(sender, instance, **kwargs):
    """
    Cria automaticamente a próxima mensalidade após o pagamento da atual.

    Regras:
    - A nova mensalidade só será criada se:
        - A mensalidade atual estiver marcada como paga (`pgto=True`) e possuir `dt_pagamento`.
        - A data de vencimento da mensalidade não for muito antiga (até 7 dias de defasagem).
        - Não existir já uma mensalidade futura não paga para o cliente (evita duplicidade).
    - A data base para o novo vencimento será:
        - A data de vencimento anterior (caso tenha sido pagamento antecipado), ou
        - A data atual (caso tenha sido em atraso).
    - O novo vencimento será ajustado conforme o tipo do plano do cliente (mensal, trimestral, etc).
    - Aplica desconto progressivo se houver descontos ativos.
    - Ao final, além de criar a nova mensalidade, o campo `data_vencimento` do cliente será atualizado.

    Parâmetros:
        sender (Model): O modelo que acionou o signal (Mensalidade).
        instance (Mensalidade): A instância da mensalidade que está sendo salva.
        kwargs: Argumentos adicionais do signal.
    """
    hoje = timezone.localdate()

    if instance.dt_pagamento and instance.pgto and not instance.dt_vencimento < hoje - timedelta(days=7):
        if Mensalidade.objects.filter(
            cliente=instance.cliente,
            dt_vencimento__gt=instance.dt_vencimento,
            pgto=False,
            cancelado=False
        ).exists():
            return

        data_vencimento_anterior = instance.dt_vencimento

        if data_vencimento_anterior > hoje:
            nova_data_vencimento = data_vencimento_anterior
        else:
            nova_data_vencimento = hoje

        plano_nome = instance.cliente.plano.nome.lower()
        if "mensal" in plano_nome:
            nova_data_vencimento += relativedelta(months=1)
        elif "bimestral" in plano_nome:
            nova_data_vencimento += relativedelta(months=2)
        elif "trimestral" in plano_nome:
            nova_data_vencimento += relativedelta(months=3)
        elif "semestral" in plano_nome:
            nova_data_vencimento += relativedelta(months=6)
        elif "anual" in plano_nome:
            nova_data_vencimento += relativedelta(years=1)

        # Calcular valor da mensalidade com desconto progressivo
        from cadastros.utils import calcular_desconto_progressivo_total
        from .models import PlanoIndicacao
        from decimal import Decimal

        valor_base = instance.cliente.plano.valor
        desconto_info = calcular_desconto_progressivo_total(instance.cliente)

        # Aplicar desconto se houver
        if desconto_info["valor_total"] > Decimal("0.00") and desconto_info["plano"]:
            valor_com_desconto = valor_base - desconto_info["valor_total"]
            # Respeitar valor mínimo configurado
            valor_minimo = desconto_info["plano"].valor_minimo_mensalidade
            valor_final = max(valor_com_desconto, valor_minimo)
        else:
            valor_final = valor_base

        Mensalidade.objects.create(
            cliente=instance.cliente,
            valor=valor_final,
            dt_vencimento=nova_data_vencimento,
            usuario=instance.usuario,
        )

        instance.cliente.data_vencimento = nova_data_vencimento
        instance.cliente.save()


# Cacheia valores antes do `save` para identificar mudanças relevantes.
_clientes_servidor_anterior = {}
_clientes_cancelado_anterior = {}

# Mapeamento fixo de labels para paleta definida no WhatsApp.
LABELS_CORES_FIXAS = {
    "LEADS": "#F0B330",
    "CLUB": "#8B6990",
    "PLAY": "#792138",
    "REVENDA": "#6E257E",
    "CANCELADOS": "#F0B330",
    "NOVOS": "#A62C71",
    "SEVEN": "#26C4DC",
    "WAREZ": "#54C265",
}

@receiver(pre_save, sender=Cliente)
def registrar_valores_anteriores(sender, instance, **kwargs):
    """Captura o estado atual do cliente para detectar mudanças relevantes após o save."""
    if instance.pk:
        try:
            cliente_existente = Cliente.objects.get(pk=instance.pk)
        except Cliente.DoesNotExist:
            return

        _clientes_servidor_anterior[instance.pk] = cliente_existente.servidor_id
        _clientes_cancelado_anterior[instance.pk] = cliente_existente.cancelado


@receiver(post_save, sender=Cliente)
def cliente_post_save(sender, instance, created, **kwargs):
    """Sincroniza as labels do contato no WhatsApp após criação ou atualização do cliente."""
    func_name = cliente_post_save.__name__
    servidor_foi_modificado = False
    cliente_foi_cancelado = False
    cliente_foi_reativado = False

    if not created:
        # Detecta mudança de servidor
        if instance.pk in _clientes_servidor_anterior:
            servidor_anterior_id = _clientes_servidor_anterior.pop(instance.pk)
            servidor_foi_modificado = servidor_anterior_id != instance.servidor_id

        # Detecta mudança de cancelamento (usa .get() para não remover ainda)
        if instance.pk in _clientes_cancelado_anterior:
            cancelado_anterior = _clientes_cancelado_anterior.get(instance.pk)
            cliente_foi_cancelado = not cancelado_anterior and instance.cancelado
            cliente_foi_reativado = cancelado_anterior and not instance.cancelado

    if not (created or servidor_foi_modificado or cliente_foi_cancelado or cliente_foi_reativado):
        return

    telefone = str(instance.telefone)

    token = SessaoWpp.objects.filter(usuario=instance.usuario, is_active=True).first()
    if not token:
        _log_event(logging.INFO, instance, func_name, "Sessão do WhatsApp não encontrada para o usuário.")
        return

    # TODO: Reativar a verificação de número (`check_number_status`) caso volte a ser necessária.

    try:
        labels_atuais = get_label_contact(telefone, token.token, user=token)
    except Exception as error:
        _log_event(logging.ERROR, instance, func_name, "Erro ao obter labels atuais do contato.", exc_info=error)
        labels_atuais = []

    try:
        label_desejada = "CANCELADOS" if cliente_foi_cancelado else instance.servidor.nome
        hex_color = LABELS_CORES_FIXAS.get(label_desejada.upper())

        nova_label_id = criar_label_se_nao_existir(label_desejada, token.token, user=token, hex_color=hex_color)
        if not nova_label_id:
            _log_event(
                logging.INFO,
                instance,
                func_name,
                f"Não foi possível obter ou criar a label '{label_desejada}'.",
            )
            return

        add_or_remove_label_contact(
            label_id_1=nova_label_id,
            label_id_2=labels_atuais,
            label_name=label_desejada,
            telefone=telefone,
            token=token.token,
            user=token,
        )

    except Exception as error:
        _log_event(logging.ERROR, instance, func_name, "Erro ao alterar label do contato.", exc_info=error)


# ============================================================================
# SIGNALS PARA DESCONTO PROGRESSIVO POR INDICAÇÃO
# ============================================================================

@receiver(post_save, sender=Cliente)
def gerenciar_desconto_progressivo_indicacao(sender, instance, created, **kwargs):
    """
    Gerencia descontos progressivos quando um cliente é criado ou atualizado.

    - Ao criar cliente com indicação: cria desconto progressivo e envia mensagem
    - Ao cancelar cliente: desativa descontos onde ele é indicado
    - Ao reativar cliente: reativa descontos onde ele é indicado
    """
    from .models import DescontoProgressivoIndicacao, PlanoIndicacao, Mensalidade
    from cadastros.utils import calcular_desconto_progressivo_total
    from decimal import Decimal

    func_name = gerenciar_desconto_progressivo_indicacao.__name__

    # Verificar se plano progressivo está ativo
    plano_progressivo = PlanoIndicacao.objects.filter(
        usuario=instance.usuario,
        tipo_plano="desconto_progressivo",
        ativo=True,
        status=True
    ).first()

    if not plano_progressivo:
        return

    # CASO 1: Novo cliente com indicação - criar desconto progressivo
    if created and instance.indicado_por and not instance.cancelado:
        try:
            # Criar desconto progressivo
            desconto = DescontoProgressivoIndicacao.objects.create(
                cliente_indicador=instance.indicado_por,
                cliente_indicado=instance,
                plano_indicacao=plano_progressivo,
                valor_desconto=plano_progressivo.valor,
                usuario=instance.usuario,
                ativo=True
            )

            _log_event(
                logging.INFO,
                instance,
                func_name,
                f"Desconto progressivo criado: {desconto.cliente_indicador.nome} ← {instance.nome} (R$ {desconto.valor_desconto})"
            )

            # Atualizar mensalidade em aberto do indicador
            atualizar_mensalidade_indicador_com_desconto(instance.indicado_por, plano_progressivo)

            # Enviar mensagem WhatsApp (será implementado na próxima etapa)
            from cadastros.utils import envio_desconto_progressivo_indicacao
            try:
                envio_desconto_progressivo_indicacao(instance.usuario, instance, instance.indicado_por)
            except Exception as e:
                _log_event(logging.WARNING, instance, func_name, f"Falha ao enviar mensagem WhatsApp: {e}")

        except Exception as error:
            _log_event(logging.ERROR, instance, func_name, "Erro ao criar desconto progressivo.", exc_info=error)

    # CASO 2: Cliente cancelado - desativar desconto progressivo
    if not created and instance.pk in _clientes_cancelado_anterior:
        cancelado_anterior = _clientes_cancelado_anterior.get(instance.pk)
        cliente_foi_cancelado = not cancelado_anterior and instance.cancelado
        cliente_foi_reativado = cancelado_anterior and not instance.cancelado

        if cliente_foi_cancelado:
            # Desativar descontos onde este cliente é o indicado
            descontos = DescontoProgressivoIndicacao.objects.filter(
                cliente_indicado=instance,
                ativo=True
            )

            for desconto in descontos:
                desconto.ativo = False
                desconto.data_fim = timezone.localdate()
                desconto.save()

                _log_event(
                    logging.INFO,
                    instance,
                    func_name,
                    f"Desconto progressivo desativado: {desconto.cliente_indicador.nome} ← {instance.nome}"
                )

                # Atualizar mensalidade em aberto do indicador
                atualizar_mensalidade_indicador_com_desconto(desconto.cliente_indicador, plano_progressivo)

        # CASO 3: Cliente reativado - reativar desconto progressivo
        elif cliente_foi_reativado:
            # Reativar descontos onde este cliente é o indicado
            descontos = DescontoProgressivoIndicacao.objects.filter(
                cliente_indicado=instance,
                ativo=False,
                data_fim__isnull=False
            )

            for desconto in descontos:
                desconto.ativo = True
                desconto.data_fim = None
                desconto.save()

                _log_event(
                    logging.INFO,
                    instance,
                    func_name,
                    f"Desconto progressivo reativado: {desconto.cliente_indicador.nome} ← {instance.nome}"
                )

                # Atualizar mensalidade em aberto do indicador
                atualizar_mensalidade_indicador_com_desconto(desconto.cliente_indicador, plano_progressivo)

    # Limpar cache do estado anterior após processar
    if instance.pk in _clientes_cancelado_anterior:
        _clientes_cancelado_anterior.pop(instance.pk, None)


def atualizar_mensalidade_indicador_com_desconto(cliente_indicador, plano_progressivo):
    """Atualiza o valor da mensalidade em aberto do indicador com desconto progressivo."""
    from .models import Mensalidade
    from cadastros.utils import calcular_desconto_progressivo_total
    from decimal import Decimal

    # Buscar mensalidade em aberto
    mensalidade_aberta = Mensalidade.objects.filter(
        cliente=cliente_indicador,
        pgto=False,
        cancelado=False,
        dt_cancelamento=None
    ).order_by('dt_vencimento').first()

    if not mensalidade_aberta:
        return

    # Calcular desconto total
    desconto_info = calcular_desconto_progressivo_total(cliente_indicador)
    valor_base = cliente_indicador.plano.valor

    if desconto_info["valor_total"] > Decimal("0.00"):
        valor_com_desconto = valor_base - desconto_info["valor_total"]
        valor_minimo = plano_progressivo.valor_minimo_mensalidade
        valor_final = max(valor_com_desconto, valor_minimo)
    else:
        valor_final = valor_base

    # Atualizar apenas se o valor mudou
    if mensalidade_aberta.valor != valor_final:
        mensalidade_aberta.valor = valor_final
        mensalidade_aberta.save()


@receiver(post_save, sender='auth.User')
def create_user_profile(sender, instance, created, **kwargs):
    """Cria UserProfile automaticamente ao criar novo User."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender='auth.User')
def save_user_profile(sender, instance, **kwargs):
    """Garante que o UserProfile seja salvo junto com o User."""
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        # Cria profile se não existir (para usuários antigos)
        UserProfile.objects.get_or_create(user=instance)


# ============================================================================
# SIGNALS PARA REGISTRO DE LOGIN
# ============================================================================

from django.contrib.auth.signals import user_logged_in, user_login_failed
from .models import LoginLog


@receiver(user_logged_in)
def log_user_login_success(sender, request, user, **kwargs):
    """
    Registra login bem-sucedido no LoginLog.

    Este signal é disparado automaticamente pelo Django após um login bem-sucedido.
    Captura informações importantes como IP, User-Agent, e método de login.
    """
    from cadastros.utils import get_client_ip

    # Determinar método de login
    # Se há pending_2fa_user_id na sessão, significa que acabou de fazer 2FA
    if 'pending_2fa_user_id' in request.session:
        login_method = LoginLog.METHOD_2FA
    # Se há backup_code_used
    elif request.session.get('backup_code_used'):
        login_method = LoginLog.METHOD_BACKUP_CODE
    else:
        login_method = LoginLog.METHOD_PASSWORD

    try:
        LoginLog.objects.create(
            usuario=user,
            username_tentado=user.username,
            ip=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            login_method=login_method,
            success=True
        )
        logger.info(f'[LOGIN_LOG] Login bem-sucedido registrado para usuário {user.username} (ID: {user.id})')

        # Limpar flags de sessão
        request.session.pop('backup_code_used', None)

    except Exception as e:
        logger.error(f'[LOGIN_LOG] Erro ao registrar login bem-sucedido: {str(e)}', exc_info=True)


@receiver(user_login_failed)
def log_user_login_failure(sender, credentials, request, **kwargs):
    """
    Registra tentativa de login falhada no LoginLog.

    Este signal é disparado quando uma tentativa de login falha.
    Útil para detectar:
    - Tentativas de brute force
    - Acessos não autorizados
    - Usuários esquecendo senhas
    """
    from cadastros.utils import get_client_ip
    from django.contrib.auth import get_user_model

    User = get_user_model()

    username = credentials.get('username', '')

    # Tentar encontrar o usuário
    user = None
    if username:
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            pass

    # Determinar razão da falha
    if not username:
        failure_reason = 'Username não fornecido'
    elif not user:
        failure_reason = 'Usuário não encontrado'
    else:
        failure_reason = 'Senha incorreta'

    try:
        LoginLog.objects.create(
            usuario=user,
            username_tentado=username[:150],
            ip=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            login_method=LoginLog.METHOD_PASSWORD,
            success=False,
            failure_reason=failure_reason
        )
        logger.warning(f'[LOGIN_LOG] Login falhado registrado para username "{username}". Razão: {failure_reason}')

    except Exception as e:
        logger.error(f'[LOGIN_LOG] Erro ao registrar login falhado: {str(e)}', exc_info=True)
