import os
import sys
import json
import django
import calendar
import requests
import subprocess
import threading
from pathlib import Path
from django.db.models import Q
from django.utils import timezone
from urllib3.util.retry import Retry
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
import base64, mimetypes, re, time, random
from django.db import transaction, IntegrityError
import logging

# Adiciona o caminho para imports do novo sistema de logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importa configuração centralizada de logging
from cadastros.services.logging_config import get_logger
from scripts.logging_utils import (
    registrar_log_json_auditoria,
    log_envio_mensagem,
)

# Configuração do logger com rotação automática
logger = get_logger(__name__, log_file="logs/WhatsApp/mensagens_wpp.log")

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carregar as configurações do Django
django.setup()

from django.utils import timezone
from django.utils.timezone import localtime
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from cadastros.utils import (
    get_saudacao_por_hora,
    registrar_log,
)
from cadastros.services.wpp import (
    LogTemplates,
    MessageSendConfig,
    send_message,
)
from wpp.api_connection import (
    check_number_status,
)
from integracoes.openai_chat import consultar_chatgpt

from cadastros.models import (
    Mensalidade, SessaoWpp, MensagemEnviadaWpp,
    Cliente, DadosBancarios, HorarioEnvios,
    MensagensLeads, TelefoneLeads
)

URL_API_WPP = os.getenv("URL_API_WPP")
DIR_LOGS_AGENDADOS = os.getenv("DIR_LOGS_AGENDADOS")
DIR_LOGS_INDICACOES = os.getenv("DIR_LOGS_INDICACOES")
TEMPLATE_LOG_MSG_SUCESSO = os.getenv("TEMPLATE_LOG_MSG_SUCESSO")
TEMPLATE_LOG_MSG_FALHOU = os.getenv("TEMPLATE_LOG_MSG_FALHOU")
TEMPLATE_LOG_TELEFONE_INVALIDO = os.getenv("TEMPLATE_LOG_TELEFONE_INVALIDO")
AUDIT_LOG_PATH = Path("logs/Audit/envios_wpp.log")


def registrar_log_auditoria(evento: dict) -> None:
    """
    Persiste eventos de envio em um arquivo de auditoria estruturado.

    NOTA: Esta função agora usa o sistema centralizado de logging.
    """
    registrar_log_json_auditoria(AUDIT_LOG_PATH, evento, auto_timestamp=True)

##################################################################
################ FUNÇÃO PARA ENVIAR MENSAGENS ####################
##################################################################

def enviar_mensagem_agendada(telefone: str, mensagem: str, usuario: str, token: str, cliente: str, tipo_envio: str) -> None:
    """
    Envia uma mensagem via API WPP para um número validado.
    Registra logs de sucesso, falha e número inválido.
    """
    usuario_str = str(usuario)

    log_writer = lambda log: registrar_log(log, usuario_str, DIR_LOGS_AGENDADOS)
    templates = LogTemplates(
        success=TEMPLATE_LOG_MSG_SUCESSO,
        failure=TEMPLATE_LOG_MSG_FALHOU,
        invalid=TEMPLATE_LOG_TELEFONE_INVALIDO,
    )

    request_payload = {
        "phone": telefone,
        "message": mensagem,
        "isGroup": False,
    }

    config = MessageSendConfig(
        usuario=usuario_str,
        token=token,
        telefone=telefone,
        mensagem=mensagem,
        tipo_envio=tipo_envio,
        cliente=cliente,
        log_writer=log_writer,
        log_templates=templates,
        retry_wait=(20.0, 30.0),
        audit_callback=registrar_log_auditoria,
        audit_base_payload={
            "funcao": "enviar_mensagem_agendada",
            "payload": request_payload,
        },
    )

    send_message(config)
##### FIM #####


#####################################################################
##### FUNÇÃO PARA FILTRAR AS MENSALIDADES DOS CLIENTES A VENCER #####
#####################################################################

