from django.contrib import admin
from .models import (
    Plano,
    Cliente,
    Servidor,
    ServidorImagem,
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
    DescontoProgressivoIndicacao,
    ContaDoAplicativo,
    MensagemEnviadaWpp,
    DominiosDNS,
    TelefoneLeads,
    EnviosLeads,
    MensagensLeads,
    UserActionLog,
    NotificationRead,
    LoginLog,
    OfertaPromocionalEnviada,
    ContaReseller,
    TarefaMigracaoDNS,
    DispositivoMigracaoDNS,
    TarefaEnvio,
    HistoricoExecucaoTarefa,
    # Integração Bancária
    InstituicaoBancaria,
    ContaBancaria,
    ClienteContaBancaria,
    # Modelos adicionais
    ClientePlanoHistorico,
    AssinaturaCliente,
    OfertaPromocional,
    PlanoLinkPagamento,
    CredencialAPI,
    ConfiguracaoLimite,
    NotificacaoSistema,
    PushSubscription,
    CobrancaPix,
    UserProfile,
    ConfiguracaoAutomacao,
    TemplateMensagem,
    ConfiguracaoEnvio,
    VarianteMensagem,
    ConfiguracaoAgendamento,
)

# --- ADMINISTRADORES ---

class ServidorAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "usuario", "imagem_admin")
    list_filter = ("usuario",)
    search_fields = ("nome", "usuario")
    ordering = ("-id", "nome",)


class ServidorImagemAdmin(admin.ModelAdmin):
    list_display = ("id", "servidor", "usuario", "imagem", "criado_em", "atualizado_em")
    list_filter = ("servidor", "usuario", "criado_em")
    search_fields = ("servidor__nome", "usuario__username")
    autocomplete_fields = ("servidor",)
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-criado_em",)


class Tipos_pgtoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "conta_bancaria", "tem_api", "usuario")
    list_filter = ("usuario", "nome", "conta_bancaria__instituicao")
    search_fields = ("nome", "usuario__username", "conta_bancaria__nome_identificacao")
    autocomplete_fields = ("conta_bancaria",)
    ordering = ("-id", "nome",)

    def tem_api(self, obj):
        """Exibe se tem integração com API."""
        return obj.tem_integracao_api
    tem_api.boolean = True
    tem_api.short_description = "API"


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
        "id", "nome", "telefone", "uf", "pais", "servidor", "dispositivo", "sistema",
        "data_vencimento", "forma_pgto", "plano", "data_adesao",
        "data_cancelamento", "ultimo_pagamento", "indicado_por", "notas",
        "cancelado", "nao_enviar_msgs", "usuario",
    )
    list_filter = ("servidor", "usuario", "forma_pgto", "data_vencimento", "cancelado", "sistema", "pais")
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
    list_display = ("id", "nome", "tipo_plano", "descricao", "exemplo", "valor", "valor_minimo_mensalidade", "limite_indicacoes", "usuario", "status", "ativo")
    list_filter = ("usuario", "ativo")
    search_fields = ("nome", "tipo_plano")
    ordering = ("-id", "nome",)


class DescontoProgressivoIndicacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente_indicador", "cliente_indicado", "valor_desconto", "data_inicio", "data_fim", "ativo", "usuario", "criado_em")
    list_filter = ("ativo", "usuario", "data_inicio")
    search_fields = ("cliente_indicador__nome", "cliente_indicado__nome")
    autocomplete_fields = ("cliente_indicador", "cliente_indicado", "plano_indicacao")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-criado_em",)


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


# --- INTEGRAÇÃO BANCÁRIA ---

