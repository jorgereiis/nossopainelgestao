from django.contrib import admin
from .models import (
    Plano,
    Cliente,
    Qtd_tela,
    Servidor,
    SessaoWpp,
    Aplicativo,
    Tipos_pgto,
    Mensalidade,
    Dispositivo,
    HorarioEnvios,
    DadosBancarios,
    PlanoIndicacao,
    SecretTokenAPI,
    ContaDoAplicativo,
    MensagemEnviadaWpp,
)


class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nome",
        "telefone",
        "servidor",
        "dispositivo",
        "sistema",
        "data_pagamento",
        "forma_pgto",
        "plano",
        "telas",
        "data_adesao",
        "data_cancelamento",
        "ultimo_pagamento",
        "indicado_por",
        "notas",
        "cancelado",
        "usuario",
    )
    list_filter = (
        "servidor",
        "usuario",
        'forma_pgto',
        'data_pagamento',
        'cancelado',
        'sistema',
    )

    search_fields = (
        'nome',
        'telefone',
    )


class MensalidadeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cliente",
        "usuario",
        "dt_vencimento",
        "dt_pagamento",
        "dt_cancelamento",
        "valor",
        "pgto",
        "cancelado",
    )

    list_filter = (
        'dt_vencimento',
        'dt_pagamento',
        'pgto',
        'cancelado',
        "usuario",
    )

    search_fields = ("cliente__nome",)


class PlanoAdmin(admin.ModelAdmin):
    list_display = ("nome", "valor")


class ContaDoAplicativoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "app", "device_id", "device_key", "email", "verificado")
    list_filter = ("usuario", "app")
    search_fields = ("email", "cliente__nome",)


class SessaoWppAdmin(admin.ModelAdmin):
    list_display = ("usuario", "token", "dt_inicio")


class MensagemEnviadaWppAdmin(admin.ModelAdmin):
    list_display = ("telefone", "data_envio")


admin.site.register(MensagemEnviadaWpp, MensagemEnviadaWppAdmin)
admin.site.register(ContaDoAplicativo, ContaDoAplicativoAdmin)
admin.site.register(Mensalidade, MensalidadeAdmin)
admin.site.register(SessaoWpp, SessaoWppAdmin)
admin.site.register(Cliente, ClienteAdmin)
admin.site.register(Plano, PlanoAdmin)
admin.site.register(PlanoIndicacao)
admin.site.register(DadosBancarios)
admin.site.register(SecretTokenAPI)
admin.site.register(HorarioEnvios)
admin.site.register(Dispositivo)
admin.site.register(Aplicativo)
admin.site.register(Tipos_pgto)
admin.site.register(Qtd_tela)
admin.site.register(Servidor)