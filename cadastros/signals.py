from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from datetime import datetime
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from .models import Mensalidade, Cliente, Plano, definir_dia_pagamento

# funcão para definir o dia de pagamento
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
        dia = 30
    return dia_pagamento

# Atualiza o `ultimo_pagamento` do cliente da mensalidade
@receiver(post_save, sender=Mensalidade)
def atualiza_ultimo_pagamento(sender, instance, **kwargs):
    cliente = instance.cliente

    # verifica se `dt_pagamento` e `pgto` da Mensalidade são verdadeiros
    if instance.dt_pagamento and instance.pgto:
        # verifica e atualiza o `ultimo_pagamento` do cliente.
        if (
            not cliente.ultimo_pagamento
            or instance.dt_pagamento > cliente.ultimo_pagamento
        ):
            cliente.ultimo_pagamento = instance.dt_pagamento
            cliente.save()


# CRIA NOVA MENSALIDADE QUANDO UM NOVO CLIENTE FOR CRIADO
@receiver(post_save, sender=Cliente)
def criar_mensalidade(sender, instance, created, **kwargs):
    if created:
        if instance.ultimo_pagamento:
            dia = instance.ultimo_pagamento.day
            dia_pagamento = definir_dia_pagamento(dia)

        elif instance.data_adesao and instance.data_pagamento == None:
            dia = instance.data_adesao.day
            dia_pagamento = definir_dia_pagamento(dia)

        else:
            dia_pagamento = instance.data_pagamento

        mes = timezone.localtime().date().month
        ano = timezone.localtime().date().year
        vencimento = datetime(ano, mes, dia_pagamento)

        """
        # Se o dia de vencimento for menor do que a data de hoje,
        # cria a primeira mensalidade com vencimento para o próximo mês
        # ou para o mês de acordo com o plano mensal escolhido.
        # Se não, cria para o mês atual.
        if vencimento.day < timezone.localtime().date().day:
            if instance.plano.nome == Plano.CHOICES[0][0]:
                vencimento += relativedelta(months=1)
            elif instance.plano.nome == Plano.CHOICES[1][0]:
                vencimento += relativedelta(months=6)
            elif instance.plano.nome == Plano.CHOICES[2][0]:
                vencimento += relativedelta(years=1)
        """
        Mensalidade.objects.create(
            cliente=instance, valor=instance.plano.valor, dt_vencimento=vencimento
        )


# CRIA NOVA MENSALIDADE APÓS A ATUAL SER PAGA
@receiver(pre_save, sender=Mensalidade)
def criar_nova_mensalidade(sender, instance, **kwargs):
    if instance.dt_pagamento and instance.pgto:
        data_vencimento_anterior = instance.dt_vencimento # recebe a data de vencimento da mensalidade que foi paga
        data_atual = timezone.localtime().date() # recebe a data de hoje

        # Verifica se a data de vencimento da mensalidade anterior é maior que a data atual.
        # Se verdadeiro, significa que a mensalidade anterior foi paga antecipada e 
        # atribua à `nova_data_vencimento` o valor de `data_vencimento_anterior`
        if data_vencimento_anterior > data_atual:
            nova_data_vencimento = data_vencimento_anterior 
        
        # Se não, significa que a mensalidade foi paga em atraso e atribui à `nova_data_vencimento` o 
        # resultado obtido da função `definir_dia_pagamento`
        else:
            novo_dia_de_pagamento = definir_dia_renovacao(data_atual.day)
            nova_data_vencimento = datetime(
                data_vencimento_anterior.year,
                data_vencimento_anterior.month,
                novo_dia_de_pagamento,
            )

        # Define o mês/ano de vencimento de acordo com o plano do cliente
        if instance.cliente.plano.nome == Plano.CHOICES[0][0]:
            nova_data_vencimento += relativedelta(months=1)
        elif instance.cliente.plano.nome == Plano.CHOICES[1][0]:
            nova_data_vencimento += relativedelta(months=6)
        elif instance.cliente.plano.nome == Plano.CHOICES[2][0]:
            nova_data_vencimento += relativedelta(years=1)

        Mensalidade.objects.create(
            cliente=instance.cliente,
            valor=instance.cliente.plano.valor,
            dt_vencimento=nova_data_vencimento,
        )

        # Atualiza a `data_pagamento` do cliente com o valor de `nova_data_vencimento` da mensalidade.
        instance.cliente.data_pagamento = nova_data_vencimento.day
        instance.cliente.save()
