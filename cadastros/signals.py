from .models import Mensalidade, Cliente, Plano, PlanoIndicacao, definir_dia_pagamento
from .utils import check_number_status, get_label_contact, add_or_remove_label_contact, get_all_labels, criar_label_se_nao_existir
from django.db.models.signals import post_save, pre_save
import os, json, random, time, requests, re
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from django.dispatch import receiver
from django.contrib import messages
from django.utils import timezone
from .models import SessaoWpp

URL_API_WPP = os.getenv("URL_API_WPP")

# Função para definir o dia de pagamento com base em um dia fornecido
def definir_dia_renovacao(dia):
    if dia in range(5, 10):
        dia_pagamento = 5
    elif dia in range(10, 15):
        dia_pagamento = 10
    elif dia in range(15, 20):
        dia_pagamento = 15
    elif dia in range(20, 25):
        dia_pagamento = 20
    elif dia in range(25, 30):
        dia_pagamento = 25
    else:
        dia_pagamento = 30  # Se nenhum dos intervalos anteriores for correspondido, atribui o dia 30 como padrão
    return dia_pagamento


# Signal para atualizar o `ultimo_pagamento` do cliente com base na Mensalidade
@receiver(post_save, sender=Mensalidade)
def atualiza_ultimo_pagamento(sender, instance, **kwargs):
    cliente = instance.cliente

    # Verifica se `dt_pagamento` e `pgto` da Mensalidade são verdadeiros
    if instance.dt_pagamento and instance.pgto:
        # Verifica se o `ultimo_pagamento` do cliente não existe ou se a data de pagamento da Mensalidade é posterior ao `ultimo_pagamento`
        if not cliente.ultimo_pagamento or instance.dt_pagamento > cliente.ultimo_pagamento:
            cliente.ultimo_pagamento = instance.dt_pagamento
            cliente.save()


# CRIA NOVA MENSALIDADE QUANDO UM NOVO CLIENTE FOR CRIADO
@receiver(post_save, sender=Cliente)
def criar_mensalidade(sender, instance, created, **kwargs):
    request = kwargs.get('request')
    if request is not None and request.user.is_authenticated:
        usuario = request.user

    # Verifica se o Cliente acabou de ser criado
    if created:
        # Define o dia de pagamento com base em diferentes cenários
        if instance.ultimo_pagamento:
            dia = instance.ultimo_pagamento.day
            dia_pagamento = definir_dia_pagamento(dia)
        elif instance.data_adesao and instance.data_pagamento is None:
            dia = instance.data_adesao.day
            dia_pagamento = definir_dia_pagamento(dia)
        else:
            dia_pagamento = instance.data_pagamento

        # Obtém o mês e o ano atual
        mes = timezone.localtime().date().month
        ano = timezone.localtime().date().year

        # Define a data de vencimento com base no dia de pagamento
        vencimento = datetime(ano, mes, dia_pagamento)

        # Se o dia de vencimento for menor do que a data atual,
        # cria a primeira mensalidade com vencimento para o próximo mês
        # ou para o mês de acordo com o plano mensal escolhido.
        # Caso contrário, cria para o mês atual.
        if vencimento.day < timezone.localtime().date().day:
            if instance.plano.nome == Plano.CHOICES[0][0]:
                vencimento += relativedelta(months=1)
            elif instance.plano.nome == Plano.CHOICES[1][0]:
                vencimento += relativedelta(months=3)
            elif instance.plano.nome == Plano.CHOICES[2][0]:
                vencimento += relativedelta(months=6)
            elif instance.plano.nome == Plano.CHOICES[3][0]:
                vencimento += relativedelta(years=1)

        # Cria uma nova instância de Mensalidade com os valores definidos
        Mensalidade.objects.create(
            cliente=instance,
            valor=instance.plano.valor,
            dt_vencimento=vencimento,
            usuario=instance.usuario,
        )


