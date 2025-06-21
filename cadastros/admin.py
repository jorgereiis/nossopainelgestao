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
    DominiosDNS,
    TelefoneLeads,
    EnviosLeads,
    MensagensLeads,
)

# --- ADMINISTRADORES ---

class ServidorAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    ordering = ("-id", "nome",)


class Tipos_pgtoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    ordering = ("-id", "nome",)


class DispositivoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario",)
    ordering = ("-id", "nome",)


class AplicativoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "device_has_mac", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    list_editable = ("device_has_mac",)
    ordering = ("-id", "nome",)


class PlanoAdmin(admin.ModelAdmin):
    list_display = ("nome", "telas", "valor", "usuario")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    list_editable = ("telas",)
    ordering = ("nome", "valor")


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


class PlanoIndicacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "tipo_plano", "descricao", "exemplo", "valor", "valor_minimo_mensalidade", "usuario", "status", "ativo")
    list_filter = ("usuario", "ativo")
    search_fields = ("nome", "tipo_plano")
    ordering = ("-id", "nome",)


class ContaDoAplicativoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "app", "device_id", "device_key", "email", "usuario", "verificado")
    list_filter = ("usuario", "app")
    search_fields = ("email", "cliente__nome")
    autocomplete_fields = ("cliente", "app")
    ordering = ("-id", "cliente",)


class SessaoWppAdmin(admin.ModelAdmin):
    list_display = ("usuario", "token", "dt_inicio", "is_active")
    list_filter = ("usuario", "dt_inicio")
    search_fields = ("usuario", "token")
    ordering = ("-dt_inicio",)


class SecretTokenAPIAdmin(admin.ModelAdmin):
    list_display = ("id", "token", "usuario", "dt_criacao")
    list_filter = ("usuario", "dt_criacao")
    search_fields = ("token", "usuario")
    ordering = ("-dt_criacao",)


class DadosBancariosAdmin(admin.ModelAdmin):
    list_display = ("id", "beneficiario", "instituicao", "tipo_chave", "chave", "usuario", "wpp")
    list_filter = ("usuario", "instituicao")
    search_fields = ("beneficiario", "instituicao")
    ordering = ("-id",)


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


class HorarioEnviosAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "tipo_envio",  "descricao", "exemplo", "horario", "usuario", "ultimo_envio", "status", "ativo")
    list_filter = ("usuario", "horario", "ativo")
    search_fields = ("usuario", "horario")
    ordering = ("-id",)


class DominiosDNSAdmin(admin.ModelAdmin):
    list_display = ("id", "servidor", "dominio", "data_online", "data_offline", "acesso_canais", "data_ultima_verificacao", "data_envio_alerta","usuario", "status", "monitorado")
    list_filter = ("usuario", "status")
    list_editable = ("monitorado", "status", "data_online", "data_offline", "acesso_canais",)
    search_fields = ("dominio",)
    ordering = ("-id",)


class TelefoneLeadsAdmin(admin.ModelAdmin):
    list_display = ("id", "telefone", "usuario")
    list_filter = ("usuario",)
    search_fields = ("telefone",)
    ordering = ("-id",)


class EnviosLeadsAdmin(admin.ModelAdmin):
    list_display = ("id", "telefone", "data_envio", "mensagem", "usuario")
    list_filter = ("usuario", "data_envio")
    search_fields = ("telefone",)
    ordering = ("-data_envio",)


class MensagensLeadsAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "tipo", "mensagem", "usuario")
    list_filter = ("usuario", "tipo")
    search_fields = ("telefone",)
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
admin.site.register(DominiosDNS, DominiosDNSAdmin)
admin.site.register(TelefoneLeads, TelefoneLeadsAdmin)
admin.site.register(EnviosLeads, EnviosLeadsAdmin)
admin.site.register(MensagensLeads, MensagensLeadsAdmin)

# Configurações adicionais do admin
admin.site.site_header = "Administração do Sistema"
admin.site.site_title = "Painel de Administração"
admin.site.index_title = "Bem-vindo ao Painel de Administração"
admin.site.enable_nav_sidebar = False  # Desabilita a barra lateral de navegação
admin.site.empty_value_display = '- vazio -'  # Exibe '- vazio -' para campos vazios