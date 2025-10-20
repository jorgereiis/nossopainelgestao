"""Funções auxiliares utilizadas nas rotinas de cadastros e automações."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import logging
import os
import re

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import localtime, now
from .models import (
    Cliente,
    ClientePlanoHistorico,
    Mensalidade,
    Plano,
    PlanoIndicacao,
    SessaoWpp,
    UserActionLog,
)
from cadastros.services.logging import append_line
from cadastros.services.wpp import (
    LogTemplates,
    MessageSendConfig,
    send_message,
)
from wpp.api_connection import (
    check_number_status,
)

logger = logging.getLogger(__name__)

URL_API_WPP = os.getenv("URL_API_WPP")
USER_SESSION_WPP = os.getenv("USER_SESSION_WPP")
MEU_NUM_CLARO = os.getenv("MEU_NUM_CLARO")
DIR_LOGS_AGENDADOS = os.getenv("DIR_LOGS_AGENDADOS")
DIR_LOGS_INDICACOES = os.getenv("DIR_LOGS_INDICACOES")
TEMPLATE_LOG_MSG_SUCESSO = os.getenv("TEMPLATE_LOG_MSG_SUCESSO")
TEMPLATE_LOG_MSG_FALHOU = os.getenv("TEMPLATE_LOG_MSG_FALHOU")
TEMPLATE_LOG_TELEFONE_INVALIDO = os.getenv("TEMPLATE_LOG_TELEFONE_INVALIDO")


def get_saudacao_por_hora(hora_referencia=None):
    """Retorna saudação contextual de acordo com a hora informada ou atual."""
    if not hora_referencia:
        hora_referencia = localtime(now()).time()

    if hora_referencia < datetime.strptime("12:00:00", "%H:%M:%S").time():
        return "Bom dia"
    elif hora_referencia < datetime.strptime("18:00:00", "%H:%M:%S").time():
        return "Boa tarde"
    return "Boa noite"


def registrar_log(mensagem: str, usuario: str, log_directory: str) -> None:
    """Anexa ``mensagem`` ao arquivo de log associado ao ``usuario``."""
    if not log_directory:
        logger.warning("Log directory not configured for usuario=%s. Mensagem: %s", usuario, mensagem)
        return

    log_filename = Path(log_directory) / f"{usuario}.log"
    append_line(log_filename, mensagem)


def historico_obter_vigente(cliente: Cliente):
    """Retorna o registro de histórico vigente (sem fim) do cliente, se existir."""
    return (
        ClientePlanoHistorico.objects
        .filter(cliente=cliente, usuario=cliente.usuario, fim__isnull=True)
        .order_by('-inicio', '-criado_em')
        .first()
    )


def historico_encerrar_vigente(cliente: Cliente, fim: date) -> None:
    """Fecha o histórico ativo do cliente na data fornecida, respeitando o início."""
    vigente = historico_obter_vigente(cliente)
    if not vigente:
        return
    if fim < vigente.inicio:
        fim = vigente.inicio
    vigente.fim = fim
    vigente.save(update_fields=["fim"])


def historico_iniciar(
    cliente: Cliente,
    plano: Plano = None,
    inicio: date = None,
    motivo: str = ClientePlanoHistorico.MOTIVO_CREATE,
) -> ClientePlanoHistorico:
    """Cria um novo registro de histórico ajustando valores padrão quando necessários."""
    if inicio is None:
        inicio = timezone.localdate()
    if plano is None:
        plano = cliente.plano
    return ClientePlanoHistorico.objects.create(
        cliente=cliente,
        usuario=cliente.usuario,
        plano=plano,
        plano_nome=getattr(plano, 'nome', ''),
        telas=getattr(plano, 'telas', 1) or 1,
        valor_plano=getattr(plano, 'valor', 0) or 0,
        inicio=inicio,
        motivo=motivo,
    )



def _prepare_extra_payload(value):
    """Normaliza payloads extras para serem serializados em ``JSONField``."""
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {str(key): _prepare_extra_payload(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_prepare_extra_payload(item) for item in value]

    return str(value)


def log_user_action(
    request,
    action: str,
    instance=None,
    message: str = "",
    extra=None,
    entity: str = None,
    object_id=None,
    object_repr: str = None,
) -> None:
    """Registra uma ação manual do usuário autenticado no ``UserActionLog``."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return

    try:
        if entity is None and instance is not None:
            entity = instance.__class__.__name__

        if object_id is None and instance is not None:
            object_id = getattr(instance, "pk", "") or ""

        if object_repr is None and instance is not None:
            object_repr = str(instance)

        ip_address = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if ip_address:
            ip_address = ip_address.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR", "")

        payload = {
            "usuario": user,
            "acao": action if action in dict(UserActionLog.ACTION_CHOICES) else UserActionLog.ACTION_OTHER,
            "entidade": entity or "",
            "objeto_id": str(object_id) if object_id not in (None, "") else "",
            "objeto_repr": (object_repr or "")[:255],
            "mensagem": message or "",
            "extras": _prepare_extra_payload(extra),
            "ip": ip_address or None,
            "request_path": (getattr(request, "path", "") or "")[:255],
        }

        UserActionLog.objects.create(**payload)

    except Exception as exc:
        logger.exception("Falha ao registrar log de ação do usuário: %s", exc)


