"""Signals responsáveis por garantir consistência interna e integrações externas.

Centraliza regras de atualização automática vinculadas a clientes e mensalidades,
além de orquestrar a sincronização de labels do WhatsApp após alterações.
"""

import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import Cliente, Mensalidade, SessaoWpp, UserProfile, AssinaturaCliente
from wpp.api_connection import add_or_remove_label_contact, criar_label_se_nao_existir, get_label_contact, remover_todas_labels_contato

logger = logging.getLogger(__name__)


def _log_event(level, instance, func_name, message, exc_info=None):
    """Centraliza a formatação dos registros de log para este módulo."""
    logger.log(level, "[%s] [%s] %s", func_name, instance.usuario, message, exc_info=exc_info)

@receiver(post_save, sender=Mensalidade)
def atualiza_ultimo_pagamento(sender, instance, **kwargs):
    """
    Atualiza o campo `ultimo_pagamento` do cliente ao registrar um pagamento válido.
    Também verifica se é a primeira mensalidade paga para enviar mensagem de boas-vindas.
    """
    cliente = instance.cliente

    if instance.dt_pagamento and instance.pgto:
        if not cliente.ultimo_pagamento or instance.dt_pagamento > cliente.ultimo_pagamento:
            cliente.ultimo_pagamento = instance.dt_pagamento
            cliente.save()

        # Verificar se é a primeira mensalidade paga do cliente (pagamento manual)
        # Só envia se NÃO foi via PIX (CobrancaPix já envia via _enviar_notificacoes_pagamento)
        try:
            from nossopainel.models import CobrancaPix
            # Verificar se existe uma CobrancaPix paga para esta mensalidade
            cobranca_pix_existe = CobrancaPix.objects.filter(
                mensalidade=instance,
                status='paid'
            ).exists()

            if not cobranca_pix_existe:
                # É pagamento manual - verificar se é primeira mensalidade
                qtd_mensalidades_pagas = Mensalidade.objects.filter(
                    cliente=cliente,
                    pgto=True
                ).count()

                if qtd_mensalidades_pagas == 1:
                    # Primeira mensalidade paga manualmente - enviar boas-vindas
                    logger.info(f"[Signal] Primeira mensalidade paga manualmente para {cliente.nome}")
                    from nossopainel.utils import envio_apos_novo_cadastro
                    envio_apos_novo_cadastro(cliente)
        except Exception as e:
            logger.error(f"[Signal] Erro ao verificar/enviar mensagem de boas-vindas: {e}")


