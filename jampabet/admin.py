"""
Admin do JampaBet
"""
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse, path
from django.utils.html import format_html
from .models import (
    JampabetUser, LoginToken, Match, Bet, AuditLog,
    BrazilianTeam, Competition, Fixture, APIConfig
)
from .auth import JampabetAuth


@admin.register(JampabetUser)
class JampabetUserAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'email', 'points', 'hits',
        'is_verified_badge', 'is_active', 'is_admin', 'created_at'
    ]
    list_filter = ['is_active', 'is_verified', 'is_admin', 'created_at']
    search_fields = ['name', 'email']
    ordering = ['-points', 'name']
    readonly_fields = ['created_at', 'updated_at', 'verification_token', 'verification_expires']
    actions = ['resend_activation_email', 'activate_users']

    fieldsets = (
        ('Informacoes Basicas', {
            'fields': ('name', 'email', 'password_hash')
        }),
        ('Pontuacao', {
            'fields': ('points', 'hits')
        }),
        ('Status', {
            'fields': ('is_active', 'is_verified', 'is_admin')
        }),
        ('Verificacao de E-mail', {
            'fields': ('verification_token', 'verification_expires'),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def is_verified_badge(self, obj):
        if obj.is_verified:
            return format_html(
                '<span style="color: #00ff88; font-weight: bold;">&#10004; Verificado</span>'
            )
        return format_html(
            '<span style="color: #ff4757;">&#10008; Pendente</span>'
        )
    is_verified_badge.short_description = 'E-mail'
    is_verified_badge.admin_order_field = 'is_verified'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:user_id>/send-activation/',
                self.admin_site.admin_view(self.send_activation_view),
                name='jampabet_jampabetuser_send_activation',
            ),
        ]
        return custom_urls + urls

    def send_activation_view(self, request, user_id):
        """View para reenviar e-mail de ativacao"""
        try:
            user = JampabetUser.objects.get(id=user_id)
            if user.is_verified:
                messages.warning(request, f'Usuario {user.name} ja esta verificado.')
            else:
                if JampabetAuth.send_activation_email(user, request):
                    messages.success(request, f'E-mail de ativacao enviado para {user.email}')
                else:
                    messages.error(request, 'Erro ao enviar e-mail. Verifique as configuracoes de SMTP.')
        except JampabetUser.DoesNotExist:
            messages.error(request, 'Usuario nao encontrado.')

        return HttpResponseRedirect(reverse('admin:jampabet_jampabetuser_changelist'))

    @admin.action(description='Reenviar e-mail de ativacao')
    def resend_activation_email(self, request, queryset):
        """Acao para reenviar e-mail de ativacao em massa"""
        sent_count = 0
        for user in queryset.filter(is_verified=False):
            if JampabetAuth.send_activation_email(user, request):
                sent_count += 1

        if sent_count > 0:
            messages.success(request, f'E-mail de ativacao enviado para {sent_count} usuario(s).')
        else:
            messages.warning(request, 'Nenhum e-mail enviado. Usuarios ja verificados ou erro no envio.')

    @admin.action(description='Ativar usuarios selecionados (sem e-mail)')
    def activate_users(self, request, queryset):
        """Ativa usuarios diretamente sem precisar de e-mail"""
        updated = queryset.filter(is_verified=False).update(
            is_verified=True,
            verification_token=None,
            verification_expires=None
        )
        messages.success(request, f'{updated} usuario(s) ativado(s).')

    def save_model(self, request, obj, form, change):
        """
        Ao criar novo usuario pelo admin:
        - Se is_verified=False, gera token e envia e-mail
        - Nao define senha (usuario define ao ativar)
        """
        is_new = not obj.pk

        # Se e novo e nao esta verificado, gera token
        if is_new and not obj.is_verified:
            obj.password_hash = ''  # Senha vazia ate ativacao
            super().save_model(request, obj, form, change)
            # Envia e-mail de ativacao
            if JampabetAuth.send_activation_email(obj, request):
                messages.info(request, f'E-mail de ativacao enviado para {obj.email}')
            else:
                messages.warning(
                    request,
                    f'Usuario criado, mas houve erro ao enviar e-mail. '
                    f'Reenvie manualmente pela lista de usuarios.'
                )
        else:
            super().save_model(request, obj, form, change)


@admin.register(LoginToken)
class LoginTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token', 'is_valid_badge', 'used', 'ip_address', 'created_at', 'expires_at']
    list_filter = ['used', 'created_at']
    search_fields = ['user__name', 'user__email', 'ip_address']
    ordering = ['-created_at']
    readonly_fields = ['user', 'token', 'created_at', 'expires_at', 'used', 'ip_address']

    def is_valid_badge(self, obj):
        if obj.is_valid():
            return format_html(
                '<span style="color: #00ff88; font-weight: bold;">Valido</span>'
            )
        return format_html(
            '<span style="color: #888;">Expirado/Usado</span>'
        )
    is_valid_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'competition', 'status', 'result_bahia', 'result_opponent', 'date']
    list_filter = ['status', 'competition', 'location']
    search_fields = ['home_team', 'away_team', 'competition']
    ordering = ['-date']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Partida', {
            'fields': ('home_team', 'away_team', 'date', 'venue', 'location')
        }),
        ('Competicao', {
            'fields': ('competition', 'competition_logo', 'round')
        }),
        ('Resultado', {
            'fields': ('status', 'result_bahia', 'result_opponent', 'elapsed_time')
        }),
        ('Logos', {
            'fields': ('home_team_logo', 'away_team_logo'),
            'classes': ('collapse',)
        }),
        ('API', {
            'fields': ('external_id',),
            'classes': ('collapse',)
        }),
        ('Datas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ['user', 'match', 'home_win_bahia', 'home_win_opponent',
                    'draw_bahia', 'draw_opponent', 'points_earned', 'created_at']
    list_filter = ['points_earned', 'created_at']
    search_fields = ['user__name', 'user__email']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user', 'match']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'entity_type', 'entity_id', 'ip_address', 'created_at']
    list_filter = ['action', 'entity_type', 'created_at']
    search_fields = ['user__name', 'ip_address']
    ordering = ['-created_at']
    readonly_fields = ['user', 'action', 'entity_type', 'entity_id',
                       'old_value', 'new_value', 'ip_address', 'user_agent', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BrazilianTeam)
