import os
import sys
import json
import django
import calendar
import requests
import requests
import subprocess
from pathlib import Path
from django.db.models import Q
from django.utils import timezone
from urllib3.util.retry import Retry
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
import base64, mimetypes, re, time, random
from django.db import transaction, IntegrityError
import logging

# Configuração do logger
logger = logging.getLogger(__name__)

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
    """
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        registro = dict(evento or {})
        registro.setdefault("timestamp", localtime().strftime('%d-%m-%Y %H:%M:%S'))
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Erro ao registrar log de auditoria: %s", exc, exc_info=exc)

##################################################################
################ FUNÇÃO PARA ENVIAR MENSAGENS ####################
##################################################################

def enviar_mensagem_agendada(telefone: str, mensagem: str, usuario: str, token: str, cliente: str, tipo_envio: str) -> None:
    """
    Envia uma mensagem via API WPP para um número validado.
    Registra logs de sucesso, falha e número inválido.
    """
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    usuario_str = str(usuario)

    if not telefone:
        log = TEMPLATE_LOG_TELEFONE_INVALIDO.format(
            timestamp, tipo_envio.upper(), usuario, cliente
        )
        registrar_log(log, usuario, DIR_LOGS_AGENDADOS)
        print(log.strip())
        registrar_log_auditoria({
            "funcao": "enviar_mensagem_agendada",
            "status": "cancelado_sem_telefone",
            "usuario": usuario_str,
            "cliente": cliente,
            "telefone": telefone,
            "tipo_envio": tipo_envio,
            "mensagem": mensagem,
        })
        return

    url = f"{URL_API_WPP}/{usuario}/send-message"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    for tentativa in range(1, 3):
        body = {
            'phone': telefone,
            'message': mensagem,
            'isGroup': False
        }

        response = None
        response_payload = None
        status_code = None
        error_message = None
        timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')

        try:
            response = requests.post(url, headers=headers, json=body)
            status_code = response.status_code

            try:
                response_payload = response.json()
            except json.JSONDecodeError:
                response_payload = response.text

            if status_code in (200, 201):
                log = TEMPLATE_LOG_MSG_SUCESSO.format(
                    timestamp, tipo_envio.upper(), usuario, telefone
                )
                registrar_log(log, usuario, DIR_LOGS_AGENDADOS)
                registrar_log_auditoria({
                    "funcao": "enviar_mensagem_agendada",
                    "status": "sucesso",
                    "usuario": usuario_str,
                    "cliente": cliente,
                    "telefone": telefone,
                    "tipo_envio": tipo_envio,
                    "tentativa": tentativa,
                    "http_status": status_code,
                    "mensagem": mensagem,
                    "payload": body,
                    "response": response_payload,
                })
                break

            error_message = (
                response_payload.get('message', 'Erro desconhecido')
                if isinstance(response_payload, dict)
                else str(response_payload)
            )

        except requests.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if getattr(e, "response", None) is not None:
                try:
                    response_payload = e.response.json()
                except (ValueError, AttributeError):
                    response_payload = getattr(e.response, "text", None)
            error_message = str(e)

        if status_code in (200, 201):
            continue

        if error_message is None:
            error_message = "Erro desconhecido"

        log = TEMPLATE_LOG_MSG_FALHOU.format(
            timestamp, tipo_envio.upper(), usuario, cliente,
            status_code if status_code is not None else 'N/A',
            tentativa, error_message
        )
        registrar_log(log, usuario, DIR_LOGS_AGENDADOS)
        registrar_log_auditoria({
            "funcao": "enviar_mensagem_agendada",
            "status": "falha",
            "usuario": usuario_str,
            "cliente": cliente,
            "telefone": telefone,
            "tipo_envio": tipo_envio,
            "tentativa": tentativa,
            "http_status": status_code,
            "mensagem": mensagem,
            "erro": error_message,
            "payload": body,
            "response": response_payload,
        })
        time.sleep(random.uniform(20, 30))
##### FIM #####


#####################################################################
##### FUNÇÃO PARA FILTRAR AS MENSALIDADES DOS CLIENTES A VENCER #####
#####################################################################

def obter_mensalidades_a_vencer(usuario_query):
    dias_envio = (
        (2, "à vencer 2 dias"),
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

        print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [{tipo_mensagem.upper()}] QUANTIDADE DE ENVIOS: {mensalidades.count()}")

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

            if tipo_mensagem == "à vencer 2 dias":
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

            elif tipo_mensagem == "à vencer 1 dias":
                mensagem = (
                    f"⚠️ *ATENÇÃO, {primeiro_nome} !!!* ⚠️\n\n"
                    f"O seu plano *{plano_nome}* vencerá em *{dias} dia*.\n\n"
                    f"Fique atento(a)! 💡"
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

        print(f"[{localtime().strftime('%d-%m-%Y %H:%M:%S')}] [{tipo_mensagem.upper()}] QUANTIDADE DE ENVIOS: {mensalidades.count()}")

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
        print(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] [CANCELADAS HÁ {qtd_dias} DIAS] QUANTIDADE DE ENVIOS: {qtd}")

        if not qtd:
            print(f"Nenhum envio realizado para clientes cancelados há {qtd_dias} dias.")
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
                print(f"[ERRO] Sessão WPP não encontrada para '{usuario}'. Pulando...")
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

            print(f"[ENVIO PROMO REALIZADO] {qtd} clientes atualizados para 'enviado_oferta_promo = True'")
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
        print(f"[ERRO] Tipo de envio desconhecido: {tipo_envio}")
        return

    if not destinatarios:
        registrar_log_auditoria({
            "funcao": "envia_mensagem_personalizada",
            "status": "sem_destinatarios",
            "usuario": usuario.username,
            "tipo_envio": tipo_envio,
        })

    print(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] [ENVIO][{tipo_envio.upper()}] [QTD.][{len(destinatarios)}]")

    for destinatario in destinatarios:
        telefone = destinatario["telefone"]
        cliente_nome = destinatario.get("cliente_nome")
        cliente_id = destinatario.get("cliente_id")
        if total_enviados >= LIMITE_ENVIO_DIARIO:
            print(f"[LIMITE] Atingido o limite diário de {LIMITE_ENVIO_DIARIO} envios.")
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
                registrar_log(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - 🗑️ Deletado do banco (avulso)", usuario, DIR_LOGS_AGENDADOS)
            continue

        # Obter mensagem personalizada
        message = obter_mensagem_personalizada(nome=nome_msg, tipo=tipo_envio, usuario=usuario)
        if not message:
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
        print(f"[ERRO] Ao abrir imagem: {e}")
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
        print(f"[ERRO] processa_telefones(): {e}")
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
            print(f"[AVISO] Mensagem '{nome}' do tipo '{tipo}' não encontrada no banco.")
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
        print(f"[ERRO] obter_mensagem_personalizada(): {e}")
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
            print(f"[{now.strftime('%d-%m-%Y %H:%M:%S')}] [TAREFA] Executando envio programado para {tipo.upper()}")
            envia_mensagem_personalizada(tipo_envio=tipo, image_name=imagem, nome_msg=nome_msg)
        else:
            print(f"[{now.strftime('%d-%m-%Y %H:%M:%S')}] [TAREFA] Nenhum envio agendado para hoje.")

    except Exception as e:
        print(f"[ERRO] run_scheduled_tasks(): {str(e)}")
##### FIM #####


###########################################################
##### FUNÇÃO PARA VALIDAR E EXECUTAR ENVIOS AGENDADOS #####
###########################################################

def executar_envios_agendados():
    agora = timezone.localtime()
    hora_atual = agora.strftime('%H:%M')
    hoje = agora.date()

    horarios = HorarioEnvios.objects.filter(
        status=True,
        ativo=True,
        horario__isnull=False
    )

    for h in horarios:
        if (
            h.horario.strftime('%H:%M') == hora_atual and
            (h.ultimo_envio is None or h.ultimo_envio < hoje)
        ):
            print(f'Executando envios para usuário: {h.usuario} (horário: {h.horario})')

            # Verifica o tipo de envio e executa a função correspondente
            if h.tipo_envio == 'mensalidades_a_vencer':
                obter_mensalidades_a_vencer(h.usuario)
            elif h.tipo_envio == 'obter_mensalidades_vencidas':
                obter_mensalidades_vencidas(h.usuario)

            # Atualiza o último envio
            h.ultimo_envio = hoje
            h.save(update_fields=['ultimo_envio'])


##############################################################################################
##### FUNÇÃO PARA EXECUTAR O SCRIPT DE BACKUP DO "DB.SQLITE3" PARA O DIRETÓRIO DO DRIVE. #####
##############################################################################################

def backup_db_sh():
    """
    Executa o script 'backup_db.sh' para realizar backup do banco SQLite.
    """
    # Obter a data e hora atual formatada
    data_hora_atual = localtime().strftime('%d-%m-%Y %H:%M:%S')

    # Caminho para o script de backup
    caminho_arquivo_sh = 'backup_db.sh'

    # Executar o script de backup
    resultado = subprocess.run(['sh', caminho_arquivo_sh], capture_output=True, text=True)
    
    # Verificar o resultado da execução do script
    if resultado.returncode == 0:
        print('[{}] [BACKUP DIÁRIO] Backup do DB realizado.'.format(data_hora_atual))
    else:
        print('[{}] [BACKUP DIÁRIO] Falha durante backup do DB.'.format(data_hora_atual))
        print('[ERROR] ', resultado.stderr)
        
    time.sleep(random.randint(10, 20))
##### FIM #####
