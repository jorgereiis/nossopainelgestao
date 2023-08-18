from .models import (Cliente, Servidor, Dispositivo, Aplicativo, Tipos_pgto, Plano, Qtd_tela, Mensalidade, ContaDoAplicativo, SessaoWpp, SecretTokenAPI, DadosBancarios, HorarioEnvios)
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.deletion import ProtectedError
from django.core.exceptions import ValidationError
from django.contrib.auth.views import LoginView
from django.views.generic.list import ListView
from django.forms.models import model_to_dict
from django.contrib.auth.models import User
from babel.numbers import format_currency
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import render
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from django.db.models import Q
from datetime import timedelta
from datetime import datetime
from django.views import View
from .forms import LoginForm
import pandas as pd
import requests
import operator
import logging
import random
import base64
import json
import time
import re
import os

logger = logging.getLogger(__name__)

############################################ WPP VIEW ############################################

# VIEW PARA REALIZAR O ENVIO AUTOMÁTICO DAS NOTIFICAÇÕES AOS CLIENTES VIA WHATSAPP
@login_required
def notificar_cliente(request):
    if request.method == 'POST':

        # Função para enviar mensagens e registrar em arquivo de log
        def enviar_mensagem(telefone, mensagem, usuario, token, cliente):
            url = 'https://api.nossopainel.com.br/api/{}/send-message'.format(usuario)
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
                    response_data = json.loads(response.text)
                    error_message = response_data.get('message')
                    with open(log_filename, 'a') as log_file:
                        log_file.write('[{}] [TIPO][Agendado] [USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), usuario, cliente, response.status_code, tentativa, error_message))

                # Incrementa o número de tentativas
                tentativa += 1

                # Tempo de espera aleatório entre cada tentativa com limite máximo de 40 segundos
                tempo_espera = random.uniform(20, 40)
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
                pgto=False,
                cancelado=False,
                usuario=request.user
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
                
                # Tempo de espera aleatório entre cada tentativa com limite máximo de 90 segundos
                tempo_espera = random.uniform(20, 90)
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
                pgto=False,
                cancelado=False,
                usuario=request.user
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

                # Tempo de espera aleatório entre cada tentativa com limite máximo de 90 segundos
                tempo_espera = random.uniform(20, 90)
                time.sleep(tempo_espera)


        # Agendar a execução das funções
        mensalidades_a_vencer()
        mensalidades_vencidas()

############################################ AUTH VIEW ############################################

# PÁGINA DE LOGIN
class Login(LoginView):
    template_name = 'login.html'
    form_class = LoginForm
    redirect_authenticated_user = True
    success_url = 'dashboard/'

# PÁGINA DE ERRO 404
def not_found(request, exception):
    return render(request, 'pages/404-error.html')

############################################ LIST VIEW ############################################

class CarregarContasDoAplicativo(LoginRequiredMixin, View):
    """
    View para carregar as contas dos aplicativos existentes por cliente e exibi-las no modal de informações do cliente no painel de controle.
    """
    def get(self, request):
        """
        Método GET para retornar as contas dos aplicativos existentes por cliente.

        Obtém o ID do cliente da consulta na URL.
        Filtra as contas do aplicativo para o cliente e o usuário atual.
        Cria uma lista para armazenar as contas de aplicativo serializadas.
        Itera sobre as contas de aplicativo.
        - Obtém o nome do aplicativo.
        - Serializa a conta de aplicativo em um dicionário Python.
        - Adiciona o nome do aplicativo ao dicionário.
        - Adiciona a conta de aplicativo serializada à lista.
        Ordena a lista de contas de aplicativo pelo nome do aplicativo.
        Imprime a lista de contas de aplicativo para fins de depuração.
        Retorna a lista de contas de aplicativo como resposta JSON.
        """
        id = self.request.GET.get("cliente_id")
        cliente = Cliente.objects.get(id=id)
        conta_app = ContaDoAplicativo.objects.filter(cliente=cliente, usuario=self.request.user).select_related('app')

        conta_app_json = []

        for conta in conta_app:
            nome_aplicativo = conta.app.nome
            conta_json = model_to_dict(conta)
            conta_json['nome_aplicativo'] = nome_aplicativo
            conta_app_json.append(conta_json)

        conta_app_json = sorted(conta_app_json, key=operator.itemgetter('nome_aplicativo'))

        return JsonResponse({"conta_app": conta_app_json}, safe=False)


class CarregarQuantidadesMensalidades(LoginRequiredMixin, View):
    """
    View para retornar as quantidades de mensalidades pagas, inadimplentes e canceladas existentes para o modal de informações na listagem do cliente.
    """
    def get(self, request):
        """
        Método GET para retornar as quantidades de mensalidades pagas, inadimplentes e canceladas.

        Obtém o ID do cliente da consulta na URL.
        Filtra as mensalidades pagas para o cliente e o usuário atual.
        Filtra as mensalidades pendentes para o cliente e o usuário atual.
        Filtra as mensalidades canceladas para o cliente e o usuário atual.
        Inicializa as variáveis para as quantidades de mensalidades pagas, pendentes e canceladas como zero.
        Itera sobre as mensalidades pagas, incrementando a quantidade de mensalidades pagas para o cliente específico.
        Itera sobre as mensalidades pendentes, incrementando a quantidade de mensalidades pendentes para o cliente específico.
        Itera sobre as mensalidades canceladas, incrementando a quantidade de mensalidades canceladas para o cliente específico.
        Cria um dicionário com os valores de quantidade de mensalidades para cada status.
        Retorna a resposta em formato JSON com os dados de quantidade de mensalidades.
        """
        id = self.request.GET.get("cliente_id")
        cliente = Cliente.objects.get(id=id)
        hoje = timezone.localtime().date()
        mensalidades_totais = Mensalidade.objects.filter(usuario=self.request.user, cliente=cliente).order_by('-id').values()
        mensalidades_pagas = Mensalidade.objects.filter(usuario=self.request.user, pgto=True, cliente=cliente)
        mensalidades_pendentes = Mensalidade.objects.filter(usuario=self.request.user, dt_pagamento=None, pgto=False, cancelado=False, dt_cancelamento=None, dt_vencimento__lt=hoje, cliente=cliente)
        mensalidades_canceladas = Mensalidade.objects.filter(usuario=self.request.user, cancelado=True, cliente=cliente)

        qtd_mensalidades_pagas = 0
        for mensalidade in mensalidades_pagas:
            if mensalidade.cliente.id == cliente.id:
                qtd_mensalidades_pagas += 1

        qtd_mensalidades_pendentes = 0
        for mensalidade in mensalidades_pendentes:
            if mensalidade.cliente.id == cliente.id:
                qtd_mensalidades_pendentes += 1

        qtd_mensalidades_canceladas = 0
        for mensalidade in mensalidades_canceladas:
            if mensalidade.cliente.id == cliente.id:
                qtd_mensalidades_canceladas += 1

        data = {
            'mensalidades_totais': list(mensalidades_totais),
            'qtd_mensalidades_pagas': qtd_mensalidades_pagas,
            'qtd_mensalidades_pendentes': qtd_mensalidades_pendentes,
            'qtd_mensalidades_canceladas': qtd_mensalidades_canceladas
        }

        return JsonResponse(data)
    

class CarregarInidicacoes(LoginRequiredMixin, View):

    def get(self, request):
        id = self.request.GET.get("cliente_id")
        indicados = Cliente.objects.filter(indicado_por=id).order_by('-id').values()

        data = {'indicacoes': list(indicados),}

        return JsonResponse(data)


class ClientesCancelados(LoginRequiredMixin, ListView):
    """
    View para listar clientes, considerando clientes cancelados e ativos.
    """
    model = Cliente
    template_name = "pages/clientes-cancelados.html"
    paginate_by = 15

    def get_queryset(self):
        """
        Retorna a queryset de clientes para a exibição na página.

        Filtra os clientes do usuário atual e os ordena pela data de adesão.
        Se houver uma consulta (q) na URL, filtra os clientes cujo nome contenha o valor da consulta.
        """
        query = self.request.GET.get("q")
        queryset = (
            Cliente.objects.filter(usuario=self.request.user, cancelado=True)
            .order_by("-data_cancelamento")
        )
        
        if query:
            queryset = queryset.filter(nome__icontains=query)
        return queryset
    
    def get_context_data(self, **kwargs):
        """
        Retorna o contexto dos dados para serem exibidos no template.

        Adiciona informações adicionais ao contexto, como objetos relacionados e variáveis de controle de página.
        """
        context = super().get_context_data(**kwargs)
        page_group = 'clientes'
        page = 'lista-clientes'
        range_num = range(1,32)

        context.update(
            {
                "range": range_num,
                "page_group": page_group,
                "page": page,
            }
        )
        return context


class TabelaDashboard(LoginRequiredMixin, ListView):
    """
    View para listagem de clientes, suas mensalidades e outras informações exibidas no dashboard.
    """
    login_url = "login"
    model = Cliente
    template_name = "dashboard.html"
    paginate_by = 10

    def get_queryset(self):
        """
        Retorna a queryset para a listagem de clientes no dashboard.

        Filtra os clientes que não foram cancelados e possuem mensalidades não canceladas, não pagas e sem data de pagamento definida.
        Ordena a queryset pelo campo de data de vencimento da mensalidade.
        Realiza a operação distinct() para evitar duplicatas na listagem.
        Caso haja um valor de busca na URL (parâmetro 'q'), filtra a queryset pelos clientes cujo nome contém o valor de busca.
        """
        query = self.request.GET.get("q")
        queryset = (
            Cliente.objects.filter(cancelado=False).filter(
                mensalidade__cancelado=False,
                mensalidade__dt_cancelamento=None,
                mensalidade__dt_pagamento=None,
                mensalidade__pgto=False,
                usuario=self.request.user,
            ).order_by("mensalidade__dt_vencimento").distinct()
        )
        if query:
            queryset = queryset.filter(nome__icontains=query)
        return queryset

    def get_context_data(self, **kwargs):
        """
        Retorna o contexto de dados para serem exibidos no dashboard.

        Inicializa as variáveis necessárias, como a moeda utilizada, a data de hoje e o ano atual.
        Calcula o total de clientes baseado na queryset.
        Obtém o mês atual.
        Define a página atual como 'dashboard'.
        Filtra os clientes em atraso.
        Calcula o valor total pago no mês atual.
        Calcula a quantidade de mensalidades pagas no mês atual.
        Calcula o valor total a receber no mês atual.
        Calcula a quantidade de mensalidades a receber na próxima semana.
        Calcula a quantidade de novos clientes no mês atual.
        Calcula a quantidade de clientes cancelados no mês atual.
        Obtém a lista de aplicativos do usuário ordenados por nome.
        Atualiza o contexto com as informações calculadas.
        Retorna o contexto atualizado.
        """
        moeda = "BRL"
        page = 'dashboard'
        hoje = timezone.localtime().date()
        f_name = self.request.user.first_name
        ano_atual = timezone.localtime().year
        proxima_semana = hoje + timedelta(days=7)
        dt_inicio = str(self.request.user.date_joined)
        context = super().get_context_data(**kwargs)
        total_clientes = self.get_queryset().count()
        mes_atual = timezone.localtime().date().month

        # Variáveis para context do modal de edição do cadastro do cliente
        indicadores = Cliente.objects.filter(usuario=self.request.user).order_by('nome')
        servidores = Servidor.objects.filter(usuario=self.request.user).order_by('nome')
        formas_pgtos = Tipos_pgto.objects.filter(usuario=self.request.user)
        planos = Plano.objects.filter(usuario=self.request.user).order_by('nome')
        telas = Qtd_tela.objects.all().order_by('telas')
        dispositivos = Dispositivo.objects.filter(usuario=self.request.user).order_by('nome')
        aplicativos = Aplicativo.objects.filter(usuario=self.request.user).order_by('nome')

        clientes_em_atraso = Cliente.objects.filter(
            cancelado=False,
            mensalidade__cancelado=False,
            mensalidade__dt_pagamento=None,
            mensalidade__pgto=False,
            mensalidade__dt_vencimento__lt=hoje,
            usuario=self.request.user,
        ).count()

        valor_total_pago = (
            Mensalidade.objects.filter(
                cancelado=False,
                dt_pagamento__year=ano_atual,
                dt_pagamento__month=mes_atual,
                usuario=self.request.user,
                pgto=True,
            ).aggregate(valor_total=Sum("valor"))["valor_total"]
            or 0
        )

        valor_total_pago = format_currency(valor_total_pago, moeda)

        valor_total_pago_qtd = Mensalidade.objects.filter(
            cancelado=False,
            dt_pagamento__year=ano_atual,
            dt_pagamento__month=mes_atual,
            usuario=self.request.user,
            pgto=True,
        ).count()

        valor_total_receber = (
            Mensalidade.objects.filter(
                cancelado=False,
                dt_vencimento__year=ano_atual,
                dt_vencimento__month=mes_atual,
                usuario=self.request.user,
                pgto=False,
            ).aggregate(valor_total=Sum("valor"))["valor_total"]
            or 0
        )
        valor_total_receber = format_currency(valor_total_receber, moeda)

        valor_total_receber_qtd = Mensalidade.objects.filter(
            cancelado=False,
            dt_vencimento__gte=hoje,
            dt_vencimento__lt=proxima_semana,
            usuario=self.request.user,
            pgto=False,
        ).count()

        novos_clientes_qtd = (
            Cliente.objects.filter(
                cancelado=False,
                data_adesao__year=ano_atual,
                data_adesao__month=mes_atual,
                usuario=self.request.user,
            )
        ).count()

        clientes_cancelados_qtd = Cliente.objects.filter(
            cancelado=True,
            data_cancelamento__year=ano_atual,
            data_cancelamento__month=mes_atual,
            usuario=self.request.user,
        ).count()

        aplicativos = Aplicativo.objects.filter(usuario=self.request.user).order_by('nome')
        range_num = range(1,32)

        context.update(
            {
                "hoje": hoje,
                "page": page,
                "range": range_num,
                "nome_user": f_name,
                "aplicativos": aplicativos,
                "data_criacao_user": dt_inicio,
                "total_clientes": total_clientes,
                "valor_total_pago": valor_total_pago,
                "novos_clientes_qtd": novos_clientes_qtd,
                "clientes_em_atraso": clientes_em_atraso,
                "valor_total_receber": valor_total_receber,
                "valor_total_pago_qtd": valor_total_pago_qtd,
                "valor_total_receber_qtd": valor_total_receber_qtd,
                "clientes_cancelados_qtd": clientes_cancelados_qtd,
                ## context para modal de edição
                "telas": telas,
                "planos": planos,
                "servidores": servidores,
                "aplicativos": aplicativos,
                "indicadores": indicadores,
                "dispositivos": dispositivos,
                "formas_pgtos": formas_pgtos,
            }
        )
        return context


@login_required
def EnviarMensagemWpp(request):
    if request.method == 'POST':
        BASE_URL = 'https://api.nossopainel.com.br/api/{}/send-{}'
        sessao = get_object_or_404(SessaoWpp, usuario=request.user)
        tipo_envio = request.POST.get('options')
        mensagem = request.POST.get('mensagem')
        imagem = request.FILES.get('imagem')
        usuario = request.user
        token = sessao.token
        clientes = None
        log_directory = './logs/Envios manuais/'
        log_filename = os.path.join(log_directory, '{}.log'.format(usuario))
        log_send_result_filename = os.path.join(log_directory, '{}_send_result.log'.format(usuario))
        if imagem:
            imagem_base64 = base64.b64encode(imagem.read()).decode('utf-8')

        def enviar_mensagem(url, telefone):
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

            if imagem:
                body['filename'] = str(imagem)
                body['caption'] = mensagem
                body['base64'] = 'data:image/png;base64,' + imagem_base64

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
                        log_file.write('[{}] [TIPO][Manual] [USUÁRIO][{}] [TELEFONE][{}] Mensagem enviada!\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), usuario, telefone))
                    with open(log_send_result_filename, 'a') as log_file:
                        log_file.write('[{}] {} - Mensagem enviada\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), telefone))
                    time.sleep(random.uniform(30, 70))
                    break
                else:
                    if attempts <= max_attempts:
                        time.sleep(random.uniform(5, 10))
                    # Verificar se o diretório de logs existe e criar se necessário
                    if not os.path.exists(log_directory):
                        os.makedirs(log_directory)
                    # Verificar se o arquivo de log existe e criar se necessário
                    if not os.path.isfile(log_filename):
                        open(log_filename, 'w').close()
                    # Escrever no arquivo de log
                    with open(log_filename, 'a') as log_file:
                        response_data = json.loads(response.text)
                        error_message = response_data.get('message')
                        log_file.write('[{}] [TIPO][Manual] [USUÁRIO][{}] [TELEFONE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), usuario, telefone, response.status_code, attempts, error_message))

                    attempts += 1

                if attempts == max_attempts:
                    # Verificar se o diretório de logs existe e criar se necessário
                    if not os.path.exists(log_directory):
                        os.makedirs(log_directory)
                    # Verificar se o arquivo de log existe e criar se necessário
                    if not os.path.isfile(log_send_result_filename):
                        open(log_send_result_filename, 'w').close()
                    # Escrever no arquivo de log
                    with open(log_send_result_filename, 'a') as log_file:
                        log_file.write('[{}] {} - Número sem WhatsApp\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), telefone))

        if tipo_envio == 'ativos':
            clientes = Cliente.objects.filter(usuario=usuario, cancelado=False)
            telefones = ','.join([re.sub(r'\s+|\W', '', cliente.telefone) for cliente in clientes])

        elif tipo_envio == 'cancelados':
            clientes = Cliente.objects.filter(usuario=usuario, cancelado=True)
            telefones = ','.join([re.sub(r'\s+|\W', '', cliente.telefone) for cliente in clientes])

        elif tipo_envio == 'avulso':
            telefones_file = request.FILES.get('telefones')
            if telefones_file:
                telefones_data = telefones_file.read().decode('utf-8').split('\n')
                telefones = ','.join([re.sub(r'\s+|\W', '', telefone) for telefone in telefones_data if telefone.strip()])


        if clientes is not None:
            url = BASE_URL.format(usuario, 'image' if imagem else 'message')
            for cliente in clientes:
                enviar_mensagem(url, re.sub(r'\s+|\W', '', cliente.telefone))

        elif telefones:
            url = BASE_URL.format(usuario, 'image' if imagem else 'message')
            [enviar_mensagem(url, telefone) for telefone in telefones.split(',')]

        return JsonResponse({'success': 'Envio concluído'}, status=200)

    return JsonResponse({'error': 'Método inválido'}, status=400)


@login_required
def SecretTokenAPIView(request):
    """
        Função de view para consultar o Secret Token da API WPP Connect
    """
    if request.method == 'GET':
        if request.user:
            query = SecretTokenAPI.objects.get(id=1)
            token = query.token
        else:
            return JsonResponse({"error_message": "Usuário da requisição não identificado."}, status=500)
    else:
        return JsonResponse({"error_message": "Método da requisição não permitido."}, status=500)
    
    return JsonResponse({"stkn": token}, status=200)


@login_required
def ObterSessionWpp(request):
    """
        Função de view para consultar o Token da sessão WhatsApp do usuário da requisição.
    """
    if request.method == 'GET':
        if request.user:
            sessao = get_object_or_404(SessaoWpp, usuario=request.user)
            token = sessao.token
        else:
            return JsonResponse({"error_message": "Usuário da requisição não identificado."}, status=500)
    else:
        return JsonResponse({"error_message": "Método da requisição não permitido."}, status=500)

    return JsonResponse({"token": token}, status=200)


@login_required
def ObterLogsWpp(request):
    if request.method == 'POST':

        file_path = './logs/Envios manuais/{}_send_result.log'.format(request.user)
        with open(file_path, 'r') as file:
            logs = file.read()

    return JsonResponse({'logs': logs})


def Perfil(request):
    user = User.objects.get(username=request.user)
    dados_bancarios = DadosBancarios.objects.filter(usuario=user.id).first()

    dt_inicio = user.date_joined.strftime('%d/%m/%Y') if user.date_joined else '--'
    f_name = user.first_name if user.first_name else '--'
    l_name = user.last_name if user.last_name else '--'
    email = user.email if user.email else '--'

    beneficiario = dados_bancarios.beneficiario if dados_bancarios else '--'
    instituicao = dados_bancarios.instituicao if dados_bancarios else '--'
    tipo_chave = dados_bancarios.tipo_chave if dados_bancarios else '--'
    chave = dados_bancarios.chave if dados_bancarios else '--'

    return render(
        request,
        'pages/perfil.html',
        {
            'beneficiario': beneficiario,
            'instituicao': instituicao,
            'tipo_chave': tipo_chave,
            'sobrenome_user': l_name,
            'dt_inicio': dt_inicio,
            'nome_user': f_name,
            'username': user,
            'email': email,
            'chave': chave
        },
    )


############################################ UPDATE VIEW ############################################

from django.views.decorators.http import require_POST

@require_POST
@login_required
def HorarioEnvio(request):
    usuario = request.user
    horario = request.POST.get('horario')

    try:
        obj_existente = HorarioEnvio.objects.get(usuario=usuario)
    except HorarioEnvio.DoesNotExist:
        obj_existente = None

    if request.POST.get('ativar'):
        if not obj_existente:
            obj = HorarioEnvio.objects.create(usuario=usuario, horario=horario, ativo=True)
            obj.save()
        else:
            obj_existente.horario = horario
            obj_existente.ativo = True
            obj_existente.save()

    elif request.POST.get('desativar'):
        if not obj_existente:
            obj = HorarioEnvio.objects.create(usuario=usuario, horario=None, ativo=False)
            obj.save()
        else:
            obj_existente.horario = None
            obj_existente.ativo = False
            obj_existente.save()

    return JsonResponse({"success_message": "Horário de envio atualizado com sucesso."}, status=200)


@login_required
def SessionWpp(request):
    """
    Função de view para criar ou deletar uma sessão do WhatsApp
    """
    if request.method == 'DELETE':
        try:
            sessao = SessaoWpp.objects.filter(usuario=request.user)
            sessao.delete()
            # Realizar outras ações necessárias após a exclusão, se houver
            return JsonResponse({"success_message_session": "Sessão deletada com sucesso."}, status=200)
        except ObjectDoesNotExist:
            return JsonResponse({"error_message": "A sessão não existe."}, status=404)
        except Exception as e:
            return JsonResponse({"error_message": str(e)}, status=500)

    elif request.method in ['PUT', 'PATCH']:
        body = json.loads(request.body)
        token = body.get('token')
        try:
            sessao, created = SessaoWpp.objects.update_or_create(
                usuario=request.user,
                token=token,
                dt_inicio=timezone.localtime()
            )
            # Realizar outras ações necessárias após salvar/atualizar, se houver
            return JsonResponse({"success_message_session": "Sessão salva/atualizada com sucesso."}, status=200)
        except Exception as e:
            return JsonResponse({"error_message": str(e)}, status=500)

    else:
        return JsonResponse({"error_message": "Método da requisição não permitido."}, status=405)



@login_required
def reativar_cliente(request, cliente_id):
    """
    Função de view para reativar um cliente previamente cancelado.
    """
    cliente = Cliente.objects.get(pk=cliente_id, usuario=request.user)
    data_hoje = timezone.localtime().date()

    # Muda o valor do atributo "cancelado" de True para False
    # Define o valor de "data_cancelamento" como None
    cliente.data_pagamento = data_hoje.day
    cliente.data_cancelamento = None
    cliente.cancelado = False
    dia = cliente.data_pagamento
    mes = data_hoje.month
    ano = data_hoje.year

    # Tratando possíveis erros
    try:
        cliente.save()

        # Cria uma nova Mensalidade para o cliente reativado
        mensalidade = Mensalidade.objects.create(
            cliente=cliente,
            valor=cliente.plano.valor,
            dt_vencimento=datetime(ano, mes, dia),
            usuario=cliente.usuario
        )
        mensalidade.save()

    except Exception as erro:
        # Registra o erro no log
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
        return JsonResponse({"error_message": "Ocorreu um erro ao tentar reativar esse cliente."})

    # Se tudo ocorrer corretamente, retorna uma confirmação
    return JsonResponse({"success_message_activate": "Reativação feita!"})

import calendar
# AÇÃO DE PAGAR MENSALIDADE
@login_required
def pagar_mensalidade(request, mensalidade_id):
    """
    Função de view para pagar uma mensalidade.
    """
    hoje = timezone.localtime().date()
    mensalidade = Mensalidade.objects.get(pk=mensalidade_id, usuario=request.user)

    # Verifica se a mensalidade está atrasada por mais de 7 dias
    if mensalidade.dt_vencimento < hoje - timedelta(days=7):
        return JsonResponse({"error_message": "erro"})
    
    # Realiza as modificações na mensalidade paga
    mensalidade.dt_pagamento = timezone.localtime().date()
    mensalidade.pgto = True
    try:
        mensalidade.save()
    except Exception as erro:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
        return JsonResponse({"error_message": "Ocorreu um erro ao tentar pagar essa mensalidade."}, status=500)

    # Retorna uma resposta JSON indicando que a mensalidade foi paga com sucesso
    return JsonResponse({"success_message_invoice": "Mensalidade paga!"}, status=200)


# AÇÃO PARA CANCELAMENTO DE CLIENTE
@login_required
def cancelar_cliente(request, cliente_id):
    if request.user.is_authenticated:
        cliente = Cliente.objects.get(pk=cliente_id, usuario=request.user)

        # Realiza as modificações no cliente
        cliente.cancelado = True
        cliente.data_cancelamento = timezone.localtime().date()
        try:
            cliente.save()
        except Exception as erro:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
            return JsonResponse({"error_message": "Ocorreu um erro ao tentar cancelar esse cliente."}, status=500)

        # Cancelar todas as mensalidades relacionadas ao cliente
        mensalidades = cliente.mensalidade_set.filter(dt_vencimento__gte=timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0), pgto=False, cancelado=False)
        for mensalidade in mensalidades:
            mensalidade.cancelado = True
            mensalidade.dt_cancelamento = timezone.localtime().date()
            mensalidade.save()

        # Retorna uma resposta JSON indicando que o cliente foi cancelado com sucesso
        return JsonResponse({"success_message_cancel": "Eita! mais um cliente cancelado?! "})
    else:
        return redirect("login")


from datetime import datetime

@login_required
def EditarCliente(request, cliente_id):
    """
    Função de view para editar um cliente.
    """
    if request.method == "POST":
        telefone = Cliente.objects.filter(telefone=request.POST.get("telefone"), usuario=request.user)

        try:
            clientes = Cliente.objects.filter(usuario=request.user).order_by("-data_adesao")
            cliente = Cliente.objects.get(pk=cliente_id, usuario=request.user)
            mensalidade = Mensalidade.objects.get(cliente=cliente, pgto=False, cancelado=False, usuario=request.user)
            plano_list = request.POST.get("plano").replace(' ', '').split('-')
            tela_list = request.POST.get("tela").split(' ')

            # Verificar e atualizar os campos modificados
            if cliente.nome != request.POST.get("nome"):
                cliente.nome = request.POST.get("nome")

            if cliente.telefone != request.POST.get("telefone"):
                telefone = Cliente.objects.filter(telefone=request.POST.get("telefone"), usuario=request.user)
                if not telefone:
                    cliente.telefone = request.POST.get("telefone")
                else:
                    return render(request, "dashboard.html", {"error_message_edit": "Já existe um cliente com este telefone informado."}, status=400)
                
            if request.POST.get("indicado_por"):
                indicado_por = Cliente.objects.get(nome=request.POST.get("indicado_por"), usuario=request.user)
                if cliente.indicado_por != indicado_por:
                    cliente.indicado_por = indicado_por

            servidor = Servidor.objects.get(nome=request.POST.get("servidor"), usuario=request.user)
            if cliente.servidor != servidor:
                cliente.servidor = servidor

            forma_pgto = Tipos_pgto.objects.filter(nome=request.POST.get("forma_pgto"), usuario=request.user).first()
            if cliente.forma_pgto != forma_pgto:
                cliente.forma_pgto = forma_pgto

            plano = Plano.objects.filter(nome=plano_list[0], valor=plano_list[1].replace(',', '.'), usuario=request.user).first()
            if cliente.plano != plano:
                cliente.plano = plano
                mensalidade.valor = int(plano.valor)
                mensalidade.save()

            tela = Qtd_tela.objects.get(telas=tela_list[0])
            if cliente.telas != tela:
                cliente.telas = tela

            if cliente.data_pagamento != int(request.POST.get("dt_pgto")):
                # Atribui o tipo do "plano" à variável "plano" para verificar nas condicionais a seguir
                plano_nome = str(plano.nome)
                plano_valor = int(plano.valor)

                # Dicionário de planos com a quantidade de meses a serem adicionados
                planos = {
                    'mensal': 1,
                    'trimestral': 3,
                    'semestral': 6,
                    'anual': 12
                }

                # Atualizar a data de vencimento da mensalidade do cliente de acordo com o tipo do plano
                novo_dia_vencimento = int(request.POST.get("dt_pgto"))
                hoje = datetime.now().date()
                meses31dias = [1, 3, 5, 7, 8, 10, 12]
                
                if plano_nome.lower() == 'mensal':
                    cliente_inalterado = Cliente.objects.get(pk=cliente_id, usuario=request.user)
                    
                    if not 'mensal' or not 'Mensal' in cliente_inalterado.plano.nome:
                        data_vencimento_atual = cliente_inalterado.ultimo_pagamento if cliente_inalterado.ultimo_pagamento != None else cliente_inalterado.data_adesao
                    else:
                        data_vencimento_atual = mensalidade.dt_vencimento
                    
                    if data_vencimento_atual.month == hoje.month:
                        if novo_dia_vencimento < hoje.day:
                            # Dia de vencimento já passou, atualizar para o próximo mês
                            mes_vencimento = data_vencimento_atual.month + 1
                            ano_vencimento = data_vencimento_atual.year
                            
                            if mes_vencimento > 12:
                                mes_vencimento -= 12
                                ano_vencimento += 1
                        else:
                            mes_vencimento = data_vencimento_atual.month
                            ano_vencimento = data_vencimento_atual.year
                    else:
                        mes_vencimento = data_vencimento_atual.month
                        ano_vencimento = data_vencimento_atual.year

                    if novo_dia_vencimento == 31 and mes_vencimento not in meses31dias:
                        novo_dia_vencimento = 1
                        mes_vencimento += 1

                else:
                    if cliente.ultimo_pagamento:
                        mes_vencimento = cliente.ultimo_pagamento.month +  planos.get(plano_nome.lower(), 0)
                        ano_vencimento = cliente.ultimo_pagamento.year

                    elif cliente.data_adesao:
                        mes_vencimento = cliente.data_adesao.month + planos.get(plano_nome.lower(), 0)
                        ano_vencimento = cliente.data_adesao.year

                    if mes_vencimento > 12:
                        mes_vencimento -= 12
                        ano_vencimento += 1

                    if novo_dia_vencimento == 31 and mes_vencimento not in meses31dias:
                        novo_dia_vencimento = 1
                        mes_vencimento += 1
                            
                nova_data_vencimento = datetime(year=ano_vencimento, month=mes_vencimento, day=novo_dia_vencimento)
                mensalidade.dt_vencimento = nova_data_vencimento
                cliente.data_pagamento = novo_dia_vencimento
                mensalidade.valor = plano_valor

                mensalidade.save()
                cliente.save()

            dispositivo = Dispositivo.objects.get(nome=request.POST.get("dispositivo"), usuario=request.user)
            if cliente.dispositivo != dispositivo:
                cliente.dispositivo = dispositivo

            aplicativo = Aplicativo.objects.get(nome=request.POST.get("aplicativo"), usuario=request.user)
            if cliente.sistema != aplicativo:
                cliente.sistema = aplicativo

            if cliente.notas != request.POST.get("notas"):
                cliente.notas = request.POST.get("notas")

            cliente.save()

            # Em caso de sucesso, renderiza a página de listagem de clientes com uma mensagem de sucesso
            return render(request, "dashboard.html", {"success_message_edit": "{} foi atualizado com sucesso.".format(cliente.nome)}, status=200)

        except Exception as e:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
            return render(request, "dashboard.html", {"error_message_edi": "Ocorreu um erro ao tentar atualizar esse cliente."}, status=500)

    # Redireciona para a página de listagem de clientes se o método HTTP não for POST
    return redirect("dashboard")


# AÇÃO PARA EDITAR O OBJETO PLANO MENSAL
@login_required
def EditarPlanoAdesao(request, plano_id):
    """
    Função de view para editar um plano de adesão mensal.
    """
    plano_mensal = get_object_or_404(Plano, pk=plano_id, usuario=request.user)

    planos_mensalidades = Plano.objects.all().order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")
        valor = request.POST.get("valor")

        if nome and valor:
            plano_mensal.nome = nome
            plano_mensal.valor = valor

            try:
                plano_mensal.save()

            except ValidationError as erro1:
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                # Capturando a exceção ValidationError e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-plano-adesao.html",
                    {
                        'planos_mensalidades': planos_mensalidades,
                        "error_message": "Já existe um plano com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o plano e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-plano-adesao.html",
                    {
                        'planos_mensalidades': planos_mensalidades,
                        "error_message": "Ocorreu um erro ao salvar o plano. Verifique o log!",
                    },
                )
            
            # Em caso de sucesso, renderiza a página novamente com a mensagem de sucesso
            return render(
                request,
                "pages/cadastro-plano-adesao.html",
                {"planos_mensalidades": planos_mensalidades, "success_update": True},
            )

        else:
            return render(
                request,
                "pages/cadastro-plano-adesao.html",
                {
                    "planos_mensalidades": planos_mensalidades,
                    "error_message": "O campo do valor não pode estar em branco.",
                },
            )

    # Redireciona para a página de cadastro de plano de adesão se o método HTTP não for POST
    return redirect("cadastro-plano-adesao")


# AÇÃO PARA EDITAR O OBJETO SERVIDOR
@login_required
def EditarServidor(request, servidor_id):
    servidor = get_object_or_404(Servidor, pk=servidor_id, usuario=request.user)

    servidores = Servidor.objects.filter(usuario=request.user).order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:         
            servidor.nome = nome
            try:
                servidor.save()

            except ValidationError as erro1:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-servidor.html",
                    {
                        'servidores': servidores,
                        "error_message": "Já existe um servidor com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o servidor
                return render(
                    request,
                    "pages/cadastro-servidor.html",
                    {
                        'servidores': servidores,
                        "error_message": "Ocorreu um erro ao salvar o servidor. Verifique o log!",
                    },
                )
            
            return render(
                request,
                "pages/cadastro-servidor.html",
                {"servidores": servidores, "success_update": True},
            )

    return redirect("cadastro-servidor")


# AÇÃO PARA EDITAR O OBJETO DISPOSITIVO
@login_required
def EditarDispositivo(request, dispositivo_id):
    dispositivo = get_object_or_404(Dispositivo, pk=dispositivo_id, usuario=request.user)

    dispositivos = Dispositivo.objects.filter(usuario=request.user).order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:         
            dispositivo.nome = nome
            try:
                dispositivo.save()

            except ValidationError as erro1:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-dispositivo.html",
                    {
                        'dispositivos': dispositivos,
                        "error_message": "Já existe um dispositivo com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o dispositivo
                return render(
                    request,
                    "pages/cadastro-dispositivo.html",
                    {
                        'dispositivos': dispositivos,
                        "error_message": "Ocorreu um erro ao salvar o dispositivo. Verifique o log!",
                    },
                )
            
            return render(
                request,
                "pages/cadastro-dispositivo.html",
                {"dispositivos": dispositivos, "success_update": True},
            )

    return redirect("cadastro-dispositivo")


# AÇÃO PARA EDITAR O OBJETO APLICATIVO
@login_required
def EditarAplicativo(request, aplicativo_id):
    aplicativo = get_object_or_404(Aplicativo, pk=aplicativo_id, usuario=request.user)

    aplicativos = Aplicativo.objects.filter(usuario=request.user).order_by('nome')

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:         
            aplicativo.nome = nome
            try:
                aplicativo.save()

            except ValidationError as erro1:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-aplicativo.html",
                    {
                        'aplicativos': aplicativos,
                        "error_message": "Já existe um aplicativo com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o aplicativo
                return render(
                    request,
                    "pages/cadastro-aplicativo.html",
                    {
                        'aplicativos': aplicativos,
                        "error_message": "Ocorreu um erro ao salvar o aplicativo. Verifique o log!",
                    },
                )
            
            return render(
                request,
                "pages/cadastro-aplicativo.html",
                {"aplicativos": aplicativos, "success_update": True},
            )

    return redirect("cadastro-aplicativo")


@login_required
def EditarPerfil(request):
    if request.method == "POST":
        if request.user.is_authenticated:
            try:
                user = request.user
                dados_usuario = user
                dados_usuario.last_name = request.POST.get('sobrenome', '')
                dados_usuario.first_name = request.POST.get('nome', '')
                dados_usuario.email = request.POST.get('email', '')
                dados_usuario.save()

                dados_bancarios = DadosBancarios.objects.filter(usuario=user).first()
                beneficiario = request.POST.get('beneficiario', '')
                instituicao = request.POST.get('instituicao', '')
                tipo_chave = request.POST.get('tipo_chave', '')
                chave = request.POST.get('chave', '')

                if not dados_bancarios:
                    dados_bancarios = DadosBancarios(usuario=user)

                dados_bancarios.beneficiario = beneficiario
                dados_bancarios.instituicao = instituicao
                dados_bancarios.tipo_chave = tipo_chave
                dados_bancarios.chave = chave
                dados_bancarios.save()

                messages.success(request, 'Perfil editado com sucesso!')
            except Exception as e:
                messages.error(request, 'Ocorreu um erro ao editar o perfil. Verifique o log!')
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
        else:
            messages.error(request, 'Usuário da requisição não identificado!')
    else:
        messages.error(request, 'Método da requisição não permitido!')

    return redirect('perfil')


def Teste(request):
    clientes = Cliente.objects.all()

    return render(
        request,
        'teste.html',
        {
            'clientes': clientes,
        },
    )


############################################ CREATE VIEW ############################################

@login_required
def CadastroContaAplicativo(request):

    if request.method == "POST":
        app = Aplicativo.objects.get(nome=request.POST.get('app-nome'))
        cliente = Cliente.objects.get(id=request.POST.get('cliente-id'))
        device_id = request.POST.get('device-id') if request.POST.get('device-id') != None or '' or ' ' else None
        device_key = request.POST.get('device-key') if request.POST.get('device-key') != None or '' or ' ' else None
        app_email = request.POST.get('app-email') if request.POST.get('app-email') != None or '' or ' ' else None
    
        nova_conta_app = ContaDoAplicativo(cliente=cliente, app=app, device_id=device_id, device_key=device_key, email=app_email, usuario=request.user)

        try:
            nova_conta_app.save()
            
            # retorna a mensagem de sucesso como resposta JSON
            return JsonResponse({"success_message_cancel": "Conta do aplicativo cadastrada com sucesso!"}, status=200)

        except Exception as erro:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
        
        return JsonResponse({"error_message": "Ocorreu um erro ao tentar realizar o cadastro."}, status=500)
    else:
        return JsonResponse({"error_message": "Ocorreu um erro ao tentar realizar o cadastro."}, status=500)


@login_required
def ImportarClientes(request):

    num_linhas_importadas = 0  # Inicializa o contador de linhas importadas
    num_linhas_nao_importadas = 0  # Inicializa o contador de linhas não importadas
    nomes_clientes_existentes = []  # Inicializa a lista de nomes de clientes existentes não importados
    nomes_clientes_erro_importacao = [] # Inicializa a lista de nomes de clientes que tiveram erro na importação
    usuario_request = request.user # Usuário que fez a requisição
    page_group = 'clientes'
    page = 'importar-clientes'

    if request.method == "POST" and 'importar' in request.POST:
        if not str(request.FILES['arquivo']).endswith('.xls') and not str(request.FILES['arquivo']).endswith('.xlsx'):
            # se o arquivo não possui a extensão esperada (.xls/.xlsx), retorna erro ao usuário.
            return render(request, "pages/importar-cliente.html",
                {"error_message": "O arquivo não é uma planilha válida (.xls, .xlsx)."},)

        try:
            # realiza a leitura dos dados da planilha.
            dados = pd.read_excel(request.FILES['arquivo'], engine='openpyxl')
        
        except Exception as erro1:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
            return render(request, "pages/importar-cliente.html",
                {"error_message": "Erro ao tentar ler planilha. Verifique o arquivo e tente novamente."},)
        
        # transforma cada linha dos dados lidos da planilha em um dicionário para que seja iterado no loop FOR.
        lista_de_objetos = dados.to_dict('records')

        with transaction.atomic(): # Adicionando a transação atomica
            i=0
            for dado in lista_de_objetos:
                i+=1

                servidor_import = str(dado['servidor']).replace(" ", "") if not pd.isna(dado['servidor']) else None
                dispositivo_import = str(dado['dispositivo']) if not pd.isna(dado['dispositivo']) else None
                sistema_import = str(dado['sistema']) if not pd.isna(dado['sistema']) else None
                device_id_import = str(dado['device_id']).replace(" ", "") if not pd.isna(dado['device_id']) else None
                email_import = str(dado['email']).replace(" ", "") if not pd.isna(dado['email']) else None
                device_key_import = str(dado['device_key']).replace(" ", "") if not pd.isna(dado['device_key']) else None
                nome_import = str(dado['nome']).title() if not pd.isna(dado['nome']) else None
                telefone_import = str(dado['telefone']).replace(" ", "") if not pd.isna(dado['telefone']) else None
                indicado_por_import = str(dado['indicado_por']) if not pd.isna(dado['indicado_por']) else None
                data_pagamento_import = int(dado['data_pagamento']) if not pd.isna(dado['data_pagamento']) else None
                forma_pgto_import = str(dado['forma_pgto']) if not pd.isna(dado['forma_pgto']) else 'PIX'
                tipo_plano_import = str(dado['tipo_plano']).replace(" ", "").title() if not pd.isna(dado['tipo_plano']) else None
                plano_valor_import = int(dado['plano_valor']) if not pd.isna(dado['plano_valor']) else None
                telas_import = str(dado['telas']).replace(" ", "") if not pd.isna(dado['telas']) else None
                data_adesao_import = dado['data_adesao'] if not pd.isna(dado['data_adesao']) else None

                if (servidor_import is None) or (dispositivo_import is None) or (sistema_import is None) or (nome_import is None) or (telefone_import is None) or (data_adesao_import is None) or (forma_pgto_import is None) or (plano_valor_import is None) or (tipo_plano_import is None):
                    num_linhas_nao_importadas += 1
                    nomes_clientes_erro_importacao.append('Linha {} da planilha - (há campos obrigatórios em branco)'.format(i))
                    continue
                
                try:
                    with transaction.atomic(): # Nova transação atomica para cada cliente importado
                        
                        # Verifica se já existe um cliente com esse nome ou telefone
                        cliente_existente = Cliente.objects.filter(Q(nome__iexact=nome_import) | Q(telefone=telefone_import), usuario=usuario_request).exists()
                        if cliente_existente:
                            num_linhas_nao_importadas += 1 # incrementa mais 1 a contagem
                            nomes_clientes_existentes.append('Linha {} da planilha - {}'.format(i, nome_import.title()))  # Adiciona o nome do cliente já existente
                            continue # pula a inserção desse cliente
                        
                        servidor, created = Servidor.objects.get_or_create(nome=servidor_import, usuario=usuario_request)
                        dispositivo, created = Dispositivo.objects.get_or_create(nome=dispositivo_import, usuario=usuario_request)
                        sistema, created = Aplicativo.objects.get_or_create(nome=sistema_import, usuario=usuario_request)
                        indicado_por = None
                        if indicado_por_import:
                            indicado_por = Cliente.objects.filter(nome__iexact=nome_import, usuario=usuario_request).first()
                        data_pagamento = data_pagamento_import
                        forma_pgto, created = Tipos_pgto.objects.get_or_create(nome=forma_pgto_import, usuario=usuario_request)
                        plano, created = Plano.objects.get_or_create(nome=tipo_plano_import, valor=plano_valor_import, usuario=usuario_request)
                        telas, created = Qtd_tela.objects.get_or_create(telas=int(telas_import))
                        data_adesao = data_adesao_import

                        novo_cliente = Cliente(
                            servidor=servidor,
                            dispositivo=dispositivo,
                            sistema=sistema,
                            nome=nome_import,
                            telefone=telefone_import,
                            indicado_por=indicado_por,
                            data_pagamento=data_pagamento,
                            forma_pgto=forma_pgto,
                            plano=plano,
                            telas=telas,
                            data_adesao=data_adesao,
                            usuario=usuario_request,
                        )
                        novo_cliente.save()
                        
                        check_sistema = sistema_import.lower().replace(" ", "")
                        if check_sistema == "clouddy" or check_sistema == "duplexplay" or check_sistema == "duplecast" or check_sistema == "metaplayer":
                            device_id = device_id_import
                            email = email_import
                            device_key = device_key_import.split('.')[0]
                            dados_do_app = ContaDoAplicativo(
                                device_id=device_id,
                                email=email,
                                device_key=device_key,
                                app=Aplicativo.objects.filter(nome__iexact=check_sistema, usuario=usuario_request).first(),
                                cliente=novo_cliente,
                                usuario=usuario_request,
                            )
                            dados_do_app.save()

                        num_linhas_importadas += 1  # Incrementa o contador de linhas importadas com sucesso
                except Exception as erro2:
                    logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                    # Se ocorrer um erro, apenas incrementa 1 a contagem e adiciona o nome do cliente a lista dos não importados, e continua para o próximo cliente.
                    num_linhas_nao_importadas += 1
                    nomes_clientes_erro_importacao.append('Linha {} da planilha - {}'.format(i, nome_import.title()))
                    continue

            time.sleep(2)
            return render(
                    request,
                    "pages/importar-cliente.html",
                    {
                        "success_message": "Importação concluída!",
                        "num_linhas_importadas": num_linhas_importadas,
                        "num_linhas_nao_importadas": num_linhas_nao_importadas,
                        "nomes_clientes_existentes": nomes_clientes_existentes,
                        "nomes_clientes_erro_importacao": nomes_clientes_erro_importacao,
                        "page_group": page_group,
                        "page": page,
                        },
            )
    
    return render(request, "pages/importar-cliente.html", {"page_group": page_group,"page": page,})


# AÇÃO PARA CRIAR NOVO CLIENTE ATRAVÉS DO FORMULÁRIO
@login_required
def CadastroCliente(request):
    # Criando os queryset para exibir os dados nos campos do fomulário
    plano_queryset = Plano.objects.filter(usuario=request.user).order_by('nome')
    telas_queryset = Qtd_tela.objects.all().order_by('telas')
    forma_pgto_queryset = Tipos_pgto.objects.filter(usuario=request.user)
    servidor_queryset = Servidor.objects.filter(usuario=request.user).order_by('nome')
    sistema_queryset = Aplicativo.objects.filter(usuario=request.user).order_by('nome')
    indicador_por_queryset = Cliente.objects.filter(usuario=request.user).order_by('nome')
    dispositivo_queryset = Dispositivo.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "clientes"
    page = "cadastro-cliente"

    # Recebendo os dados da requisição para criar um novo cliente
    if request.method == 'POST' and 'cadastrar' in request.POST:
        nome = request.POST.get('nome')
        notas = request.POST.get('notas')
        telefone = request.POST.get('telefone')
        sobrenome = request.POST.get('sobrenome')
        indicador = request.POST.get('indicador_list')
        lista_plano = request.POST.get('plano').split("-")
        nome_do_plano = lista_plano[0]
        valor_do_plano = float(lista_plano[1].replace(',', '.'))
        plano, created = Plano.objects.get_or_create(nome=nome_do_plano, valor=valor_do_plano, usuario=usuario)
        telas, created = Qtd_tela.objects.get_or_create(telas=request.POST.get('telas'))
        sistema, created = Aplicativo.objects.get_or_create(nome=request.POST.get('sistema'), usuario=usuario)
        servidor, created = Servidor.objects.get_or_create(nome=request.POST.get('servidor'), usuario=usuario)
        forma_pgto, created = Tipos_pgto.objects.get_or_create(nome=request.POST.get('forma_pgto'), usuario=usuario)
        dispositivo, created = Dispositivo.objects.get_or_create(nome=request.POST.get('dispositivo'), usuario=usuario)
        data_pagamento = int(request.POST.get('data_pagamento')) if request.POST.get('data_pagamento') else None
        valida_cliente_exists = Cliente.objects.filter(telefone=telefone).exists()

        if indicador is None or indicador == "" or indicador == " ":
            indicador = None
        else:
            indicador = Cliente.objects.get(nome=indicador, usuario=usuario)

        if telefone is None or telefone == "" or telefone == " ":
            return render(
                request,
                "pages/cadastro-cliente.html",
                {
                    "error_message": "O campo telefone não pode estar em branco.",
                },
            )
        
        elif not valida_cliente_exists:

            cliente = Cliente(
                nome=(nome + " " + sobrenome),
                telefone=(telefone),
                dispositivo=dispositivo,
                sistema=sistema,
                indicado_por=indicador,
                servidor=servidor,
                forma_pgto=forma_pgto,
                plano=plano,
                telas=telas,
                data_pagamento=data_pagamento,
                notas=notas,
                usuario=usuario,
            )
            try:
                cliente.save()

            except ValidationError as erro1:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                return render(
                    request,
                    "pages/cadastro-cliente.html",
                    {
                        "error_message": "Não foi possível cadastrar cliente!"
                    },
                )
            
            except Exception as erro2:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                return render(
                    request,
                    "pages/cadastro-cliente.html",
                    {
                        "error_message": "Não foi possível cadastrar cliente!",
                    },
                )
            
            check_sistema = request.POST.get('sistema').lower().replace(" ", "")
            if check_sistema == "clouddy" or check_sistema == "duplexplay" or check_sistema == "duplecast" or check_sistema == "metaplayer":
                dados_do_app = ContaDoAplicativo(
                    device_id=request.POST.get('id'),
                    email=request.POST.get('email'),
                    device_key=request.POST.get('senha'),
                    app=Aplicativo.objects.get(nome=sistema, usuario=usuario),
                    cliente=cliente,
                    usuario=usuario,
                )
                dados_do_app.save()

            return render(
                request,
                "pages/cadastro-cliente.html",
                {
                    "success_message": "Novo cliente cadastrado com sucesso!" ,
                },
            )
        
        else:
            valida_cliente_get = Cliente.objects.get(telefone=telefone)
            return render(
                request,
                "pages/cadastro-cliente.html",
                {
                    "error_message": "Há um cliente cadastrado com o telefone informado! <br><br><strong>Nome:</strong> {} <br> <strong>Telefone:</strong> {}".format(valida_cliente_get.nome, valida_cliente_get.telefone),
                },
            )
        
    return render(
        request,
        "pages/cadastro-cliente.html",
        {
            'servidores': servidor_queryset,
            'dispositivos': dispositivo_queryset,
            'sistemas': sistema_queryset,
            'indicadores': indicador_por_queryset,
            'formas_pgtos': forma_pgto_queryset,
            'planos': plano_queryset,
            'telas': telas_queryset,
            'page_group': page_group,
            'page': page,
        },
    )


# AÇÃO PARA CRIAR NOVO OBJETO PLANO MENSAL
@login_required
def CadastroPlanoAdesao(request):
    planos_mensalidades = Plano.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "plano_adesao"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                plano, created = Plano.objects.get_or_create(nome=request.POST.get('nome'), valor=int(request.POST.get('valor')), usuario=usuario)

                if created:
                    return render(
                            request,
                        'pages/cadastro-plano-adesao.html',
                        {
                            'planos_mensalidades': planos_mensalidades,
                            "success_message": "Novo Plano cadastrada com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        'pages/cadastro-plano-adesao.html',
                        {
                            'planos_mensalidades': planos_mensalidades,
                            "error_message": "Já existe um Plano com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-plano-adesao.html",
                    {
                        'planos_mensalidades': planos_mensalidades,
                        "error_message": "Não foi possível cadastrar este novo Plano. Verifique os logs!",
                    },
                )

    return render(
        request, 'pages/cadastro-plano-adesao.html', {'planos_mensalidades': planos_mensalidades, "page_group": page_group, "page": page}
    )

# AÇÃO PARA CRIAR NOVO OBJETO SERVIDOR
@login_required
def CadastroServidor(request):
    servidores = Servidor.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "servidor"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                servidor, created = Servidor.objects.get_or_create(nome=nome, usuario=usuario)

                if created:
                    return render(
                            request,
                        'pages/cadastro-servidor.html',
                        {
                            'servidores': servidores,
                            "success_message": "Novo Servidor cadastrado com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        'pages/cadastro-servidor.html',
                        {
                            'servidores': servidores,
                            "error_message": "Já existe um Servidor com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "'pages/cadastro-servidor.html",
                    {
                        'servidores': servidores,
                        "error_message": "Não foi possível cadastrar este novo Servidor. Verifique os logs!",
                    },
                )

    return render(
        request, 'pages/cadastro-servidor.html', {'servidores': servidores, "page_group": page_group, "page": page}
    )


# AÇÃO PARA CRIAR NOVO OBJETO FORMA DE PAGAMENTO (TIPOS_PGTO)
@login_required
def CadastroFormaPagamento(request):
    formas_pgto = Tipos_pgto.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "forma_pgto"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                formapgto, created = Tipos_pgto.objects.get_or_create(nome=nome, usuario=usuario)

                if created:
                    return render(
                            request,
                        'pages/cadastro-forma-pagamento.html',
                        {
                            'formas_pgto': formas_pgto,
                            "success_message": "Nova Forma de Pagamento cadastrada com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        'pages/cadastro-forma-pagamento.html',
                        {
                            'formas_pgto': formas_pgto,
                            "error_message": "Já existe uma Forma de Pagamento com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-forma-pagamento.html",
                    {
                        'formas_pgto': formas_pgto,
                        "error_message": "Não foi possível cadastrar esta nova Forma de Pagamento. Verifique os logs!",
                    },
                )

    return render(
        request, 'pages/cadastro-forma-pagamento.html', {'formas_pgto': formas_pgto, "page_group": page_group, "page": page}
    )


# AÇÃO PARA CRIAR NOVO OBJETO DISPOSITIVO
@login_required
def CadastroDispositivo(request):
    dispositivos = Dispositivo.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "dispositivo"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                dispositivo, created = Dispositivo.objects.get_or_create(nome=nome, usuario=usuario)

                if created:
                    return render(
                            request,
                        "pages/cadastro-dispositivo.html",
                        {
                            'dispositivos': dispositivos,
                            "success_message": "Novo Dispositivo cadastrado com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        "pages/cadastro-dispositivo.html",
                        {
                            'dispositivos': dispositivos,
                            "error_message": "Já existe um Dispositivo com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-dispositivo.html",
                    {
                        'dispositivos': dispositivos,
                        "error_message": "Não foi possível cadastrar este novo Dispositivo. Verifique os logs!",
                    },
                )

    return render(
        request, "pages/cadastro-dispositivo.html", {'dispositivos': dispositivos, "page_group": page_group, "page": page}
    )


# AÇÃO PARA CRIAR NOVO OBJETO APLICATIVO
@login_required
def CadastroAplicativo(request):
    aplicativos = Aplicativo.objects.filter(usuario=request.user).order_by('nome')
    usuario = request.user
    page_group = "cadastros"
    page = "aplicativo"

    if request.method == "POST":
        nome = request.POST.get("nome")

        if nome:

            try:
                # Consultando o objeto requisitado. Caso não exista, será criado.
                aplicativo, created = Aplicativo.objects.get_or_create(nome=nome, usuario=usuario)

                if created:
                    return render(
                            request,
                        "pages/cadastro-aplicativo.html",
                        {
                            'aplicativos': aplicativos,
                            "success_message": "Novo Aplicativo cadastrado com sucesso!",
                        },
                    )
                
                else:
                    return render(
                            request,
                        "pages/cadastro-aplicativo.html",
                        {
                            'aplicativos': aplicativos,
                            "error_message": "Já existe um Aplicativo com este nome!",
                        },
                    )
                
            except Exception as e:
                logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-aplicativo.html",
                    {
                        'aplicativos': aplicativos,
                        "error_message": "Não foi possível cadastrar este novo Aplicativo. Verifique os logs!",
                    },
                )

    return render(
        request, "pages/cadastro-aplicativo.html", {'aplicativos': aplicativos, "page_group": page_group, "page": page}
    )


############################################ DELETE VIEW ############################################

@login_required
def DeleteContaAplicativo(request, pk):
    if request.method == "DELETE":
        try:
            conta_app = ContaDoAplicativo.objects.get(pk=pk, usuario=request.user)
            conta_app.delete()

            return JsonResponse({'success_message': 'deu bom'}, status=200)
        
        except Aplicativo.DoesNotExist as erro1:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
            error_msg = 'Você tentou excluir uma conta de aplicativo que não existe.'
            
            return JsonResponse({'error_message': 'erro'}, status=500)
        
        except ProtectedError as erro2:
            logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
            error_msg = 'Essa conta de aplicativo não pôde ser excluída.'

            return JsonResponse(status=500)
    else:
        return JsonResponse({'error_message': 'erro'}, status=500)
    

@login_required
def DeleteAplicativo(request, pk):
    try:
        aplicativo = Aplicativo.objects.get(pk=pk, usuario=request.user)
        aplicativo.delete()
    except Aplicativo.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Aplicativo não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    else:
        return redirect('cadastro-aplicativo')
    

@login_required
def DeleteDispositivo(request, pk):
    try:
        dispositivo = Dispositivo.objects.get(pk=pk, usuario=request.user)
        dispositivo.delete()
    except Dispositivo.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Dispositivo não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    else:
        return redirect('cadastro-dispositivo')
    

@login_required
def DeleteFormaPagamento(request, pk):
    try:
        formapgto = Tipos_pgto.objects.get(pk=pk, usuario=request.user)
        formapgto.delete()
    except Tipos_pgto.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Servidor não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    else:
        return redirect('cadastro-forma-pagamento')
    

@login_required
def DeleteServidor(request, pk):
    try:
        servidor = Servidor.objects.get(pk=pk, usuario=request.user)
        servidor.delete()
    except Servidor.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Servidor não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    else:
        return redirect('cadastro-servidor')
    

@login_required
def DeletePlanoAdesao(request, pk):
    try:
        plano_mensal = Plano.objects.get(pk=pk, usuario=request.user)
        plano_mensal.delete()
    except Plano.DoesNotExist as erro1:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s] [USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Plano não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )

    return redirect('cadastro-plano-adesao')