# CRIA NOVA MENSALIDADE APÓS A ATUAL SER PAGA
@receiver(pre_save, sender=Mensalidade)
def criar_nova_mensalidade(sender, instance, **kwargs):
    hoje = timezone.localtime().date()

    # Verificar se a mensalidade está paga e a data de vencimento está dentro do intervalo desejado
    if instance.dt_pagamento and instance.pgto and not instance.dt_vencimento < hoje - timedelta(days=7):
        data_vencimento_anterior = instance.dt_vencimento  # recebe a data de vencimento da mensalidade que foi paga

        # Verifica se a data de vencimento da mensalidade anterior é maior que a data atual.
        # Se verdadeiro, significa que a mensalidade anterior foi paga antecipadamente e
        # atribui à `nova_data_vencimento` o valor de `data_vencimento_anterior`
        if data_vencimento_anterior > hoje:
            nova_data_vencimento = data_vencimento_anterior

        # Se não, significa que a mensalidade foi paga em atraso e atribui à `nova_data_vencimento` baseado no valor de `hoje`
        else:
            nova_data_vencimento = datetime(
                hoje.year,
                hoje.month,
                hoje.day,
            )

        # Define o mês/ano de vencimento de acordo com o plano do cliente
        if instance.cliente.plano.nome == Plano.CHOICES[0][0]:
            nova_data_vencimento += relativedelta(months=1)
        elif instance.cliente.plano.nome == Plano.CHOICES[1][0]:
            nova_data_vencimento += relativedelta(months=3)
        elif instance.cliente.plano.nome == Plano.CHOICES[2][0]:
            nova_data_vencimento += relativedelta(months=6)
        elif instance.cliente.plano.nome == Plano.CHOICES[3][0]:
            nova_data_vencimento += relativedelta(years=1)

        # Cria uma nova instância de Mensalidade com os valores atualizados
        Mensalidade.objects.create(
            cliente=instance.cliente,
            valor=instance.cliente.plano.valor,
            dt_vencimento=nova_data_vencimento,
            usuario=instance.usuario,
        )

        # Atualiza a `data_pagamento` do cliente com o dia de `nova_data_vencimento` da mensalidade.
        instance.cliente.data_pagamento = nova_data_vencimento.day
        instance.cliente.save()


# REALIZA ENVIO PARA CLIENTE INDICADOR QUANDO HOUVER CADASTRO DE NOVO CLIENTE COM INDICAÇÃO
@receiver(post_save, sender=Cliente)
def envio_apos_novo_cadastro(sender, instance, created, **kwargs):
    if created:
        usuario = instance.usuario
        cliente = instance
        nome_cliente = str(cliente)
        primeiro_nome = nome_cliente.split(' ')[0]
        telefone = str(cliente.telefone)
        telefone_formatado = '55' + re.sub(r'\D', '', telefone)
        indicador = cliente.indicado_por
        tipo_envio = "Cadastro"

        try:
            token_user = SessaoWpp.objects.get(usuario=usuario)
        except SessaoWpp.DoesNotExist:
            pass

        mensagem = f"""Obrigado, {primeiro_nome}. O seu pagamento foi confirmado e o seu acesso já foi disponibilizado!\n\nA partir daqui, caso precise de algum auxílio pode entrar em contato.\nPeço que salve o nosso contato para que receba as nossas notificações aqui no WhatsApp."""

        enviar_mensagem(telefone_formatado, mensagem, usuario, token_user.token, nome_cliente,tipo_envio)

        if cliente.indicado_por:
            envio_apos_nova_indicacao(usuario, cliente, cliente.indicado_por)


