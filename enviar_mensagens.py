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

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Carregar as configurações do Django
django.setup()

from cadastros.models import Mensalidade, SessaoWpp

def enviar_mensagem_telefone(telefone, mensagem, usuario, token, cliente):
    url = 'http://localhost:21465/api/{}/send-message'.format(usuario)
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

    response = requests.post(url, headers=headers, json=body)

    # Verificar o status da resposta e tomar ações apropriadas, se necessário
    if response.status_code == 200 or response.status_code == 201:
        print('[USUÁRIO][{}] [CLIENTE][{}] Mensagem enviada!'.format(usuario, cliente))
    elif response.status_code == 400:
        response_data = json.loads(response.text)
        error_message = response_data.get('message')
        print('[USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] - Erro ao enviar mensagem: {}'.format(usuario, cliente, response.status_code, error_message))
    else:
        response_data = json.loads(response.text)
        error_message = response_data.get('message')
        print('[USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] - Erro ao enviar mensagem: {}'.format(usuario, cliente, response.status_code, error_message))

    # Tempo de espera aleatório entre o envio de cada mensagem com limite máximo de 60 segundos
    tempo_espera = random.uniform(15, 60)
    time.sleep(tempo_espera)


def filtrar_mensalidades_enviar_mensagens():
    # Obter a data atual
    data_atual = datetime.now().date()

    # Calcula a data daqui a 2 dias
    data_daqui_a_2_dias = data_atual + timedelta(days=2)

    # Filtrar as mensalidades
    mensalidades = Mensalidade.objects.filter(
        dt_vencimento=data_daqui_a_2_dias,
        pgto=False,
        cancelado=False
    )
    print('Mensalidades filtradas: ', mensalidades)

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
        except SessaoWpp.DoesNotExist:
            continue  # Pula para a próxima iteração caso o objeto não seja encontrado

        mensagem = """⚠️ *ATENÇÃO, {} !!!* ⚠️\n\n*A SUA MENSALIDADE VENCERÁ EM {}.*\n\n▶️ Deseja continuar com acesso ao nosso serviço?? Faça o seu pagamento até a data informada e evite a perca do acesso!\n\n▫ *PAGAMENTO COM PIX*\n\nCelular\n83993329190\nNuBank\nJorge Reis Galvão\n\n‼️ _Caso já tenha pago, por favor me envie o comprovante para confirmação e continuidade do acesso._""".format(primeiro_nome, dt_vencimento)

        enviar_mensagem_telefone(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente)


# Agendar a tarefa para ser executada diariamente às 10h
schedule.every().day.at('10:00').do(filtrar_mensalidades_enviar_mensagens)


# Loop infinito para executar as tarefas agendadas
while True:
    schedule.run_pending()
    time.sleep(1)
