import os
import json
import re
import time
import codecs
import base64
import random
import calendar
import requests
import functools
import subprocess
from datetime import datetime, timedelta
from django.utils.timezone import localtime

import django
from django.utils import timezone
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from cadastros.utils import (
    validar_numero_whatsapp,
    get_saudacao_por_hora,
    registrar_log,
)

from cadastros.models import (
    Mensalidade, SessaoWpp, MensagemEnviadaWpp,
    Cliente, DadosBancarios
)

# Configuração do Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

URL_API_WPP = os.getenv("URL_API_WPP")
DIR_LOGS_AGENDADOS = os.getenv("DIR_LOGS_AGENDADOS")
DIR_LOGS_INDICACOES = os.getenv("DIR_LOGS_INDICACOES")
TEMPLATE_LOG_MSG_SUCESSO = os.getenv("TEMPLATE_LOG_MSG_SUCESSO")
TEMPLATE_LOG_MSG_FALHOU = os.getenv("TEMPLATE_LOG_MSG_FALHOU")
TEMPLATE_LOG_TELEFONE_INVALIDO = os.getenv("TEMPLATE_LOG_TELEFONE_INVALIDO")


##################################################################
################ FUNÇÃO PARA ENVIAR MENSAGENS ####################
##################################################################

def enviar_mensagem(telefone: str, mensagem: str, usuario: str, token: str, cliente: str, tipo_envio: str) -> None:
    """
    Envia uma mensagem via API WPP para um número validado.
    Registra logs de sucesso, falha e número inválido.
    """
    telefone_validado = validar_numero_whatsapp(telefone, token)
    timestamp = localtime().strftime('%Y-%m-%d %H:%M:%S')

    if not telefone_validado:
        log = TEMPLATE_LOG_TELEFONE_INVALIDO.format(
            timestamp, tipo_envio.upper(), usuario, cliente
        )
        registrar_log(log, usuario, DIR_LOGS_AGENDADOS)
        print(log.strip())
        return

    url = f"{URL_API_WPP}/{usuario}/send-message"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    for tentativa in range(1, 3):
        body = {
            'phone': telefone_validado,
            'message': mensagem,
            'isGroup': False
        }

        try:
            response = requests.post(url, headers=headers, json=body)
            timestamp = localtime().strftime('%Y-%m-%d %H:%M:%S')

            if response.status_code in (200, 201):
                log = TEMPLATE_LOG_MSG_SUCESSO.format(
                    timestamp, tipo_envio.upper(), usuario, telefone_validado
                )
                registrar_log(log, usuario, DIR_LOGS_AGENDADOS)
                break

            # Tentativa com erro
            response_data = response.json()
            error_message = response_data.get('message', 'Erro desconhecido')

        except (requests.RequestException, json.JSONDecodeError) as e:
            error_message = str(e)

        log = TEMPLATE_LOG_MSG_FALHOU.format(
            timestamp, tipo_envio.upper(), usuario, cliente,
            response.status_code if 'response' in locals() else 'N/A',
            tentativa, error_message
        )
        registrar_log(log, usuario, DIR_LOGS_AGENDADOS)
        time.sleep(random.uniform(20, 30))
##### FIM #####


#####################################################################
##### FUNÇÃO PARA FILTRAR AS MENSALIDADES DOS CLIENTES A VENCER #####
#####################################################################

def obter_mensalidades_a_vencer():
    """
    Verifica mensalidades com vencimento em 2 dias e envia mensagem de aviso via WhatsApp.
    Apenas clientes ativos e com número de telefone válido receberão mensagem.
    """
    data_referencia = timezone.now().date() + timedelta(days=2)
    horario_log = timezone.now().strftime("%d-%m-%Y %H:%M:%S")

    mensalidades = Mensalidade.objects.filter(
        dt_vencimento=data_referencia,
        cliente__nao_enviar_msgs=False,
        pgto=False,
        cancelado=False
    )

    quantidade = mensalidades.count()
    print(f"[{horario_log}] [A VENCER] QUANTIDADE DE ENVIOS A SEREM FEITOS: {quantidade}")

    for mensalidade in mensalidades:
        usuario = mensalidade.usuario
        cliente = mensalidade.cliente
        plano_nome = cliente.plano.nome.upper()
        

        telefone = str(cliente.telefone).strip()
        if not telefone:
            print(f"[AVISO] Cliente '{cliente}' sem telefone cadastrado. Pulando...")
            continue

        primeiro_nome = cliente.nome.split()[0].upper()
        dt_formatada = mensalidade.dt_vencimento.strftime("%d/%m")

        # Tenta buscar sessão ativa e dados bancários do usuário
        try:
            sessao = SessaoWpp.objects.get(usuario=usuario)
        except SessaoWpp.DoesNotExist:
            print(f"[ERRO] Sessão WPP não encontrada para '{usuario}'. Pulando...")
            continue

        try:
            dados = DadosBancarios.objects.get(usuario=usuario)
        except DadosBancarios.DoesNotExist:
            print(f"[ERRO] Dados bancários não encontrados para '{usuario}'. Pulando...")
            continue

        # Mensagem a ser enviada
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
            f"‼️ _Caso já tenha pago, por favor, nos envie o comprovante para confirmação._"
        )

        # Envio da mensagem
        enviar_mensagem(
            telefone=telefone,
            mensagem=mensagem,
            usuario=usuario,
            token=sessao.token,
            cliente=cliente.nome,
            tipo_envio="A vencer"
        )

        # Intervalo aleatório entre envios
        time.sleep(random.uniform(30, 60))