# Função para realizar envio de mensagem após cadastro de um novo cliente. Além disso, verifica se o novo cliente veio por indicação e realiza envio ao cliente indicador.
def envio_apos_nova_indicacao(usuario, novo_cliente, cliente_indicador):
    nome_cliente = str(cliente_indicador)
    primeiro_nome = nome_cliente.split(' ')[0]
    telefone = str(cliente_indicador.telefone)
    telefone_formatado = '55' + re.sub(r'\D', '', telefone)
    tipo_envio = "Indicação"
    now = datetime.now()
    hora_atual = now.time()

    mensalidade_em_aberto = Mensalidade.objects.filter(
        cliente=cliente_indicador,
        dt_pagamento=None,
        dt_cancelamento=None,
        pgto=False,
        cancelado=False
    ).first()

    mensalidade_mes_atual = Mensalidade.objects.filter(
        cliente=cliente_indicador,
        dt_vencimento__month=now.month,
        dt_vencimento__year=now.year
    ).first()

    qtd_indicacoes = Cliente.objects.filter(
        indicado_por=cliente_indicador,
        data_adesao__gte=now.replace(day=1)
    ).count()

    valor_desconto = PlanoIndicacao.objects.filter(tipo_plano="desconto").first()
    if valor_desconto:
        valor_desconto = valor_desconto.valor
    else:
        valor_desconto = 0  # Tratar o caso onde não há plano de desconto

    try:
        token_user = SessaoWpp.objects.get(usuario=usuario)
    except SessaoWpp.DoesNotExist:
        return  # Tratar o caso onde a sessão WPP não existe

    # Definir a saudação de acordo com o horário atual
    if hora_atual < datetime.strptime("12:00:00", "%H:%M:%S").time():
        saudacao = 'Bom dia'
    elif hora_atual < datetime.strptime("18:00:00", "%H:%M:%S").time():
        saudacao = 'Boa tarde'
    else:
        saudacao = 'Boa noite'

    # Definir tipo da mensagem com base na quantidade de indicações já realizadas

    if qtd_indicacoes == 1 and mensalidade_em_aberto:
        valor = mensalidade_em_aberto.valor - valor_desconto
        valor = max(valor, 13.99) # Garantir que o valor não fique abaixo de 13.99
        valor_formatado = f"{valor:.2f}".replace(",", ".")
        vencimento = f"{mensalidade_em_aberto.dt_vencimento.day}/{mensalidade_em_aberto.dt_vencimento.month}"       
        mensagem = f"""Olá, {primeiro_nome}. {saudacao}!\n\nAgradeço pela indicação do(a) *{novo_cliente.nome}*.\nA adesão dele(a) foi concluída e por isso estamos lhe bonificando com desconto.\n\n⚠ *FIQUE ATENTO AO SEU VENCIMENTO:*\n\n- [{vencimento}] R$ {valor_formatado}\n\nObrigado! 😁"""
        mensalidade_em_aberto.valor = valor
        mensalidade_em_aberto.save()

        enviar_mensagem(
            telefone_formatado,
            mensagem,
            usuario,
            token_user.token,
            nome_cliente,
            tipo_envio
        )

    elif qtd_indicacoes == 2:

        if mensalidade_mes_atual.valor < 20 and mensalidade_mes_atual.pgto:

            valor = mensalidade_em_aberto.valor - valor_desconto
            valor = max(valor, 5)
            valor_formatado = f"{valor:.2f}".replace(",", ".")
            vencimento = f"{mensalidade_em_aberto.dt_vencimento.day}/{mensalidade_em_aberto.dt_vencimento.month}"       
            mensagem = f"""Olá, {primeiro_nome}. {saudacao}!\n\nAgradeço pela indicação do(a) *{novo_cliente.nome}*.\nA adesão dele(a) foi concluída e por isso estamos lhe bonificando com desconto.\n\n⚠ *FIQUE ATENTO AO SEU VENCIMENTO:*\n\n- [{vencimento}] R$ {valor_formatado}\n\nObrigado! 😁"""
            mensalidade_em_aberto.valor = valor
            mensalidade_em_aberto.save()

        else:    

            linhas_indicacoes = []

            for indicacao in Cliente.objects.filter(indicado_por=cliente_indicador, data_adesao__gte=datetime.now().replace(day=1)):
                data_adesao = indicacao.data_adesao.strftime('%d/%m')
                nome = indicacao.nome
                linhas_indicacoes.append(f"- [{data_adesao}] [{nome}]")

            mensagem = f"""🎉 *PARABÉNS PELAS INDICAÇÕES!* 🎉\n\nOlá, {primeiro_nome}. {saudacao}! Tudo bem?\n\nAgradecemos muito pela sua parceria e confiança em nossos serviços. Este mês, registramos as seguintes indicações feitas por você:\n\n""" + "\n".join(linhas_indicacoes) + """\n\nCom isso, você tem um *bônus de R$ 50* para receber de nós! 😍\n\nAgora, você pode escolher como prefere:\n\n- *Receber o valor via PIX* em sua conta.\n- *Aplicar como desconto* nas suas próximas mensalidades.\n\nNos avise aqui qual opção prefere, e nós registraremos a sua bonificação.."""
        
        enviar_mensagem(
            telefone_formatado,
            mensagem,
            usuario,
            token_user.token,
            nome_cliente,
            tipo_envio
        )