def gerar_variacoes_telefone2(telefone: str) -> list:
    """Retorna variações comuns de números nacionais para pesquisa em banco."""
    variacoes = set()
    tel = re.sub(r'\D+', '', telefone)
    logger.debug("[TEL_VARIACOES] Gerando variações para: %s", tel)

    if len(tel) < 8:
        logger.debug("[TEL_VARIACOES] Telefone muito curto, retornando: %s", tel)
        return [tel]
    if len(tel) == 11 and tel[2] == '9':
        variacoes.add(tel)
        variacoes.add(tel[2:])
        variacoes.add(tel[3:])
        variacoes.add('55' + tel)
        variacoes.add('55' + tel[:2] + tel[3:])
        logger.debug("[TEL_VARIACOES] Variações (celular atual): %s", variacoes)
    elif len(tel) == 10:
        variacoes.add(tel)
        variacoes.add(tel[2:])
        variacoes.add('9' + tel[2:])
        variacoes.add('55' + tel)
        variacoes.add('55' + tel[:2] + '9' + tel[2:])
        logger.debug("[TEL_VARIACOES] Variações (fixo/cel sem 9): %s", variacoes)
    elif len(tel) == 9 and tel[0] == '9':
        variacoes.add(tel)
        variacoes.add(tel[1:])
        logger.debug("[TEL_VARIACOES] Variações (9 + NNNNNNNN): %s", variacoes)
    elif len(tel) == 8:
        variacoes.add(tel)
        logger.debug("[TEL_VARIACOES] Variações (NNNNNNNN): %s", variacoes)
    elif len(tel) == 13 and tel.startswith('55'):
        variacoes.add(tel)
        variacoes.add(tel[:4] + tel[5:])
        logger.debug("[TEL_VARIACOES] Variações (55DD9NNNNNNNN): %s", variacoes)
    elif len(tel) == 12 and tel.startswith('55'):
        variacoes.add(tel)
        variacoes.add(tel[:4] + '9' + tel[4:])
        logger.debug("[TEL_VARIACOES] Variações (55DDNNNNNNNN): %s", variacoes)
    if len(tel) > 8:
        variacoes.add(tel)
    logger.debug("[TEL_VARIACOES] Variações finais: %s", variacoes)
    return sorted(variacoes)


def gerar_variacoes_telefone(telefone: str) -> set:
    """Gera variações básicas (com/sem DDI) utilizadas na busca de clientes existentes."""
    tel = re.sub(r'\D+', '', telefone)
    variacoes = set()

    # Base sempre com e sem +
    if tel.startswith('55'):
        variacoes.add(tel)
        variacoes.add('+' + tel)
    else:
        variacoes.add(tel)
        variacoes.add('55' + tel)
        variacoes.add('+55' + tel)

    if len(tel) == 13 and tel[4] == '9':
        sem_nove = tel[:4] + tel[5:]
        variacoes.add(sem_nove)
        variacoes.add('+' + sem_nove)
    elif len(tel) == 11 and tel[2] == '9':
        sem_nove = tel[:2] + tel[3:]
        variacoes.add(sem_nove)
        variacoes.add('+' + sem_nove)

    return variacoes


def existe_cliente_variacoes(telefone_variacoes, user):
    """Confere se alguma variação pertence a clientes cadastrados do usuário."""
    q = Q()
    for var in telefone_variacoes:
        telefone_formatado = var if str(var).startswith('+') else f'+{str(var)}'
        q |= Q(telefone=telefone_formatado)
    
    cliente = Cliente.objects.filter(q, usuario=user).first()
    if cliente:
        cliente_telefone = cliente.telefone
    else:
        cliente_telefone = None

    return cliente_telefone