def obter_mensalidades_a_vencer(usuario_query):
    dias_envio = (
        (1, "à vencer 1 dias"),
        (0, "vence hoje"),
    )

    for dias, tipo_mensagem in dias_envio:
        data_referencia = localtime().date() + timedelta(days=dias)

        mensalidades = Mensalidade.objects.filter(
            usuario=usuario_query,
            dt_vencimento=data_referencia,
            cliente__nao_enviar_msgs=False,
            pgto=False,
            cancelado=False
        )

        logger.info(
            "Mensalidades a vencer | tipo=%s quantidade=%d data_ref=%s usuario=%s",
            tipo_mensagem.upper(),
            mensalidades.count(),
            data_referencia.strftime('%d-%m-%Y'),
            usuario_query
        )

        for mensalidade in mensalidades:
            cliente = mensalidade.cliente
            usuario = mensalidade.usuario
            telefone = str(cliente.telefone).strip()
            if not telefone:
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_a_vencer",
                    "status": "cancelado_sem_telefone",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            sessao = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
            if not sessao:
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_a_vencer",
                    "status": "sessao_indisponivel",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            primeiro_nome = cliente.nome.split()[0].upper()
            dt_formatada = mensalidade.dt_vencimento.strftime("%d/%m")
            plano_nome = cliente.plano.nome.upper()

            mensagem = None

            if tipo_mensagem == "à vencer 1 dias":
                dados = DadosBancarios.objects.filter(usuario=usuario).first()
                if not dados:
                    registrar_log_auditoria({
                        "funcao": "obter_mensalidades_a_vencer",
                        "status": "dados_bancarios_ausentes",
                        "usuario": str(usuario),
                        "cliente": cliente.nome,
                        "cliente_id": cliente.id,
                        "tipo_envio": tipo_mensagem,
                        "mensalidade_id": mensalidade.id,
                    })
                    continue

                mensagem = (
                    f"⚠️ *ATENÇÃO, {primeiro_nome} !!!* ⚠️\n\n"
                    f"▫️ *DETALHES DO SEU PLANO:*\n"
                    f"_________________________________\n"
                    f"🔖 *Plano*: {plano_nome}\n"
                    f"📆 *Vencimento*: {dt_formatada}\n"
                    f"💰 *Valor*: R$ {mensalidade.valor}\n"
                    f"_________________________________\n\n"
                    f"▫️ *PAGAMENTO COM PIX:*\n"
                    f"_________________________________\n"
                    f"🔑 *Tipo*: {dados.tipo_chave}\n"
                    f"🔢 *Chave*: {dados.chave}\n"
                    f"🏦 *Banco*: {dados.instituicao}\n"
                    f"👤 *Beneficiário*: {dados.beneficiario}\n"
                    f"_________________________________\n\n"
                    f"‼️ _Caso já tenha pago, por favor, nos envie o comprovante._"
                )

            elif tipo_mensagem == "vence hoje":
                mensagem = (
                    f"⚠️ *ATENÇÃO, {primeiro_nome} !!!* ⚠️\n\n"
                    f"O seu plano *{plano_nome}* *vence hoje* ({dt_formatada}).\n\n"
                    f"Evite interrupções e mantenha seu acesso em dia! ✅"
                )

            if not mensagem:
                registrar_log(
                    f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [ERRO][TIPO DESCONHECIDO] [{usuario}] {cliente.nome}",
                    str(usuario),
                    DIR_LOGS_AGENDADOS,
                )
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_a_vencer",
                    "status": "mensagem_nao_montada",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            # Envio
            enviar_mensagem_agendada(
                telefone=telefone,
                mensagem=mensagem,
                usuario=usuario,
                token=sessao.token,
                cliente=cliente.nome,
                tipo_envio=tipo_mensagem
            )

            time.sleep(random.uniform(30, 60))
##### FIM #####


######################################################################
##### FUNÇÃO PARA FILTRAR AS MENSALIDADES DOS CLIENTES EM ATRASO #####
######################################################################

def obter_mensalidades_vencidas(usuario_query):
    dias_atraso = {
        2: "lembrete atraso",
        3: "suspensao"
    }

    for dias, tipo_mensagem in dias_atraso.items():
        data_referencia = localtime().date() - timedelta(days=dias)
        mensalidades = Mensalidade.objects.filter(
            usuario=usuario_query,
            dt_vencimento=data_referencia,
            cliente__nao_enviar_msgs=False,
            pgto=False,
            cancelado=False
        )

        logger.info(
            "Mensalidades vencidas | tipo=%s quantidade=%d dias_atraso=%d data_ref=%s usuario=%s",
            tipo_mensagem.upper(),
            mensalidades.count(),
            dias,
            data_referencia.strftime('%d-%m-%Y'),
            usuario_query
        )

        for mensalidade in mensalidades:
            cliente = mensalidade.cliente
            usuario = mensalidade.usuario
            telefone = str(cliente.telefone).strip()
            if not telefone:
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_vencidas",
                    "status": "cancelado_sem_telefone",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            sessao = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
            if not sessao:
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_vencidas",
                    "status": "sessao_indisponivel",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            primeiro_nome = cliente.nome.split()[0]
            saudacao = get_saudacao_por_hora(localtime().time())

            if tipo_mensagem == "lembrete atraso":
                mensagem = (
                    f"*{saudacao}, {primeiro_nome} 😊*\n\n"
                    f"*Ainda não identificamos o pagamento da sua mensalidade para renovação.*\n\n"
                    f"Caso já tenha feito, envie aqui novamente o seu comprovante, por favor!"
                )
            elif tipo_mensagem == "suspensao":
                mensagem = (
                    f"*{saudacao}, {primeiro_nome}*\n\n"
                    f"Informamos que, devido à falta de pagamento, o seu acesso ao sistema está sendo *suspenso*.\n\n"
                    f"⚠️ Se o seu plano atual for promocional ou incluir algum desconto, esses benefícios poderão não estar mais disponíveis para futuras renovações.\n\n"
                    f"Agradecemos pela confiança e esperamos poder contar com você novamente em breve."
                )

            enviar_mensagem_agendada(
                telefone=telefone,
                mensagem=mensagem,
                usuario=usuario,
                token=sessao.token,
                cliente=cliente.nome,
                tipo_envio=f"Atraso {dias}d"
            )

            time.sleep(random.uniform(30, 60))
##### FIM #####