##### FIM #####


######################################################################
##### FUNÇÃO PARA FILTRAR AS MENSALIDADES DOS CLIENTES EM ATRASO #####
######################################################################

def obter_mensalidades_vencidas():
    """
    Verifica mensalidades vencidas há 2 dias e envia mensagens de lembrete via WhatsApp.
    """
    data_referencia = timezone.now().date() - timedelta(days=2)
    horario_log = timezone.now().strftime("%d-%m-%Y %H:%M:%S")
    hora_atual = timezone.now().time()

    mensalidades = Mensalidade.objects.filter(
        dt_vencimento=data_referencia,
        cliente__nao_enviar_msgs=False,
        pgto=False,
        cancelado=False
    )

    quantidade = mensalidades.count()
    print(f"[{horario_log}] [EM ATRASO] QUANTIDADE DE ENVIOS A SEREM FEITOS: {quantidade}")

    for mensalidade in mensalidades:
        usuario = mensalidade.usuario
        cliente = mensalidade.cliente

        telefone = str(cliente.telefone).strip()
        if not telefone:
            print(f"[AVISO] Cliente '{cliente}' sem telefone cadastrado. Pulando...")
            continue

        primeiro_nome = cliente.nome.split()[0]
        saudacao = get_saudacao_por_hora(hora_atual)

        try:
            sessao = SessaoWpp.objects.get(usuario=usuario)
        except SessaoWpp.DoesNotExist:
            print(f"[ERRO] Sessão WPP não encontrada para '{usuario}'. Pulando...")
            continue

        mensagem = (
            f"*{saudacao}, {primeiro_nome} 😊*\n\n"
            f"*Ainda não identificamos o pagamento da sua mensalidade para renovação.*\n\n"
            f"Caso já tenha feito, envie aqui novamente o seu comprovante, por favor!"
        )

        enviar_mensagem(
            telefone=telefone,
            mensagem=mensagem,
            usuario=usuario,
            token=sessao.token,
            cliente=cliente.nome,
            tipo_envio="Vencidas"
        )

        time.sleep(random.uniform(30, 60))
##### FIM #####


################################################################################################
##### BLOCO DE ENVIO DE MENSAGENS PERSONALIZADAS PARA CLIENTES CANCELADOS POR QTD. DE DIAS #####
################################################################################################

def mensalidades_canceladas():
    """
    Envia mensagens personalizadas para clientes cancelados há X dias,
    utilizando a lógica de saudação e validando número antes do envio.
    """
    atrasos = [
        {
            "dias": 5,
            "mensagem": "*{}, {}.* 👍🏼\n\nVimos em nosso sistema que já fazem uns dias que o seu acesso foi encerrado e gostaríamos de saber se você deseja continuar utilizando?"
        },
        {
            "dias": 15,
            "mensagem": "*{}, {}* 🫡\n\nTudo bem? Espero que sim.\n\nFaz um tempo que você deixou de ser nosso cliente ativo, e ficamos preocupados. Houve algo que não agradou em nosso sistema?\n\nPergunto, pois se algo não agradou, nos informe para fornecermos uma plataforma melhor para você, tá bom?\n\nEstamos à disposição! 🙏🏼"
        },
        {
            "dias": 45,
            "mensagem": "*Opa.. {}!! Tudo bacana?*\n\nComo você já foi nosso cliente, trago uma notícia que talvez você goste muuuiito!!\n\nVocê pode renovar a sua mensalidade conosco pagando *APENAS R$ 24.90* nos próximos 3 meses. Olha só que bacana?!?!\n\nEsse tipo de desconto não oferecemos a qualquer um, viu? rsrs\n\nCaso tenha interesse, avise aqui, pois iremos garantir essa oferta apenas essa semana. 👏🏼👏🏼"
        }
    ]

    for atraso in atrasos:
        qtd_dias = atraso["dias"]
        mensagem_template = atraso["mensagem"]

        data_alvo = timezone.now().date() - timedelta(days=qtd_dias)

        mensalidades = Mensalidade.objects.filter(
            cliente__cancelado=True,
            cliente__nao_enviar_msgs=False,
            cliente__enviado_oferta_promo=False,
            dt_cancelamento=data_alvo,
            pgto=False,
            cancelado=True,
            notificacao_wpp1=False
        )

        qtd = mensalidades.count()
        print(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] [CANCELADAS HÁ {qtd_dias} DIAS] QUANTIDADE DE ENVIOS A SEREM FEITOS: {qtd}")

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
                sessao = SessaoWpp.objects.get(usuario=usuario)
            except SessaoWpp.DoesNotExist:
                print(f"[ERRO] Sessão WPP não encontrada para '{usuario}'. Pulando...")
                continue

            enviar_mensagem(
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
                dt_notif_wpp1=timezone.now()
            )

            Cliente.objects.filter(mensalidade__id__in=ids).update(enviado_oferta_promo=True)

            print(f"[ENVIO PROMO REALIZADO] {qtd} clientes atualizados para 'enviado_oferta_promo = True'")
