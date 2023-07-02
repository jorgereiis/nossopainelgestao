from .models import Mensalidade, Cliente, Plano, definir_dia_pagamento
from django.db.models.signals import post_save, pre_save
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from django.dispatch import receiver
from django.utils import timezone
import calendar


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
    if instance.dt_pagamento and instance.pgto and hoje - timedelta(days=7) >= instance.dt_vencimento:
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