################################################################################################
##### BLOCO DE ENVIO DE MENSAGENS PERSONALIZADAS PARA CLIENTES CANCELADOS POR QTD. DE DIAS #####
################################################################################################

def obter_mensalidades_canceladas():
    """
    Envia mensagens personalizadas para clientes cancelados há X dias,
    utilizando a lógica de saudação e validando número antes do envio.
    """
    atrasos = [
        {
            "dias": 20,
            "mensagem": "*{}, {}* 🫡\n\nTudo bem? Espero que sim.\n\nFaz um tempo que você deixou de ser nosso cliente ativo e ficamos preocupados. Houve algo que não agradou em nosso sistema?\n\nPergunto, pois se algo não agradou, nos informe para fornecermos uma plataforma melhor para você, tá bom?\n\nEstamos à disposição! 🙏🏼"
        },
        {
            "dias": 60,
            "mensagem": "*Opa.. {}!! Tudo bacana?*\n\nComo você já foi nosso cliente, trago uma notícia que talvez você goste muuuiito!!\n\nVocê pode renovar a sua mensalidade conosco pagando *APENAS R$ 24.90* nos próximos 3 meses. Olha só que bacana?!?!\n\nEsse tipo de desconto não oferecemos a qualquer um, viu? rsrs\n\nCaso tenha interesse, avise aqui, pois iremos garantir essa oferta apenas essa semana. 👏🏼👏🏼"
        }
    ]

    for atraso in atrasos:
        admin = User.objects.get(is_superuser=True)
        qtd_dias = atraso["dias"]
        mensagem_template = atraso["mensagem"]

        data_alvo = localtime().date() - timedelta(days=qtd_dias)

        mensalidades = Mensalidade.objects.filter(
            cliente__cancelado=True,
            cliente__nao_enviar_msgs=False,
            cliente__enviado_oferta_promo=False,
            dt_cancelamento=data_alvo,
            pgto=False,
            cancelado=True,
            notificacao_wpp1=False,
            usuario = admin
        )

        qtd = mensalidades.count()
        logger.info(
            "Mensalidades canceladas | dias_cancelamento=%d quantidade=%d usuario=%s",
            qtd_dias,
            qtd,
            admin
        )

        if not qtd:
            logger.debug(
                "Nenhum envio para clientes cancelados há %d dias", qtd_dias
            )
            continue

        for mensalidade in mensalidades:
            usuario = mensalidade.usuario
            cliente = mensalidade.cliente
            primeiro_nome = cliente.nome.split(' ')[0]
            saudacao = get_saudacao_por_hora()
            mensagem = mensagem_template.format(saudacao, primeiro_nome)

            try:
                sessao = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
            except SessaoWpp.DoesNotExist:
                logger.warning("Sessão WPP não encontrada | usuario=%s", usuario)
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_canceladas",
                    "status": "sessao_indisponivel",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "mensalidade_id": mensalidade.id,
                    "dias_cancelado": qtd_dias,
                })
                continue

            if not sessao or not sessao.token:
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_canceladas",
                    "status": "sessao_indisponivel",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "mensalidade_id": mensalidade.id,
                    "dias_cancelado": qtd_dias,
                })
                continue

            enviar_mensagem_agendada(
                telefone=cliente.telefone,
                mensagem=mensagem,
                usuario=usuario,
                token=sessao.token,
                cliente=cliente.nome,
                tipo_envio="Canceladas"
            )

            time.sleep(random.uniform(30, 60))

        if qtd_dias > 30:
            ids = mensalidades.values_list('id', flat=True)

            Mensalidade.objects.filter(id__in=ids).update(
                notificacao_wpp1=True,
                dt_notif_wpp1=localtime().now()
            )

            Cliente.objects.filter(mensalidade__id__in=ids).update(enviado_oferta_promo=True)

            logger.info(
                "Envio promocional concluído | quantidade=%d atualizado_oferta_promo=True",
                qtd
            )
##### FIM #####


#####################################################################################################
##### BLOCO PARA ENVIO DE MENSAGENS AOS CLIENTES ATIVOS, CANCELADOS E FUTUROS CLIENTES (AVULSO) #####
#####################################################################################################