class InstituicaoBancariaAdmin(admin.ModelAdmin):
    """Admin para gerenciar instituições bancárias."""
    list_display = ("id", "nome", "tipo_integracao", "tem_api", "ativo", "criado_em")
    list_filter = ("tipo_integracao", "ativo")
    search_fields = ("nome",)
    ordering = ("nome",)
    list_editable = ("ativo",)

    fieldsets = (
        ("Informações da Instituição", {
            "fields": ("nome", "tipo_integracao", "ativo")
        }),
    )

    def tem_api(self, obj):
        """Exibe se tem integração com API."""
        return obj.tem_api
    tem_api.boolean = True
    tem_api.short_description = "API"


class ClienteContaBancariaInline(admin.TabularInline):
    """Inline para mostrar clientes associados à conta."""
    model = ClienteContaBancaria
    extra = 0
    autocomplete_fields = ("cliente",)
    readonly_fields = ("criado_em",)


class ContaBancariaAdmin(admin.ModelAdmin):
    """Admin para gerenciar contas bancárias dos usuários."""
    list_display = (
        "id", "nome_identificacao", "instituicao", "tipo_conta",
        "beneficiario", "chave_pix_truncada", "tem_api", "clientes_count",
        "limite_display", "ativo", "usuario"
    )
    list_filter = ("tipo_conta", "instituicao", "ativo", "usuario", "ambiente_sandbox")
    search_fields = ("nome_identificacao", "beneficiario", "chave_pix", "usuario__username")
    ordering = ("-criado_em",)
    list_editable = ("ativo",)
    autocomplete_fields = ("usuario", "instituicao")
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [ClienteContaBancariaInline]

    fieldsets = (
        ("Identificação", {
            "fields": ("usuario", "instituicao", "nome_identificacao", "tipo_conta")
        }),
        ("Dados Bancários", {
            "fields": ("beneficiario", "tipo_chave_pix", "chave_pix")
        }),
        ("Credenciais FastDePix", {
            "fields": ("_api_key", "_webhook_secret", "webhook_id", "tipo_cobranca_fastdepix"),
            "classes": ("collapse",),
            "description": "Preencha apenas para integração FastDePix. Campos sensíveis são armazenados criptografados."
        }),
        ("Credenciais API (Efi Bank / Mercado Pago)", {
            "fields": ("api_client_id", "_api_client_secret", "api_certificado", "_api_access_token", "ambiente_sandbox"),
            "classes": ("collapse",),
            "description": "Preencha apenas se a instituição tiver integração com API. Campos sensíveis são armazenados criptografados."
        }),
        ("Controle MEI", {
            "fields": ("limite_mensal",),
            "description": "O limite efetivo será 10% menor que o cadastrado."
        }),
        ("Status", {
            "fields": ("ativo",)
        }),
        ("Metadados", {
            "fields": ("criado_em", "atualizado_em"),
            "classes": ("collapse",)
        }),
    )

    def chave_pix_truncada(self, obj):
        """Exibe chave PIX truncada para segurança."""
        if obj.chave_pix and len(obj.chave_pix) > 10:
            return f"{obj.chave_pix[:6]}...{obj.chave_pix[-4:]}"
        return obj.chave_pix
    chave_pix_truncada.short_description = "Chave PIX"

    def tem_api(self, obj):
        """Exibe se tem integração com API."""
        return obj.tem_integracao_api
    tem_api.boolean = True
    tem_api.short_description = "API"

    def clientes_count(self, obj):
        """Exibe quantidade de clientes associados."""
        count = obj.get_clientes_associados_count()
        if obj.tipo_conta == 'pf':
            return "Ilimitado"
        return count
    clientes_count.short_description = "Clientes"

    def limite_display(self, obj):
        """Exibe limite formatado."""
        if obj.limite_mensal:
            efetivo = obj.limite_efetivo
            return f"R$ {obj.limite_mensal:,.2f} (efetivo: R$ {efetivo:,.2f})"
        return "-"
    limite_display.short_description = "Limite MEI"


