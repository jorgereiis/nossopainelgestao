from .models import (Cliente, Servidor, Dispositivo, Aplicativo, Tipos_pgto, Plano, Qtd_tela, Mensalidade, ContaDoAplicativo)
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.db.models.deletion import ProtectedError
from django.contrib.auth.views import LoginView, PasswordResetView
from django.core.exceptions import ValidationError
from django.views.generic.list import ListView
from babel.numbers import format_currency
from .models import definir_dia_pagamento
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from django.db.models import Q
from datetime import timedelta
from datetime import datetime
from .forms import LoginForm
import pandas as pd
import json
import time
import logging

logger = logging.getLogger(__name__)

############################################ AUTH VIEW ############################################

# PÁGINA DE LOGIN
class Login(LoginView):
    template_name = 'login.html'
    form_class = LoginForm

############################################ LIST VIEW ############################################

class ListaClientes(LoginRequiredMixin, ListView):
    """
        AÇÃO PARA LISTAGEM DE CLIENTES TOTAIS, CONSIDERANDO CANCELADOS E ATIVOS
    """
    model = Cliente
    template_name = "pages/lista-clientes.html"
    paginate_by = 15

    # QUERY PARA O CAMPO DE PESQUISA DO DASHBOARD
    def get_queryset(self):
        query = self.request.GET.get("q")
        queryset = (
            Cliente.objects.filter(usuario=self.request.user)
            .order_by("-data_adesao")
        )
        
        if query:
            queryset = queryset.filter(nome__icontains=query)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clientes = Cliente.objects.filter(usuario=self.request.user)
        indicadores = Cliente.objects.all()
        servidores = Servidor.objects.all()
        formas_pgtos = Tipos_pgto.objects.all()
        planos = Plano.objects.all().order_by('valor')
        telas = Qtd_tela.objects.all().order_by('telas')
        dispositivos = Dispositivo.objects.all().order_by('nome')
        aplicativos = Aplicativo.objects.all().order_by('nome')
        page_group = 'clientes'
        page = 'lista-clientes'
        range_num = range(1,32)

        context.update(
            {
                "clientes": clientes,
                "indicadores": indicadores,
                "servidores": servidores,
                "formas_pgtos": formas_pgtos,
                "dispositivos": dispositivos,
                "aplicativos": aplicativos,
                "planos": planos,
                "telas": telas,
                "range": range_num,
                "page_group": page_group,
                "page": page,
            }
        )
        return context


class TabelaDashboard(LoginRequiredMixin, ListView):
    """
        AÇÃO PARA LISTAGEM DE CLIENTES, SUAS MENSALIDADES E OUTRAS INFORMAÇÕES EXIBIDAS NO DASHBOARD
    """
    login_url = "login"
    model = Cliente
    template_name = "dashboard.html"
    paginate_by = 15


    # QUERY PARA O CAMPO DE PESQUISA DO DASHBOARD
    def get_queryset(self):
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

    # FUNÇÃO PARA RETORNAR RESULTADOS DAS QUERY UTILIZADAS NO DASHBOARD
    def get_context_data(self, **kwargs):
        moeda = "BRL"
        hoje = timezone.localtime().date()
        ano_atual = timezone.localtime().year
        proxima_semana = hoje + timedelta(days=7)
        context = super().get_context_data(**kwargs)
        total_clientes = self.get_queryset().count()
        mes_atual = timezone.localtime().date().month
        page = 'dashboard'

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

        context.update(
            {
                "hoje": hoje,
                "page": page,
                "total_clientes": total_clientes,
                "valor_total_pago": valor_total_pago,
                "novos_clientes_qtd": novos_clientes_qtd,
                "clientes_em_atraso": clientes_em_atraso,
                "valor_total_receber": valor_total_receber,
                "valor_total_pago_qtd": valor_total_pago_qtd,
                "valor_total_receber_qtd": valor_total_receber_qtd,
                "clientes_cancelados_qtd": clientes_cancelados_qtd,
            }
        )
        return context

############################################ UPDATE VIEW ############################################

from .models import Mensalidade

@login_required
def reativar_cliente(request, cliente_id):
    cliente = Cliente.objects.get(pk=cliente_id, usuario=request.user)
    data_hoje = timezone.localtime().date()

    # muda o valor do atributo "cancelado" de True para False
    # define o valor de "data_cancelamento" como None
    # altera o valor de "data_adesao" para a data do momento da requisição
    cliente.data_adesao = data_hoje
    cliente.data_pagamento = definir_dia_pagamento(data_hoje.day)
    cliente.data_cancelamento = None
    cliente.cancelado = False
    dia = cliente.data_pagamento
    mes = data_hoje.month
    ano = data_hoje.year

    # tratando possíveis erros
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
        # registra erro no log
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
        return JsonResponse({"error_message": "Ocorreu um erro ao tentar reativar esse cliente."})

    # se deu tudo certo, retorna confirmação
    return JsonResponse({"success_message_activate": "Reativação feita!"})


# AÇÃO DE PAGAR MENSALIDADE
@login_required
def pagar_mensalidade(request, mensalidade_id):

        mensalidade = Mensalidade.objects.get(pk=mensalidade_id, usuario=request.user)

        # realiza as modificações na mensalidade paga
        mensalidade.dt_pagamento = timezone.localtime().date()
        mensalidade.pgto = True
        try:
            mensalidade.save()
        except Exception as erro:
            logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
            return JsonResponse({"error_message": "Ocorreu um erro ao tentar pagar essa mensalidade."})
        # redireciona para a página anterior
        return JsonResponse({"success_message_invoice": "Mensalidade paga!"})


