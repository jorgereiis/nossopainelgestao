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
    criar_label_se_nao_existir,
)
# URL base da API do WhatsApp
URL_API_WPP = os.getenv("URL_API_WPP")
DIR_LOGS_AGENDADOS = os.getenv("DIR_LOGS_AGENDADOS")
DIR_LOGS_INDICACOES = os.getenv("DIR_LOGS_INDICACOES")
TEMPLATE_LOG_MSG_SUCESSO = os.getenv("TEMPLATE_LOG_MSG_SUCESSO")
TEMPLATE_LOG_MSG_FALHOU = os.getenv("TEMPLATE_LOG_MSG_FALHOU")
TEMPLATE_LOG_TELEFONE_INVALIDO = os.getenv("TEMPLATE_LOG_TELEFONE_INVALIDO")

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')


# Atualiza o último pagamento do cliente sempre que uma mensalidade for paga
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
        telefone = str(instance.telefone)

        # Obtém token da sessão
        try:
            token = SessaoWpp.objects.filter(usuario=instance.usuario, is_active=True).first()
        except SessaoWpp.DoesNotExist:
            print(f"⚠️ Sessão do WhatsApp não encontrada para o usuário {instance.usuario}")
            return

        # Verifica se número existe no WhatsApp
        try:
            numero_existe = check_number_status(telefone, token.token)
            if not numero_existe:
                print(f"⚠️ Número {telefone} não é válido no WhatsApp.")
                return
        except Exception as e:
            print(f"❌ Erro ao verificar número no WhatsApp: {e}")
            return

        # Obtém labels atuais
        try:
            labels_atuais = get_label_contact(telefone, token.token)
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
            nova_label_id = criar_label_se_nao_existir(label_desejada, token.token, hex_color=hex_color)
            if not nova_label_id:
                print(f"⚠️ Não foi possível obter ou criar a label '{label_desejada}'")
                return

            # Altera labels do contato
            add_or_remove_label_contact(
                label_id_1=nova_label_id,
                label_id_2=labels_atuais,
                label_name=label_desejada,
                telefone=telefone,
                token=token.token
            )

        except Exception as e:
            print(f"❌ Erro ao alterar label do contato: {e}")