class ClienteContaBancariaAdmin(admin.ModelAdmin):
    """Admin para visualizar associações cliente-conta."""
    list_display = ("id", "cliente", "conta_bancaria", "criado_em")
    list_filter = ("conta_bancaria__instituicao", "conta_bancaria__tipo_conta", "criado_em")
    search_fields = ("cliente__nome", "conta_bancaria__nome_identificacao")
    autocomplete_fields = ("cliente", "conta_bancaria")
    readonly_fields = ("criado_em",)
    ordering = ("-criado_em",)


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


class NotificationReadAdmin(admin.ModelAdmin):
    list_display = ("usuario", "mensalidade", "marcado_em")
    list_filter = ("usuario", "marcado_em")
    search_fields = ("usuario__username", "mensalidade__cliente__nome", "mensalidade__cliente__telefone")
    ordering = ("-marcado_em",)


class UserActionLogAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "usuario", "acao", "entidade", "objeto_repr")
    list_filter = ("acao", "entidade", "usuario")
    search_fields = ("objeto_repr", "mensagem", "usuario__username", "objeto_id")
    readonly_fields = ("usuario", "acao", "entidade", "objeto_id", "objeto_repr", "mensagem", "extras", "ip", "request_path", "criado_em")
    ordering = ("-criado_em",)
    list_per_page = 50


class LoginLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "usuario", "username_tentado", "ip", "login_method", "success", "failure_reason")
    list_filter = ("success", "login_method", "created_at", "usuario")
    search_fields = ("username_tentado", "ip", "usuario__username", "user_agent")
    readonly_fields = (
        "usuario", "username_tentado", "ip", "user_agent", "login_method",
        "success", "failure_reason", "location_country", "location_city", "created_at"
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50

    def has_add_permission(self, request):
        """Não permite adicionar logs manualmente - só via signals."""
        return False

    def has_change_permission(self, request, obj=None):
        """Não permite editar logs - são apenas leitura."""
        return False


class OfertaPromocionalEnviadaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "numero_oferta", "dias_apos_cancelamento", "data_cancelamento_ref", "data_envio", "usuario")
    list_filter = ("numero_oferta", "dias_apos_cancelamento", "usuario", "data_envio")
    search_fields = ("cliente__nome", "cliente__telefone")
    autocomplete_fields = ("cliente",)
    readonly_fields = ("data_envio",)
    ordering = ("-data_envio",)
    list_per_page = 50


class ContaResellerAdmin(admin.ModelAdmin):
    """Admin para gerenciar contas de reseller (credenciais e sessões)."""
    list_display = ("id", "usuario", "aplicativo", "email_login", "sessao_valida", "ultimo_login", "data_atualizacao")
    list_filter = ("aplicativo", "sessao_valida", "usuario")
    search_fields = ("usuario__username", "email_login", "aplicativo__nome")
    readonly_fields = ("data_criacao", "data_atualizacao", "ultimo_login")
    ordering = ("-data_atualizacao",)
    list_per_page = 30

    fieldsets = (
        ("Informações Básicas", {
            "fields": ("usuario", "aplicativo", "email_login")
        }),
        ("Senha (Criptografada)", {
            "fields": ("senha_login",),
            "description": "A senha é criptografada automaticamente. Nunca exiba ou compartilhe."
        }),
        ("Sessão e Autenticação", {
            "fields": ("sessao_valida", "ultimo_login", "session_data"),
            "description": "Dados de sessão para reutilização de login (cookies e localStorage)."
        }),
        ("Metadados", {
            "fields": ("data_criacao", "data_atualizacao"),
            "classes": ("collapse",),
        }),
    )


class DispositivoMigracaoDNSInline(admin.TabularInline):
    """Inline para mostrar dispositivos dentro da tarefa de migração."""
    model = DispositivoMigracaoDNS
    extra = 0
    readonly_fields = ("device_id", "nome_dispositivo", "status", "dns_encontrado", "dns_atualizado", "mensagem_erro", "processado_em")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        """Não permite adicionar dispositivos manualmente."""
        return False