# AÇÃO PARA CANCELAMENTO DE CLIENTE
@login_required
def cancelar_cliente(request, cliente_id):
    if request.user.is_authenticated:
        cliente = Cliente.objects.get(pk=cliente_id, usuario=request.user)

        # realiza as modificações no cliente
        cliente.cancelado = True
        cliente.data_cancelamento = timezone.localtime().date()
        try:
            cliente.save()
        except Exception as erro:
            logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro, exc_info=True)
            return JsonResponse({"error_message": "Ocorreu um erro ao tentar cancelar esse cliente."}, status=500)

        # retorna a mensagem de sucesso como resposta JSON
        return JsonResponse({"success_message_cancel": "Eita! mais um cliente cancelado?! "})
    else:
        redirect("login")


# AÇÃO PARA EDITAR O OBJETO PLANO MENSAL
@login_required
def EditarPlanoAdesao(request, plano_id):
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
                # Capturando outras exceções e renderizando a página novamente com a mensagem de erro
                return render(
                    request,
                    "pages/cadastro-plano-adesao.html",
                    {
                        'planos_mensalidades': planos_mensalidades,
                        "error_message": "Já existe um plano com este nome!",
                    },
                )

            except Exception as erro2:
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
                # Capturando outros possíveis erros ao tentar salvar o servidor
                return render(
                    request,
                    "pages/cadastro-plano-adesao.html",
                    {
                        'planos_mensalidades': planos_mensalidades,
                        "error_message": "Ocorreu um erro ao salvar o plano. Verifique o log!",
                    },
                )
            
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
            logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
            return render(request, "pages/importar-cliente.html",
                {"error_message": "Erro ao tentar ler planilha. Verifique o arquivo e tente novamente."},)
        
        # transforma cada linha dos dados lidos da planilha em um dicionário para que seja iterado no loop FOR.
        lista_de_objetos = dados.to_dict('records')

        with transaction.atomic(): # Adicionando a transação atomica
            i=0
            for dado in lista_de_objetos:
                i+=1
                servidor_import = str(dado['servidor']).replace(" ", "") if str(dado['servidor']) != 'nan' else None
                dispositivo_import = str(dado['dispositivo']) if str(dado['dispositivo']) != 'nan' else None
                sistema_import = str(dado['sistema']) if str(dado['sistema']) != 'nan' else None
                device_id_import = str(dado['device_id']).replace(" ", "") if str(dado['device_id']) != 'nan' else None
                email_import = str(dado['email']).replace(" ", "") if str(dado['email']) != 'nan' else None
                device_key_import = str(dado['device_key']).replace(" ", "").split('.')[0] if '.' in str(dado['device_key']) else None
                nome_import = str(dado['nome']).title() if str(dado['nome']) != 'nan' else None
                telefone_import = str(dado['telefone']).replace(" ", "") if str(dado['telefone']) != 'nan' else None
                indicado_por_import = str(dado['indicado_por']) if str(dado['indicado_por']) != 'nan' else None
                data_pagamento_import = int(dado['data_pagamento']) if dado['data_pagamento'] != 'nan' else None
                forma_pgto_import = str(dado['forma_pgto']) if str(dado['forma_pgto']) != 'nan' else 'PIX'
                tipo_plano_import = str(dado['tipo_plano']).replace(" ", "").title() if str(dado['tipo_plano']) != 'nan' else None
                plano_valor_import = int(dado['plano_valor']) if str(dado['plano_valor']) != 'nan' else None
                telas_import = str(dado['telas']).replace(" ", "") if str(dado['telas']) != 'nan' else None
                data_adesao_import = dado['data_adesao'] if dado['data_adesao'] != 'nan' else None

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
                            device_key = device_key_import
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
                    logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
    plano_queryset = Plano.objects.filter(usuario=request.user)
    telas_queryset = Qtd_tela.objects.all().order_by('telas')
    forma_pgto_queryset = Tipos_pgto.objects.filter(usuario=request.user)
    servidor_queryset = Servidor.objects.filter(usuario=request.user).order_by('nome')
    sistema_queryset = Aplicativo.objects.filter(usuario=request.user).order_by('-nome')
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
                return render(
                    request,
                    "pages/cadastro-cliente.html",
                    {
                        "error_message": "Não foi possível cadastrar cliente!"
                    },
                )
            
            except Exception as erro2:
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
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
                logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], e, exc_info=True)
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
def DeleteAplicativo(request, pk):
    try:
        aplicativo = Aplicativo.objects.get(pk=pk, usuario=request.user)
        aplicativo.delete()
    except Aplicativo.DoesNotExist as erro1:
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
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
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro1, exc_info=True)
        return HttpResponseNotFound(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )
    except ProtectedError as erro2:
        logger.error('[%s][USER][%s] [IP][%s] [ERRO][%s]', timezone.localtime(), request.user, request.META['REMOTE_ADDR'], erro2, exc_info=True)
        error_msg = 'Este Plano não pode ser excluído porque está relacionado com algum cliente.'
        return HttpResponseBadRequest(
            json.dumps({'error_delete': error_msg}), content_type='application/json'
        )

    return redirect('cadastro-plano-adesao')