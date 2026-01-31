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
from nossopainel.services.logging_config import get_logger
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
from nossopainel.utils import (
    get_saudacao_por_hora,
    registrar_log,
)
from nossopainel.services.wpp import (
    LogTemplates,
    MessageSendConfig,
    send_message,
    _sanitize_response,
)
from wpp.api_connection import (
    check_number_status,
    check_connection,
)
from integracoes.openai_chat import consultar_chatgpt

from nossopainel.models import (
    Mensalidade, SessaoWpp, MensagemEnviadaWpp,
    Cliente, DadosBancarios, HorarioEnvios,
    MensagensLeads, TelefoneLeads, OfertaPromocionalEnviada,
    TarefaEnvio, HistoricoExecucaoTarefa,
    ConfiguracaoAgendamento, ConfiguracaoEnvio,
)

API_WPP_URL_PROD = os.getenv("API_WPP_URL_PROD")
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
######## FUNÇÃO PARA VERIFICAR SAÚDE DA SESSÃO WHATSAPP ##########
##################################################################

def verificar_saude_sessao(usuario: str, token: str) -> bool:
    """
    Verifica se a sessão WhatsApp está realmente ativa via check-connection.

    Detecta inconsistências onde status-session retorna CONNECTED mas
    check-connection retorna Disconnected (problema de detached frame).

    Args:
        usuario: Nome da sessão WPPCONNECT
        token: Token de autenticação da sessão

    Returns:
        bool: True se sessão está saudável, False se com problema no WPPCONNECT.

    Nota:
        NÃO marca a sessão como inativa no Django. Após rebuild do container
        WPPCONNECT, a sessão volta a funcionar automaticamente.
    """
    try:
        dados, status_code = check_connection(usuario, token)

        # API não respondeu corretamente
        if status_code != 200:
            logger.warning(
                "[Health Check] Sessão %s - API não respondeu (HTTP %s) - envios cancelados para este horário",
                usuario,
                status_code
            )
            registrar_log_auditoria({
                "funcao": "verificar_saude_sessao",
                "status": "api_indisponivel",
                "usuario": usuario,
                "http_status": status_code,
                "response": dados,
            })
            return False

        # Verifica se conexão está realmente ativa
        # check-connection retorna {"status": true/false, "message": "Connected"/"Disconnected"}
        connection_status = dados.get("status") if isinstance(dados, dict) else None
        connection_message = dados.get("message", "") if isinstance(dados, dict) else ""

        if connection_status is False or connection_message == "Disconnected":
            logger.warning(
                "[Health Check] Sessão %s com problema no WPPCONNECT (status=%s, message=%s) - "
                "envios cancelados para este horário",
                usuario,
                connection_status,
                connection_message
            )
            registrar_log_auditoria({
                "funcao": "verificar_saude_sessao",
                "status": "sessao_desconectada",
                "usuario": usuario,
                "http_status": status_code,
                "connection_status": connection_status,
                "connection_message": connection_message,
            })
            return False

        logger.debug(
            "[Health Check] Sessão %s está saudável (status=%s, message=%s)",
            usuario,
            connection_status,
            connection_message
        )
        return True

    except Exception as e:
        logger.error(
            "[Health Check] Erro ao verificar sessão %s: %s",
            usuario,
            str(e),
            exc_info=True
        )
        registrar_log_auditoria({
            "funcao": "verificar_saude_sessao",
            "status": "erro",
            "usuario": usuario,
            "erro": str(e),
        })
        # Em caso de erro, retorna False por segurança (não tenta enviar)
        return False


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


##########################################################################
##### FUNÇÃO AUXILIAR PARA VALIDAR FORMA DE PAGAMENTO DO CLIENTE #####
##########################################################################

def validar_forma_pagamento_cliente(cliente):
    """
    Valida se o cliente tem forma de pagamento válida para receber notificações.

    Verifica:
    1. Se o cliente tem forma de pagamento associada
    2. Se a forma tem API (PIX automático), está válido
    3. Se for PIX sem API, verifica se os dados estão completos

    Returns:
        tuple: (valido, motivo, dados_pix)
        - valido: bool - Se pode enviar notificação
        - motivo: str - Motivo caso inválido
        - dados_pix: dict|None - Dados PIX para montar mensagem
    """
    # 1. Verificar se tem forma de pagamento
    if not cliente.forma_pgto:
        return (False, "sem_forma_pagamento", None)

    forma_pgto = cliente.forma_pgto

    # 2. Se tem API, está válido (PIX automático)
    if forma_pgto.tem_integracao_api:
        return (True, "com_api", None)

    # 3. Se não tem API e é PIX, validar dados
    if forma_pgto.nome == "PIX":
        # Tentar via conta_bancaria (formas novas)
        if forma_pgto.conta_bancaria:
            cb = forma_pgto.conta_bancaria
            if all([
                cb.instituicao and cb.instituicao.nome,
                cb.beneficiario,
                cb.tipo_chave_pix,
                cb.chave_pix
            ]):
                return (True, "pix_manual_completo", {
                    "instituicao": cb.instituicao.nome,
                    "beneficiario": cb.beneficiario,
                    "tipo_chave": cb.tipo_chave_pix,
                    "chave": cb.chave_pix
                })
            return (False, "pix_dados_incompletos", None)

        # Tentar via dados_bancarios FK (formas antigas/legadas)
        if forma_pgto.dados_bancarios:
            db = forma_pgto.dados_bancarios
            if all([db.instituicao, db.beneficiario, db.tipo_chave, db.chave]):
                return (True, "pix_manual_completo", {
                    "instituicao": db.instituicao,
                    "beneficiario": db.beneficiario,
                    "tipo_chave": db.tipo_chave,
                    "chave": db.chave
                })
            return (False, "pix_dados_incompletos", None)

        # Fallback: buscar DadosBancarios diretamente pelo usuário do cliente
        # (para formas de pagamento antigas que ainda não foram editadas na nova interface)
        dados_bancarios_usuario = DadosBancarios.objects.filter(
            usuario=cliente.usuario
        ).first()
        if dados_bancarios_usuario:
            db = dados_bancarios_usuario
            if all([db.instituicao, db.beneficiario, db.tipo_chave, db.chave]):
                return (True, "pix_manual_fallback", {
                    "instituicao": db.instituicao,
                    "beneficiario": db.beneficiario,
                    "tipo_chave": db.tipo_chave,
                    "chave": db.chave
                })
            return (False, "pix_dados_incompletos_fallback", None)

        return (False, "pix_sem_dados", None)

    # 4. Boleto e Cartão não precisam de dados extras
    return (True, "forma_valida", None)


##########################################################################
##### FUNÇÃO PARA OBTER TIPO DE INTEGRAÇÃO DA FORMA DE PAGAMENTO #####
##########################################################################

def obter_tipo_integracao_cliente(cliente):
    """
    Retorna o tipo de integração da forma de pagamento do cliente.

    Returns:
        str: 'fastdepix', 'mercado_pago', 'efi_bank', 'manual', 'boleto', 'cartao', None
    """
    if not cliente.forma_pgto:
        return None

    forma = cliente.forma_pgto

    if forma.nome == "Cartão de Crédito":
        return 'cartao'

    if forma.nome == "Boleto":
        return 'boleto'

    # PIX - verificar integração
    if forma.nome == "PIX":
        if forma.conta_bancaria and forma.conta_bancaria.instituicao:
            return forma.conta_bancaria.instituicao.tipo_integracao  # fastdepix, mercado_pago, efi_bank, manual
        return 'manual'

    return None


##########################################################################
##### FUNÇÃO PARA OBTER URL BASE DO PAINEL DO CLIENTE #####
##########################################################################

def get_url_painel_cliente(usuario):
    """
    Retorna URL base do painel do cliente para o usuário.

    Args:
        usuario: User do Django (admin responsável pelo painel)

    Returns:
        str: URL completa (ex: "https://meunegocio.pagar.cc/") ou None
    """
    from painel_cliente.models import SubdominioPainelCliente

    config = SubdominioPainelCliente.objects.filter(
        admin_responsavel=usuario,
        ativo=True
    ).first()

    if not config:
        return None

    return f"https://{config.dominio_completo}/"