def validar_tel_whatsapp(telefone: str, token: str, user=None) -> dict:
    """
    Valida um telefone contra a base de clientes e a API do WhatsApp.

    Retorna um dicionário contendo o telefone original, o telefone formatado
    para WhatsApp (quando válido), a existência de cliente associado e se o
    número está apto a receber mensagens.
    """
    func_name = validar_tel_whatsapp.__name__
    telefone_variacoes = gerar_variacoes_telefone(telefone)
    resultado = {
        "telefone_cadastro": telefone,
        "telefone_validado_wpp": None,
        "cliente_existe_telefone": None,
        "wpp": False,
    }
    wpp_valido = False

    try:
        check = check_number_status(telefone, token, user)
        if check.get("status"):
            wpp_valido = True
            telefone = str(check.get("user") or telefone)
    except Exception as exc:
        logger.error("[VALIDAR][ERRO] Erro ao checar %s no WhatsApp: %s", telefone, exc)

    if not wpp_valido:
        return resultado

    numero_formatado = telefone if str(telefone).startswith('+') else f'+{telefone}'
    resultado["telefone_validado_wpp"] = numero_formatado
    resultado["wpp"] = True
    resultado["cliente_existe_telefone"] = existe_cliente_variacoes(telefone_variacoes, user)

    logger.info("[%s] [%s] Resultado da validação: %s", func_name, user, resultado)
    return resultado


def envio_apos_novo_cadastro(cliente):
    """
    Após cadastrar um novo cliente, envia mensagem de boas-vindas e, se houver indicação,
    avalia bônus para o cliente indicador.
    """
    usuario = cliente.usuario
    nome_cliente = str(cliente)
    primeiro_nome = nome_cliente.split(' ')[0]

    tipo_envio = "Cadastro"
    token_user = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    if not token_user:
        return

    telefone = str(cliente.telefone or "").strip()

    if not telefone:
        return

    mensagem = (
        f"Obrigado, {primeiro_nome}. O seu pagamento foi confirmado e o seu acesso já foi disponibilizado!\n\n"
        "A partir daqui, caso precise de algum auxílio pode entrar em contato.\n"
        "Peço que salve o nosso contato para que receba as nossas notificações aqui no WhatsApp."
    )

    try:
        enviar_mensagem(
            telefone,
            mensagem,
            usuario,
            token_user.token,
            nome_cliente,
            tipo_envio
        )
    except Exception as e:
        logger.error(f"[WPP] Falha ao enviar mensagem para {telefone}: {e}", exc_info=True)

    plano_indicacao_ativo = PlanoIndicacao.objects.filter(usuario=usuario, ativo=True).first()
    if cliente.indicado_por and plano_indicacao_ativo:
        envio_apos_nova_indicacao(usuario, cliente, cliente.indicado_por)