class BrazilianTeamAdmin(admin.ModelAdmin):
    """Admin para times brasileiros."""
    list_display = [
        'name', 'short_name', 'external_id', 'code',
        'city', 'state', 'is_active', 'updated_at'
    ]
    list_filter = ['is_active', 'state']
    search_fields = ['name', 'short_name', 'code', 'city']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_active']

    fieldsets = (
        ('Identificacao', {
            'fields': ('external_id', 'name', 'short_name', 'display_name', 'code')
        }),
        ('Logos', {
            'fields': ('logo_url', 'custom_logo_url'),
            'classes': ('collapse',)
        }),
        ('Localizacao', {
            'fields': ('country', 'city', 'state', 'stadium', 'stadium_capacity')
        }),
        ('Informacoes', {
            'fields': ('founded', 'is_active')
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    """Admin para competicoes."""
    list_display = [
        'name', 'short_name', 'external_id', 'competition_type',
        'current_season', 'is_tracked', 'is_active', 'updated_at'
    ]
    list_filter = ['competition_type', 'is_tracked', 'is_active', 'country']
    search_fields = ['name', 'short_name']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_tracked', 'is_active']

    fieldsets = (
        ('Identificacao', {
            'fields': ('external_id', 'name', 'short_name', 'logo_url')
        }),
        ('Configuracao', {
            'fields': ('competition_type', 'country', 'current_season')
        }),
        ('Status', {
            'fields': ('is_active', 'is_tracked')
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Fixture)
class FixtureAdmin(admin.ModelAdmin):
    """Admin para partidas de competicoes."""
    list_display = [
        '__str__', 'competition', 'round', 'status',
        'home_goals', 'away_goals', 'date'
    ]
    list_filter = ['status', 'competition', 'season']
    search_fields = [
        'home_team__name', 'away_team__name',
        'home_team_name', 'away_team_name'
    ]
    ordering = ['-date']
    readonly_fields = ['created_at', 'updated_at', 'last_api_update']
    autocomplete_fields = ['competition', 'home_team', 'away_team']
    date_hierarchy = 'date'

    fieldsets = (
        ('Partida', {
            'fields': (
                'external_id', 'competition', 'season', 'round', 'round_number'
            )
        }),
        ('Times (Cadastrados)', {
            'fields': ('home_team', 'away_team')
        }),
        ('Times (API)', {
            'fields': (
                'home_team_api_id', 'home_team_name', 'home_team_logo',
                'away_team_api_id', 'away_team_name', 'away_team_logo'
            ),
            'classes': ('collapse',)
        }),
        ('Placar', {
            'fields': (
                'home_goals', 'away_goals', 'home_goals_ht', 'away_goals_ht'
            )
        }),
        ('Data e Local', {
            'fields': ('date', 'venue', 'venue_city')
        }),
        ('Status', {
            'fields': ('status', 'elapsed_time')
        }),
        ('Controle', {
            'fields': ('last_api_update', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(APIConfig)
class APIConfigAdmin(admin.ModelAdmin):
    """Admin para configuracoes da API (singleton)."""
    list_display = [
        'api_enabled', 'polling_interval', 'auto_update_scores',
        'total_api_calls_today', 'last_poll_at', 'last_poll_status'
    ]
    readonly_fields = [
        'last_poll_at', 'last_poll_status', 'last_poll_message',
        'total_api_calls_today', 'last_api_call_reset',
        'created_at', 'updated_at'
    ]

    fieldsets = (
        ('Configuracoes da API', {
            'fields': ('api_key', 'api_enabled')
        }),
        ('Polling', {
            'fields': (
                'polling_interval', 'auto_start_matches', 'auto_update_scores',
                'minutes_before_match'
            )
        }),
        ('Pontuacao', {
            'fields': ('points_exact_victory', 'points_exact_draw', 'round_cost')
        }),
        ('Status do Polling', {
            'fields': ('last_poll_at', 'last_poll_status', 'last_poll_message'),
            'classes': ('collapse',)
        }),
        ('Contagem de Chamadas', {
            'fields': ('total_api_calls_today', 'last_api_call_reset'),
            'classes': ('collapse',)
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """Permite apenas 1 registro (singleton)."""
        return not APIConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Nao permite excluir o registro singleton."""
        return False
