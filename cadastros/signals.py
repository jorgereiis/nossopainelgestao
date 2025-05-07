import os
import re
import json
import time
import random
import requests
from decimal import Decimal
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging

from django.utils import timezone
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Mensalidade, Cliente, Plano, PlanoIndicacao, SessaoWpp
from .utils import (
    check_number_status,
    get_label_contact,
    add_or_remove_label_contact,
    get_all_labels,
    criar_label_se_nao_existir,
    get_saudacao_por_hora,
)
# URL base da API do WhatsApp
URL_API_WPP = os.getenv("URL_API_WPP")

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')


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


@receiver(post_save, sender=Mensalidade)
def atualiza_ultimo_pagamento(sender, instance, **kwargs):
    """
    Atualiza o campo `ultimo_pagamento` do cliente sempre que uma mensalidade for paga com sucesso.
    """
    cliente = instance.cliente

    if instance.dt_pagamento and instance.pgto:
        if not cliente.ultimo_pagamento or instance.dt_pagamento > cliente.ultimo_pagamento:
            cliente.ultimo_pagamento = instance.dt_pagamento
            cliente.save()


@receiver(post_save, sender=Cliente)
def criar_mensalidade(sender, instance, created, **kwargs):
    """
    Cria automaticamente uma nova mensalidade ao cadastrar um novo cliente.
    A data de vencimento é calculada com base em:
    - Último pagamento (se houver)
    - Data de adesão (se houver)
    - Data de vencimento definida manualmente (fallback)
    O vencimento sempre aponta para o próximo ciclo válido, conforme o tipo do plano.
    """
    if not created:
        return

    hoje = timezone.localdate()

    # Define o dia de pagamento com base na lógica disponível
    if instance.ultimo_pagamento:
        dia_pagamento = definir_dia_pagamento(instance.ultimo_pagamento.day)
    elif instance.data_adesao and instance.data_vencimento is None:
        dia_pagamento = definir_dia_pagamento(instance.data_adesao.day)
    else:
        dia_pagamento = instance.data_vencimento.day if instance.data_vencimento else hoje.day

    # Calcula a data inicial do vencimento no mês atual
    mes = hoje.month
    ano = hoje.year

    try:
        vencimento = datetime(ano, mes, dia_pagamento)
    except ValueError:
        # Ex: 31 de fevereiro → último dia válido do mês
        vencimento = (datetime(ano, mes, 1) + relativedelta(months=1)) - timedelta(days=1)

    # Se o vencimento caiu no passado, ajusta com base no tipo de plano
    if vencimento.date() < hoje:
        plano_nome = instance.plano.nome.lower()
        if "mensal" in plano_nome:
            vencimento += relativedelta(months=1)
        elif "trimestral" in plano_nome:
            vencimento += relativedelta(months=3)
        elif "semestral" in plano_nome:
            vencimento += relativedelta(months=6)
        elif "anual" in plano_nome:
            vencimento += relativedelta(years=1)

    # Cria a mensalidade
    Mensalidade.objects.create(
        cliente=instance,
        valor=instance.plano.valor,
        dt_vencimento=vencimento.date(),
        usuario=instance.usuario,
    )


# CRIA NOVA MENSALIDADE APÓS A ATUAL SER PAGA
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
        elif "trimestral" in plano_nome:
            nova_data_vencimento += relativedelta(months=3)
        elif "semestral" in plano_nome:
            nova_data_vencimento += relativedelta(months=6)
        elif "anual" in plano_nome:
            nova_data_vencimento += relativedelta(years=1)

        Mensalidade.objects.create(
            cliente=instance.cliente,
            valor=instance.cliente.plano.valor,
            dt_vencimento=nova_data_vencimento,
            usuario=instance.usuario,
        )

        instance.cliente.data_vencimento = nova_data_vencimento
        instance.cliente.save()