def envia_mensagem_personalizada(tipo_envio: str, image_name: str, nome_msg: str) -> None:
    """
    Envia mensagens via WhatsApp para grupos de clientes com base no tipo de envio:
    - 'ativos': clientes em dia.
    - 'cancelados': clientes inativos há mais de 40 dias.
    - 'avulso': números importados via arquivo externo.

    Parâmetros:
        tipo_envio (str): Tipo de grupo alvo ('ativos', 'cancelados', 'avulso').
        image_name (str): Nome da imagem opcional a ser enviada.
        message (str): Conteúdo da mensagem (texto ou legenda).

    A mensagem só é enviada se:
    - O número for validado via API do WhatsApp.
    - Ainda não tiver sido enviada naquele dia.
    """
    usuario = User.objects.get(id=1)
    sessao = SessaoWpp.objects.filter(usuario=usuario).first()
    if not sessao or not sessao.token:
        logger.error("Sessão/token WPP ausente", extra={"user": usuario.username})
        registrar_log_auditoria({
            "funcao": "envia_mensagem_personalizada",
            "status": "abortado_sem_sessao",
            "usuario": usuario.username,
            "tipo_envio": tipo_envio,
        })
        return
    token = sessao.token

    url_envio = f"{URL_API_WPP}/{usuario}/send-{'image' if image_name else 'message'}"
    image_base64 = obter_img_base64(image_name, tipo_envio) if image_name else None

    # Limite de 100 envios por execução
    total_enviados = 0
    LIMITE_ENVIO_DIARIO = 100

    destinatarios = []

    # Obtenção dos números com base no tipo
    if tipo_envio == 'ativos':
        clientes = Cliente.objects.filter(usuario=usuario, cancelado=False, nao_enviar_msgs=False)
        destinatarios = [
            {
                "telefone": cliente.telefone,
                "cliente_id": cliente.id,
                "cliente_nome": cliente.nome,
            }
            for cliente in clientes
        ]
    elif tipo_envio == 'cancelados':
        clientes = Cliente.objects.filter(
            usuario=usuario,
            cancelado=True,
            nao_enviar_msgs=False,
            data_cancelamento__lte=localtime().now() - timedelta(days=40)
        )
        destinatarios = [
            {
                "telefone": cliente.telefone,
                "cliente_id": cliente.id,
                "cliente_nome": cliente.nome,
            }
            for cliente in clientes
        ]
    elif tipo_envio == 'avulso':
        telefones_str = processa_telefones(usuario)
        numeros = telefones_str.split(',') if telefones_str else []
        destinatarios = [
            {
                "telefone": telefone.strip(),
                "cliente_id": None,
                "cliente_nome": None,
            }
            for telefone in numeros
            if telefone.strip()
        ]
    else:
        logger.error("Tipo de envio desconhecido: %s", tipo_envio)
        return

    if not destinatarios:
        logger.warning(
            "Nenhum destinatário encontrado | tipo=%s usuario=%s",
            tipo_envio,
            usuario.username
        )
        registrar_log_auditoria({
            "funcao": "envia_mensagem_personalizada",
            "status": "sem_destinatarios",
            "usuario": usuario.username,
            "tipo_envio": tipo_envio,
        })

    logger.info(
        "Iniciando envios personalizados | tipo=%s quantidade=%d usuario=%s",
        tipo_envio.upper(),
        len(destinatarios),
        usuario.username
    )

    for destinatario in destinatarios:
        telefone = destinatario["telefone"]
        cliente_nome = destinatario.get("cliente_nome")
        cliente_id = destinatario.get("cliente_id")
        if total_enviados >= LIMITE_ENVIO_DIARIO:
            logger.warning(
                "Limite diário atingido | limite=%d enviados=%d",
                LIMITE_ENVIO_DIARIO,
                total_enviados
            )
            registrar_log_auditoria({
                "funcao": "envia_mensagem_personalizada",
                "status": "limite_diario_atingido",
                "usuario": usuario.username,
                "tipo_envio": tipo_envio,
                "total_enviados": total_enviados,
                "limite": LIMITE_ENVIO_DIARIO,
            })
            break

        # Ignora se já enviado hoje
        if MensagemEnviadaWpp.objects.filter(usuario=usuario, telefone=telefone, data_envio=localtime().now().date()).exists():
            registrar_log(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - ⚠️ Já foi feito envio hoje!", usuario, DIR_LOGS_AGENDADOS)
            registrar_log_auditoria({
                "funcao": "envia_mensagem_personalizada",
                "status": "ignorado_envio_diario",
                "usuario": usuario.username,
                "tipo_envio": tipo_envio,
                "telefone": telefone,
                "cliente_nome": cliente_nome,
                "cliente_id": cliente_id,
            })
            continue

        # ignora se já enviado neste mês (avulso, ativos e cancelados)
        if tipo_envio in ["avulso", "ativos", "cancelados"]:
            hoje = localtime()
            if MensagemEnviadaWpp.objects.filter(
                usuario=usuario,
                telefone=telefone,
                data_envio__year=hoje.year,
                data_envio__month=hoje.month
            ).exists():
                logger.debug(
                    "Envio ignorado (já enviado este mês) | telefone=%s tipo=%s usuario=%s",
                    telefone,
                    tipo_envio,
                    usuario.username
                )
                registrar_log(f"[{hoje.strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - ⚠️ Já recebeu envio este mês (avulso)", usuario, DIR_LOGS_AGENDADOS)
                registrar_log_auditoria({
                    "funcao": "envia_mensagem_personalizada",
                    "status": "ignorado_envio_mensal",
                    "usuario": usuario.username,
                    "tipo_envio": tipo_envio,
                    "telefone": telefone,
                    "cliente_nome": cliente_nome,
                    "cliente_id": cliente_id,
                })
                continue

        if not telefone:
            log = TEMPLATE_LOG_TELEFONE_INVALIDO.format(localtime().strftime('%d-%m-%Y %H:%M:%S'), tipo_envio.upper(), usuario, telefone)
            registrar_log(log, usuario, DIR_LOGS_AGENDADOS)
            registrar_log_auditoria({
                "funcao": "envia_mensagem_personalizada",
                "status": "cancelado_sem_telefone",
                "usuario": usuario.username,
                "tipo_envio": tipo_envio,
                "telefone": telefone,
                "cliente_nome": cliente_nome,
                "cliente_id": cliente_id,
            })
            continue

        # Validação via WhatsApp
        numero_existe = check_number_status(telefone, token, usuario)
        if not numero_existe:
            logger.warning(
                "Número não está no WhatsApp | telefone=%s usuario=%s tipo=%s",
                telefone,
                usuario.username,
                tipo_envio
            )
            registrar_log(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - ❌ Número inválido no WhatsApp", usuario, DIR_LOGS_AGENDADOS)
            registrar_log_auditoria({
                "funcao": "envia_mensagem_personalizada",
                "status": "numero_invalido",
                "usuario": usuario.username,
                "tipo_envio": tipo_envio,
                "telefone": telefone,
                "cliente_nome": cliente_nome,
                "cliente_id": cliente_id,
            })
            if tipo_envio == 'avulso':
                TelefoneLeads.objects.filter(telefone=telefone, usuario=usuario).delete()
                logger.info(
                    "Telefone deletado do banco (lead inválido) | telefone=%s usuario=%s",
                    telefone,
                    usuario.username
                )
                registrar_log(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - 🗑️ Deletado do banco (avulso)", usuario, DIR_LOGS_AGENDADOS)
            continue

        # Obter mensagem personalizada
        message = obter_mensagem_personalizada(nome=nome_msg, tipo=tipo_envio, usuario=usuario)
        if not message:
            logger.error(
                "Falha ao gerar mensagem personalizada | nome_msg=%s tipo=%s telefone=%s usuario=%s",
                nome_msg,
                tipo_envio,
                telefone,
                usuario.username
            )
            registrar_log(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - ❌ Falha ao gerar variação da mensagem", usuario, DIR_LOGS_AGENDADOS)
            registrar_log_auditoria({
                "funcao": "envia_mensagem_personalizada",
                "status": "erro_template",
                "usuario": usuario.username,
                "tipo_envio": tipo_envio,
                "telefone": telefone,
                "cliente_nome": cliente_nome,
                "cliente_id": cliente_id,
            })
            continue

        # Monta payload
        payload = {
            'phone': telefone,
            'isGroup': False,
            'message': message
        }

        if image_base64:
            payload['filename'] = image_name
            payload['caption'] = message
            payload['base64'] = f'data:image/png;base64,{image_base64}'

        audit_payload = {k: v for k, v in payload.items() if k != 'base64'}
        audit_payload["tem_base64"] = bool(payload.get('base64'))
        audit_payload["arquivo_imagem"] = image_name

        for tentativa in range(1, 4):
            response = None
            response_payload = None
            status_code = None
            error_message = None
            timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')

            try:
                response = requests.post(url_envio, headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                }, json=payload)
                status_code = response.status_code

                try:
                    response_payload = response.json()
                except json.JSONDecodeError:
                    response_payload = response.text

                if status_code in (200, 201):
                    registrar_log(
                        TEMPLATE_LOG_MSG_SUCESSO.format(timestamp, tipo_envio.upper(), usuario, telefone),
                        usuario,
                        DIR_LOGS_AGENDADOS
                    )
                    registro_envio = MensagemEnviadaWpp.objects.create(usuario=usuario, telefone=telefone)
                    registrar_log_auditoria({
                        "funcao": "envia_mensagem_personalizada",
                        "status": "sucesso",
                        "usuario": usuario.username,
                        "tipo_envio": tipo_envio,
                        "telefone": telefone,
                        "cliente_nome": cliente_nome,
                        "cliente_id": cliente_id,
                        "tentativa": tentativa,
                        "http_status": status_code,
                        "mensagem": message,
                        "payload": audit_payload,
                        "response": response_payload,
                        "registro_envio_id": registro_envio.id,
                    })
                    total_enviados += 1
                    break

                error_message = (
                    response_payload.get('message', 'Erro desconhecido')
                    if isinstance(response_payload, dict)
                    else str(response_payload)
                )

            except requests.RequestException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if getattr(exc, "response", None) is not None:
                    try:
                        response_payload = exc.response.json()
                    except (ValueError, AttributeError):
                        response_payload = getattr(exc.response, "text", None)
                error_message = str(exc)

            if status_code in (200, 201):
                continue

            if error_message is None:
                error_message = "Erro desconhecido"

            registrar_log(
                TEMPLATE_LOG_MSG_FALHOU.format(timestamp, tipo_envio.upper(), usuario, telefone, status_code if status_code is not None else 'N/A', tentativa, error_message),
                usuario, DIR_LOGS_AGENDADOS
            )
            registrar_log_auditoria({
                "funcao": "envia_mensagem_personalizada",
                "status": "falha",
                "usuario": usuario.username,
                "tipo_envio": tipo_envio,
                "telefone": telefone,
                "cliente_nome": cliente_nome,
                "cliente_id": cliente_id,
                "tentativa": tentativa,
                "http_status": status_code,
                "mensagem": message,
                "erro": error_message,
                "payload": audit_payload,
                "response": response_payload,
            })
            time.sleep(random.uniform(10, 20))

        time.sleep(random.uniform(30, 180))


def obter_img_base64(image_name: str, sub_directory: str) -> str:
    """
    Converte uma imagem localizada em /images/{sub_directory} para base64.

    Args:
        image_name (str): Nome do arquivo da imagem.
        sub_directory (str): Diretório onde a imagem está localizada.

    Returns:
        str: Imagem codificada em base64 ou None se falhar.
    """
    image_path = os.path.join(os.path.dirname(__file__), f'../images/{sub_directory}', image_name)

    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(
            "Erro ao abrir imagem | imagem=%s subdir=%s erro=%s",
            image_name,
            sub_directory,
            str(e)
        )
        return None


def processa_telefones(usuario: User = None) -> str:
    """
    Obtém os telefones dos leads salvos no banco (modelo TelefoneLeads) e retorna uma string com os números limpos, separados por vírgula.

    Args:
        usuario (User, opcional): Usuário para filtrar os leads. Se None, retorna todos.

    Returns:
        str: Telefones limpos separados por vírgula.
    """
    try:
        queryset = TelefoneLeads.objects.all()
        if usuario:
            queryset = queryset.filter(usuario=usuario)

        telefones = queryset.values_list('telefone', flat=True)
        numeros_limpos = [
            re.sub(r'\D', '', t) for t in telefones if t and re.sub(r'\D', '', t)
        ]
        return ','.join(numeros_limpos) if numeros_limpos else None

    except Exception as e:
        logger.error("Erro ao processar telefones | erro=%s", str(e), exc_info=True)
        return None


def obter_mensagem_personalizada(nome: str, tipo: str, usuario: User = None) -> str:
    """
    Obtém a mensagem do banco de dados (MensagensLeads) e gera uma versão personalizada via ChatGPT.

    Args:
        nome (str): Nome identificador da mensagem (ex: 'msg1', 'msg2-2', etc.).
        tipo (str): Tipo de envio (ex: 'ativos', 'cancelados', 'avulso').
        usuario (User, opcional): Usuário responsável (pode filtrar mensagens por usuário se necessário).

    Returns:
        str: Mensagem reescrita com variações, ou None em caso de erro.
    """
    try:
        filtro = MensagensLeads.objects.filter(nome=nome, tipo=tipo)
        if usuario:
            filtro = filtro.filter(usuario=usuario)

        mensagem_obj = filtro.first()
        if not mensagem_obj:
            logger.warning(
                "Mensagem não encontrada no banco | nome=%s tipo=%s usuario=%s",
                nome,
                tipo,
                usuario
            )
            return None

        mensagem_original = mensagem_obj.mensagem

        prompt = (
            "Você é um redator especialista em marketing pelo WhatsApp. "
            "Reescreva o texto abaixo mantendo a mesma intenção, "
            "mas com frases diferentes, trocando palavras por sinônimos, mudando a ordem e emojis quando necessário, "
            "deixando o texto natural, envolvente, mas atrativo e adequado para o WhatsApp.\n\n"
            f"{mensagem_original}"
        )

        mensagem_reescrita = consultar_chatgpt(pergunta=prompt, user=usuario)
        return mensagem_reescrita

    except Exception as e:
        logger.error(
            "Erro ao obter mensagem personalizada | nome=%s tipo=%s erro=%s",
            nome,
            tipo,
            str(e),
            exc_info=True
        )
        return None
#### FIM #####


##########################################################################
##### FUNÇÃO PARA EXECUTAR TAREFAS AGENDADAS PARA ENVIO DE MENSAGENS #####
##########################################################################

def run_scheduled_tasks():
    """
    Executa tarefas agendadas de envio de mensagens com base no dia da semana e dia do mês:
    - Sábado: clientes ativos (2º e último sábado).
    - Quarta e domingo: clientes avulsos (3 intervalos de dias).
    - Segunda: clientes cancelados (3 intervalos de dias).
    """
    try:
        now = datetime.now()
        dia = now.day
        dia_semana = now.strftime('%A')
        ano = now.year
        mes = now.month

        def get_second_saturday(year, month):
            first_day = datetime(year, month, 1)
            first_saturday = first_day + timedelta(days=(5 - first_day.weekday()) % 7)
            return (first_saturday + timedelta(days=7)).day

        def get_last_saturday(year, month):
            last_day = datetime(year, month, calendar.monthrange(year, month)[1])
            return (last_day - timedelta(days=(last_day.weekday() - 5) % 7)).day

        second_saturday = get_second_saturday(ano, mes)
        last_saturday = get_last_saturday(ano, mes)

        # Inicializa parâmetros
        tipo = None
        imagem = None
        nome_msg = None

        if dia_semana in ["Monday", "Wednesday"]:
            tipo = "ativos"
            imagem = "img1.png"
            if dia <= 14:
                nome_msg = "msg1"
            elif dia >= 15:
                nome_msg = "msg2"

        elif dia_semana in ["Tuesday", "Thursday", "Saturday"]:
            tipo = "avulso"
            if 1 <= dia <= 10:
                imagem, nome_msg = "img2-1.png", "msg2-1"
            elif 11 <= dia <= 20:
                imagem, nome_msg = "img2-2.png", "msg2-2"
            elif dia >= 21:
                imagem, nome_msg = "img2-3.png", "msg2-3"
            else:
                nome_msg = None

        elif dia_semana in ["Friday", "Sunday"]:
            tipo = "cancelados"
            if 1 <= dia <= 10:
                imagem, nome_msg = "img3-1.png", "msg3-1"
            elif 11 <= dia <= 20:
                imagem, nome_msg = "img3-2.png", "msg3-2"
            elif dia >= 21:
                imagem, nome_msg = "img3-3.png", "msg3-3"
            else:
                nome_msg = None

        # Execução final do envio
        if tipo and imagem and nome_msg:
            logger.info(
                "Executando envio programado | tipo=%s imagem=%s msg=%s",
                tipo.upper(),
                imagem,
                nome_msg
            )
            envia_mensagem_personalizada(tipo_envio=tipo, image_name=imagem, nome_msg=nome_msg)
        else:
            logger.debug(
                "Nenhum envio agendado para hoje | dia_semana=%s dia=%d",
                dia_semana,
                dia
            )

    except Exception as e:
        logger.error(
            "Erro em run_scheduled_tasks | erro=%s",
            str(e),
            exc_info=True
        )
##### FIM #####


###########################################################
##### FUNÇÃO PARA VALIDAR E EXECUTAR ENVIOS AGENDADOS #####
###########################################################

# Gerenciamento de locks por usuário (permite processamento paralelo de usuários diferentes)
_locks_por_usuario = {}
_locks_manager_lock = threading.Lock()

def _obter_lock_usuario(usuario_id):
    """
    Retorna o lock específico de um usuário, criando-o se necessário.
    Thread-safe através do _locks_manager_lock.
    """
    with _locks_manager_lock:
        if usuario_id not in _locks_por_usuario:
            _locks_por_usuario[usuario_id] = threading.Lock()
        return _locks_por_usuario[usuario_id]


def executar_envio_para_usuario(h_candidato, agora, hoje):
    """
    Executa envio para um usuário específico em thread separada.

    Proteções implementadas:
    1. threading.Lock() por usuário - evita processamento duplicado do mesmo usuário
    2. select_for_update(skip_locked=True) - proteção inter-processo via DB
    3. Update atômico de ultimo_envio antes de iniciar envio

    Args:
        h_candidato: Registro HorarioEnvios candidato a processamento
        agora: datetime atual
        hoje: date atual
    """
    usuario_id = h_candidato.usuario.id
    usuario_lock = _obter_lock_usuario(usuario_id)

    # Verifica se este usuário já está sendo processado neste processo
    if usuario_lock.locked():
        registrar_log_auditoria({
            "funcao": "executar_envio_para_usuario",
            "status": "usuario_em_processamento_local",
            "usuario": str(h_candidato.usuario),
            "tipo_envio": h_candidato.tipo_envio,
            "horario": str(h_candidato.horario),
            "motivo": "lock_local_do_usuario_ja_adquirido",
        })
        return

    with usuario_lock:
        try:
            with transaction.atomic():
                # select_for_update com skip_locked: se outro processo já travou este registro, pula
                horarios_locked = HorarioEnvios.objects.select_for_update(
                    skip_locked=True
                ).filter(
                    id=h_candidato.id,
                    status=True,
                    ativo=True
                ).filter(
                    Q(ultimo_envio__isnull=True) | Q(ultimo_envio__lt=hoje)
                )

                h = horarios_locked.first()

                if not h:
                    # Outro processo já pegou este registro ou condições mudaram
                    registrar_log_auditoria({
                        "funcao": "executar_envio_para_usuario",
                        "status": "lock_db_nao_adquirido",
                        "usuario": str(h_candidato.usuario),
                        "tipo_envio": h_candidato.tipo_envio,
                        "horario": str(h_candidato.horario),
                        "motivo": "registro_travado_por_outro_processo_ou_ja_processado",
                    })
                    return

                # Lock DB adquirido! Atualiza IMEDIATAMENTE para bloquear outros processos
                h.ultimo_envio = hoje
                h.save(update_fields=['ultimo_envio'])

                logger.info(
                    "Lock adquirido - iniciando envios | thread=%s usuario=%s tipo=%s horario=%s",
                    threading.current_thread().name,
                    h.usuario,
                    h.tipo_envio,
                    h.horario
                )

                registrar_log_auditoria({
                    "funcao": "executar_envio_para_usuario",
                    "status": "iniciando",
                    "usuario": str(h.usuario),
                    "tipo_envio": h.tipo_envio,
                    "horario": str(h.horario),
                    "thread": threading.current_thread().name,
                })

            # Transação commitada, lock DB liberado. Agora executa o envio (pode demorar)
            try:
                if h.tipo_envio == 'mensalidades_a_vencer':
                    obter_mensalidades_a_vencer(h.usuario)
                elif h.tipo_envio == 'obter_mensalidades_vencidas':
                    obter_mensalidades_vencidas(h.usuario)

                logger.info(
                    "Envios concluídos | thread=%s usuario=%s tipo=%s",
                    threading.current_thread().name,
                    h.usuario,
                    h.tipo_envio
                )

                registrar_log_auditoria({
                    "funcao": "executar_envio_para_usuario",
                    "status": "concluido",
                    "usuario": str(h.usuario),
                    "tipo_envio": h.tipo_envio,
                    "thread": threading.current_thread().name,
                })
            except Exception as exc_envio:
                logger.error(f"Erro ao executar envio para usuário {h.usuario}: {exc_envio}", exc_info=exc_envio)
                registrar_log_auditoria({
                    "funcao": "executar_envio_para_usuario",
                    "status": "erro_durante_envio",
                    "usuario": str(h.usuario),
                    "tipo_envio": h.tipo_envio,
                    "erro": str(exc_envio),
                    "thread": threading.current_thread().name,
                })

        except Exception as exc_lock:
            logger.error(f"Erro ao adquirir lock DB para usuário {h_candidato.usuario}: {exc_lock}", exc_info=exc_lock)
            registrar_log_auditoria({
                "funcao": "executar_envio_para_usuario",
                "status": "erro_lock_db",
                "usuario": str(h_candidato.usuario),
                "tipo_envio": h_candidato.tipo_envio,
                "erro": str(exc_lock),
                "thread": threading.current_thread().name,
            })


def executar_envios_agendados():
    """
    Executa envios agendados com processamento paralelo por usuário.

    Comportamento:
    - Busca todos os horários elegíveis
    - Cria uma thread separada para cada usuário elegível
    - Cada usuário é processado em paralelo (threads diferentes)
    - Mesmo usuário nunca processa 2x simultaneamente (lock por usuário)
    - Proteção inter-processo via select_for_update(skip_locked=True)

    Exemplo:
        Usuario A (12h00) + Usuario B (12h00) → Ambos processam EM PARALELO
        Usuario A (12h00) + Usuario A (12h01) → Segundo bloqueado até primeiro terminar
    """
    agora = timezone.localtime()
    hora_atual = agora.strftime('%H:%M')
    hoje = agora.date()

    # Busca horários elegíveis (sem lock ainda)
    horarios_candidatos = HorarioEnvios.objects.filter(
        status=True,
        ativo=True,
        horario__isnull=False
    ).filter(
        Q(ultimo_envio__isnull=True) | Q(ultimo_envio__lt=hoje)
    )

    threads_criadas = []

    for h_candidato in horarios_candidatos:
        # Verifica se o horário bate
        if h_candidato.horario.strftime('%H:%M') != hora_atual:
            continue

        # Cria thread separada para este usuário (processamento paralelo)
        thread_name = f"EnvioUsuario-{h_candidato.usuario.id}-{h_candidato.tipo_envio}"
        t = threading.Thread(
            target=executar_envio_para_usuario,
            args=(h_candidato, agora, hoje),
            name=thread_name,
            daemon=True
        )
        t.start()
        threads_criadas.append({
            "thread": t,
            "usuario": str(h_candidato.usuario),
            "tipo_envio": h_candidato.tipo_envio,
        })

        logger.debug(
            "Thread criada para envio | thread=%s usuario=%s tipo=%s",
            thread_name,
            h_candidato.usuario,
            h_candidato.tipo_envio
        )

    if threads_criadas:
        registrar_log_auditoria({
            "funcao": "executar_envios_agendados",
            "status": "threads_criadas",
            "quantidade": len(threads_criadas),
            "threads": [
                {"usuario": t["usuario"], "tipo_envio": t["tipo_envio"]}
                for t in threads_criadas
            ],
        })

    # Não aguarda threads terminarem (daemon=True permite execução em background)
    # O scheduler continuará funcionando e as threads processarão em paralelo


def executar_envios_agendados_com_lock():
    """
    Entry point para execução de envios agendados.

    Nota: O lock global foi REMOVIDO para permitir processamento paralelo.
    Agora usa locks POR USUÁRIO, permitindo que diferentes usuários sejam
    processados simultaneamente.
    """
    try:
        executar_envios_agendados()
    except Exception as exc:
        logger.exception(f"Erro em executar_envios_agendados_com_lock: {exc}")


##############################################################################################
##### FUNÇÃO PARA EXECUTAR O SCRIPT DE BACKUP DO "DB.SQLITE3" PARA O DIRETÓRIO DO DRIVE. #####
##############################################################################################

def backup_db_sh():
    """
    Executa o script 'backup_db.sh' para realizar backup do banco SQLite.
    """
    # Caminho para o script de backup
    caminho_arquivo_sh = 'backup_db.sh'

    # Executar o script de backup
    resultado = subprocess.run(['sh', caminho_arquivo_sh], capture_output=True, text=True)

    # Verificar o resultado da execução do script
    if resultado.returncode == 0:
        logger.info("Backup do DB realizado com sucesso")
    else:
        logger.error(
            "Falha durante backup do DB | returncode=%d stderr=%s",
            resultado.returncode,
            resultado.stderr
        )

    time.sleep(random.randint(10, 20))
##### FIM #####