class TarefaMigracaoDNSAdmin(admin.ModelAdmin):
    """Admin para visualizar e gerenciar tarefas de migração DNS."""
    list_display = ("id", "usuario", "aplicativo", "tipo_migracao", "status", "progresso_display", "criada_em")
    list_filter = ("status", "tipo_migracao", "aplicativo", "usuario", "criada_em")
    search_fields = ("usuario__username", "mac_alvo", "dominio_origem", "dominio_destino")
    readonly_fields = (
        "usuario", "aplicativo", "conta_reseller", "tipo_migracao", "mac_alvo",
        "dominio_origem", "dominio_destino", "status", "total_dispositivos",
        "processados", "sucessos", "falhas", "criada_em", "iniciada_em",
        "concluida_em", "erro_geral", "progresso_display"
    )
    ordering = ("-criada_em",)
    list_per_page = 30
    date_hierarchy = "criada_em"
    inlines = [DispositivoMigracaoDNSInline]

    fieldsets = (
        ("Informações da Tarefa", {
            "fields": ("usuario", "aplicativo", "conta_reseller", "tipo_migracao", "mac_alvo")
        }),
        ("Configuração DNS", {
            "fields": ("dominio_origem", "dominio_destino")
        }),
        ("Status e Progresso", {
            "fields": ("status", "progresso_display", "total_dispositivos", "processados", "sucessos", "falhas")
        }),
        ("Timestamps", {
            "fields": ("criada_em", "iniciada_em", "concluida_em")
        }),
        ("Erros", {
            "fields": ("erro_geral",),
            "classes": ("collapse",),
        }),
    )

    def progresso_display(self, obj):
        """Exibe o progresso visualmente."""
        if obj.total_dispositivos == 0:
            return "N/A"
        percentual = obj.get_progresso_percentual()
        return f"{obj.processados}/{obj.total_dispositivos} ({percentual}%)"
    progresso_display.short_description = "Progresso"

    def has_add_permission(self, request):
        """Não permite criar tarefas manualmente - só via interface web."""
        return False

    def has_change_permission(self, request, obj=None):
        """Tarefas são readonly."""
        return False


class DispositivoMigracaoDNSAdmin(admin.ModelAdmin):
    """Admin para visualizar dispositivos em migração (geralmente acessado via inline)."""
    list_display = ("id", "tarefa", "device_id", "nome_dispositivo", "status", "processado_em")
    list_filter = ("status", "processado_em")
    search_fields = ("device_id", "nome_dispositivo", "dns_encontrado", "dns_atualizado")
    readonly_fields = ("tarefa", "device_id", "nome_dispositivo", "status", "dns_encontrado", "dns_atualizado", "mensagem_erro", "processado_em")
    ordering = ("-processado_em",)
    list_per_page = 50

    def has_add_permission(self, request):
        """Não permite adicionar dispositivos manualmente."""
        return False

    def has_change_permission(self, request, obj=None):
        """Dispositivos são readonly."""
        return False


# --- REGISTRO NO ADMIN ---

admin.site.register(Plano, PlanoAdmin)
admin.site.register(Cliente, ClienteAdmin)
admin.site.register(Servidor, ServidorAdmin)
admin.site.register(ServidorImagem, ServidorImagemAdmin)
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
admin.site.register(DescontoProgressivoIndicacao, DescontoProgressivoIndicacaoAdmin)
admin.site.register(ContaDoAplicativo, ContaDoAplicativoAdmin)
admin.site.register(MensagemEnviadaWpp, MensagemEnviadaWppAdmin)
admin.site.register(DominiosDNS, DominiosDNSAdmin)
admin.site.register(TelefoneLeads, TelefoneLeadsAdmin)
admin.site.register(EnviosLeads, EnviosLeadsAdmin)
admin.site.register(MensagensLeads, MensagensLeadsAdmin)
admin.site.register(NotificationRead, NotificationReadAdmin)
admin.site.register(UserActionLog, UserActionLogAdmin)
admin.site.register(LoginLog, LoginLogAdmin)
admin.site.register(OfertaPromocionalEnviada, OfertaPromocionalEnviadaAdmin)
admin.site.register(ContaReseller, ContaResellerAdmin)
admin.site.register(TarefaMigracaoDNS, TarefaMigracaoDNSAdmin)
admin.site.register(DispositivoMigracaoDNS, DispositivoMigracaoDNSAdmin)

