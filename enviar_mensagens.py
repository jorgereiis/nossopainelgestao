import calendar
from django.shortcuts import get_object_or_404
from pathlib import os
import django

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Carregar URLs da API
url_api = os.getenv("URL_API")

# Carregar as configurações do Django
django.setup()

from cadastros.models import Mensalidade, SessaoWpp, MensagemEnviadaWpp, Cliente, DadosBancarios
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.utils import timezone
from gc import get_objects
import subprocess
import functools
import threading
import requests
import schedule
import random
import codecs
import base64
import time
import json
import sys
import os
import re


##### Função para enviar mensagens e registrar em arquivo de log
def enviar_mensagem(telefone, mensagem, usuario, token, cliente):
    url = '{}/{}/send-message'.format(url_api, usuario)
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
    log_directory = './logs/Envios agendados/'
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
                log_file.write('[{}] [TIPO][Agendado] [USUÁRIO][{}] [CLIENTE][{}] Mensagem enviada!\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), usuario, cliente))
            break  # Sai do loop se a resposta for de sucesso
        elif response.status_code == 400:
            response_data = json.loads(response.text)
            error_message = response_data.get('message')
            with open(log_filename, 'a') as log_file:
                log_file.write('[{}] [TIPO][Agendado] [USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), usuario, cliente, response.status_code, tentativa, error_message))
        else:
            print(f"[ERRO ENVIO DE MSGS] [{response.status_code}] \n [{response.text}]")
            response_data = json.loads(response.text)
            error_message = response_data.get('message')
            with open(log_filename, 'a') as log_file:
                log_file.write('[{}] [TIPO][Agendado] [USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), usuario, cliente, response.status_code, tentativa, error_message))

        # Incrementa o número de tentativas
        tentativa += 1

        # Tempo de espera aleatório entre cada tentativa com limite máximo de 30 segundos
        tempo_espera = random.uniform(20, 30)
        time.sleep(tempo_espera)
#####


##### Função para filtrar as mensalidades dos clientes a vencer
def mensalidades_a_vencer():
    # Obter a data atual
    data_atual = datetime.now().date()
    # Obter data e hora formatada
    data_hora_atual = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    # Calcula a data daqui a 2 dias
    data_daqui_a_2_dias = data_atual + timedelta(days=2)

    # Filtra os dados de pagamento do usuário
    

    # Filtrar as mensalidades
    mensalidades = Mensalidade.objects.filter(
        dt_vencimento=data_daqui_a_2_dias,
        cliente__nao_enviar_msgs=False,
        pgto=False,
        cancelado=False
    )
    quantidade_mensalidades = mensalidades.count()
    print('[{}] [A VENCER] QUANTIDADE DE ENVIOS A SEREM FEITOS: {}'.format(data_hora_atual, quantidade_mensalidades))

    # Iterar sobre as mensalidades e enviar mensagens
    for mensalidade in mensalidades:
        usuario = mensalidade.usuario
        cliente = mensalidade.cliente
        valor = mensalidade.valor
        nome_cliente = str(cliente)
        primeiro_nome = nome_cliente.split(' ')[0].upper()
        dt_vencimento = mensalidade.dt_vencimento.strftime("%d/%m")
        telefone = str(cliente.telefone)
        telefone_formatado = '55' + re.sub(r'\D', '', telefone)

        try:
            token_user = SessaoWpp.objects.get(usuario=usuario)
            dados_pagamento = DadosBancarios.objects.get(usuario=usuario)
        except SessaoWpp.DoesNotExist or DadosBancarios.DoesNotExist:
            continue  # Pula para a próxima iteração caso o objeto não seja encontrado

        mensagem = """⚠️ *ATENÇÃO, {} !!!* ⚠️\n\n*SUA MENSALIDADE VENCE EM:*\n\n💰 [{}] R$ {}\n\n_Faça o seu pagamento até a data informada e evite a perca do acesso!_\n\n▫ *PAGAMENTO COM PIX*\n\n{}\n{}\n{}\n{}\n\n‼️ _Caso já tenha pago, por favor, nos envie o comprovante para confirmação e continuidade do acesso._""".format(primeiro_nome, dt_vencimento, valor, dados_pagamento.tipo_chave, dados_pagamento.chave, dados_pagamento.instituicao, dados_pagamento.beneficiario)

        enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente)
        
        # Tempo de espera aleatório entre cada tentativa com limite máximo de 60 segundos
        tempo_espera = random.uniform(30, 60)
        time.sleep(tempo_espera)
#####


##### Função para filtrar as mensalidades dos clientes em atraso
def mensalidades_vencidas():
    # Obter a data atual
    data_atual = datetime.now().date()
    # Obter o horário atual
    hora_atual = datetime.now().time()
    # Obter data e hora formatada
    data_hora_atual = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    # Calcula a data de dois dias atrás
    data_dois_dias_atras = data_atual - timedelta(days=2)

    # Filtrar as mensalidades vencidas há dois dias
    mensalidades = Mensalidade.objects.filter(
        dt_vencimento=data_dois_dias_atras,
        cliente__nao_enviar_msgs=False,
        pgto=False,
        cancelado=False
    )
    quantidade_mensalidades = mensalidades.count()
    print('[{}] [EM ATRASO] QUANTIDADE DE ENVIOS A SEREM FEITOS: {}'.format(data_hora_atual, quantidade_mensalidades))

    # Iterar sobre as mensalidades e enviar mensagens
    for mensalidade in mensalidades:
        usuario = mensalidade.usuario
        cliente = mensalidade.cliente
        nome_cliente = str(cliente)
        primeiro_nome = nome_cliente.split(' ')[0]
        telefone = str(cliente.telefone)
        telefone_formatado = '55' + re.sub(r'\D', '', telefone)
        saudacao = ''

        # Definir a saudação de acordo com o horário atual
        if hora_atual < datetime.strptime("12:00:00", "%H:%M:%S").time():
            saudacao = 'Bom dia'
        elif hora_atual < datetime.strptime("18:00:00", "%H:%M:%S").time():
            saudacao = 'Boa tarde'
        else:
            saudacao = 'Boa noite'

        try:
            token_user = SessaoWpp.objects.get(usuario=usuario)
        except SessaoWpp.DoesNotExist:
            continue  # Pula para a próxima iteração caso o objeto não seja encontrado

        mensagem = """*{}, {} 😊*\n\n*Ainda não identificamos o pagamento da sua mensalidade para renovação.*\n\nCaso já tenha feito, envie aqui novamente o seu comprovante, por favor!""".format(saudacao, primeiro_nome)

        enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente)

        # Tempo de espera aleatório entre cada tentativa com limite máximo de 60 segundos
        tempo_espera = random.uniform(30, 60)
        time.sleep(tempo_espera)
#####


##### BLOCO DE ENVIO DE MENSAGENS PERSONALIZADAS PARA CLIENTES CANCELADOS POR QTD. DE DIAS
# Função para enviar mensagem
def enviar_mensagem_formatada(mensalidades, mensagem_template, hora_atual):
    for mensalidade in mensalidades:
        usuario = mensalidade.usuario
        cliente = mensalidade.cliente
        nome_cliente = str(cliente)
        primeiro_nome = nome_cliente.split(' ')[0]
        telefone = str(cliente.telefone)
        telefone_formatado = '55' + re.sub(r'\D', '', telefone)

        # Definir a saudação de acordo com o horário atual
        if hora_atual < datetime.strptime("12:00:00", "%H:%M:%S").time():
            saudacao = 'Bom dia'
        elif hora_atual < datetime.strptime("18:00:00", "%H:%M:%S").time():
            saudacao = 'Boa tarde'
        else:
            saudacao = 'Boa noite'

        try:
            token_user = SessaoWpp.objects.get(usuario=usuario)
        except SessaoWpp.DoesNotExist:
            continue  # Pula para a próxima iteração caso o objeto não seja encontrado

        mensagem = mensagem_template.format(saudacao, primeiro_nome)

        enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente)

        # Tempo de espera aleatório entre cada tentativa com limite máximo de 60 segundos
        tempo_espera = random.uniform(30, 60)
        time.sleep(tempo_espera)
