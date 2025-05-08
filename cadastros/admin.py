from django.contrib import admin
from .models import (
    Plano,
    Cliente,
    Servidor,
    SessaoWpp,
    Aplicativo,
    Tipos_pgto,
    Mensalidade,
    Dispositivo,
    ConteudoM3U8,
    HorarioEnvios,
    SecretTokenAPI,
    DadosBancarios,
    PlanoIndicacao,
    ContaDoAplicativo,
    MensagemEnviadaWpp,
)


# --- ADMINISTRADORES ---

class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        "id", "nome", "telefone", "uf", "servidor", "dispositivo", "sistema",
        "data_vencimento", "forma_pgto", "plano", "data_adesao",
        "data_cancelamento", "ultimo_pagamento", "indicado_por", "notas",
        "cancelado", "nao_enviar_msgs", "usuario",
    )
    list_filter = ("servidor", "usuario", "forma_pgto", "data_vencimento", "cancelado", "sistema")
    search_fields = ("nome", "telefone")
    ordering = ("-data_adesao",)


class MensalidadeAdmin(admin.ModelAdmin):
    list_display = (
        "id", "cliente", "usuario", "dt_vencimento", "dt_pagamento",
        "dt_cancelamento", "valor", "pgto", "cancelado", "notificacao_wpp1", "dt_notif_wpp1",
    )
    list_editable = ("pgto", "cancelado", "dt_cancelamento", "dt_pagamento", "dt_vencimento")
    list_filter = ("dt_vencimento", "dt_pagamento", "pgto", "cancelado", "usuario")
    search_fields = ("cliente__nome",)
    ordering = ("-id",)
    autocomplete_fields = ("cliente",)


class PlanoAdmin(admin.ModelAdmin):
    list_display = ("nome", "valor")


class ContaDoAplicativoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "app", "device_id", "device_key", "email", "verificado")
    list_filter = ("usuario", "app")
    search_fields = ("email", "cliente__nome")
    autocomplete_fields = ("cliente", "app")


class SessaoWppAdmin(admin.ModelAdmin):
    list_display = ("usuario", "token", "dt_inicio")
    list_filter = ("usuario", "dt_inicio")
    search_fields = ("usuario", "token")
    ordering = ("-dt_inicio",)


class MensagemEnviadaWppAdmin(admin.ModelAdmin):
    list_display = ("telefone", "data_envio")
    list_filter = ("data_envio",)
    search_fields = ("telefone",)
    ordering = ("-data_envio",)


class ConteudoM3U8Admin(admin.ModelAdmin):
    list_display = ("id", "nome", "capa", "temporada", "episodio", "criado_em", "upload")
    list_filter = ("criado_em",)
    search_fields = ("nome",)
    ordering = ("-criado_em",)


class PlanoIndicacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "tipo_plano", "valor", "valor_minimo_mensalidade", "usuario", "ativo")
    list_filter = ("usuario", "ativo")
    search_fields = ("nome", "tipo_plano")
    ordering = ("-id",)


class DadosBancariosAdmin(admin.ModelAdmin):
    list_display = ("id", "beneficiario", "instituicao", "tipo_chave", "chave", "usuario", "wpp")
    list_filter = ("usuario", "instituicao")
    search_fields = ("beneficiario", "instituicao")
    ordering = ("-id",)


class SecretTokenAPIAdmin(admin.ModelAdmin):
    list_display = ("id", "token", "usuario", "dt_criacao")
    list_filter = ("usuario", "dt_criacao")
    search_fields = ("token", "usuario")
    ordering = ("-dt_criacao",)


class HorarioEnviosAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "horario", "ativo")
    list_filter = ("usuario", "horario", "ativo")
    search_fields = ("usuario", "horario")
    ordering = ("-id",)


class DispositivoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    ordering = ("-id",)


class AplicativoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "device_has_mac", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    ordering = ("-id",)


class Tipos_pgtoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    ordering = ("-id",)


class ServidorAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    ordering = ("-id",)

# --- REGISTRO NO ADMIN ---

admin.site.register(Plano, PlanoAdmin)
admin.site.register(Cliente, ClienteAdmin)
admin.site.register(Servidor, ServidorAdmin)
admin.site.register(SessaoWpp, SessaoWppAdmin)
admin.site.register(Tipos_pgto, Tipos_pgtoAdmin)
admin.site.register(Aplicativo, AplicativoAdmin)
admin.site.register(Mensalidade, MensalidadeAdmin)
admin.site.register(Dispositivo, DispositivoAdmin)
admin.site.register(ConteudoM3U8, ConteudoM3U8Admin)
admin.site.register(HorarioEnvios, HorarioEnviosAdmin)
admin.site.register(SecretTokenAPI, SecretTokenAPIAdmin)
admin.site.register(DadosBancarios, DadosBancariosAdmin)
admin.site.register(PlanoIndicacao, PlanoIndicacaoAdmin)
admin.site.register(ContaDoAplicativo, ContaDoAplicativoAdmin)
admin.site.register(MensagemEnviadaWpp, MensagemEnviadaWppAdmin)