##########################################################################
##### FUNÇÃO PARA OBTER TEMPLATE DE MENSAGEM DO BANCO DE DADOS #####
##########################################################################

def get_template_mensagem(nome_job: str, chave_template: str, texto_padrao: str) -> str:
    """
    Busca um template de mensagem configurado no banco de dados.

    Args:
        nome_job: Nome do job em ConfiguracaoAgendamento (ex: 'envios_vencimento')
        chave_template: Chave do template no JSON (ex: 'observacao_fastdepix')
        texto_padrao: Texto padrão caso não encontre no banco

    Returns:
        str: Template encontrado no banco ou texto_padrao como fallback
    """
    try:
        config = ConfiguracaoAgendamento.objects.filter(nome=nome_job).first()
        if config and config.templates_mensagem:
            template = config.templates_mensagem.get(chave_template)
            if template:
                return template
    except Exception as e:
        logger.warning(f"Erro ao buscar template '{chave_template}' do job '{nome_job}': {e}")

    return texto_padrao


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

            # Obter tipo de integração do cliente
            tipo_integracao = obter_tipo_integracao_cliente(cliente)

            # Não enviar para clientes com Cartão de Crédito
            if tipo_integracao == 'cartao':
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_a_vencer",
                    "status": "ignorado_cartao_credito",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            # Não enviar para clientes com Mercado Pago ou EfiBank (APIs pendentes)
            if tipo_integracao in ('mercado_pago', 'efi_bank'):
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_a_vencer",
                    "status": f"ignorado_api_pendente_{tipo_integracao}",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            # Validar forma de pagamento do cliente
            valido, motivo, dados_pix = validar_forma_pagamento_cliente(cliente)
            if not valido:
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_a_vencer",
                    "status": f"forma_pgto_invalida_{motivo}",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            # Para FastDePix, obter URL do painel
            url_painel = None
            if tipo_integracao == 'fastdepix':
                url_painel = get_url_painel_cliente(usuario)
                if not url_painel:
                    registrar_log_auditoria({
                        "funcao": "obter_mensalidades_a_vencer",
                        "status": "fastdepix_sem_painel_configurado",
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

            # ===== MENSALIDADE A VENCER (1 DIA ANTES) =====
            if tipo_mensagem == "à vencer 1 dias":

                # Template FastDePix - com link do painel
                if tipo_integracao == 'fastdepix':
                    mensagem = (
                        f"⚠️ *ATENÇÃO, {primeiro_nome}!* ⚠️\n\n"
                        f"▫️ *DETALHES DO SEU PLANO:*\n"
                        f"_________________________________\n"
                        f"🔖 *Plano*: {plano_nome}\n"
                        f"📆 *Vencimento*: {dt_formatada}\n"
                        f"💰 *Valor*: R$ {mensalidade.valor}\n"
                        f"_________________________________\n\n"
                        f"▫️ *PAGAMENTO COM PIX:*\n"
                        f"📱 Acesse o link abaixo, faça login para visualizar sua mensalidade e efetuar o pagamento:\n\n"
                        f"🔗 {url_painel}\n\n"
                        f"✅ O pagamento será confirmado automaticamente!"
                    )

                # Template Boleto
                elif tipo_integracao == 'boleto':
                    mensagem = (
                        f"⚠️ *ATENÇÃO, {primeiro_nome}!* ⚠️\n\n"
                        f"▫️ *DETALHES DO SEU PLANO:*\n"
                        f"_________________________________\n"
                        f"🔖 *Plano*: {plano_nome}\n"
                        f"📆 *Vencimento*: {dt_formatada}\n"
                        f"💰 *Valor*: R$ {mensalidade.valor}\n"
                        f"_________________________________\n\n"
                        f"▫️ *PAGAMENTO COM BOLETO:*\n\n"
                        f"✉️ O seu boleto já foi emitido\n"
                        f"📧 Caso não o identifique em seu e-mail, solicite aqui no WhatsApp\n\n"
                        f"‼️ _Caso já tenha pago, desconsidere esta mensagem._"
                    )

                # Template PIX Manual - com dados bancários
                elif tipo_integracao == 'manual' and dados_pix:
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
                        f"🔑 *Tipo*: {dados_pix['tipo_chave']}\n"
                        f"🔢 *Chave*: {dados_pix['chave']}\n"
                        f"🏦 *Banco*: {dados_pix['instituicao']}\n"
                        f"👤 *Beneficiário*: {dados_pix['beneficiario']}\n"
                        f"_________________________________\n\n"
                        f"‼️ _Caso já tenha pago, por favor, nos envie o comprovante._"
                    )

            # ===== VENCE HOJE =====
            elif tipo_mensagem == "vence hoje":

                # Template FastDePix - com link do painel
                if tipo_integracao == 'fastdepix':
                    mensagem = (
                        f"⚠️ *ATENÇÃO, {primeiro_nome}!* ⚠️\n\n"
                        f"O seu plano *{plano_nome}* *vence hoje* ({dt_formatada}).\n\n"
                        f"📱 Acesse o link abaixo, faça login para visualizar sua mensalidade e efetuar o pagamento:\n"
                        f"🔗 {url_painel}\n\n"
                        f"✅ Evite interrupções e mantenha seu acesso em dia!"
                    )

                # Template Manual/Boleto - sem link
                elif tipo_integracao in ('manual', 'boleto'):
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
                    "tipo_integracao": tipo_integracao,
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

            # Enviar mensagem de observação para FastDePix apenas no "à vencer 1 dias"
            if tipo_integracao == 'fastdepix' and tipo_mensagem == "à vencer 1 dias":
                time.sleep(10)  # Aguarda 10 segundos antes de enviar a observação

                # Busca template do banco de dados, com fallback para texto padrão
                texto_padrao_observacao = (
                    "OBSERVAÇÃO: Estamos mudando a forma como os clientes devem fazer seus pagamentos "
                    "e não aceitaremos mais pagamento enviados na chave pix anterior. Você precisa acessar "
                    "o link do nosso Painel do Cliente, acessar com seu número de telefone e realizar o "
                    "pagamento da mensalidade que estará em aberto na tela inicial."
                )
                mensagem_observacao = get_template_mensagem(
                    nome_job='envios_vencimento',
                    chave_template='observacao_fastdepix',
                    texto_padrao=texto_padrao_observacao
                )

                enviar_mensagem_agendada(
                    telefone=telefone,
                    mensagem=mensagem_observacao,
                    usuario=usuario,
                    token=sessao.token,
                    cliente=cliente.nome,
                    tipo_envio="observação fastdepix"
                )

                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_a_vencer",
                    "status": "observacao_fastdepix_enviada",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })

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

            # Obter tipo de integração do cliente
            tipo_integracao = obter_tipo_integracao_cliente(cliente)

            # Não enviar para clientes com Cartão de Crédito
            if tipo_integracao == 'cartao':
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_vencidas",
                    "status": "ignorado_cartao_credito",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            # Não enviar para clientes com Mercado Pago ou EfiBank (APIs pendentes)
            if tipo_integracao in ('mercado_pago', 'efi_bank'):
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_vencidas",
                    "status": f"ignorado_api_pendente_{tipo_integracao}",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            # Validar forma de pagamento do cliente
            valido, motivo, _ = validar_forma_pagamento_cliente(cliente)
            if not valido:
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_vencidas",
                    "status": f"forma_pgto_invalida_{motivo}",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "mensalidade_id": mensalidade.id,
                })
                continue

            # Para FastDePix no lembrete de atraso, obter URL do painel
            url_painel = None
            if tipo_integracao == 'fastdepix' and tipo_mensagem == "lembrete atraso":
                url_painel = get_url_painel_cliente(usuario)
                if not url_painel:
                    registrar_log_auditoria({
                        "funcao": "obter_mensalidades_vencidas",
                        "status": "fastdepix_sem_painel_configurado",
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

            mensagem = None

            # ===== LEMBRETE DE ATRASO (2 DIAS) =====
            if tipo_mensagem == "lembrete atraso":

                # Template FastDePix - com link do painel
                if tipo_integracao == 'fastdepix':
                    mensagem = (
                        f"*{saudacao}, {primeiro_nome}* 😊\n\n"
                        f"*Ainda não identificamos o pagamento da sua mensalidade.*\n\n"
                        f"📱 Acesse o link abaixo, faça login para visualizar sua mensalidade e efetuar o pagamento:\n"
                        f"🔗 {url_painel}"
                    )

                # Template Manual/Boleto - sem link
                elif tipo_integracao in ('manual', 'boleto'):
                    mensagem = (
                        f"*{saudacao}, {primeiro_nome} 😊*\n\n"
                        f"*Ainda não identificamos o pagamento da sua mensalidade para renovação.*\n\n"
                        f"Caso já tenha feito, envie aqui novamente o seu comprovante, por favor!"
                    )

            # ===== SUSPENSÃO (3 DIAS) - Mesmo template para todos =====
            elif tipo_mensagem == "suspensao":
                mensagem = (
                    f"*{saudacao}, {primeiro_nome}*\n\n"
                    f"Informamos que, devido à falta de pagamento, o seu acesso ao sistema está sendo *suspenso*.\n\n"
                    f"⚠️ Se o seu plano atual for promocional ou incluir algum desconto, esses benefícios poderão não estar mais disponíveis para futuras renovações.\n\n"
                    f"Agradecemos pela confiança e esperamos poder contar com você novamente em breve."
                )

            if not mensagem:
                registrar_log_auditoria({
                    "funcao": "obter_mensalidades_vencidas",
                    "status": "mensagem_nao_montada",
                    "usuario": str(usuario),
                    "cliente": cliente.nome,
                    "cliente_id": cliente.id,
                    "tipo_envio": tipo_mensagem,
                    "tipo_integracao": tipo_integracao,
                    "mensalidade_id": mensalidade.id,
                })
                continue

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
    Envia mensagens personalizadas para clientes cancelados há X dias.

    Sistema de ofertas progressivas:
    - 20 dias: Feedback
    - 60 dias: Oferta 1 (2 meses)
    - 240 dias: Oferta 2 (8 meses)
    - 420 dias: Oferta 3 (14 meses)

    Cada cliente recebe no máximo 3 ofertas promocionais em toda a vida.
    A contagem de dias é sempre a partir da data_cancelamento atual.

    Placeholders disponíveis nos templates: {saudacao}, {nome}
    """
    admin = User.objects.filter(is_superuser=True).order_by('id').first()

    # Textos padrão (fallback)
    texto_padrao_feedback = (
        "*{saudacao}, {nome}* 🫡\n\n"
        "Tudo bem? Espero que sim.\n\n"
        "Faz um tempo que você deixou de ser nosso cliente ativo e ficamos preocupados. "
        "Houve algo que não agradou em nosso sistema?\n\n"
        "Pergunto, pois se algo não agradou, nos informe para fornecermos uma plataforma "
        "melhor para você, tá bom?\n\n"
        "Estamos à disposição! 🙏🏼"
    )

    texto_padrao_oferta_1 = (
        "*Opa.. {saudacao}, {nome}!! Tudo bacana?*\n\n"
        "Como você já foi nosso cliente, trago uma notícia que talvez você goste muuuiito!!\n\n"
        "Você pode renovar a sua mensalidade conosco pagando *APENAS R$ 24.90* nos próximos "
        "3 meses. Olha só que bacana?!?!\n\n"
        "Esse tipo de desconto não oferecemos a qualquer um, viu? rsrs\n\n"
        "Caso tenha interesse, avise aqui, pois iremos garantir essa oferta apenas essa semana. 👏🏼👏🏼"
    )

    texto_padrao_oferta_2 = (
        "*{saudacao}, {nome}!* 😊\n\n"
        "Sentimos muito a sua falta por aqui!\n\n"
        "Que tal voltar para a nossa família com uma *SUPER OFERTA EXCLUSIVA*?\n\n"
        "Estamos oferecendo *os próximos 3 meses por apenas R$ 24,90 cada* para você "
        "que já foi nosso cliente! 🎉\n\n"
        "Esta é uma oportunidade única de retornar com um preço especial. Não perca!\n\n"
        "Tem interesse? É só responder aqui! 🙌"
    )

    texto_padrao_oferta_3 = (
        "*{saudacao}, {nome}!* 🌟\n\n"
        "Esta é a nossa *ÚLTIMA OFERTA ESPECIAL* para você!\n\n"
        "Sabemos que você já foi parte da nossa família e queremos muito ter você de volta.\n\n"
        "✨ *OFERTA FINAL: R$ 24,90 para os próximos 3 meses* ✨\n\n"
        "Esta é realmente a última oportunidade de aproveitar este preço exclusivo.\n\n"
        "O que acha? Vamos renovar essa parceria? 🤝"
    )

    # Busca templates do banco de dados com fallback para texto padrão
    # Mensagem de feedback (20 dias)
    feedback_config = {
        "dias": 20,
        "tipo": "feedback",
        "mensagem": get_template_mensagem(
            nome_job='mensalidades_canceladas',
            chave_template='feedback_20_dias',
            texto_padrao=texto_padrao_feedback
        )
    }

    # Ofertas promocionais progressivas
    ofertas_config = [
        {
            "dias": 60,
            "numero_oferta": 1,
            "mensagem": get_template_mensagem(
                nome_job='mensalidades_canceladas',
                chave_template='oferta_1_60_dias',
                texto_padrao=texto_padrao_oferta_1
            )
        },
        {
            "dias": 240,
            "numero_oferta": 2,
            "mensagem": get_template_mensagem(
                nome_job='mensalidades_canceladas',
                chave_template='oferta_2_240_dias',
                texto_padrao=texto_padrao_oferta_2
            )
        },
        {
            "dias": 420,
            "numero_oferta": 3,
            "mensagem": get_template_mensagem(
                nome_job='mensalidades_canceladas',
                chave_template='oferta_3_420_dias',
                texto_padrao=texto_padrao_oferta_3
            )
        }
    ]

    # Processa feedback de 20 dias (separado das ofertas)
    _processar_feedback(admin, feedback_config)

    # Processa ofertas promocionais progressivas
    for oferta_config in ofertas_config:
        _processar_oferta_promocional(admin, oferta_config)


def _processar_feedback(admin, config):
    """Processa envio de feedback para clientes cancelados há 20 dias."""
    qtd_dias = config["dias"]
    mensagem_template = config["mensagem"]
    data_alvo = localtime().date() - timedelta(days=qtd_dias)

    # Busca clientes cancelados há exatamente 20 dias
    clientes = Cliente.objects.filter(
        usuario=admin,
        cancelado=True,
        nao_enviar_msgs=False,
        data_cancelamento=data_alvo
    )

    qtd = clientes.count()
    logger.info(
        "Feedback para cancelados | dias=%d quantidade=%d",
        qtd_dias,
        qtd
    )

    if not qtd:
        logger.debug("Nenhum feedback para enviar (20 dias)")
        return

    for cliente in clientes:
        _enviar_mensagem_cliente(
            cliente=cliente,
            admin=admin,
            mensagem_template=mensagem_template,
            qtd_dias=qtd_dias,
            tipo_envio="Feedback 20d"
        )
        time.sleep(random.uniform(30, 60))


def _processar_oferta_promocional(admin, oferta_config):
    """
    Processa envio de ofertas promocionais progressivas.

    Verifica:
    1. Se cliente já recebeu 3 ofertas (limite vitalício)
    2. Se cliente já recebeu esta oferta específica
    3. Se cliente está cancelado há exatamente X dias
    """
    qtd_dias = oferta_config["dias"]
    numero_oferta = oferta_config["numero_oferta"]
    mensagem_template = oferta_config["mensagem"]
    data_alvo = localtime().date() - timedelta(days=qtd_dias)

    # Busca clientes cancelados há exatamente X dias
    clientes_candidatos = Cliente.objects.filter(
        usuario=admin,
        cancelado=True,
        nao_enviar_msgs=False,
        data_cancelamento=data_alvo
    )

    clientes_enviados = 0
    clientes_ignorados = 0

    for cliente in clientes_candidatos:
        # Verifica quantas ofertas este cliente já recebeu na vida
        total_ofertas_recebidas = cliente.ofertas_enviadas.count()

        if total_ofertas_recebidas >= 3:
            logger.debug(
                "Cliente atingiu limite de ofertas | cliente=%s total_ofertas=%d",
                cliente.nome,
                total_ofertas_recebidas
            )
            registrar_log_auditoria({
                "funcao": "_processar_oferta_promocional",
                "status": "limite_ofertas_atingido",
                "cliente": cliente.nome,
                "cliente_id": cliente.id,
                "total_ofertas_recebidas": total_ofertas_recebidas,
                "numero_oferta_tentada": numero_oferta,
                "dias_cancelado": qtd_dias,
            })
            clientes_ignorados += 1
            continue

        # Verifica se já recebeu ESTA oferta específica
        ja_recebeu_esta_oferta = cliente.ofertas_enviadas.filter(
            numero_oferta=numero_oferta
        ).exists()

        if ja_recebeu_esta_oferta:
            logger.debug(
                "Cliente já recebeu esta oferta | cliente=%s numero_oferta=%d",
                cliente.nome,
                numero_oferta
            )
            registrar_log_auditoria({
                "funcao": "_processar_oferta_promocional",
                "status": "oferta_ja_recebida",
                "cliente": cliente.nome,
                "cliente_id": cliente.id,
                "numero_oferta": numero_oferta,
                "dias_cancelado": qtd_dias,
            })
            clientes_ignorados += 1
            continue

        # Cliente elegível! Envia oferta
        sucesso = _enviar_mensagem_cliente(
            cliente=cliente,
            admin=admin,
            mensagem_template=mensagem_template,
            qtd_dias=qtd_dias,
            tipo_envio=f"Oferta {numero_oferta}"
        )

        if sucesso:
            # Registra no histórico de ofertas
            OfertaPromocionalEnviada.objects.create(
                cliente=cliente,
                usuario=admin,
                numero_oferta=numero_oferta,
                dias_apos_cancelamento=qtd_dias,
                data_cancelamento_ref=cliente.data_cancelamento,
                mensagem_enviada=mensagem_template
            )

            clientes_enviados += 1

            logger.info(
                "Oferta enviada e registrada | cliente=%s numero_oferta=%d total_ofertas_cliente=%d",
                cliente.nome,
                numero_oferta,
                total_ofertas_recebidas + 1
            )

            registrar_log_auditoria({
                "funcao": "_processar_oferta_promocional",
                "status": "oferta_enviada",
                "cliente": cliente.nome,
                "cliente_id": cliente.id,
                "numero_oferta": numero_oferta,
                "dias_cancelado": qtd_dias,
                "total_ofertas_apos_envio": total_ofertas_recebidas + 1,
            })

        time.sleep(random.uniform(30, 60))

    logger.info(
        "Processamento oferta concluído | numero_oferta=%d dias=%d enviados=%d ignorados=%d",
        numero_oferta,
        qtd_dias,
        clientes_enviados,
        clientes_ignorados
    )


def _enviar_mensagem_cliente(cliente, admin, mensagem_template, qtd_dias, tipo_envio):
    """
    Envia mensagem para um cliente específico.

    Placeholders suportados no template:
        {saudacao} - Saudação conforme horário (Bom dia, Boa tarde, Boa noite)
        {nome} - Primeiro nome do cliente

    Returns:
        bool: True se enviou com sucesso, False caso contrário
    """
    primeiro_nome = cliente.nome.split(' ')[0]
    saudacao = get_saudacao_por_hora()
    mensagem = mensagem_template.format(saudacao=saudacao, nome=primeiro_nome)

    sessao = SessaoWpp.objects.filter(usuario=admin, is_active=True).first()

    if not sessao or not sessao.token:
        logger.warning("Sessão WPP não encontrada | usuario=%s", admin)
        registrar_log_auditoria({
            "funcao": "_enviar_mensagem_cliente",
            "status": "sessao_indisponivel",
            "usuario": str(admin),
            "cliente": cliente.nome,
            "cliente_id": cliente.id,
            "dias_cancelado": qtd_dias,
            "tipo_envio": tipo_envio,
        })
        return False

    try:
        enviar_mensagem_agendada(
            telefone=cliente.telefone,
            mensagem=mensagem,
            usuario=admin,
            token=sessao.token,
            cliente=cliente.nome,
            tipo_envio=tipo_envio
        )
        return True
    except Exception as e:
        logger.error(
            "Erro ao enviar mensagem | cliente=%s erro=%s",
            cliente.nome,
            str(e),
            exc_info=True
        )
        registrar_log_auditoria({
            "funcao": "_enviar_mensagem_cliente",
            "status": "erro_envio",
            "usuario": str(admin),
            "cliente": cliente.nome,
            "cliente_id": cliente.id,
            "dias_cancelado": qtd_dias,
            "tipo_envio": tipo_envio,
            "erro": str(e),
        })
        return False
##### FIM #####


#####################################################################################################
##### BLOCO PARA ENVIO DE MENSAGENS AOS CLIENTES ATIVOS, CANCELADOS E FUTUROS CLIENTES (AVULSO) #####
#####################################################################################################

def envia_mensagem_personalizada(
    tipo_envio: str,
    image_name: str = None,
    nome_msg: str = None,
    mensagem_direta: str = None,
    image_path: str = None,
    usuario_id: int = None,
    filtro_estados: list = None,
    filtro_cidades: list = None,
    dias_cancelamento: int = 10,
    limite_envios: int = None,
    tarefa_id: int = None
) -> dict:
    """
    Envia mensagens via WhatsApp para grupos de clientes com base no tipo de envio:
    - 'ativos': clientes em dia.
    - 'cancelados': clientes inativos há mais de X dias (configurável).
    - 'avulso': números importados via arquivo externo.

    Parâmetros:
        tipo_envio (str): Tipo de grupo alvo ('ativos', 'cancelados', 'avulso').
        image_name (str): Nome da imagem opcional a ser enviada (modo legado).
        nome_msg (str): Nome do template da mensagem (modo legado).
        mensagem_direta (str): Mensagem direta a ser enviada (modo TarefaEnvio).
        image_path (str): Caminho completo da imagem (modo TarefaEnvio).
        usuario_id (int): ID do usuário para envio (modo TarefaEnvio).
        filtro_estados (list): Lista de UFs para filtrar clientes (ex: ['BA', 'SE']).
        filtro_cidades (list): Lista de cidades para filtrar clientes.
        dias_cancelamento (int): Dias mínimos de cancelamento para tipo 'cancelados' (padrão: 10).
        limite_envios (int): Limite máximo de envios por execução (padrão: ConfiguracaoEnvio).
        tarefa_id (int): ID da tarefa de envio (controle de duplicidade por tarefa).

    Retorna:
        dict: {'enviados': int, 'erros': int, 'ja_receberam': int, 'detalhes': list, 'total_destinatarios': int}

    Controle de duplicidade:
    - Com tarefa_id: Permite 1 envio por tarefa por mês para cada telefone.
    - Sem tarefa_id (legado): Permite 1 envio por dia para cada telefone.
    """
    # Resultado para retorno
    resultado = {'enviados': 0, 'erros': 0, 'ja_receberam': 0, 'detalhes': []}

    # Determina o usuário
    if usuario_id:
        usuario = User.objects.get(id=usuario_id)
    else:
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
        return resultado
    token = sessao.token

    # Determina se vai enviar imagem (modo legado ou modo TarefaEnvio)
    tem_imagem = image_name or image_path
    url_envio = f"{API_WPP_URL_PROD}/{usuario}/send-{'image' if tem_imagem else 'message'}"

    # Obtém a imagem em base64
    image_base64 = None
    if image_path and os.path.exists(image_path):
        # Modo TarefaEnvio: carrega imagem do caminho completo
        try:
            with open(image_path, 'rb') as img_file:
                image_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Erro ao carregar imagem de TarefaEnvio: {e}")
    elif image_name:
        # Modo legado: carrega imagem por nome
        image_base64 = obter_img_base64(image_name, tipo_envio)

    # Obtém configuração global de envio
    config_envio = ConfiguracaoEnvio.get_config()

    # Limite de envios por execução (parâmetro > configuração global > padrão 100)
    total_enviados = 0
    LIMITE_ENVIO_DIARIO = limite_envios or config_envio.limite_envios_por_execucao or 100

    destinatarios = []

    # Obtenção dos números com base no tipo
    if tipo_envio == 'ativos':
        clientes = Cliente.objects.filter(
            usuario=usuario,
            cancelado=False,
            nao_enviar_msgs=False
        )
        # Aplica filtro de estados se fornecido
        if filtro_estados:
            clientes = clientes.filter(uf__in=filtro_estados)
        # Aplica filtro de cidades se fornecido
        if filtro_cidades:
            clientes = clientes.filter(cidade__in=filtro_cidades)

        # Usa iterator() para otimizar memória em bases grandes
        destinatarios = [
            {
                "telefone": cliente.telefone,
                "cliente_id": cliente.id,
                "cliente_nome": cliente.nome,
            }
            for cliente in clientes.iterator()
        ]
    elif tipo_envio == 'cancelados':
        clientes = Cliente.objects.filter(
            usuario=usuario,
            cancelado=True,
            nao_enviar_msgs=False,
            data_cancelamento__lte=localtime() - timedelta(days=dias_cancelamento)
        )
        # Aplica filtro de estados se fornecido
        if filtro_estados:
            clientes = clientes.filter(uf__in=filtro_estados)
        # Aplica filtro de cidades se fornecido
        if filtro_cidades:
            clientes = clientes.filter(cidade__in=filtro_cidades)

        # Usa iterator() para otimizar memória em bases grandes
        destinatarios = [
            {
                "telefone": cliente.telefone,
                "cliente_id": cliente.id,
                "cliente_nome": cliente.nome,
            }
            for cliente in clientes.iterator()
        ]
    elif tipo_envio == 'avulso':
        # Leads não possuem filtro geográfico (modelo não tem UF/cidade)
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

        # Controle de duplicidade - depende se tem tarefa_id ou não
        hoje = localtime()

        if tarefa_id:
            # MODO TAREFA: Verifica se já enviou ESTA TAREFA para este telefone ESTE MÊS
            if MensagemEnviadaWpp.objects.filter(
                usuario=usuario,
                telefone=telefone,
                tarefa_id=tarefa_id,
                data_envio__year=hoje.year,
                data_envio__month=hoje.month
            ).exists():
                logger.debug(
                    "Envio ignorado (já enviado esta tarefa este mês) | telefone=%s tarefa_id=%s usuario=%s",
                    telefone,
                    tarefa_id,
                    usuario.username
                )
                registrar_log(f"[{hoje.strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - ⚠️ Já recebeu esta tarefa este mês", usuario, DIR_LOGS_AGENDADOS)
                registrar_log_auditoria({
                    "funcao": "envia_mensagem_personalizada",
                    "status": "ignorado_tarefa_mensal",
                    "usuario": usuario.username,
                    "tipo_envio": tipo_envio,
                    "telefone": telefone,
                    "cliente_nome": cliente_nome,
                    "cliente_id": cliente_id,
                    "tarefa_id": tarefa_id,
                })
                resultado['ja_receberam'] += 1
                continue
        else:
            # MODO LEGADO (sem tarefa): Mantém comportamento original
            # Ignora se já enviado hoje
            if MensagemEnviadaWpp.objects.filter(
                usuario=usuario,
                telefone=telefone,
                tarefa_id__isnull=True,
                data_envio=hoje.date()
            ).exists():
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
                resultado['ja_receberam'] += 1
                continue

            # Ignora se já enviado neste mês (modo legado)
            if tipo_envio in ["avulso", "ativos", "cancelados"]:
                if MensagemEnviadaWpp.objects.filter(
                    usuario=usuario,
                    telefone=telefone,
                    tarefa_id__isnull=True,
                    data_envio__year=hoje.year,
                    data_envio__month=hoje.month
                ).exists():
                    logger.debug(
                        "Envio ignorado (já enviado este mês) | telefone=%s tipo=%s usuario=%s",
                        telefone,
                        tipo_envio,
                        usuario.username
                    )
                    registrar_log(f"[{hoje.strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - ⚠️ Já recebeu envio este mês (legado)", usuario, DIR_LOGS_AGENDADOS)
                    registrar_log_auditoria({
                        "funcao": "envia_mensagem_personalizada",
                        "status": "ignorado_envio_mensal",
                        "usuario": usuario.username,
                        "tipo_envio": tipo_envio,
                        "telefone": telefone,
                        "cliente_nome": cliente_nome,
                        "cliente_id": cliente_id,
                    })
                    resultado['ja_receberam'] += 1
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
        if not numero_existe or not numero_existe.get('status'):
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
                # Marca lead como inválido ao invés de deletar (soft delete)
                TelefoneLeads.objects.filter(telefone=telefone, usuario=usuario).update(
                    valido=False,
                    data_validacao=localtime()
                )
                logger.info(
                    "Lead marcado como inválido | telefone=%s usuario=%s",
                    telefone,
                    usuario.username
                )
                registrar_log(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {telefone} - ⚠️ Marcado como inválido (avulso)", usuario, DIR_LOGS_AGENDADOS)
            resultado['erros'] += 1
            resultado['detalhes'].append({
                'telefone': telefone,
                'cliente_nome': cliente_nome,
                'cliente_id': cliente_id,
                'motivo': 'Número não possui WhatsApp',
                'tipo': 'numero_invalido'
            })
            continue

        # Obter mensagem: usa mensagem_direta (TarefaEnvio) ou template (legado)
        # Ambos os modos agora usam ChatGPT para variar a mensagem e evitar detecção de spam
        if mensagem_direta:
            message = variar_mensagem_chatgpt(mensagem_original=mensagem_direta, usuario=usuario)
        else:
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
            # Determina o nome do arquivo (TarefaEnvio ou legado)
            if image_path:
                filename = os.path.basename(image_path)
            else:
                filename = image_name or 'imagem.png'
            payload['filename'] = filename
            payload['caption'] = message
            payload['base64'] = f'data:image/png;base64,{image_base64}'

        audit_payload = {k: v for k, v in payload.items() if k != 'base64'}
        audit_payload["tem_base64"] = bool(payload.get('base64'))
        audit_payload["arquivo_imagem"] = image_path or image_name

        for tentativa in range(1, 4):
            response = None
            response_payload = None
            status_code = None
            error_message = None
            timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')

            try:
                response = requests.post(
                    url_envio,
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'Authorization': f'Bearer {token}'
                    },
                    json=payload,
                    timeout=30  # Timeout de 30 segundos para evitar travamentos
                )
                status_code = response.status_code

                try:
                    response_payload = response.json()
                except json.JSONDecodeError:
                    # Sanitiza para evitar registrar HTML de páginas de erro
                    response_payload = _sanitize_response(response.text)

                if status_code in (200, 201):
                    registrar_log(
                        TEMPLATE_LOG_MSG_SUCESSO.format(timestamp, tipo_envio.upper(), usuario, telefone),
                        usuario,
                        DIR_LOGS_AGENDADOS
                    )
                    # Registra envio - usa try/except para tratar IntegrityError em race condition
                    # (campo data_envio usa auto_now_add=True, então get_or_create não funciona bem)
                    try:
                        registro_envio = MensagemEnviadaWpp.objects.create(
                            usuario=usuario,
                            telefone=telefone,
                            tarefa_id=tarefa_id  # None para envios legados
                        )
                        registro_criado = True
                    except IntegrityError:
                        # Registro já existe (criado por outra instância paralela)
                        registro_envio = MensagemEnviadaWpp.objects.filter(
                            usuario=usuario,
                            telefone=telefone,
                            data_envio=localtime().date()
                        ).first()
                        registro_criado = False
                        logger.warning(
                            "IntegrityError: Registro MensagemEnviadaWpp já existia (race condition) | telefone=%s usuario=%s",
                            telefone,
                            usuario.username
                        )
                        logger.debug(
                            "Registro MensagemEnviadaWpp já existia (race condition tratada) | telefone=%s",
                            telefone
                        )
                    registrar_log_auditoria({
                        "funcao": "envia_mensagem_personalizada",
                        "status": "sucesso" if registro_criado else "sucesso_registro_existente",
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
                        "registro_envio_id": registro_envio.id if registro_envio else None,
                        "registro_criado": registro_criado,
                    })
                    total_enviados += 1
                    resultado['enviados'] += 1
                    break

                error_message = (
                    # Suporta tanto respostas da API quanto dicts sanitizados de HTML
                    response_payload.get('message') or response_payload.get('mensagem', 'Erro desconhecido')
                    if isinstance(response_payload, dict)
                    else str(response_payload)
                )

            except requests.RequestException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if getattr(exc, "response", None) is not None:
                    try:
                        response_payload = exc.response.json()
                    except (ValueError, AttributeError):
                        # Sanitiza para evitar registrar HTML de páginas de erro
                        response_payload = _sanitize_response(getattr(exc.response, "text", None))
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
        else:
            # Se saiu do loop sem sucesso (todas tentativas falharam)
            resultado['erros'] += 1
            resultado['detalhes'].append({
                'telefone': telefone,
                'cliente_nome': cliente_nome,
                'cliente_id': cliente_id,
                'motivo': f'Falha no envio após 3 tentativas: {error_message}',
                'tipo': 'falha_envio',
                'http_status': status_code,
                'ultima_resposta': str(response_payload)[:200] if response_payload else None
            })

        # Usa intervalo configurado (min/max) para delay entre mensagens
        intervalo_delay = random.uniform(config_envio.intervalo_minimo, config_envio.intervalo_maximo)
        time.sleep(intervalo_delay)

        # ============================================================
        # VERIFICAÇÃO DE CONFLITO DURANTE EXECUÇÃO
        # Pausa se notificações estão prestes a iniciar ou em execução
        # ============================================================
        if tarefa_id:
            tem_conflito, motivo = verificar_conflito_notificacoes(usuario.id)
            if tem_conflito:
                logger.info(
                    "Tarefa pausada durante execução por conflito | tarefa_id=%d motivo=%s enviados_ate_agora=%d",
                    tarefa_id, motivo, resultado['enviados']
                )
                # Atualiza status da tarefa no banco
                try:
                    tarefa_obj = TarefaEnvio.objects.get(id=tarefa_id)
                    tarefa_obj.pausado_por_notificacao = True
                    tarefa_obj.pausado_motivo = motivo
                    tarefa_obj.save(update_fields=['pausado_por_notificacao', 'pausado_motivo'])
                except TarefaEnvio.DoesNotExist:
                    pass

                # Aguarda até que o conflito seja resolvido (verifica a cada 30 segundos)
                tempo_aguardando = 0
                max_espera = 3600  # Máximo 1 hora de espera
                while tem_conflito and tempo_aguardando < max_espera:
                    time.sleep(30)
                    tempo_aguardando += 30
                    tem_conflito, motivo = verificar_conflito_notificacoes(usuario.id)
                    if tempo_aguardando % 300 == 0:  # Log a cada 5 minutos
                        logger.info(
                            "Tarefa ainda aguardando | tarefa_id=%d tempo_aguardando=%d min motivo=%s",
                            tarefa_id, tempo_aguardando // 60, motivo
                        )

                # Conflito resolvido - retoma execução
                logger.info(
                    "Tarefa retomando execução | tarefa_id=%d tempo_aguardado=%d seg",
                    tarefa_id, tempo_aguardando
                )
                try:
                    tarefa_obj = TarefaEnvio.objects.get(id=tarefa_id)
                    tarefa_obj.pausado_por_notificacao = False
                    tarefa_obj.pausado_motivo = ""
                    tarefa_obj.save(update_fields=['pausado_por_notificacao', 'pausado_motivo'])
                except TarefaEnvio.DoesNotExist:
                    pass

    # Adiciona total de destinatarios ao resultado
    resultado['total_destinatarios'] = len(destinatarios)

    # Retorna resultado para uso em TarefaEnvio
    return resultado


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
        queryset = TelefoneLeads.objects.filter(valido=True)  # Apenas leads válidos
        if usuario:
            queryset = queryset.filter(usuario=usuario)

        telefones = queryset.values_list('telefone', flat=True)

        # Preserva o '+' no número (formato internacional)
        # Remove apenas caracteres que não são dígitos ou '+', mantendo +5571999999999
        numeros_limpos = []
        for t in telefones:
            if not t:
                continue
            # Mantém apenas + e dígitos
            numero = re.sub(r'[^\d+]', '', t)
            if numero:
                numeros_limpos.append(numero)

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


def variar_mensagem_chatgpt(mensagem_original: str, usuario: User = None) -> str:
    """
    Gera uma variação da mensagem usando ChatGPT para evitar detecção de spam.

    Args:
        mensagem_original (str): Texto original da mensagem configurada na tarefa.
        usuario (User, opcional): Usuário responsável pelo envio.

    Returns:
        str: Mensagem reescrita com variações, ou a mensagem original em caso de erro.
    """
    if not mensagem_original or not mensagem_original.strip():
        return mensagem_original

    try:
        prompt = (
            "Você é um redator especialista em marketing pelo WhatsApp. "
            "Reescreva o texto abaixo mantendo a mesma intenção e informações, "
            "mas com frases ligeiramente diferentes, trocando algumas palavras por sinônimos, "
            "variando a ordem quando possível, e ajustando emojis se houver. "
            "O texto deve parecer natural, envolvente e adequado para WhatsApp. "
            "IMPORTANTE: Mantenha todos os dados importantes (valores, datas, nomes, links) exatamente como estão. "
            "Responda APENAS com o texto reescrito, sem explicações.\n\n"
            f"{mensagem_original}"
        )

        mensagem_variada = consultar_chatgpt(pergunta=prompt, user=usuario)

        if mensagem_variada and mensagem_variada.strip():
            logger.info(
                "Mensagem variada com sucesso via ChatGPT | usuario=%s | tamanho_original=%d | tamanho_variada=%d",
                usuario.username if usuario else "N/A",
                len(mensagem_original),
                len(mensagem_variada)
            )
            return mensagem_variada
        else:
            logger.warning(
                "ChatGPT retornou vazio, usando mensagem original | usuario=%s",
                usuario.username if usuario else "N/A"
            )
            return mensagem_original

    except Exception as e:
        logger.error(
            "Erro ao variar mensagem via ChatGPT, usando original | erro=%s | usuario=%s",
            str(e),
            usuario.username if usuario else "N/A",
            exc_info=True
        )
        return mensagem_original
#### FIM #####


###########################################################
##### VERIFICAÇÃO DE CONFLITO COM NOTIFICAÇÕES        #####
###########################################################

MARGEM_NOTIFICACAO_MINUTOS = 5


def verificar_conflito_notificacoes(usuario_id: int) -> tuple:
    """
    Verifica se há notificações de Vencimento/Atrasos que devem ter prioridade.

    Regras:
    1. Se uma notificação está em execução → PAUSA
    2. Se faltam menos de 5 minutos para uma notificação → PAUSA
    3. Se notificação deveria ter executado hoje mas ainda não → PAUSA

    Args:
        usuario_id: ID do usuário da tarefa

    Returns:
        tuple: (tem_conflito: bool, motivo: str)
    """
    agora = localtime()
    hoje = agora.date()
    hora_atual = agora.time()
    margem = timedelta(minutes=MARGEM_NOTIFICACAO_MINUTOS)

    # Buscar notificações ativas do usuário
    notificacoes = HorarioEnvios.objects.filter(
        usuario_id=usuario_id,
        status=True,
        ativo=True
    )

    for notif in notificacoes:
        tipo_nome = "Vencimentos" if notif.tipo_envio == "mensalidades_a_vencer" else "Atrasos"

        # 1. Notificação em execução
        if notif.em_execucao:
            return True, f"Notificação de {tipo_nome} em execução"

        # 2. Faltam menos de 5 minutos para a notificação
        horario_notif_dt = datetime.combine(hoje, notif.horario)
        # Tornar timezone-aware se necessário
        if agora.tzinfo is not None:
            horario_notif_dt = agora.tzinfo.localize(horario_notif_dt) if hasattr(agora.tzinfo, 'localize') else horario_notif_dt.replace(tzinfo=agora.tzinfo)

        diferenca = horario_notif_dt - agora
        if timedelta(0) < diferenca <= margem:
            minutos_restantes = int(diferenca.total_seconds() / 60)
            return True, f"Notificação de {tipo_nome} inicia em {minutos_restantes} minutos"

        # 3. Notificação deveria ter executado mas não executou
        if notif.ultimo_envio is None or notif.ultimo_envio < hoje:
            if hora_atual >= notif.horario:
                return True, f"Notificação de {tipo_nome} pendente de execução"

    return False, ""


def limpar_flags_tarefas_pausadas():
    """
    Limpa a flag pausado_por_notificacao de tarefas que não têm mais conflito.

    Esta função deve ser chamada SEMPRE no início do scheduler, independente
    de haver tarefas para executar na hora atual. Isso resolve o bug onde
    tarefas pausadas em uma hora nunca eram retomadas porque o filtro
    horario__hour=hora_atual não as incluía após a mudança de hora.
    """
    tarefas_pausadas = TarefaEnvio.objects.filter(
        pausado_por_notificacao=True,
        ativo=True
    )

    for tarefa in tarefas_pausadas:
        tem_conflito, motivo = verificar_conflito_notificacoes(tarefa.usuario_id)

        if not tem_conflito:
            tarefa.pausado_por_notificacao = False
            tarefa.pausado_motivo = ""
            tarefa.save(update_fields=['pausado_por_notificacao', 'pausado_motivo'])
            logger.info(
                "[TAREFAS] Flag de pausa limpa | tarefa_id=%d nome=%s usuario_id=%d",
                tarefa.id, tarefa.nome, tarefa.usuario_id
            )


###########################################################
##### FUNÇÃO PARA EXECUTAR TAREFAS DE ENVIO DO BANCO  #####
###########################################################

def run_scheduled_tasks_from_db():
    """
    Executa tarefas de envio configuradas no banco de dados (TarefaEnvio).
    Esta função roda em paralelo com run_scheduled_tasks() que usa lógica hardcoded.

    Verifica a cada execução:
    - Horário atual dentro da janela permitida (ConfiguracaoEnvio)
    - Tarefas ativas
    - Horário atual dentro da janela de execução (5 minutos de margem)
    - Se já executou hoje (evita duplicação)
    - Se deve executar hoje (dia da semana + período do mês)
    """
    try:
        # ============================================================
        # PRIMEIRO: Limpar flags de tarefas pausadas que não têm mais conflito
        # Isso deve acontecer ANTES de qualquer outra verificação
        # ============================================================
        limpar_flags_tarefas_pausadas()

        agora = localtime()
        hoje = agora.date()
        hora_atual = agora.hour
        minuto_atual = agora.minute
        hora_atual_time = agora.time()

        # ============================================================
        # VERIFICAÇÃO DE HORÁRIO PERMITIDO
        # ============================================================
        config_envio = ConfiguracaoEnvio.get_config()
        if config_envio.horario_inicio_permitido and config_envio.horario_fim_permitido:
            if not (config_envio.horario_inicio_permitido <= hora_atual_time <= config_envio.horario_fim_permitido):
                logger.debug(
                    "Fora do horário permitido para envios | atual=%s permitido=%s-%s",
                    hora_atual_time.strftime('%H:%M'),
                    config_envio.horario_inicio_permitido.strftime('%H:%M'),
                    config_envio.horario_fim_permitido.strftime('%H:%M')
                )
                return

        # Busca tarefas ativas que devem executar no horário atual (com margem de 5 min)
        tarefas = TarefaEnvio.objects.filter(
            ativo=True,
            horario__hour=hora_atual,
        ).select_related('usuario')

        # Filtra por minuto (dentro de janela de 5 minutos)
        tarefas_para_executar = []
        for tarefa in tarefas:
            minuto_tarefa = tarefa.horario.minute
            # Verifica se está dentro da janela de 5 minutos
            if minuto_tarefa <= minuto_atual <= minuto_tarefa + 5:
                tarefas_para_executar.append(tarefa)

        if not tarefas_para_executar:
            return

        for tarefa in tarefas_para_executar:
            try:
                # ============================================================
                # VERIFICAÇÃO DE CONFLITO COM NOTIFICAÇÕES
                # ============================================================
                tem_conflito, motivo = verificar_conflito_notificacoes(tarefa.usuario_id)
                if tem_conflito:
                    logger.info(
                        "TarefaEnvio pausada por conflito | tarefa_id=%d nome=%s motivo=%s",
                        tarefa.id,
                        tarefa.nome,
                        motivo
                    )
                    # Atualizar status de pausa
                    if not tarefa.pausado_por_notificacao:
                        tarefa.pausado_por_notificacao = True
                        tarefa.pausado_motivo = motivo
                        tarefa.save(update_fields=['pausado_por_notificacao', 'pausado_motivo'])
                    continue

                # Limpar flag de pausa se estava pausada
                if tarefa.pausado_por_notificacao:
                    tarefa.pausado_por_notificacao = False
                    tarefa.pausado_motivo = ""
                    tarefa.save(update_fields=['pausado_por_notificacao', 'pausado_motivo'])
                    logger.info(
                        "TarefaEnvio retomada após notificações | tarefa_id=%d nome=%s",
                        tarefa.id,
                        tarefa.nome
                    )

                # Pula se já executou hoje (exceto se execução não foi completa)
                if tarefa.ultimo_envio and tarefa.ultimo_envio.date() == hoje:
                    # Permitir reexecução se última execução não foi completa
                    if tarefa.execucao_completa:
                        logger.debug(
                            "TarefaEnvio já executada hoje com sucesso | tarefa_id=%d nome=%s",
                            tarefa.id,
                            tarefa.nome
                        )
                        continue
                    else:
                        logger.info(
                            "TarefaEnvio reexecutando - última execução incompleta | tarefa_id=%d nome=%s",
                            tarefa.id,
                            tarefa.nome
                        )

                # Verifica dia da semana + período do mês
                if not tarefa.deve_executar_hoje():
                    logger.debug(
                        "TarefaEnvio não deve executar hoje | tarefa_id=%d nome=%s",
                        tarefa.id,
                        tarefa.nome
                    )
                    continue

                # ============================================================
                # PROTEÇÃO CONTRA EXECUÇÃO PARALELA (com transação atômica)
                # ============================================================
                # Usa select_for_update para garantir lock exclusivo no banco
                with transaction.atomic():
                    # Tenta adquirir lock exclusivo na tarefa
                    tarefa_locked = TarefaEnvio.objects.select_for_update(
                        skip_locked=True
                    ).filter(
                        id=tarefa.id,
                        em_execucao=False
                    ).first()

                    if not tarefa_locked:
                        # Tarefa já está em execução ou foi bloqueada por outro processo
                        # Verifica se está travada (execução > 2 horas)
                        tarefa.refresh_from_db()
                        if tarefa.em_execucao and tarefa.execucao_iniciada_em:
                            tempo_execucao = agora - tarefa.execucao_iniciada_em
                            if tempo_execucao.total_seconds() > 7200:  # 2 horas
                                logger.warning(
                                    "TarefaEnvio travada detectada (>2h) - resetando | tarefa_id=%d nome=%s tempo=%s",
                                    tarefa.id,
                                    tarefa.nome,
                                    str(tempo_execucao)
                                )
                                tarefa.em_execucao = False
                                tarefa.execucao_iniciada_em = None
                                tarefa.save(update_fields=['em_execucao', 'execucao_iniciada_em'])
                        else:
                            logger.debug(
                                "TarefaEnvio já em execução ou bloqueada | tarefa_id=%d nome=%s",
                                tarefa.id,
                                tarefa.nome
                            )
                        continue

                    # Lock adquirido com sucesso - marca como em execução
                    tarefa = tarefa_locked

                    # Salvar ultimo_envio anterior para possível reversão em caso de erro
                    ultimo_envio_anterior = tarefa.ultimo_envio

                    # Marcar como execução em andamento (não completa)
                    tarefa.em_execucao = True
                    tarefa.execucao_iniciada_em = agora
                    tarefa.execucao_completa = False
                    tarefa.ultimo_envio = agora
                    tarefa.save(update_fields=['em_execucao', 'execucao_iniciada_em', 'execucao_completa', 'ultimo_envio'])

                logger.info(
                    "Iniciando execução de TarefaEnvio | tarefa_id=%d nome=%s tipo=%s usuario=%s",
                    tarefa.id,
                    tarefa.nome,
                    tarefa.tipo_envio,
                    tarefa.usuario.username
                )

                inicio = time.time()

                try:
                    # Determina caminho da imagem
                    image_path = None
                    if tarefa.imagem:
                        image_path = tarefa.imagem.path

                    # Executa envio usando a função existente
                    resultado = envia_mensagem_personalizada(
                        tipo_envio=tarefa.tipo_envio,
                        mensagem_direta=tarefa.mensagem_plaintext or tarefa.mensagem,
                        image_path=image_path,
                        usuario_id=tarefa.usuario_id,
                        filtro_estados=tarefa.filtro_estados or None,
                        filtro_cidades=tarefa.filtro_cidades or None,
                        dias_cancelamento=tarefa.dias_cancelamento or 10,
                        tarefa_id=tarefa.id,  # Controle de duplicidade por tarefa
                    )

                    duracao = int(time.time() - inicio)

                    # Determina status
                    if resultado['erros'] == 0 and resultado['enviados'] > 0:
                        status = 'sucesso'
                    elif resultado['enviados'] > 0:
                        status = 'parcial'
                    elif resultado['erros'] == 0 and resultado['ja_receberam'] > 0:
                        # Nenhum envio, nenhum erro, mas há contatos que já receberam
                        status = 'concluido'
                    else:
                        status = 'erro'

                    # Registra histórico
                    # Estrutura detalhes como objeto com chave 'erros' para compatibilidade com frontend
                    detalhes_estruturados = {
                        'erros': resultado.get('detalhes', []),
                        'total_destinatarios': resultado.get('total_destinatarios', 0),
                        'enviados': resultado['enviados'],
                        'falhas': resultado['erros'],
                        'ja_receberam': resultado.get('ja_receberam', 0)
                    }
                    HistoricoExecucaoTarefa.objects.create(
                        tarefa=tarefa,
                        status=status,
                        quantidade_enviada=resultado['enviados'],
                        quantidade_erros=resultado['erros'],
                        detalhes=json.dumps(detalhes_estruturados),
                        duracao_segundos=duracao
                    )

                    # Atualiza tarefa (marca execução como completa)
                    tarefa.execucao_completa = True
                    tarefa.ultimo_envio = agora
                    tarefa.total_envios += resultado['enviados']
                    tarefa.em_execucao = False
                    tarefa.execucao_iniciada_em = None
                    tarefa.save(update_fields=['execucao_completa', 'ultimo_envio', 'total_envios', 'em_execucao', 'execucao_iniciada_em'])

                    logger.info(
                        "TarefaEnvio concluída | tarefa_id=%d nome=%s status=%s enviados=%d erros=%d duracao=%ds",
                        tarefa.id,
                        tarefa.nome,
                        status,
                        resultado['enviados'],
                        resultado['erros'],
                        duracao
                    )

                except Exception as e:
                    # Garante que em_execucao é resetado e reverte ultimo_envio em caso de erro interno
                    tarefa.ultimo_envio = ultimo_envio_anterior
                    tarefa.execucao_completa = False
                    tarefa.em_execucao = False
                    tarefa.execucao_iniciada_em = None
                    tarefa.save(update_fields=['ultimo_envio', 'execucao_completa', 'em_execucao', 'execucao_iniciada_em'])
                    raise  # Re-lança a exceção para o handler externo

            except Exception as e:
                logger.exception(
                    "Erro ao executar TarefaEnvio | tarefa_id=%d nome=%s erro=%s",
                    tarefa.id,
                    tarefa.nome,
                    str(e)
                )
                # Garante que em_execucao é resetado e reverte ultimo_envio para permitir reexecução
                try:
                    tarefa.ultimo_envio = ultimo_envio_anterior if 'ultimo_envio_anterior' in locals() else tarefa.ultimo_envio
                    tarefa.execucao_completa = False
                    tarefa.em_execucao = False
                    tarefa.execucao_iniciada_em = None
                    tarefa.save(update_fields=['ultimo_envio', 'execucao_completa', 'em_execucao', 'execucao_iniciada_em'])
                except:
                    pass
                # Registra erro no histórico
                HistoricoExecucaoTarefa.objects.create(
                    tarefa=tarefa,
                    status='erro',
                    quantidade_enviada=0,
                    quantidade_erros=0,
                    detalhes=json.dumps({'erro': str(e)}),
                    duracao_segundos=int(time.time() - inicio) if 'inicio' in locals() else 0
                )

    except Exception as e:
        logger.exception("Erro em run_scheduled_tasks_from_db | erro=%s", str(e))


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

                # Health check ANTES de atualizar ultimo_envio
                sessao = SessaoWpp.objects.filter(usuario=h.usuario, is_active=True).first()
                if sessao and sessao.token:
                    if not verificar_saude_sessao(str(h.usuario), sessao.token):
                        logger.warning(
                            "[Health Check] Sessão com problema - envios cancelados | thread=%s usuario=%s tipo=%s",
                            threading.current_thread().name,
                            h.usuario,
                            h.tipo_envio
                        )
                        registrar_log_auditoria({
                            "funcao": "executar_envio_para_usuario",
                            "status": "cancelado_sessao_problema",
                            "usuario": str(h.usuario),
                            "tipo_envio": h.tipo_envio,
                            "thread": threading.current_thread().name,
                            "motivo": "health_check_falhou",
                        })
                        return  # ultimo_envio NÃO atualizado - permite nova tentativa

                # Guarda valor anterior para possível reversão em caso de erro
                ultimo_envio_anterior = h.ultimo_envio

                # Lock DB adquirido! Atualiza para bloquear outros processos
                h.ultimo_envio = hoje
                h.em_execucao = True
                h.execucao_iniciada_em = agora
                h.save(update_fields=['ultimo_envio', 'em_execucao', 'execucao_iniciada_em'])

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

                # Marca execução como finalizada
                h.em_execucao = False
                h.execucao_iniciada_em = None
                h.save(update_fields=['em_execucao', 'execucao_iniciada_em'])

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
                # Extrai apenas status_code e mensagem (sem HTML)
                status_code = None
                error_msg = str(exc_envio)

                if hasattr(exc_envio, 'response') and exc_envio.response is not None:
                    status_code = exc_envio.response.status_code
                    try:
                        error_data = exc_envio.response.json()
                        error_msg = error_data.get('message', error_data.get('error', str(error_data)))
                    except Exception:
                        # Sanitiza para evitar registrar HTML de páginas de erro (ex: Cloudflare 504)
                        sanitized = _sanitize_response(exc_envio.response.text)
                        if isinstance(sanitized, dict):
                            error_msg = sanitized.get('mensagem', 'Erro desconhecido')
                        else:
                            error_msg = str(sanitized)

                logger.error(
                    "Erro no envio - revertendo ultimo_envio | usuario=%s tipo=%s status_code=%s erro=%s",
                    h.usuario,
                    h.tipo_envio,
                    status_code,
                    error_msg
                )

                # Reverte ultimo_envio para permitir nova tentativa e marca execução como finalizada
                h.ultimo_envio = ultimo_envio_anterior
                h.em_execucao = False
                h.execucao_iniciada_em = None
                h.save(update_fields=['ultimo_envio', 'em_execucao', 'execucao_iniciada_em'])

                registrar_log_auditoria({
                    "funcao": "executar_envio_para_usuario",
                    "status": "erro_envio_revertido",
                    "usuario": str(h.usuario),
                    "tipo_envio": h.tipo_envio,
                    "status_code": status_code,
                    "erro": error_msg,
                    "acao": "ultimo_envio_revertido",
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

    # ============================================================
    # VERIFICAÇÃO DE TIMEOUT: Detecta notificações travadas (>2h)
    # ============================================================
    horarios_travados = HorarioEnvios.objects.filter(
        em_execucao=True,
        execucao_iniciada_em__isnull=False
    )
    for h_travado in horarios_travados:
        tempo_execucao = agora - h_travado.execucao_iniciada_em
        if tempo_execucao.total_seconds() > 7200:  # 2 horas
            logger.warning(
                "[NOTIFICACOES] HorarioEnvios travado detectado (>2h) - resetando | "
                "id=%d tipo=%s usuario_id=%d tempo=%s",
                h_travado.id, h_travado.tipo_envio, h_travado.usuario_id,
                str(tempo_execucao)
            )
            h_travado.em_execucao = False
            h_travado.execucao_iniciada_em = None
            h_travado.save(update_fields=['em_execucao', 'execucao_iniciada_em'])

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