#####


#####
def calcular_data_atraso(qtd_dias):
    return datetime.now().date() - timedelta(days=qtd_dias)
#####


##### Função principal para filtrar as mensalidades dos clientes cancelados entre 3 e 35 dias
def mensalidades_canceladas():
    atrasos = [
        {"dias": 3, "mensagem": "*{}, {}.* 👍🏼\n\nVimos em nosso sistema que já fazem uns dias que o seu acesso foi encerrado e gostaríamos de saber se você deseja continuar utilizando?"},
        {"dias": 15, "mensagem": "*{}, {}* 🫡\n\nTudo bem? Espero que sim.\n\nFaz um tempo que você deixou de ser nosso cliente ativo, e ficamos preocupados. Houve algo que não agradou em nosso sistema?\n\nPergunto, pois se algo não agradou, nos informe para fornecermos uma plataforma melhor para você, tá bom?\n\nEstamos à disposição! 🙏🏼"},
        {"dias": 35, "mensagem": "*Opa.. {}!! Tudo bacana?*\n\nComo você já foi nosso cliente, trago uma notícia que talvez você goste muuuiito!!\n\nVocê pode renovar a sua mensalidade conosco pagando *APENAS R$ 24.90* nos próximos 3 meses. Olha só que bacana?!?!\n\nEsse tipo de desconto não oferecemos a qualquer um, viu? rsrs\n\nCaso tenha interesse, avise aqui, pois iremos garantir essa oferta apenas essa semana. 👏🏼👏🏼"}
    ]

    for atraso in atrasos:
        qtd_dias = atraso["dias"]
        mensagem_template = atraso["mensagem"]

        data_atraso = calcular_data_atraso(qtd_dias)
        mensalidades = Mensalidade.objects.filter(
            cliente__cancelado=True,
            cliente__nao_enviar_msgs=False,
            dt_cancelamento=data_atraso,
            pgto=False,
            cancelado=True,
            notificacao_wpp1=False
        )

        quantidade = mensalidades.count()
        print(f'[{datetime.now().strftime("%d-%m-%Y %H:%M:%S")}] [CANCELADAS HÁ {qtd_dias} DIAS] QUANTIDADE DE ENVIOS A SEREM FEITOS: {quantidade}')
        
        if quantidade > 0:
            enviar_mensagem_formatada(mensalidades, mensagem_template, datetime.now().time())
            if qtd_dias > 30:
                for mensalidade in mensalidades:
                    try:
                        mensalidade.notificacao_wpp1 = True
                        mensalidade.dt_notif_wpp1 = datetime.now()
                        mensalidade.save()
                        print(f"[ENVIO PROMO REALIZADO] {mensalidade.cliente.nome} - [DT CANCEL] {mensalidade.dt_cancelamento}")
                    except Exception as e:
                        print(f"[ERROR] Erro ao salvar Mensalidade ID {mensalidade.id}: {e}")
        else:
            print(f"Nenhum envio realizado para mensalidades vencidas há {qtd_dias} dias")