# Integração Bancária
admin.site.register(InstituicaoBancaria, InstituicaoBancariaAdmin)
admin.site.register(ContaBancaria, ContaBancariaAdmin)
admin.site.register(ClienteContaBancaria, ClienteContaBancariaAdmin)


# --- TAREFAS DE ENVIO ---

class HistoricoExecucaoTarefaInline(admin.TabularInline):
    model = HistoricoExecucaoTarefa
    extra = 0
    readonly_fields = ('data_execucao', 'status', 'quantidade_enviada', 'quantidade_erros', 'duracao_segundos')
    can_delete = False
    ordering = ('-data_execucao',)
    max_num = 10


class TarefaEnvioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo_envio', 'get_dias_semana_str', 'horario', 'ativo', 'ultimo_envio', 'total_envios', 'usuario')
    list_filter = ('tipo_envio', 'ativo', 'usuario', 'periodo_mes')
    search_fields = ('nome', 'mensagem')
    readonly_fields = ('ultimo_envio', 'total_envios', 'mensagem_plaintext', 'criado_em', 'atualizado_em')
    ordering = ('-criado_em',)
    inlines = [HistoricoExecucaoTarefaInline]

    fieldsets = (
        ('Identificação', {
            'fields': ('nome', 'tipo_envio', 'usuario')
        }),
        ('Agendamento', {
            'fields': ('dias_semana', 'periodo_mes', 'horario')
        }),
        ('Conteúdo', {
            'fields': ('imagem', 'mensagem', 'mensagem_plaintext')
        }),
        ('Status', {
            'fields': ('ativo', 'ultimo_envio', 'total_envios')
        }),
        ('Metadados', {
            'fields': ('criado_em', 'atualizado_em'),
            'classes': ('collapse',)
        }),
    )

    def get_dias_semana_str(self, obj):
        return ', '.join(obj.get_dias_semana_abrev()) if obj.dias_semana else '-'
    get_dias_semana_str.short_description = 'Dias'


class HistoricoExecucaoTarefaAdmin(admin.ModelAdmin):
    list_display = ('tarefa', 'data_execucao', 'status', 'quantidade_enviada', 'quantidade_erros', 'get_duracao_formatada')
    list_filter = ('status', 'tarefa__tipo_envio', 'data_execucao')
    search_fields = ('tarefa__nome',)
    readonly_fields = ('tarefa', 'data_execucao', 'status', 'quantidade_enviada', 'quantidade_erros', 'detalhes', 'duracao_segundos')
    ordering = ('-data_execucao',)


admin.site.register(TarefaEnvio, TarefaEnvioAdmin)
admin.site.register(HistoricoExecucaoTarefa, HistoricoExecucaoTarefaAdmin)


# --- MODELOS ADICIONAIS ---

class ClientePlanoHistoricoAdmin(admin.ModelAdmin):
    """Admin para histórico de planos dos clientes."""
    list_display = ("id", "cliente", "plano_nome", "valor_plano", "telas", "inicio", "fim", "motivo", "usuario")
    list_filter = ("motivo", "usuario", "inicio")
    search_fields = ("cliente__nome", "plano_nome")
    autocomplete_fields = ("cliente", "plano")
    readonly_fields = ("criado_em",)
    ordering = ("-inicio", "-criado_em")
    date_hierarchy = "inicio"