##### FIM #####


#####################################################################################################
##### BLOCO PARA ENVIO DE MENSAGENS AOS CLIENTES ATIVOS, CANCELADOS E FUTUROS CLIENTES (AVULSO) #####
#####################################################################################################

def wpp_msg_ativos(tipo_envio: str, image_name: str, message: str) -> None:
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
    sessao = get_object_or_404(SessaoWpp, usuario=usuario)
    token = sessao.token

    url_envio = f"{URL_API_WPP}/{usuario}/send-{'image' if image_name else 'message'}"
    image_base64 = get_img_base64(image_name, tipo_envio) if image_name else None

    log_path_result = os.path.join(DIR_LOGS_AGENDADOS, f'{usuario}_send_result.log')

    # Obtenção dos números com base no tipo
    if tipo_envio == 'ativos':
        clientes = Cliente.objects.filter(usuario=usuario, cancelado=False, nao_enviar_msgs=False)
        numeros = [cliente.telefone for cliente in clientes]
    elif tipo_envio == 'cancelados':
        clientes = Cliente.objects.filter(
            usuario=usuario,
            cancelado=True,
            nao_enviar_msgs=False,
            data_cancelamento__lte=timezone.now() - timedelta(days=40)
        )
        numeros = [cliente.telefone for cliente in clientes]
    elif tipo_envio == 'avulso':
        numeros = process_telefones_from_file(tipo_envio).split(',') if process_telefones_from_file(tipo_envio) else []
    else:
        print(f"[ERRO] Tipo de envio desconhecido: {tipo_envio}")
        return

    print(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] [ENVIO][{tipo_envio.upper()}] [QTD.][{len(numeros)}]")

    for telefone in numeros:
        numero_limpo = validar_numero_whatsapp(telefone, token)

        # Evita envio duplicado no mesmo dia
        if MensagemEnviadaWpp.objects.filter(usuario=usuario, telefone=numero_limpo, data_envio=timezone.now().date()).exists():
            registrar_log(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] {numero_limpo} - ⚠️ Já foi feito envio hoje!", usuario, DIR_LOGS_AGENDADOS)
            continue

        telefone_validado = numero_limpo
        if not telefone_validado:
            log = TEMPLATE_LOG_TELEFONE_INVALIDO.format(localtime().strftime('%Y-%m-%d %H:%M:%S'), tipo_envio.upper(), usuario, numero_limpo)
            registrar_log(log, usuario, DIR_LOGS_AGENDADOS)
            continue

        payload = {
            'phone': telefone_validado,
            'isGroup': False,
            'message': message
        }

        if image_base64:
            payload['filename'] = image_name
            payload['caption'] = message
            payload['base64'] = f'data:image/png;base64,{image_base64}'

        for tentativa in range(1, 4):
            response = requests.post(url_envio, headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {token}'
            }, json=payload)

            timestamp = localtime().strftime('%Y-%m-%d %H:%M:%S')

            if response.status_code in (200, 201):
                registrar_log(TEMPLATE_LOG_MSG_SUCESSO.format(timestamp, tipo_envio.upper(), usuario, telefone_validado), usuario, DIR_LOGS_AGENDADOS)
                registrar_log(f"[{timestamp}] {telefone_validado} - ✅ Mensagem enviada", usuario, DIR_LOGS_AGENDADOS)
                MensagemEnviadaWpp.objects.create(usuario=usuario, telefone=telefone_validado[2:] if telefone_validado.startswith('55') else telefone_validado)
                break

            try:
                response_data = response.json()
                error_message = response_data.get('message', 'Erro desconhecido')
            except json.JSONDecodeError:
                error_message = response.text

            registrar_log(
                TEMPLATE_LOG_MSG_FALHOU.format(timestamp, tipo_envio.upper(), usuario, telefone_validado, response.status_code, tentativa, error_message),
                usuario, DIR_LOGS_AGENDADOS
            )
            time.sleep(random.uniform(10, 20))

        time.sleep(random.uniform(30, 60))