@receiver(pre_save, sender=Mensalidade)
def criar_nova_mensalidade(sender, instance, **kwargs):
    """
    Cria automaticamente a próxima mensalidade após o pagamento da atual.

    Regras:
    - A nova mensalidade só será criada se:
        - A mensalidade atual estiver marcada como paga (`pgto=True`) e possuir `dt_pagamento`.
        - A data de vencimento da mensalidade não for muito antiga (até 7 dias de defasagem).
        - Não existir já uma mensalidade futura não paga para o cliente (evita duplicidade).
        - NÃO estiver em processo de reativação (mudança de cancelado=True para cancelado=False).
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

    # PROTEÇÃO CONTRA REATIVAÇÃO: Se a mensalidade está sendo reativada, não cria nova mensalidade
    if instance.pk:  # Se já existe (é um update, não um create)
        try:
            mensalidade_original = Mensalidade.objects.get(pk=instance.pk)
            # Se estava cancelada e agora não está mais, é uma reativação - NÃO criar nova mensalidade
            if mensalidade_original.cancelado and not instance.cancelado:
                return
        except Mensalidade.DoesNotExist:
            pass

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

        # Calcular valor considerando campanhas promocionais (Simplificado)
        from nossopainel.utils import calcular_valor_mensalidade
        from .models import AssinaturaCliente

        # Verificar e processar campanha ativa
        try:
            assinatura = AssinaturaCliente.objects.get(cliente=instance.cliente, ativo=True)

            # ⭐ SIMPLIFICAÇÃO: Verifica se está em campanha usando apenas o flag
            if assinatura.em_campanha:
                # Increment campaign counter
                assinatura.campanha_mensalidades_pagas += 1

                # Check if campaign is finished
                if assinatura.campanha_duracao_total and assinatura.campanha_mensalidades_pagas >= assinatura.campanha_duracao_total:
                    assinatura.em_campanha = False
                    logger.info(
                        f"[CAMPANHA] Campanha finalizada para {instance.cliente.nome}. "
                        f"Próximas mensalidades usarão valor regular do plano."
                    )
                else:
                    logger.info(
                        f"[CAMPANHA] Mensalidade {assinatura.campanha_mensalidades_pagas}/{assinatura.campanha_duracao_total} "
                        f"para {instance.cliente.nome}"
                    )

                assinatura.save()
        except AssinaturaCliente.DoesNotExist:
            pass  # No subscription record

        # Calcular valor com rastreamento detalhado de campanha e descontos
        from decimal import Decimal
        from nossopainel.utils import calcular_desconto_progressivo_total

        cliente = instance.cliente
        valor_base = cliente.plano.valor
        gerada_em_campanha = False
        desconto_campanha = Decimal("0.00")
        desconto_progressivo = Decimal("0.00")
        tipo_campanha = None
        numero_mes_campanha = None

        # Verificar se há campanha ativa
        try:
            assinatura = AssinaturaCliente.objects.get(cliente=cliente, ativo=True)

            if assinatura.em_campanha and cliente.plano.campanha_ativa:
                numero_mes = assinatura.campanha_mensalidades_pagas + 1

                if numero_mes <= assinatura.campanha_duracao_total:
                    gerada_em_campanha = True
                    tipo_campanha = cliente.plano.campanha_tipo
                    numero_mes_campanha = numero_mes

                    # Calcular valor com campanha
                    if tipo_campanha == 'FIXO':
                        valor_com_campanha = cliente.plano.campanha_valor_fixo
                    else:  # PERSONALIZADO
                        campo = f'campanha_valor_mes_{min(numero_mes, 12)}'
                        valor_com_campanha = getattr(cliente.plano, campo, None)

                    if valor_com_campanha:
                        desconto_campanha = valor_base - valor_com_campanha
                        valor_final = valor_com_campanha
        except:
            pass

        # Se não tem campanha, verificar desconto progressivo
        if not gerada_em_campanha:
            desconto_info = calcular_desconto_progressivo_total(cliente)
            desconto_progressivo = desconto_info["valor_total"]

            if desconto_progressivo > Decimal("0.00"):
                valor_com_desconto = valor_base - desconto_progressivo
                valor_minimo = desconto_info["plano"].valor_minimo_mensalidade if desconto_info["plano"] else valor_base
                valor_final = max(valor_com_desconto, valor_minimo)
            else:
                valor_final = valor_base
        else:
            # Se tem campanha, não aplica desconto progressivo
            desconto_progressivo = Decimal("0.00")

        # Criar mensalidade com rastreamento completo
        Mensalidade.objects.create(
            cliente=cliente,
            valor=valor_final,
            dt_vencimento=nova_data_vencimento,
            usuario=instance.usuario,
            # Novos campos de rastreamento
            gerada_em_campanha=gerada_em_campanha,
            valor_base_plano=valor_base,
            desconto_campanha=desconto_campanha,
            desconto_progressivo=desconto_progressivo,
            tipo_campanha=tipo_campanha,
            numero_mes_campanha=numero_mes_campanha,
            dados_historicos_verificados=True,  # Dados precisos (mensalidade nova)
        )

        instance.cliente.data_vencimento = nova_data_vencimento
        instance.cliente.save()


# Cacheia valores antes do `save` para identificar mudanças relevantes.
_clientes_servidor_anterior = {}
_clientes_cancelado_anterior = {}
_clientes_indicado_por_anterior = {}
_clientes_telefone_anterior = {}

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
        _clientes_indicado_por_anterior[instance.pk] = cliente_existente.indicado_por_id
        _clientes_telefone_anterior[instance.pk] = cliente_existente.telefone


@receiver(post_save, sender=Cliente)
def cliente_post_save(sender, instance, created, **kwargs):
    """Sincroniza as labels do contato no WhatsApp após criação ou atualização do cliente."""
    func_name = cliente_post_save.__name__
    servidor_foi_modificado = False
    cliente_foi_cancelado = False
    cliente_foi_reativado = False
    telefone_foi_modificado = False
    telefone_anterior = None

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

        # Detecta mudança de telefone
        if instance.pk in _clientes_telefone_anterior:
            telefone_anterior = _clientes_telefone_anterior.pop(instance.pk)
            telefone_foi_modificado = telefone_anterior != instance.telefone

    if not (created or servidor_foi_modificado or cliente_foi_cancelado or cliente_foi_reativado or telefone_foi_modificado):
        return

    telefone = str(instance.telefone)

    token = SessaoWpp.objects.filter(usuario=instance.usuario, is_active=True).first()
    if not token:
        _log_event(logging.INFO, instance, func_name, "Sessão do WhatsApp não encontrada para o usuário.")
        return

    # Se telefone mudou, remover etiquetas do número antigo
    if telefone_foi_modificado and telefone_anterior:
        try:
            labels_telefone_antigo = get_label_contact(telefone_anterior, token.token, user=token)
            if labels_telefone_antigo:
                remover_todas_labels_contato(telefone_anterior, labels_telefone_antigo, token.token, token)
                _log_event(logging.INFO, instance, func_name, f"Etiquetas removidas do telefone antigo: {telefone_anterior}")
        except Exception as error:
            _log_event(logging.ERROR, instance, func_name, f"Erro ao remover etiquetas do telefone antigo {telefone_anterior}", exc_info=error)

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
    from nossopainel.utils import calcular_desconto_progressivo_total
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

            # NOTA: A mensagem WhatsApp para o indicador será enviada apenas após
            # o pagamento ser confirmado (via envio_apos_novo_cadastro em utils.py)

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

    # CASO 4: Mudança de indicador - transferir desconto progressivo
    if not created and instance.pk in _clientes_indicado_por_anterior:
        indicador_anterior_id = _clientes_indicado_por_anterior.get(instance.pk)
        indicador_atual_id = instance.indicado_por_id if instance.indicado_por else None
        indicador_mudou = indicador_anterior_id != indicador_atual_id

        if indicador_mudou and not instance.cancelado:
            # 4.1: Desativar desconto do indicador antigo (se existia)
            if indicador_anterior_id:
                desconto_antigo = DescontoProgressivoIndicacao.objects.filter(
                    cliente_indicado=instance,
                    cliente_indicador_id=indicador_anterior_id,
                    ativo=True
                ).first()

                if desconto_antigo:
                    desconto_antigo.ativo = False
                    desconto_antigo.data_fim = timezone.localdate()
                    desconto_antigo.save()

                    _log_event(
                        logging.INFO,
                        instance,
                        func_name,
                        f"Desconto progressivo removido por mudança de indicador: {desconto_antigo.cliente_indicador.nome} ← {instance.nome}"
                    )

                    # Atualizar mensalidade do indicador antigo
                    atualizar_mensalidade_indicador_com_desconto(
                        desconto_antigo.cliente_indicador,
                        plano_progressivo
                    )

            # Criar desconto para novo indicador (se informado)
            if indicador_atual_id and instance.indicado_por:
                # Verificar se já não existe um desconto ativo para evitar duplicação
                desconto_existente = DescontoProgressivoIndicacao.objects.filter(
                    cliente_indicado=instance,
                    cliente_indicador=instance.indicado_por,
                    ativo=True
                ).exists()

                if not desconto_existente:
                    DescontoProgressivoIndicacao.objects.create(
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
                        f"Desconto progressivo criado por mudança de indicador: {instance.indicado_por.nome} ← {instance.nome}"
                    )

                    # Atualizar mensalidade do novo indicador
                    atualizar_mensalidade_indicador_com_desconto(
                        instance.indicado_por,
                        plano_progressivo
                    )

                    # Enviar WhatsApp para novo indicador APENAS se o cliente já pagou alguma mensalidade
                    qtd_mensalidades_pagas = Mensalidade.objects.filter(
                        cliente=instance,
                        pgto=True
                    ).count()

                    if qtd_mensalidades_pagas > 0:
                        from nossopainel.utils import envio_desconto_progressivo_indicacao
                        try:
                            envio_desconto_progressivo_indicacao(instance.usuario, instance, instance.indicado_por)
                        except Exception as e:
                            _log_event(logging.WARNING, instance, func_name, f"Falha ao enviar WhatsApp: {e}")

    # Limpar cache do estado anterior após processar
    if instance.pk in _clientes_cancelado_anterior:
        _clientes_cancelado_anterior.pop(instance.pk, None)
    if instance.pk in _clientes_indicado_por_anterior:
        _clientes_indicado_por_anterior.pop(instance.pk, None)


def atualizar_mensalidade_indicador_com_desconto(cliente_indicador, plano_progressivo):
    """Atualiza o valor da mensalidade em aberto do indicador com desconto progressivo."""
    from .models import Mensalidade
    from nossopainel.utils import calcular_desconto_progressivo_total
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
    from nossopainel.utils import get_client_ip

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
    from nossopainel.utils import get_client_ip
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


# ============================================================================
# MVP - SIGNALS PARA ASSINATURA E CONTROLE DE RECURSOS
# ============================================================================

@receiver(post_save, sender=Cliente)
def criar_assinatura_cliente(sender, instance, created, **kwargs):
    """
    Cria automaticamente AssinaturaCliente ao cadastrar novo cliente.

    MVP - Controle de Dispositivos e Apps

    A AssinaturaCliente serve como camada de controle entre Cliente e Plano,
    rastreando recursos utilizados e preparando para funcionalidades futuras
    (ofertas e valores progressivos).
    """
    if created:
        try:
            AssinaturaCliente.objects.create(
                cliente=instance,
                plano=instance.plano,
                data_inicio_assinatura=instance.data_adesao or timezone.localdate(),
                ativo=not instance.cancelado
            )
            logger.info(
                f"[ASSINATURA] AssinaturaCliente criada automaticamente para {instance.nome} "
                f"(Plano: {instance.plano.nome})"
            )
        except Exception as e:
            logger.error(
                f"[ASSINATURA] Erro ao criar AssinaturaCliente para {instance.nome}: {str(e)}",
                exc_info=True
            )


# ============================================================================
# Sincronização de contadores de dispositivos
# ============================================================================

@receiver(post_delete, sender='nossopainel.ContaDoAplicativo')
def decrementar_contador_dispositivos(sender, instance, **kwargs):
    """
    Decrementa contador de dispositivos quando ContaDoAplicativo é excluída.

    MVP - Controle de Dispositivos

    Mantém sincronizado o contador dispositivos_usados em AssinaturaCliente
    quando um dispositivo/conta de aplicativo é removido do sistema.
    """
    try:
        assinatura = instance.cliente.assinatura

        # Decrementar apenas se contador > 0 (evitar valores negativos)
        if assinatura.dispositivos_usados > 0:
            assinatura.dispositivos_usados -= 1
            assinatura.save(update_fields=['dispositivos_usados'])

            logger.info(
                f"[CONTADOR] Dispositivo removido. Cliente: {instance.cliente.nome} - "
                f"Dispositivos: {assinatura.dispositivos_usados}/{assinatura.plano.max_dispositivos}"
            )
        else:
            logger.warning(
                f"[CONTADOR] Tentativa de decrementar contador já zerado. "
                f"Cliente: {instance.cliente.nome}"
            )

    except AttributeError:
        # Cliente não tem assinatura
        logger.warning(
            f"[CONTADOR] Cliente {instance.cliente.nome} (ID: {instance.cliente.id}) "
            f"não possui AssinaturaCliente ao remover dispositivo."
        )
    except Exception as e:
        logger.error(
            f"[CONTADOR] Erro ao decrementar dispositivos para {instance.cliente.nome}: {str(e)}",
            exc_info=True
        )


# ============================================================================
# Sincronização automática Cliente ↔ ContaDoAplicativo (conta principal)
# ============================================================================

@receiver(post_save, sender='nossopainel.ContaDoAplicativo')
def sincronizar_conta_principal(sender, instance, **kwargs):
    """
    Sincroniza Cliente.dispositivo e Cliente.sistema quando uma conta principal é salva.

    Este signal garante que os campos legados do Cliente (dispositivo e sistema)
    sempre reflitam os dados da conta marcada como principal, mantendo
    compatibilidade com código legado e relatórios.

    A sincronização ocorre automaticamente quando:
    - Uma conta é marcada como principal (is_principal=True)
    - Os dados de uma conta já principal são modificados

    Nota: Se for usar o método marcar_como_principal(), ele já faz a sincronização,
    então este signal serve como garantia adicional para edições diretas.
    """
    from .models import ContaDoAplicativo

    # ========== DEBUG: Log de entrada do signal ==========
    logger.debug(
        f"[SINCRONIZAÇÃO] Signal chamado para conta ID {instance.id} - "
        f"Cliente: {instance.cliente.nome} - "
        f"is_principal={instance.is_principal}"
    )

    # Só sincroniza se esta conta é principal
    if not instance.is_principal:
        logger.debug(f"[SINCRONIZAÇÃO] Conta {instance.id} NÃO é principal. Saindo sem sincronizar.")
        return

    try:
        cliente = instance.cliente

        # Log dos valores antes da atualização
        logger.debug(
            f"[SINCRONIZAÇÃO] ANTES - Cliente.dispositivo: {cliente.dispositivo.nome if cliente.dispositivo else 'None'}, "
            f"Cliente.sistema: {cliente.sistema.nome if cliente.sistema else 'None'} | "
            f"Conta.dispositivo: {instance.dispositivo.nome if instance.dispositivo else 'None'}, "
            f"Conta.app: {instance.app.nome}"
        )

        # Verifica se realmente precisa atualizar (evita save desnecessário)
        precisa_atualizar = False

        if cliente.dispositivo != instance.dispositivo:
            logger.debug(f"[SINCRONIZAÇÃO] Dispositivo DIFERENTE - atualizando de {cliente.dispositivo} para {instance.dispositivo}")
            cliente.dispositivo = instance.dispositivo
            precisa_atualizar = True

        if cliente.sistema != instance.app:
            logger.debug(f"[SINCRONIZAÇÃO] Sistema DIFERENTE - atualizando de {cliente.sistema} para {instance.app}")
            cliente.sistema = instance.app
            precisa_atualizar = True

        if precisa_atualizar:
            # Usa update_fields para evitar trigger de outros signals desnecessariamente
            cliente.save(update_fields=['dispositivo', 'sistema'])

            logger.info(
                f"[SINCRONIZAÇÃO] ✅ Conta principal atualizada. Cliente: {cliente.nome} - "
                f"Dispositivo: {instance.dispositivo.nome if instance.dispositivo else 'N/A'} - "
                f"App: {instance.app.nome}"
            )
        else:
            logger.debug(f"[SINCRONIZAÇÃO] Nenhuma mudança detectada. Não precisa atualizar.")

    except Exception as e:
        logger.error(
            f"[SINCRONIZAÇÃO] ❌ Erro ao sincronizar conta principal para cliente {instance.cliente.nome}: {str(e)}",
            exc_info=True
        )


# ============================================================================
# SIGNALS PARA CONTROLE DE LIMITE MEI - MUDANÇA DE PLANO
# ============================================================================

# Cache para detectar mudança de plano
_clientes_plano_anterior = {}

@receiver(pre_save, sender=Cliente)
def registrar_plano_anterior(sender, instance, **kwargs):
    """Captura o plano atual do cliente antes de salvar para detectar mudanças."""
    if instance.pk:
        try:
            cliente_existente = Cliente.objects.get(pk=instance.pk)
            _clientes_plano_anterior[instance.pk] = {
                'plano_id': cliente_existente.plano_id,
                'plano_nome': cliente_existente.plano.nome if cliente_existente.plano else None,
                'plano_valor': cliente_existente.plano.valor if cliente_existente.plano else None,
            }
        except Cliente.DoesNotExist:
            pass


@receiver(post_save, sender=Cliente)
def verificar_limite_apos_mudanca_plano(sender, instance, created, **kwargs):
    """
    Verifica se mudança de plano afeta limites MEI e cria notificação se necessário.

    Dispara quando:
    - Cliente muda de plano
    - A mudança aumenta o valor anual projetado
    - O novo total ultrapassa o limite configurado
    """
    from decimal import Decimal
    from .models import (
        ClienteContaBancaria, ConfiguracaoLimite,
        NotificacaoSistema, Plano
    )

    func_name = verificar_limite_apos_mudanca_plano.__name__

    # Ignorar clientes novos ou cancelados
    if created or instance.cancelado:
        if instance.pk in _clientes_plano_anterior:
            _clientes_plano_anterior.pop(instance.pk, None)
        return

    # Verificar se houve mudança de plano
    if instance.pk not in _clientes_plano_anterior:
        return

    plano_anterior_info = _clientes_plano_anterior.pop(instance.pk)
    plano_anterior_id = plano_anterior_info.get('plano_id')
    plano_atual_id = instance.plano_id

    if plano_anterior_id == plano_atual_id:
        return  # Plano não mudou

    # Identificar se é novo cliente (primeira atribuição de plano) ou mudança
    is_novo_cliente = plano_anterior_id is None

    # Mapear pagamentos por ano
    PAGAMENTOS_POR_ANO = {
        'Mensal': 12,
        'Bimestral': 6,
        'Trimestral': 4,
        'Semestral': 2,
        'Anual': 1,
    }

    # Calcular valores anuais
    plano_anterior_nome = plano_anterior_info.get('plano_nome', 'Mensal')
    plano_anterior_valor = plano_anterior_info.get('plano_valor', Decimal('0'))
    pagamentos_anterior = PAGAMENTOS_POR_ANO.get(plano_anterior_nome, 12)
    valor_anual_anterior = float(plano_anterior_valor * pagamentos_anterior) if plano_anterior_valor else 0

    plano_atual_nome = instance.plano.nome if instance.plano else 'Mensal'
    plano_atual_valor = instance.plano.valor if instance.plano else Decimal('0')
    pagamentos_atual = PAGAMENTOS_POR_ANO.get(plano_atual_nome, 12)
    valor_anual_atual = float(plano_atual_valor * pagamentos_atual)

    impacto_valor = valor_anual_atual - valor_anual_anterior

    # Log da mudança
    logger.info(
        f"[LIMITE_MEI] Mudança de plano detectada: {instance.nome} - "
        f"{plano_anterior_nome} (R$ {plano_anterior_valor}) → {plano_atual_nome} (R$ {plano_atual_valor}) - "
        f"Impacto anual: R$ {impacto_valor:+.2f}"
    )

    # Obter informações da conta bancária (via forma de pagamento do cliente)
    conta_info = None
    if instance.forma_pgto and instance.forma_pgto.conta_bancaria:
        conta = instance.forma_pgto.conta_bancaria
        conta_info = f"{conta.nome_identificacao} ({conta.instituicao.nome})"

    # Criar notificação de mudança/criação de plano
    try:
        NotificacaoSistema.criar_alerta_mudanca_plano(
            usuario=instance.usuario,
            cliente=instance,
            plano_antigo=f"{plano_anterior_nome} (R$ {plano_anterior_valor})" if not is_novo_cliente else None,
            plano_novo=f"{plano_atual_nome} (R$ {plano_atual_valor})",
            impacto_valor=impacto_valor,
            valor_anual_anterior=valor_anual_anterior,
            valor_anual_atual=valor_anual_atual,
            conta_info=conta_info,
            is_novo_cliente=is_novo_cliente
        )
    except Exception as e:
        logger.error(f"[LIMITE_MEI] Erro ao criar notificação de mudança de plano: {e}")

    # Se valor aumentou, verificar impacto nos limites das contas associadas
    if impacto_valor > 0:
        verificar_limites_contas_cliente(instance, impacto_valor)


def verificar_limites_contas_cliente(cliente, impacto_valor):
    """
    Verifica se o aumento de valor do cliente ultrapassa limites das contas associadas.

    Regras:
    - FastDePix: NÃO monitora limites (não tem restrição)
    - MEI: usa limite config.valor_anual
    - Pessoa Física: usa limite config.valor_anual_pf
    """
    from decimal import Decimal
    from .models import (
        ClienteContaBancaria, ContaBancaria, ConfiguracaoLimite,
        NotificacaoSistema
    )

    # Mapeamento de pagamentos por ano
    PAGAMENTOS_POR_ANO = {
        'Mensal': 12,
        'Bimestral': 6,
        'Trimestral': 4,
        'Semestral': 2,
        'Anual': 1,
    }

    # Buscar contas bancárias às quais o cliente está associado
    associacoes = ClienteContaBancaria.objects.filter(
        cliente=cliente,
        ativo=True
    ).select_related('conta_bancaria', 'conta_bancaria__instituicao')

    if not associacoes.exists():
        return  # Cliente não está associado a nenhuma conta

    # Obter configuração de limite
    config = ConfiguracaoLimite.get_config()
    margem = config.margem_seguranca
    percentual_alerta = 100 - margem  # Ex: 90% para margem de 10%

    for assoc in associacoes:
        conta = assoc.conta_bancaria

        # FastDePix não tem limite monitorado
        if conta.instituicao and conta.instituicao.tipo_integracao == 'fastdepix':
            logger.debug(f"[LIMITE] Conta {conta.id} é FastDePix - ignorando monitoramento de limite")
            continue

        # Determinar tipo de conta e limite aplicável
        tipo_conta = conta.tipo_conta  # 'mei' ou 'pf'
        if tipo_conta == 'mei':
            limite_aplicavel = float(config.valor_anual)
            tipo_label = 'MEI'
            limite_formatado = f"R$ {config.valor_anual:,.2f}"
        else:
            limite_aplicavel = float(config.valor_anual_pf)
            tipo_label = 'Pessoa Física'
            limite_formatado = f"R$ {config.valor_anual_pf:,.2f}"

        # Calcular total anual projetado de todos os clientes ATIVOS associados à conta
        # (clientes cancelados não interferem nos limites)
        clientes_conta = ClienteContaBancaria.objects.filter(
            conta_bancaria=conta,
            ativo=True,
            cliente__cancelado=False
        ).select_related('cliente__plano')

        total_anual = Decimal('0')
        for cc in clientes_conta:
            if cc.cliente.plano:
                pagamentos = PAGAMENTOS_POR_ANO.get(cc.cliente.plano.nome, 12)
                total_anual += cc.cliente.plano.valor * pagamentos

        total_anual_float = float(total_anual)
        percentual_atual = (total_anual_float / limite_aplicavel) * 100 if limite_aplicavel > 0 else 0

        # Verificar se ultrapassou alerta ou limite
        if percentual_atual >= 99:
            # Limite crítico atingido
            try:
                # Verificar se já existe notificação recente (últimas 24h) para evitar spam
                from django.utils import timezone
                from datetime import timedelta

                notif_recente = NotificacaoSistema.objects.filter(
                    usuario=cliente.usuario,
                    tipo='limite_atingido',
                    dados_extras__conta_id=conta.id,
                    criada_em__gte=timezone.now() - timedelta(hours=24)
                ).exists()

                if not notif_recente:
                    # Mensagem personalizada por tipo de conta
                    if tipo_conta == 'mei':
                        mensagem = (
                            f'A conta "{conta.beneficiario or conta.instituicao}" atingiu '
                            f'{percentual_atual:.1f}% do limite de faturamento anual do MEI ({limite_formatado}). '
                            f'Valor total projetado: R$ {total_anual_float:,.2f}. '
                            f'Ação necessária: realoque alguns clientes para outra Forma de Pagamento para '
                            f'manter o valor projetado para recebimento anual dentro do limite do MEI, '
                            f'caso contrário, o Leão poderá lhe comer vivo. '
                            f'Recomendado: separe os recebimentos entre uma conta FastDePix e MEI, '
                            f'mantendo o maior volume de recebimento em FastDePix.'
                        )
                    else:
                        mensagem = (
                            f'A conta "{conta.beneficiario or conta.instituicao}" atingiu '
                            f'{percentual_atual:.1f}% do limite de faturamento anual de Pessoa Física ({limite_formatado}). '
                            f'Valor total projetado: R$ {total_anual_float:,.2f}. '
                            f'Ação necessária: realoque alguns clientes para outra Forma de Pagamento para '
                            f'manter o valor projetado para recebimento anual dentro do limite da Pessoa Física, '
                            f'caso contrário, o Leão poderá lhe comer vivo. '
                            f'Recomendado: separe os recebimentos entre uma conta FastDePix e Pessoa Física, '
                            f'mantendo o maior volume de recebimento em FastDePix.'
                        )

                    NotificacaoSistema.objects.create(
                        usuario=cliente.usuario,
                        tipo='limite_atingido',
                        prioridade='critica',
                        titulo=f'⚠️ LIMITE CRÍTICO: {percentual_atual:.1f}%',
                        mensagem=mensagem,
                        dados_extras={
                            'conta_id': conta.id,
                            'conta_nome': conta.beneficiario or str(conta.instituicao),
                            'tipo_conta': tipo_conta,
                            'tipo_label': tipo_label,
                            'percentual': percentual_atual,
                            'valor_atual': total_anual_float,
                            'valor_limite': limite_aplicavel,
                            'cliente_causador': cliente.nome,
                            'impacto_valor': impacto_valor,
                        }
                    )
                    logger.warning(
                        f"[LIMITE_{tipo_label.upper()}] Notificação CRÍTICA criada para conta {conta.id} - "
                        f"{percentual_atual:.1f}% do limite"
                    )
            except Exception as e:
                logger.error(f"[LIMITE] Erro ao criar notificação crítica: {e}")

        elif percentual_atual >= percentual_alerta:
            # Alerta de aproximação do limite
            try:
                NotificacaoSistema.criar_alerta_limite(
                    usuario=cliente.usuario,
                    conta_bancaria=conta,
                    percentual_atual=percentual_atual,
                    valor_atual=total_anual_float,
                    valor_limite=limite_aplicavel
                )
                logger.info(
                    f"[LIMITE_{tipo_label.upper()}] Notificação de alerta criada para conta {conta.id} - "
                    f"{percentual_atual:.1f}% do limite"
                )
            except Exception as e:
                logger.error(f"[LIMITE] Erro ao criar notificação de alerta: {e}")