class AssinaturaClienteAdmin(admin.ModelAdmin):
    """Admin para assinaturas de clientes."""
    list_display = (
        "id", "cliente", "plano", "data_inicio_assinatura", "dispositivos_usados",
        "em_campanha", "campanha_mensalidades_pagas", "ativo"
    )
    list_filter = ("ativo", "em_campanha", "plano")
    search_fields = ("cliente__nome", "cliente__telefone")
    autocomplete_fields = ("cliente", "plano")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-criado_em",)
    list_editable = ("ativo",)


class OfertaPromocionalAdmin(admin.ModelAdmin):
    """Admin para ofertas promocionais."""
    list_display = (
        "id", "cliente", "plano_oferta", "numero_mensalidades",
        "mensalidades_restantes", "ativo", "criado_em"
    )
    list_filter = ("ativo", "plano_oferta", "criado_em")
    search_fields = ("cliente__nome", "cliente__telefone")
    autocomplete_fields = ("cliente", "plano_oferta")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-criado_em",)


class PlanoLinkPagamentoAdmin(admin.ModelAdmin):
    """Admin para links de pagamento dos planos."""
    list_display = ("id", "plano", "conta_bancaria", "valor_configurado", "valor_divergente_display", "criado_em")
    list_filter = ("conta_bancaria", "criado_em")
    search_fields = ("plano__nome", "conta_bancaria__nome_identificacao")
    autocomplete_fields = ("plano", "conta_bancaria")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("plano__nome",)

    def valor_divergente_display(self, obj):
        """Indica se o valor do plano diverge do configurado."""
        return obj.valor_divergente
    valor_divergente_display.boolean = True
    valor_divergente_display.short_description = "Valor Divergente"


class CredencialAPIAdmin(admin.ModelAdmin):
    """Admin para credenciais de API."""
    list_display = ("id", "nome_identificacao", "tipo_integracao", "usuario", "is_configured_display", "ambiente_sandbox", "ativo")
    list_filter = ("tipo_integracao", "ativo", "ambiente_sandbox", "usuario")
    search_fields = ("nome_identificacao", "usuario__username")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-criado_em",)

    def is_configured_display(self, obj):
        """Exibe se está configurada corretamente."""
        return obj.is_configured
    is_configured_display.boolean = True
    is_configured_display.short_description = "Configurada"

    fieldsets = (
        ("Identificação", {
            "fields": ("usuario", "nome_identificacao", "tipo_integracao", "ativo")
        }),
        ("FastDePix", {
            "fields": ("_api_key",),
            "classes": ("collapse",),
            "description": "Campos sensíveis são armazenados criptografados."
        }),
        ("Mercado Pago / Efi Bank", {
            "fields": ("api_client_id", "_api_client_secret", "_api_access_token", "api_certificado"),
            "classes": ("collapse",),
            "description": "Campos sensíveis são armazenados criptografados."
        }),
        ("Ambiente", {
            "fields": ("ambiente_sandbox",),
            "classes": ("collapse",),
        }),
        ("Metadados", {
            "fields": ("criado_em", "atualizado_em"),
            "classes": ("collapse",),
        }),
    )