def envio_apos_nova_indicacao(usuario, novo_cliente, cliente_indicador):
    """
    Avalia a quantidade de indicações feitas por um cliente e envia mensagem de bonificação com descontos ou prêmios.

    - 1 indicação: aplica desconto na mensalidade atual em aberto (com valor cheio), ou na próxima disponível.
    - 2 indicações: bonificação em dinheiro (deduzindo eventual desconto já concedido se a mensalidade foi paga).

    Regras:
    - Para aplicar desconto, deve haver PlanoIndicacao ativo do tipo 'desconto'.
    - Para aplicar bonificação, deve haver PlanoIndicacao ativo do tipo 'dinheiro'.
    - Valor final da mensalidade não pode ser inferior ao valor mínimo definido no plano.
    - Caso a mensalidade com desconto ainda esteja em aberto ao receber a segunda indicação, ela será ajustada de volta ao valor original, e o bônus será pago integralmente.
    """
    nome_cliente = str(cliente_indicador)
    telefone_cliente = str(cliente_indicador.telefone)
    primeiro_nome = nome_cliente.split(' ')[0]
    tipo_envio = "Indicação"
    now = datetime.now()

    try:
        token_user = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    except SessaoWpp.DoesNotExist:
        return

    if not telefone_cliente:
        return

    # Planos ativos
    plano_desconto = PlanoIndicacao.objects.filter(tipo_plano="desconto", usuario=usuario, ativo=True).first()
    plano_dinheiro = PlanoIndicacao.objects.filter(tipo_plano="dinheiro", usuario=usuario, ativo=True).first()

    if not plano_desconto and not plano_dinheiro:
        return # Nenhum plano ativo, então não há benefício

    # Mensalidades
    mensalidades_em_aberto = Mensalidade.objects.filter(
        cliente=cliente_indicador,
        dt_pagamento=None,
        dt_cancelamento=None,
        pgto=False,
        cancelado=False
    ).order_by('dt_vencimento')

    mensalidade_mes_atual_paga = Mensalidade.objects.filter(
        cliente=cliente_indicador,
        dt_pagamento__month=now.month,
        dt_pagamento__year=now.year,
        pgto=True
    ).first()

    qtd_indicacoes = Cliente.objects.filter(
        indicado_por=cliente_indicador,
        data_adesao__gte=now.replace(day=1)
    ).count()

    saudacao = get_saudacao_por_hora()

    # 1 INDICAÇÃO - DESCONTO
    if qtd_indicacoes == 1 and plano_desconto:
        mensalidade_alvo = None
        for m in mensalidades_em_aberto:
            if m.valor == cliente_indicador.plano.valor:
                mensalidade_alvo = m
                break
        if not mensalidade_alvo:
            for m in mensalidades_em_aberto:
                if m.valor > plano_desconto.valor_minimo_mensalidade:
                    mensalidade_alvo = m
                    break

        if mensalidade_alvo:
            novo_valor = max(mensalidade_alvo.valor - plano_desconto.valor, plano_desconto.valor_minimo_mensalidade)
            vencimento = mensalidade_alvo.dt_vencimento.strftime("%d/%m")
            valor_formatado = f"{novo_valor:.2f}"

            mensagem = (
                f"Olá, {primeiro_nome}. {saudacao}!\n\n"
                f"Agradeço pela indicação do(a) *{novo_cliente.nome}*.\n"
                f"A adesão dele(a) foi concluída e por isso estamos lhe bonificando com desconto.\n\n"
                f"⚠ *FIQUE ATENTO AO SEU VENCIMENTO:*\n\n- [{vencimento}] R$ {valor_formatado}\n\nObrigado! 😁"
            )

            mensalidade_alvo.valor = novo_valor
            mensalidade_alvo.save()
            enviar_mensagem(telefone_cliente, mensagem, usuario, token_user.token, nome_cliente, tipo_envio)

    # 2 INDICAÇÕES - BONIFICAÇÃO
    elif qtd_indicacoes == 2 and plano_dinheiro:
        bonus_total = plano_dinheiro.valor
        desconto_aplicado = Decimal("0.00")
        mensagem_extra = ""
        aplicar_deducao = False

        mensalidade_aberta_com_desconto = None
        for m in mensalidades_em_aberto:
            if m.valor < cliente_indicador.plano.valor:
                mensalidade_aberta_com_desconto = m
                break

        if mensalidade_aberta_com_desconto:
            desconto_aplicado = cliente_indicador.plano.valor - mensalidade_aberta_com_desconto.valor
            mensalidade_aberta_com_desconto.valor = cliente_indicador.plano.valor
            mensalidade_aberta_com_desconto.save()
            # Não aplica dedução no bônus
            aplicar_deducao = False

        elif mensalidade_mes_atual_paga and mensalidade_mes_atual_paga.valor < cliente_indicador.plano.valor:
            desconto_aplicado = cliente_indicador.plano.valor - mensalidade_mes_atual_paga.valor
            aplicar_deducao = True

        if aplicar_deducao:
            bonus_final = max(bonus_total - desconto_aplicado, Decimal("0.00"))
            mensagem_extra = (
                f"💡 Como você já havia recebido R$ {desconto_aplicado:.2f} de desconto em sua mensalidade deste mês, este valor foi deduzido do bônus.\n"
                f"Seu bônus total é de R$ {bonus_total:.2f}, e após a dedução você receberá R$ {bonus_final:.2f}.\n\n"
            )
        else:
            bonus_final = bonus_total

        indicacoes = Cliente.objects.filter(
            indicado_por=cliente_indicador,
            data_adesao__gte=now.replace(day=1)
        )
        linhas = [f"- [{c.data_adesao.strftime('%d/%m')}] [{c.nome}]" for c in indicacoes]

        mensagem = (
            f"🎉 *PARABÉNS PELAS INDICAÇÕES!* 🎉\n\nOlá, {primeiro_nome}. {saudacao}! Tudo bem?\n\n"
            f"Agradecemos muito pela sua parceria e confiança em nossos serviços. Este mês, registramos as seguintes indicações feitas por você:\n\n"
            + "\n".join(linhas) +
            f"\n\n{mensagem_extra}"
            "Agora, você pode escolher como prefere:\n\n"
            "- *Receber o valor via PIX* em sua conta.\n"
            "- *Aplicar como desconto* nas suas próximas mensalidades.\n\n"
            "Nos avise aqui qual opção prefere, e nós registraremos a sua bonificação."
        )

        enviar_mensagem(telefone_cliente, mensagem, usuario, token_user.token, nome_cliente, tipo_envio)