def get_img_base64(image_name: str, sub_directory: str) -> str:
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


def process_telefones_from_file(sub_directory: str) -> str:
    """
    Lê o arquivo 'telefones.txt' do diretório /archives/{sub_directory} e retorna os números limpos.

    Args:
        sub_directory (str): Nome do subdiretório (e.g. 'avulso').

    Returns:
        str: String de telefones separados por vírgula.
    """
    telefones_path = os.path.join(os.path.dirname(__file__), f'../archives/{sub_directory}', 'telefones.txt')

    try:
        with open(telefones_path, 'r', encoding='utf-8') as f:
            telefones = f.read().split('\n')
            return ','.join([re.sub(r'\s+|\W', '', t) for t in telefones if t.strip()])
    except Exception as e:
        print(f"[ERRO] Ao abrir arquivo de telefones: {e}")
        return None


def get_message_from_file(file_name: str, sub_directory: str) -> str:
    """
    Lê o conteúdo de um arquivo de mensagem localizado em /archives/{sub_directory}.

    Args:
        file_name (str): Nome do arquivo de mensagem (e.g. 'msg1.txt').
        sub_directory (str): Nome da pasta onde o arquivo está.

    Returns:
        str: Conteúdo da mensagem ou None se erro.
    """
    file_path = os.path.join(os.path.dirname(__file__), f'../archives/{sub_directory}', file_name)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"[ERRO] Ao abrir arquivo de mensagem: {e}")
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
        mensagem = None

        if dia_semana == "Saturday":
            tipo = "ativos"
            imagem = "img1.png"
            if dia == second_saturday:
                mensagem = get_message_from_file("msg1.txt", tipo)
            elif dia == last_saturday:
                mensagem = get_message_from_file("msg2.txt", tipo)

        elif dia_semana in ["Wednesday", "Sunday"]:
            tipo = "avulso"
            if 1 <= dia <= 10:
                imagem, nome_msg = "img2-1.png", "msg2-1.txt"
            elif 11 <= dia <= 20:
                imagem, nome_msg = "img2-2.png", "msg2-2.txt"
            elif dia >= 21:
                imagem, nome_msg = "img2-3.png", "msg2-3.txt"
            else:
                nome_msg = None

            if nome_msg:
                mensagem = get_message_from_file(nome_msg, tipo)

        elif dia_semana == "Monday":
            tipo = "cancelados"
            if 1 <= dia <= 10:
                imagem, nome_msg = "img3-1.png", "msg3-1.txt"
            elif 11 <= dia <= 20:
                imagem, nome_msg = "img3-2.png", "msg3-2.txt"
            elif dia >= 21:
                imagem, nome_msg = "img3-3.png", "msg3-3.txt"
            else:
                nome_msg = None

            if nome_msg:
                mensagem = get_message_from_file(nome_msg, tipo)

        # Execução final do envio
        if tipo and imagem and mensagem:
            print(f"[{now.strftime('%d-%m-%Y %H:%M:%S')}] [TAREFA] Executando envio programado para {tipo.upper()}")
            wpp_msg_ativos(tipo_envio=tipo, image_name=imagem, message=mensagem)
        else:
            print(f"[{now.strftime('%d-%m-%Y %H:%M:%S')}] [TAREFA] Nenhum envio agendado para hoje.")

    except Exception as e:
        print(f"[ERRO] run_scheduled_tasks(): {str(e)}")
##### FIM #####


##############################################################################################
##### FUNÇÃO PARA EXECUTAR O SCRIPT DE BACKUP DO "DB.SQLITE3" PARA O DIRETÓRIO DO DRIVE. #####
##############################################################################################

def backup_db_sh():
    """
    Executa o script 'backup_db.sh' para realizar backup do banco SQLite.
    """
    # Obter a data e hora atual formatada
    data_hora_atual = localtime().strftime('%Y-%m-%d %H:%M:%S')

    # Caminho para o script de backup
    caminho_arquivo_sh = 'backup_db.sh'

    # Executar o script de backup
    resultado = subprocess.run(['sh', caminho_arquivo_sh], capture_output=True, text=True)
    
    # Verificar o resultado da execução do script
    if resultado.returncode == 0:
        print('[{}] [BACKUP DIÁRIO] Backup do DB realizado.'.format(data_hora_atual))
    else:
        print('[{}] [BACKUP DIÁRIO] Falha durante backup do DB.'.format(data_hora_atual))
        print('Erro: ', resultado.stderr)
        
    time.sleep(random.randint(10, 20))
##### FIM #####