# REALIZA ENVIO PARA CLIENTE INDICADOR QUANDO HOUVER CADASTRO DE NOVO CLIENTE COM INDICAÇÃO
@receiver(post_save, sender=Cliente)
def envio_apos_novo_cadastro(sender, instance, created, **kwargs):
    """
    Quando um novo cliente é criado, envia uma mensagem de boas-vindas e verifica se ele foi indicado por outro cliente.
    Caso tenha sido indicado e o cliente indicador possua PlanoIndicacao ativo, executa a rotina de bonificação ao indicador.
    """
    if not created:
        return

    usuario = instance.usuario
    nome_cliente = str(instance)
    primeiro_nome = nome_cliente.split(' ')[0]

    telefone_raw = str(instance.telefone or "").strip()
    telefone_digits = re.sub(r'\D', '', telefone_raw)

    if len(telefone_digits) < 10:
        return  # Número inválido

    telefone_formatado = '55' + telefone_digits
    tipo_envio = "Cadastro"

    token_user = SessaoWpp.objects.filter(usuario=usuario).first()
    if not token_user:
        return

    mensagem = (
        f"Obrigado, {primeiro_nome}. O seu pagamento foi confirmado e o seu acesso já foi disponibilizado!\n\n"
        "A partir daqui, caso precise de algum auxílio pode entrar em contato.\n"
        "Peço que salve o nosso contato para que receba as nossas notificações aqui no WhatsApp."
    )

    try:
        enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente, tipo_envio)
    except Exception as e:
        logger.error(f"[WPP] Falha ao enviar mensagem para {telefone_formatado}: {e}", exc_info=True)

    plano_indicacao_ativo = PlanoIndicacao.objects.filter(usuario=usuario, ativo=True).first()

    if instance.indicado_por and plano_indicacao_ativo:
        envio_apos_nova_indicacao(usuario, instance, instance.indicado_por)


# Função para realizar envio de mensagem após cadastro de um novo cliente. Além disso, verifica se o novo cliente veio por indicação e realiza envio ao cliente indicador.
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
    primeiro_nome = nome_cliente.split(' ')[0]
    telefone_formatado = '55' + re.sub(r'\D', '', str(cliente_indicador.telefone))
    tipo_envio = "Indicação"
    now = datetime.now()

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

    try:
        token_user = SessaoWpp.objects.get(usuario=usuario)
    except SessaoWpp.DoesNotExist:
        return

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
            enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente, tipo_envio)

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

        enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente, tipo_envio)



