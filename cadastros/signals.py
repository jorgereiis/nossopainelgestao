from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from datetime import datetime
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from .models import Mensalidade, Cliente, Plano, definir_dia_pagamento


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

        if vencimento.day <= timezone.localtime().date().day:
            # Define o mês/ano de vencimento de acordo com o plano do cliente
            if instance.plano.nome == Plano.CHOICES[0][0]:
                vencimento += relativedelta(months=1)
            elif instance.plano.nome == Plano.CHOICES[1][0]:
                vencimento += relativedelta(months=6)
            elif instance.plano.nome == Plano.CHOICES[2][0]:
                vencimento += relativedelta(years=1)

        Mensalidade.objects.create(
            cliente=instance, valor=instance.plano.valor, dt_vencimento=vencimento
        )


# CRIA NOVA MENSALIDADE APÓS A ATUAL SER PAGA
@receiver(pre_save, sender=Mensalidade)
def criar_nova_mensalidade(sender, instance, **kwargs):
    if instance.dt_pagamento and instance.pgto:
        dia_vencimento = instance.dt_vencimento.day
        dia_atual = timezone.localtime().date().day

        # Verifica se o dia do vencimento da mensalidade anterior é maior que o dia atual.
        # Se verdadeiro, define a variável `novo_vencimento` como a mesma da mensalidade anterior.
        if dia_vencimento > dia_atual:
            novo_vencimento = datetime(
                instance.dt_vencimento.year,
                instance.dt_vencimento.month,
                dia_vencimento,
            )
        # Se não, define a variável tendo um nova data baseada no `dia_atual`
        else:
            novo_dia_de_pagamento = definir_dia_pagamento(dia_atual)
            novo_vencimento = datetime(
                instance.dt_pagamento.year,
                instance.dt_pagamento.month,
                novo_dia_de_pagamento,
            )

        # Define o mês/ano de vencimento de acordo com o plano do cliente
        if instance.cliente.plano.nome == Plano.CHOICES[0][0]:
            novo_vencimento += relativedelta(months=1)
        elif instance.cliente.plano.nome == Plano.CHOICES[1][0]:
            novo_vencimento += relativedelta(months=6)
        elif instance.cliente.plano.nome == Plano.CHOICES[2][0]:
            novo_vencimento += relativedelta(years=1)

        Mensalidade.objects.create(
            cliente=instance.cliente,
            valor=instance.cliente.plano.valor,
            dt_vencimento=novo_vencimento,
        )