##### FIM


##### BLOCO PARA ENVIO DE MENSAGENS AOS CLIENTES ATIVOS, CANCELADOS E FUTUROS CLIENTES (AVULSO)
def wpp_msg_ativos(type, image_name, message):
    tipo_envio = str(type)
    BASE_URL = url_api + '/{}/send-{}'
    mensagem = message
    image_base64 = get_img_base64(image_name, tipo_envio)
    usuario = User.objects.get(id=1)
    sessao = get_object_or_404(SessaoWpp, usuario=usuario)
    token = sessao.token
    log_directory = './logs/Envios agendados/'
    log_filename = os.path.join(log_directory, f'{usuario}.log')
    log_send_result_filename = os.path.join(log_directory, f'{usuario}_send_result.log')
    clientes = None

    def send_wpp_msg_actives(url, telefone):
        # Verificar se já enviou uma mensagem para este telefone hoje
        if MensagemEnviadaWpp.objects.filter(usuario=usuario, telefone=telefone, data_envio=timezone.now().date()).exists():
            # Verificar se o diretório de logs existe e criar se necessário
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)
            # Verificar se o arquivo de log existe e criar se necessário
            if not os.path.isfile(log_send_result_filename):
                open(log_send_result_filename, 'w').close()
            # Escrever no arquivo de log
            with codecs.open(log_send_result_filename, 'a', encoding='utf-8') as log_file:
                log_file.write('[{}] {} - ⚠️ Já foi feito envio hoje!\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), telefone))

        else:
            # Prossegue com o envio da mensagem
            if not telefone.startswith('55'):
                telefone = '55' + telefone

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': 'Bearer ' + token
            }
            body = {
                'phone': telefone,
                'isGroup': False,
                'message': mensagem
            }

            if image_name:
                body['filename'] = image_name
                body['caption'] = mensagem
                body['base64'] = 'data:image/png;base64,' + image_base64

            max_attempts = 3
            attempts = 1
            while attempts <= max_attempts:
                if attempts == 2:
                    # Tratando o telefone como padrão Brasileiro para remover o dígito '9' e tentar fazer novo envio
                    tel = telefone
                    if tel.startswith('55'):
                        ddi = tel[:2]
                        ddd = tel[2:4]
                        tel = tel[4:]
                        # Remove o dígito '9' se o telefone tiver 9 dígitos
                        if len(tel) == 9 and tel.startswith('9'):
                            tel = tel[1:]
                            body['phone'] = ddi + ddd + tel
                
                if attempts == 3:
                    # Tratando o telefone como padrão Internacional, revomendo apenas os dígitos '55'
                    tel = telefone
                    if tel.startswith('55'):
                        tel = tel[2:]
                        body['phone'] = tel

                response = requests.post(url, headers=headers, json=body)

                if response.status_code == 200 or response.status_code == 201:
                    # Verificar se o diretório de logs existe e criar se necessário
                    if not os.path.exists(log_directory):
                        os.makedirs(log_directory)
                    if not os.path.exists(log_directory):
                        os.makedirs(log_directory)
                    # Verificar se o arquivo de log existe e criar se necessário
                    if not os.path.isfile(log_filename):
                        open(log_filename, 'w').close()
                    if not os.path.isfile(log_send_result_filename):
                        open(log_send_result_filename, 'w').close()
                    # Escrever no arquivo de log
                    with open(log_filename, 'a') as log_file:
                        log_file.write('[{}] [TIPO][{}] [USUÁRIO][{}] [TELEFONE][{}] Mensagem enviada!\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), tipo_envio.upper(), usuario, telefone))
                    with codecs.open(log_send_result_filename, 'a', encoding='utf-8') as log_file:
                        log_file.write('[{}] {} - ✅ Mensagem enviada\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), telefone))
                    # Registrar o envio da mensagem para o dia atual
                    if telefone.startswith('55'):
                        telefone=telefone[2:]
                    MensagemEnviadaWpp.objects.create(usuario=usuario, telefone=telefone)
                    time.sleep(random.uniform(30, 60))
                    break
                else:
                    if attempts <= max_attempts:
                        time.sleep(random.uniform(10, 20))
                    # Verificar se o diretório de logs existe e criar se necessário
                    if not os.path.exists(log_directory):
                        os.makedirs(log_directory)
                    # Verificar se o arquivo de log existe e criar se necessário
                    if not os.path.isfile(log_filename):
                        open(log_filename, 'w').close()
                    # Escrever no arquivo de log
                    with open(log_filename, 'a') as log_file:
                        response_data={}
                        try:
                            response_data = json.loads(response.text)
                        except json.decoder.JSONDecodeError as e:
                            error_message = response_data.get('message') if response_data.get('message') else str(e)
                            log_file.write('[{}] [TIPO][{}] [USUÁRIO][{}] [TELEFONE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), tipo_envio.upper(), usuario, telefone, response.status_code, attempts, error_message))

                    attempts += 1

                if attempts == max_attempts:
                    # Verificar se o diretório de logs existe e criar se necessário
                    if not os.path.exists(log_directory):
                        os.makedirs(log_directory)
                    # Verificar se o arquivo de log existe e criar se necessário
                    if not os.path.isfile(log_send_result_filename):
                        open(log_send_result_filename, 'w').close()
                    # Escrever no arquivo de log
                    with codecs.open(log_send_result_filename, 'a', encoding='utf-8') as log_file:
                        log_file.write('[{}] {} - ❌ Não enviada (consultar log)\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), telefone))

    if tipo_envio == 'ativos':
        clientes = Cliente.objects.filter(usuario=usuario, cancelado=False, nao_enviar_msgs=False)
        telefones = ','.join([re.sub(r'\s+|\W', '', cliente.telefone) for cliente in clientes])

    elif tipo_envio == 'cancelados':
        clientes = Cliente.objects.filter(usuario=usuario, cancelado=True, data_cancelamento__lte=timezone.now()-timedelta(days=40), nao_enviar_msgs=False)
        telefones = ','.join([re.sub(r'\s+|\W', '', cliente.telefone) for cliente in clientes])

    elif tipo_envio == 'avulso':
        telefones = process_telefones_from_file(tipo_envio)

    if clientes is not None:
        # Preparar a URL para o envio
        url = BASE_URL.format(usuario, 'image' if image_name else 'message')

        print(f'[{datetime.now().strftime("%d-%m-%Y %H:%M:%S")}] [ENVIO][{tipo_envio.upper()}] [QTD.][{clientes.count()}]')

        for cliente in clientes:
            telefone_limpo = re.sub(r'\s+|\W', '', cliente.telefone)
            

            send_wpp_msg_actives(url, telefone_limpo)

    elif telefones:
        # Dividir os telefones em uma lista
        lista_telefones = telefones.split(',')

        # Calcular a quantidade de telefones
        quantidade = len(lista_telefones)

        # Preparar a URL para o envio
        url = BASE_URL.format(usuario, 'image' if image_name else 'message')

        print(f'[{datetime.now().strftime("%d-%m-%Y %H:%M:%S")}] [ENVIO][[{tipo_envio.upper()}]] [QTD.][{quantidade}]')

        # Loop para realizar os envios e imprimir a quantidade
        for telefone in lista_telefones:
            telefone_limpo = re.sub(r'\s+|\W', '', telefone)

            # Enviar mensagem para o telefone
            send_wpp_msg_actives(url, telefone_limpo)



def get_img_base64(image_name, sub_directory):
    # Caminho do diretório onde as imagens estão localizadas
    image_path = os.path.join(os.path.dirname(__file__), f'images\{sub_directory}', image_name)

    try:
        # Abrir a imagem e ler o conteúdo como binário
        with open(image_path, 'rb') as image_file:
            # Codificar a imagem em base64
            encoded_image = base64.b64encode(image_file.read())
            # Converter para string utf-8 e retornar
            return encoded_image.decode('utf-8')
    except Exception as e:
        print(f"Erro ao tentar abrir o arquivo de IMAGEM: {e}")
        return None


def process_telefones_from_file(sub_directory):
    # Caminho do diretório onde o arquivo "telefones" está localizado
    telefones_path = os.path.join(os.path.dirname(__file__), f'archives\{sub_directory}', 'telefones.txt')

    try:
        # Abrir e ler o arquivo
        with open(telefones_path, 'r', encoding='utf-8') as telefones_file:
            telefones_data = telefones_file.read().split('\n')
            
            # Processar os números de telefone
            telefones = ','.join([
                re.sub(r'\s+|\W', '', telefone) 
                for telefone in telefones_data if telefone.strip()
            ])
            return telefones
    except Exception as e:
        print(f"Erro ao tentar abrir o arquivo de TELEFONES: {e}")
        return None


def get_message_from_file(file_name, sub_directory):
    # Caminho do diretório onde o arquivo "msg" está localizado
    file_path = os.path.join(os.path.dirname(__file__), f'archives\{sub_directory}', file_name)

    try:
        # Abrir e ler o arquivo
        with open(file_path, 'r', encoding='utf-8') as message_file:
            message = message_file.read()
            return message
    except Exception as e:
        print(f"Erro ao tentar abrir o arquivo de MENSAGEM: {e}")
        return None
##### FIM


# Função para executar o script de backup do "db.sqlite3" para o diretório do Drive.
def backup_db_sh():
    # Obter a data e hora atual formatada
    data_hora_atual = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    # Caminho para o script de backup
    caminho_arquivo_sh = './backup_db.sh'

    # Executar o script de backup
    resultado = subprocess.run(['sh', caminho_arquivo_sh], capture_output=True, text=True)
    
    # Verificar o resultado da execução do script
    if resultado.returncode == 0:
        print('[{}] [BACKUP DIÁRIO] Backup do DB realizado.'.format(data_hora_atual))
    else:
        print('[{}] [BACKUP DIÁRIO] Falha durante backup do DB.'.format(data_hora_atual))
        print('Erro: ', resultado.stderr)
##### FIM


##### FUNÇÃO PARA EXECUTAR TAREFAS AGENDADAS PARA ENVIO DE MENSAGENS
def run_scheduled_tasks():
    try:
        # Função para encontrar o segundo sábado do mês
        def get_second_saturday(year, month):
            # Primeiro dia do mês
            first_day = datetime(year, month, 1)
            # Calcula o primeiro sábado (weekday() == 5 indica sábado)
            first_saturday = first_day + timedelta(days=(5 - first_day.weekday()) % 7)
            # Segundo sábado é 7 dias após o primeiro sábado
            second_saturday = first_saturday + timedelta(days=7)
            return second_saturday.day
        
        # Função para encontrar o último sábado do mês
        def get_last_saturday(year, month):
            # Último dia do mês
            last_day_of_month = calendar.monthrange(year, month)[1]
            last_day = datetime(year, month, last_day_of_month)
            # Calcula o último sábado
            last_saturday = last_day - timedelta(days=(last_day.weekday() - 5) % 7)
            return last_saturday.day

        # Obter o dia da semana, mês e ano
        current_day = datetime.now().day
        current_weekday = datetime.now().strftime('%A')
        year = datetime.now().year
        month = datetime.now().month

        # Inicializar variáveis
        type_schedule = None
        img_schedule = None
        msg_schedule = None

        # Calcular o segundo e o último sábado do mês
        second_saturday = get_second_saturday(year, month)
        last_saturday = get_last_saturday(year, month)

        if current_weekday == "Saturday":
            type_schedule = "ativos"
            img_schedule = 'img1.png'

            # Verifica se é o segundo ou o último sábado do mês
            if current_day == second_saturday:
                msg_schedule = get_message_from_file('msg1.txt', type_schedule)
            elif current_day == last_saturday:
                msg_schedule = get_message_from_file('msg2.txt', type_schedule)

        elif current_weekday == "Wednesday":
            type_schedule = "avulso"
            
            if current_day in range(1, 11):
                img_schedule = 'img2-1.png'
                msg_schedule = get_message_from_file('msg2-1.txt', type_schedule)
            elif current_day in range(11, 21):
                img_schedule = 'img2-2.png'
                msg_schedule = get_message_from_file('msg2-2.txt', type_schedule)
            elif current_day in range(21, 32):
                img_schedule = 'img2-3.png'
                msg_schedule = get_message_from_file('msg2-3.txt', type_schedule)

        elif current_weekday == "Monday":
            type_schedule = "cancelados"

            if current_day in range(1, 11):
                img_schedule = 'img3-1.png'
                msg_schedule = get_message_from_file('msg3-1.txt', type_schedule)
            elif current_day in range(11, 21):
                img_schedule = 'img3-2.png'
                msg_schedule = get_message_from_file('msg3-2.txt', type_schedule)
            elif current_day in range(21, 32):
                img_schedule = 'img3-3.png'
                msg_schedule = get_message_from_file('msg3-3.txt', type_schedule)

        # Verifica se todas as variáveis foram corretamente definidas e executa a função agendada
        if type_schedule and img_schedule and msg_schedule:
            envio_avulso = functools.partial(wpp_msg_ativos, type_schedule, img_schedule, msg_schedule)
            envio_avulso()
        else:
            print(f'[{datetime.now().strftime("%d-%m-%Y %H:%M:%S")}] [ENVIO] Não há envios para hoje.')

    except Exception as e:
        print(f"Erro durante a execução de [run_scheduled_tasks()]: {str(e)}")
##### FIM


##### Threading para executar os jobs em paralelo
def run_threaded(job):
    job_thread = threading.Thread(target=job)
    job_thread.start()


##### Agendar a execução das tarefas
schedule.every().day.at("10:00").do(
    run_threaded, run_scheduled_tasks
)
schedule.every().day.at("16:00").do(
    run_threaded, mensalidades_a_vencer
)
schedule.every().day.at("16:30").do(
    run_threaded, mensalidades_vencidas
)
schedule.every().day.at("17:00").do(
    run_threaded, mensalidades_canceladas
)
schedule.every(60).minutes.do(
    run_threaded, backup_db_sh
)
#####


##### Executar indefinidamente
while True:
    schedule.run_pending()
    time.sleep(5)

WIgC5Sf5vK5o
qFkhEYfzGUQ5