# Função para enviar mensagens e registrar em arquivo de log
def enviar_mensagem(telefone, mensagem, usuario, token, cliente, tipo):
    url = URL_API_WPP + '/{}/send-message'.format(usuario)
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
    log_directory = './logs/Envios indicacoes realizadas/'
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
                log_file.write('[{}] [TIPO][{}] [USUÁRIO][{}] [CLIENTE][{}] Mensagem enviada!\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), tipo, usuario, cliente))
            break  # Sai do loop se a resposta for de sucesso
        elif response.status_code == 400:
            response_data = json.loads(response.text)
            error_message = response_data.get('message')
            with open(log_filename, 'a') as log_file:
                log_file.write('[{}] [TIPO][{}] [USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), tipo, usuario, cliente, response.status_code, tentativa, error_message))
        else:
            print(f"[ERRO ENVIO DE MSGS] [{response.status_code}] \n [{response.text}]")
            response_data = json.loads(response.text)
            error_message = response_data.get('message')
            with open(log_filename, 'a') as log_file:
                log_file.write('[{}] [TIPO][{}] [USUÁRIO][{}] [CLIENTE][{}] [CODE][{}] [TENTATIVA {}] - {}\n'.format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), tipo, usuario, cliente, response.status_code, tentativa, error_message))

        # Incrementa o número de tentativas
        tentativa += 1

        # Tempo de espera aleatório entre cada tentativa com limite máximo de 50 segundos
        tempo_espera = random.uniform(20, 50)
        time.sleep(tempo_espera)


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
        telefone = re.sub(r'\D+', '', instance.telefone)
        telefone_com_55 = f'55{telefone}'

        # Obtém token da sessão
        try:
            token = SessaoWpp.objects.get(usuario=instance.usuario).token
        except SessaoWpp.DoesNotExist:
            print(f"⚠️ Sessão do WhatsApp não encontrada para o usuário {instance.usuario}")
            return

        # Verifica se número existe no WhatsApp
        try:
            numero_existe = check_number_status(telefone_com_55, token)
            if not numero_existe:
                print(f"⚠️ Número {telefone} não é válido no WhatsApp.")
                return
        except Exception as e:
            print(f"❌ Erro ao verificar número no WhatsApp: {e}")
            return

        # Obtém labels atuais
        try:
            labels_atuais = get_label_contact(telefone_com_55, token)
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
            nova_label_id = criar_label_se_nao_existir(label_desejada, token, hex_color=hex_color)
            if not nova_label_id:
                print(f"⚠️ Não foi possível obter ou criar a label '{label_desejada}'")
                return

            # Altera labels do contato
            add_or_remove_label_contact(
                label_id_1=nova_label_id,
                label_id_2=labels_atuais,
                label_name=label_desejada,
                telefone=telefone_com_55,
                token=token
            )

        except Exception as e:
            print(f"❌ Erro ao alterar label do contato: {e}")