class ConfiguracaoLimiteAdmin(admin.ModelAdmin):
    """Admin para configuração de limite MEI (singleton)."""
    list_display = ("valor_anual", "margem_seguranca", "valor_alerta_display", "atualizado_em", "atualizado_por")
    readonly_fields = ("atualizado_em",)

    def valor_alerta_display(self, obj):
        """Exibe o valor de alerta calculado."""
        return f"R$ {obj.valor_alerta:,.2f}"
    valor_alerta_display.short_description = "Valor de Alerta"

    def has_add_permission(self, request):
        """Permite apenas 1 registro (singleton)."""
        return not ConfiguracaoLimite.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Não permite excluir o registro singleton."""
        return False


class NotificacaoSistemaAdmin(admin.ModelAdmin):
    """Admin para notificações do sistema."""
    list_display = ("id", "titulo", "tipo", "prioridade", "usuario", "lida", "criada_em")
    list_filter = ("tipo", "prioridade", "lida", "criada_em")
    search_fields = ("titulo", "mensagem", "usuario__username")
    readonly_fields = ("criada_em", "data_leitura")
    ordering = ("-criada_em",)
    date_hierarchy = "criada_em"
    list_per_page = 50


class PushSubscriptionAdmin(admin.ModelAdmin):
    """Admin para subscriptions de Push Notifications."""
    list_display = ("id", "usuario", "endpoint_truncado", "ativo", "criado_em", "atualizado_em")
    list_filter = ("ativo", "criado_em")
    search_fields = ("usuario__username", "endpoint")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-criado_em",)

    def endpoint_truncado(self, obj):
        """Exibe endpoint truncado."""
        if len(obj.endpoint) > 50:
            return f"{obj.endpoint[:50]}..."
        return obj.endpoint
    endpoint_truncado.short_description = "Endpoint"


class CobrancaPixAdmin(admin.ModelAdmin):
    """Admin para cobranças PIX."""
    list_display = (
        "id", "cliente", "valor", "valor_taxa", "valor_recebido", "status", "integracao",
        "conta_bancaria", "criado_em", "expira_em", "pago_em"
    )
    list_filter = ("status", "integracao", "conta_bancaria", "criado_em")
    search_fields = ("cliente__nome", "cliente__telefone", "transaction_id", "pagador_nome")
    autocomplete_fields = ("cliente", "mensalidade", "conta_bancaria")
    readonly_fields = (
        "id", "transaction_id", "qr_code", "qr_code_url", "pix_copia_cola",
        "criado_em", "atualizado_em", "pago_em", "pagador_nome", "pagador_documento",
        "valor_recebido", "valor_taxa", "raw_response", "webhook_data"
    )
    ordering = ("-criado_em",)
    date_hierarchy = "criado_em"
    list_per_page = 50

    fieldsets = (
        ("Identificação", {
            "fields": ("id", "transaction_id", "integracao")
        }),
        ("Relacionamentos", {
            "fields": ("usuario", "conta_bancaria", "cliente", "mensalidade")
        }),
        ("Valores", {
            "fields": ("valor", "descricao", "status")
        }),
        ("Dados PIX", {
            "fields": ("qr_code", "qr_code_url", "pix_copia_cola"),
            "classes": ("collapse",),
        }),
        ("Pagamento", {
            "fields": ("pago_em", "pagador_nome", "pagador_documento", "valor_recebido", "valor_taxa"),
            "classes": ("collapse",),
        }),
        ("Datas", {
            "fields": ("criado_em", "atualizado_em", "expira_em")
        }),
        ("Dados Técnicos", {
            "fields": ("raw_response", "webhook_data"),
            "classes": ("collapse",),
        }),
    )


class UserProfileAdmin(admin.ModelAdmin):
    """Admin para perfis de usuário."""
    list_display = (
        "user", "theme_preference", "two_factor_enabled",
        "profile_public", "created_at"
    )
    list_filter = ("theme_preference", "two_factor_enabled", "profile_public")
    search_fields = ("user__username", "user__email", "bio")
    readonly_fields = ("created_at", "updated_at", "two_factor_secret", "two_factor_backup_codes")
    ordering = ("-created_at",)

    fieldsets = (
        ("Usuário", {
            "fields": ("user", "avatar", "bio", "cover_image")
        }),
        ("Preferências de Tema", {
            "fields": ("theme_preference",)
        }),
        ("Notificações por E-mail", {
            "fields": ("email_on_profile_change", "email_on_password_change", "email_on_login"),
            "classes": ("collapse",),
        }),
        ("Privacidade", {
            "fields": ("profile_public", "show_email", "show_phone", "show_statistics"),
            "classes": ("collapse",),
        }),
        ("Autenticação em Dois Fatores", {
            "fields": ("two_factor_enabled", "two_factor_secret", "two_factor_backup_codes"),
            "classes": ("collapse",),
        }),
        ("Metadados", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


class ConfiguracaoAutomacaoAdmin(admin.ModelAdmin):
    """Admin para configurações de automação."""
    list_display = ("user", "debug_headless_mode", "criado_em", "atualizado_em")
    list_filter = ("debug_headless_mode",)
    search_fields = ("user__username",)
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-atualizado_em",)


class TemplateMensagemAdmin(admin.ModelAdmin):
    """Admin para templates de mensagem."""
    list_display = ("id", "nome", "categoria", "usuario", "ativo", "criado_em")
    list_filter = ("categoria", "ativo", "usuario")
    search_fields = ("nome", "descricao", "mensagem_html")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("categoria", "nome")


class ConfiguracaoEnvioAdmin(admin.ModelAdmin):
    """Admin para configurações de envio (singleton)."""
    list_display = (
        "limite_envios_por_execucao", "intervalo_entre_mensagens",
        "horario_inicio_permitido", "horario_fim_permitido", "atualizado_em"
    )
    readonly_fields = ("atualizado_em",)

    def has_add_permission(self, request):
        """Permite apenas 1 registro (singleton)."""
        return not ConfiguracaoEnvio.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Não permite excluir o registro singleton."""
        return False


