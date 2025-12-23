"""
Configuracao do Django Admin para o Painel do Cliente.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import SubdominioPainelCliente, SessaoCliente, TentativaLogin


@admin.register(SubdominioPainelCliente)
class SubdominioPainelClienteAdmin(admin.ModelAdmin):
    """Admin para gerenciamento de subdominios do painel."""

    list_display = [
        'subdominio',
        'nome_exibicao',
        'admin_responsavel',
        'conta_bancaria_display',
        'status_badge',
        'criado_em',
    ]
    list_filter = ['ativo', 'criado_em', 'admin_responsavel']
    search_fields = ['subdominio', 'nome_exibicao', 'admin_responsavel__username']
    readonly_fields = ['dominio_completo', 'criado_em', 'atualizado_em', 'criado_por']
    ordering = ['-criado_em']

    fieldsets = (
        ('Identificacao', {
            'fields': ('subdominio', 'dominio_completo', 'nome_exibicao', 'ativo')
        }),
        ('Responsavel', {
            'fields': ('admin_responsavel', 'conta_bancaria')
        }),
        ('Personalizacao Visual', {
            'fields': ('logo', 'cor_primaria', 'cor_secundaria'),
            'classes': ('collapse',)
        }),
        ('Suporte', {
            'fields': ('whatsapp_suporte', 'mensagem_suporte', 'texto_boas_vindas'),
            'classes': ('collapse',)
        }),
        ('Auditoria', {
            'fields': ('criado_por', 'criado_em', 'atualizado_em'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        """Exibe badge de status."""
        if obj.ativo:
            return format_html(
                '<span style="background-color: #198754; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">Ativo</span>'
            )
        return format_html(
            '<span style="background-color: #dc3545; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">Inativo</span>'
        )
    status_badge.short_description = 'Status'

    def conta_bancaria_display(self, obj):
        """Exibe conta bancaria vinculada."""
        if obj.conta_bancaria:
            return obj.conta_bancaria.nome_identificacao or obj.conta_bancaria.beneficiario
        return format_html('<span style="color: #999;">Nao configurada</span>')
    conta_bancaria_display.short_description = 'Conta FastDePix'

    def save_model(self, request, obj, form, change):
        """Salva o criador do subdominio."""
        if not change:  # Novo registro
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(SessaoCliente)
class SessaoClienteAdmin(admin.ModelAdmin):
    """Admin para visualizacao de sessoes de clientes."""

    list_display = [
        'cliente',
        'subdominio',
        'ip_address',
        'status_sessao',
        'criado_em',
        'ultimo_acesso',
        'expira_em',
    ]
    list_filter = ['ativo', 'subdominio', 'criado_em']
    search_fields = ['cliente__nome', 'cliente__telefone', 'ip_address']
    readonly_fields = [
        'id', 'token', 'cliente', 'subdominio', 'ip_address',
        'user_agent', 'criado_em', 'ultimo_acesso', 'expira_em'
    ]
    ordering = ['-criado_em']
    date_hierarchy = 'criado_em'

    fieldsets = (
        ('Sessao', {
            'fields': ('id', 'token', 'ativo')
        }),
        ('Cliente', {
            'fields': ('cliente', 'subdominio')
        }),
        ('Seguranca', {
            'fields': ('ip_address', 'user_agent')
        }),
        ('Timestamps', {
            'fields': ('criado_em', 'ultimo_acesso', 'expira_em')
        }),
    )

    def status_sessao(self, obj):
        """Exibe status da sessao."""
        if not obj.ativo:
            return format_html(
                '<span style="background-color: #6c757d; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">Encerrada</span>'
            )
        if timezone.now() > obj.expira_em:
            return format_html(
                '<span style="background-color: #ffc107; color: black; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">Expirada</span>'
            )
        return format_html(
            '<span style="background-color: #198754; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">Ativa</span>'
        )
    status_sessao.short_description = 'Status'

    def has_add_permission(self, request):
        """Nao permite criar sessoes pelo admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Permite apenas encerrar sessoes."""
        return True

    actions = ['encerrar_sessoes']

    @admin.action(description='Encerrar sessoes selecionadas')
    def encerrar_sessoes(self, request, queryset):
        """Encerra as sessoes selecionadas."""
        count = queryset.filter(ativo=True).update(ativo=False)
        self.message_user(request, f'{count} sessao(oes) encerrada(s).')


@admin.register(TentativaLogin)
class TentativaLoginAdmin(admin.ModelAdmin):
    """Admin para visualizacao de tentativas de login."""

    list_display = [
        'ip_address',
        'subdominio',
        'identificador_mascarado',
        'resultado_badge',
        'criado_em',
    ]
    list_filter = ['sucesso', 'subdominio', 'criado_em']
    search_fields = ['ip_address', 'identificador']
    readonly_fields = ['ip_address', 'subdominio', 'identificador', 'sucesso', 'criado_em']
    ordering = ['-criado_em']
    date_hierarchy = 'criado_em'

    def identificador_mascarado(self, obj):
        """Mascara parte do identificador por privacidade."""
        ident = obj.identificador
        if '@' in ident:
            # Email: mostra primeiros 3 chars + ***@dominio
            parts = ident.split('@')
            return f"{parts[0][:3]}***@{parts[1]}"
        else:
            # Telefone: mostra primeiros 4 e ultimos 2
            if len(ident) > 6:
                return f"{ident[:4]}***{ident[-2:]}"
        return ident
    identificador_mascarado.short_description = 'Identificador'

    def resultado_badge(self, obj):
        """Exibe badge de resultado."""
        if obj.sucesso:
            return format_html(
                '<span style="background-color: #198754; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">Sucesso</span>'
            )
        return format_html(
            '<span style="background-color: #dc3545; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">Falha</span>'
        )
    resultado_badge.short_description = 'Resultado'

    def has_add_permission(self, request):
        """Nao permite criar tentativas pelo admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Nao permite editar tentativas."""
        return False

    actions = ['limpar_tentativas_antigas']

    @admin.action(description='Limpar tentativas com mais de 24 horas')
    def limpar_tentativas_antigas(self, request, queryset):
        """Remove tentativas antigas."""
        limite = timezone.now() - timezone.timedelta(hours=24)
        count, _ = TentativaLogin.objects.filter(criado_em__lt=limite).delete()
        self.message_user(request, f'{count} tentativa(s) removida(s).')