# Função para enviar mensagens e registrar em arquivo de log
def enviar_mensagem(telefone, mensagem, usuario, token, cliente, tipo):
    url = URL_API_WPP + '/{}/send-message'.format(usuario)
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {
        'phone': telefone,
        'message': mensagem,
        'isGroup': False
    }

    max_tentativas = 3  # Definir o número máximo de tentativas
    tentativa = 1

    # Nome do arquivo de log baseado no nome do usuário
    log_directory = './logs/Envios indicacoes realizadas/'
    log_filename = os.path.join(log_directory, '{}.log'.format(usuario))
    data_hora_atual = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    while tentativa <= max_tentativas:
        if tentativa == 2:
            tel = telefone
            if tel.startswith('55'):
                tel = tel[2:]

                body = {
                    'phone': tel,
                    'message': mensagem,
                    'isGroup': False
                }
        response = requests.post(url, headers=headers, json=body)

        # Verificar se o diretório de logs existe e criar se necessário
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)
        # Verificar se o arquivo de log existe e criar se necessário
        if not os.path.isfile(log_filename):
            open(log_filename, 'w').close()
        # Verificar o status da resposta e tomar ações apropriadas, se necessário
        if response.status_code == 200 or response.status_code == 201:
            with open(log_filename, 'a') as log_file:
                log_file.write('[{}] [TIPO][{}] [USUÁRIO][{}] [CLIENTE][{}] Mensagem enviada!\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), tipo, usuario, cliente))
            break  # Sai do loop se a resposta for de sucesso
        elif response.status_code == 400:
            response_data = json.loads(response.text)
            error_message = response_data.get('message')
            with open(log_filename, 'a') as log_file:
                log_file.write('[{}] [TIPO][{}] [USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), tipo, usuario, cliente, response.status_code, tentativa, error_message))
        else:
            print(f"[ERRO ENVIO DE MSGS] [{response.status_code}] \n [{response.text}]")
            response_data = json.loads(response.text)
            error_message = response_data.get('message')
            with open(log_filename, 'a') as log_file:
                log_file.write('[{}] [TIPO][{}] [USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), tipo, usuario, cliente, response.status_code, tentativa, error_message))

        # Incrementa o número de tentativas
        tentativa += 1

        # Tempo de espera aleatório entre cada tentativa com limite máximo de 50 segundos
        tempo_espera = random.uniform(20, 50)
        time.sleep(tempo_espera)


# ALTERAR LABEL DO CONTATO NO WHATSAPP APÓS NOVO CADASTRO OU ALTERAÇÃO DE CLIENTE
# Armazena valores antigos antes do save
_clientes_servidor_anterior = {}
_clientes_cancelado_anterior = {}

# Mapeamento fixo de labels para hexColor
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
    if instance.pk:
        try:
            cliente_existente = Cliente.objects.get(pk=instance.pk)
            _clientes_servidor_anterior[instance.pk] = cliente_existente.servidor_id
            _clientes_cancelado_anterior[instance.pk] = cliente_existente.cancelado
        except Cliente.DoesNotExist:
            pass

@receiver(post_save, sender=Cliente)
def cliente_post_save(sender, instance, created, **kwargs):
    servidor_foi_modificado = False
    cliente_foi_cancelado = False
    cliente_foi_reativado = False

    if not created:
        # Detecta mudança de servidor
        if instance.pk in _clientes_servidor_anterior:
            servidor_anterior_id = _clientes_servidor_anterior.pop(instance.pk)
            servidor_foi_modificado = servidor_anterior_id != instance.servidor_id

        # Detecta mudança de cancelamento
        if instance.pk in _clientes_cancelado_anterior:
            cancelado_anterior = _clientes_cancelado_anterior.pop(instance.pk)
            cliente_foi_cancelado = not cancelado_anterior and instance.cancelado
            cliente_foi_reativado = cancelado_anterior and not instance.cancelado

    # Se for novo, ou mudou servidor, ou cancelado, ou reativado
    if created or servidor_foi_modificado or cliente_foi_cancelado or cliente_foi_reativado:
        telefone = re.sub(r'\D+', '', instance.telefone)
        telefone_com_55 = f'55{telefone}'

        # Obtém token da sessão
        try:
            token = SessaoWpp.objects.get(usuario=instance.usuario).token
        except SessaoWpp.DoesNotExist:
            print(f"⚠️ Sessão do WhatsApp não encontrada para o usuário {instance.usuario}")
            return

        # Verifica se número existe no WhatsApp
        try:
            numero_existe = check_number_status(telefone_com_55, token)
            if not numero_existe:
                print(f"⚠️ Número {telefone} não é válido no WhatsApp.")
                return
        except Exception as e:
            print(f"❌ Erro ao verificar número no WhatsApp: {e}")
            return

        # Obtém labels atuais
        try:
            labels_atuais = get_label_contact(telefone_com_55, token)
        except Exception as e:
            print(f"❌ Erro ao obter labels atuais do contato: {e}")
            labels_atuais = []

        # Define a nova label de acordo com o contexto
        try:
            if cliente_foi_cancelado:
                label_desejada = "CANCELADOS"
            else:
                label_desejada = instance.servidor.nome

            # Escolhe a cor fixa, se existir
            hex_color = LABELS_CORES_FIXAS.get(label_desejada.upper())

            # Cria label se necessário (agora passando a cor fixa)
            nova_label_id = criar_label_se_nao_existir(label_desejada, token, hex_color=hex_color)
            if not nova_label_id:
                print(f"⚠️ Não foi possível obter ou criar a label '{label_desejada}'")
                return

            # Altera labels do contato
            add_or_remove_label_contact(
                label_id_1=nova_label_id,
                label_id_2=labels_atuais,
                label_name=label_desejada,
                telefone=telefone_com_55,
                token=token
            )

        except Exception as e:
            print(f"❌ Erro ao alterar label do contato: {e}")