def enviar_mensagem(telefone: str, mensagem: str, usuario: str, token: str, cliente: str, tipo_envio: str) -> None:
    """
    Envia uma mensagem via API WPP para um número validado.
    Registra logs de sucesso, falha e número inválido.
    """
    log_writer = lambda mensagem_log: registrar_log(mensagem_log, usuario, DIR_LOGS_INDICACOES)

    templates = LogTemplates(
        success=TEMPLATE_LOG_MSG_SUCESSO,
        failure=TEMPLATE_LOG_MSG_FALHOU,
        invalid=TEMPLATE_LOG_TELEFONE_INVALIDO,
    )

    config = MessageSendConfig(
        usuario=usuario,
        token=token,
        telefone=telefone,
        mensagem=mensagem,
        tipo_envio=tipo_envio,
        cliente=cliente,
        log_writer=log_writer,
        log_templates=templates,
        retry_wait=(5.0, 10.0),
    )
    resultado = send_message(config)

    if not resultado.success and resultado.reason == "missing_phone":
        timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
        log_line = templates.invalid.format(timestamp, tipo_envio.upper(), usuario, cliente)
        logger.warning(log_line.strip())


def definir_dia_pagamento(dia_adesao):
    """
    Define o dia padrão de pagamento com base no dia de adesão.
    Utiliza faixas de dias para arredondar a data de pagamento para dias fixos do mês.
    """
    if dia_adesao in range(3, 8):
        return 5
    elif dia_adesao in range(8, 13):
        return 10
    elif dia_adesao in range(13, 18):
        return 15
    elif dia_adesao in range(18, 23):
        return 20
    elif dia_adesao in range(23, 28):
        return 25
    return 30


# CRIA NOVA MENSALIDADE APÓS CADASTRO DE NOVO CLIENTE
def criar_mensalidade(cliente):
    """
    Cria automaticamente uma nova mensalidade ao cadastrar um novo cliente.
    A data de vencimento é calculada com base em:
    - Último pagamento (se houver)
    - Data de adesão (se houver)
    - Data de vencimento definida manualmente (fallback)
    O vencimento sempre aponta para o próximo ciclo válido, conforme o tipo do plano.
    """
    hoje = timezone.localdate()

    if cliente.ultimo_pagamento:
        dia_pagamento = definir_dia_pagamento(cliente.ultimo_pagamento.day)
    elif cliente.data_adesao and cliente.data_vencimento is None:
        dia_pagamento = definir_dia_pagamento(cliente.data_adesao.day)
    else:
        dia_pagamento = cliente.data_vencimento.day if cliente.data_vencimento else hoje.day

    mes = hoje.month
    ano = hoje.year

    try:
        vencimento = datetime(ano, mes, dia_pagamento)
    except ValueError:
        vencimento = (datetime(ano, mes, 1) + relativedelta(months=1)) - timedelta(days=1)

    if vencimento.date() < hoje:
        plano_nome = cliente.plano.nome.lower()
        if "mensal" in plano_nome:
            vencimento += relativedelta(months=1)
        elif "bimestral" in plano_nome:
            vencimento += relativedelta(months=2)
        elif "trimestral" in plano_nome:
            vencimento += relativedelta(months=3)
        elif "semestral" in plano_nome:
            vencimento += relativedelta(months=6)
        elif "anual" in plano_nome:
            vencimento += relativedelta(years=1)

    Mensalidade.objects.create(
        cliente=cliente,
        valor=cliente.plano.valor,
        dt_vencimento=vencimento.date(),
        usuario=cliente.usuario,
    )