class VarianteMensagemAdmin(admin.ModelAdmin):
    """Admin para variantes de mensagem (A/B Testing)."""
    list_display = ("id", "tarefa", "nome", "peso", "total_envios", "ativo", "criado_em")
    list_filter = ("ativo", "tarefa")
    search_fields = ("nome", "tarefa__nome")
    autocomplete_fields = ("tarefa",)
    readonly_fields = ("total_envios", "criado_em")
    ordering = ("tarefa", "nome")


class ConfiguracaoAgendamentoAdmin(admin.ModelAdmin):
    """Admin para configurações de agendamento."""
    list_display = ("nome", "nome_exibicao", "horario", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "nome_exibicao", "descricao")
    readonly_fields = ("atualizado_em",)
    ordering = ("nome",)


# Registro dos modelos adicionais
admin.site.register(ClientePlanoHistorico, ClientePlanoHistoricoAdmin)
admin.site.register(AssinaturaCliente, AssinaturaClienteAdmin)
admin.site.register(OfertaPromocional, OfertaPromocionalAdmin)
admin.site.register(PlanoLinkPagamento, PlanoLinkPagamentoAdmin)
admin.site.register(CredencialAPI, CredencialAPIAdmin)
admin.site.register(ConfiguracaoLimite, ConfiguracaoLimiteAdmin)
admin.site.register(NotificacaoSistema, NotificacaoSistemaAdmin)
admin.site.register(PushSubscription, PushSubscriptionAdmin)
admin.site.register(CobrancaPix, CobrancaPixAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(ConfiguracaoAutomacao, ConfiguracaoAutomacaoAdmin)
admin.site.register(TemplateMensagem, TemplateMensagemAdmin)
admin.site.register(ConfiguracaoEnvio, ConfiguracaoEnvioAdmin)
admin.site.register(VarianteMensagem, VarianteMensagemAdmin)
admin.site.register(ConfiguracaoAgendamento, ConfiguracaoAgendamentoAdmin)


# Configurações adicionais do admin
admin.site.site_header = "Administração do Sistema"
admin.site.site_title = "Painel de Administração"
admin.site.index_title = "Bem-vindo ao Painel de Administração"
admin.site.enable_nav_sidebar = False  # Desabilita a barra lateral de navegação
admin.site.empty_value_display = '- vazio -'  # Exibe '- vazio -' para campos vazios
