import os
import re
import sys
import json
import django
import schedule
import time
import requests
import random
from datetime import datetime, timedelta
import subprocess

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Carregar as configurações do Django
django.setup()

from cadastros.models import DadosBancarios
from cadastros.models import Mensalidade, SessaoWpp

# Função para enviar mensagens e registrar em arquivo de log
def enviar_mensagem(telefone, mensagem, usuario, token, cliente):
    url = 'http://localhost:8081/api/{}/send-message'.format(usuario)
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

        # Tempo de espera aleatório entre cada tentativa com limite máximo de 50 segundos
        tempo_espera = random.uniform(20, 50)
        time.sleep(tempo_espera)


# Função para filtrar as mensalidades dos clientes a vencer
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

        mensagem = """⚠️ *ATENÇÃO, {} !!!* ⚠️\n\n*A SUA MENSALIDADE VENCERÁ EM {}.*\n\n▶️ Deseja continuar com acesso ao nosso serviço?? Faça o seu pagamento até a data informada e evite a perca do acesso!\n\n▫ *PAGAMENTO COM PIX*\n\n{}\n{}\n{}\n{}\n\n‼️ _Caso já tenha pago, por favor me envie o comprovante para confirmação e continuidade do acesso._""".format(primeiro_nome, dt_vencimento, dados_pagamento.tipo_chave, dados_pagamento.chave, dados_pagamento.instituicao, dados_pagamento.beneficiario)

        enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente)
        
        # Tempo de espera aleatório entre cada tentativa com limite máximo de 120 segundos
        tempo_espera = random.uniform(30, 120)
        time.sleep(tempo_espera)


# Função para filtrar as mensalidades dos clientes em atraso
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

        mensagem = """*{}, {} 😊*\n\n*Vejo que você ainda não renovou o seu acesso ao nosso sistema, é isso mesmo??*\n\nPara continuar usando normalmente você precisa regularizar a sua mensalidade.\n\nMe dá um retorno, por favor??""".format(saudacao, primeiro_nome)

        enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente)

        # Tempo de espera aleatório entre cada tentativa com limite máximo de 120 segundos
        tempo_espera = random.uniform(30, 120)
        time.sleep(tempo_espera)


######### BLOCO DE ENVIO DE MENSAGENS PERSONALIZADAS #########
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

        # Tempo de espera aleatório entre cada tentativa com limite máximo de 120 segundos
        tempo_espera = random.uniform(30, 120)
        time.sleep(tempo_espera)

def calcular_data_atraso(qtd_dias):
    return datetime.now().date() - timedelta(days=qtd_dias)

# Função principal para filtrar as mensalidades dos clientes cancelados entre 5 e 30 dias
def mensalidades_canceladas():
    atrasos = [
        {"dias": 4, "mensagem": "*{}, {}.* 👍🏼\n\nVimos em nosso sistema que já fazem uns dias que o seu acesso foi encerrado e gostaríamos de saber se você deseja continuar utilizando?"},
        {"dias": 16, "mensagem": "*{}, {}* 🫡\n\nTudo bem? Espero que sim.\n\nFaz um tempo que você deixou de ser nosso cliente ativo, e ficamos preocupados. Houve algo que não agradou em nosso sistema?\n\nPergunto, pois se algo não agradou, nos informe para fornecermos uma plataforma melhor para você, tá bom?\n\nEstamos à disposição! 🙏🏼"},
        {"dias": 36, "mensagem": "*Opa.. {}!! Tudo bacana?*\n\nComo você já foi nosso cliente, trago uma notícia que talvez você goste muuuiito!!\n\nVocê pode renovar a sua mensalidade conosco pagando *APENAS R$ 24.90* nos próximos 3 meses. Olha só que bacana?!?!\n\nEsse tipo de desconto não oferecemos a qualquer um, viu? rsrs\n\nCaso tenha interesse, avise aqui, pois iremos garantir essa oferta apenas essa semana. 👏🏼👏🏼"}
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
        print(f'[{datetime.now().strftime("%d-%m-%Y %H:%M:%S")}] [VENCIDAS HÁ {qtd_dias} DIAS] QUANTIDADE DE ENVIOS A SEREM FEITOS: {quantidade}')
        
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
######### FIM DO BLOCO #########


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


# Agendar a execução das funções
schedule.every().day.at("11:05").do(mensalidades_a_vencer)
schedule.every().day.at("11:05").do(mensalidades_vencidas)
schedule.every().day.at("20:00").do(mensalidades_canceladas)
schedule.every().day.at("23:59").do(backup_db_sh)

# Executar indefinidamente
while True:
    schedule.run_pending()
    time.sleep(5)

WIgC5Sf5vK5o
