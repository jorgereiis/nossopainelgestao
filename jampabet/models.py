"""
Modelos do JampaBet - Sistema de Palpites do Bahia
"""
import secrets
from django.db import models
from django.utils import timezone
from datetime import timedelta


class JampabetUser(models.Model):
    """
    Usuário do JampaBet - COMPLETAMENTE ISOLADO do auth_user do Django.
    Cada sistema tem sua própria base de usuários.
    """
    # Categorias de usuário
    ROLE_CHOICES = [
        ('admin', 'Administrador'),
        ('supervisor', 'Supervisor'),
        ('user', 'Palpiteiro'),
    ]

    email = models.EmailField(unique=True, verbose_name='E-mail')
    password_hash = models.CharField(max_length=255, blank=True, verbose_name='Senha (hash)')
    name = models.CharField(max_length=100, verbose_name='Nome')
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='user',
        verbose_name='Categoria'
    )
    points = models.IntegerField(default=0, verbose_name='Pontos')
    hits = models.IntegerField(default=0, verbose_name='Acertos')
    is_active = models.BooleanField(default=True, verbose_name='Ativo')
    is_admin = models.BooleanField(default=False, verbose_name='Administrador (legado)')

    # Campos para verificação de e-mail e ativação de conta
    is_verified = models.BooleanField(default=False, verbose_name='E-mail verificado')
    verification_token = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        verbose_name='Token de verificação'
    )
    verification_expires = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Expiração do token'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        db_table = 'jampabet_user'
        verbose_name = 'Usuário JampaBet'
        verbose_name_plural = 'Usuários JampaBet'
        ordering = ['-points', 'name']

    def __str__(self):
        return f"{self.name} ({self.points} pts)"

    def has_admin_access(self):
        """Verifica se o usuario tem acesso administrativo (admin ou is_admin legado)"""
        return self.role == 'admin' or self.is_admin

    def has_supervisor_access(self):
        """Verifica se o usuario tem acesso de supervisor ou superior"""
        return self.role in ('admin', 'supervisor') or self.is_admin

    def get_role_display_badge(self):
        """Retorna classe CSS para o badge da categoria"""
        badges = {
            'admin': 'badge-admin',
            'supervisor': 'badge-supervisor',
            'user': 'badge-user',
        }
        return badges.get(self.role, 'badge-user')

    def generate_verification_token(self):
        """Gera um novo token de verificação de 64 caracteres"""
        self.verification_token = secrets.token_urlsafe(48)
        self.verification_expires = timezone.now() + timedelta(hours=24)
        self.save(update_fields=['verification_token', 'verification_expires'])
        return self.verification_token

    def is_verification_token_valid(self):
        """Verifica se o token de verificação ainda é válido"""
        if not self.verification_token or not self.verification_expires:
            return False
        return timezone.now() < self.verification_expires


class LoginToken(models.Model):
    """
    Token temporário para autenticação em duas etapas (2FA por e-mail).
    Enviado a cada login para confirmar a identidade do usuário.
    """
    user = models.ForeignKey(
        JampabetUser,
        on_delete=models.CASCADE,
        related_name='login_tokens',
        verbose_name='Usuário'
    )
    token = models.CharField(max_length=6, verbose_name='Token (6 dígitos)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    expires_at = models.DateTimeField(verbose_name='Expira em')
    used = models.BooleanField(default=False, verbose_name='Usado')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP')

    class Meta:
        db_table = 'jampabet_login_token'
        verbose_name = 'Token de Login'
        verbose_name_plural = 'Tokens de Login'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'token', 'used']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.token} ({'Usado' if self.used else 'Válido'})"

    @classmethod
    def generate_for_user(cls, user, ip_address=None):
        """
        Gera um novo token de 6 dígitos para o usuário.
        Invalida tokens anteriores não utilizados.
        """
        # Invalida tokens anteriores
        cls.objects.filter(user=user, used=False).update(used=True)

        # Gera novo token de 6 dígitos
        token = ''.join([str(secrets.randbelow(10)) for _ in range(6)])

        return cls.objects.create(
            user=user,
            token=token,
            expires_at=timezone.now() + timedelta(minutes=5),
            ip_address=ip_address
        )

    def is_valid(self):
        """Verifica se o token ainda é válido"""
        if self.used:
            return False
        return timezone.now() < self.expires_at

    def mark_as_used(self):
        """Marca o token como usado"""
        self.used = True
        self.save(update_fields=['used'])


class Match(models.Model):
    """Partidas do Bahia"""
    STATUS_CHOICES = [
        ('upcoming', 'Agendado'),
        ('live', 'Ao Vivo'),
        ('finished', 'Encerrado'),
        ('cancelled', 'Cancelado'),
        ('postponed', 'Adiado'),
    ]

    LOCATION_CHOICES = [
        ('home', 'Casa'),
        ('away', 'Fora'),
    ]

    external_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name='ID Externo (API-Football)'
    )
    home_team = models.CharField(max_length=100, verbose_name='Time da Casa')
    away_team = models.CharField(max_length=100, verbose_name='Time Visitante')
    home_team_logo = models.URLField(blank=True, verbose_name='Logo Time Casa')
    away_team_logo = models.URLField(blank=True, verbose_name='Logo Time Visitante')
    date = models.DateTimeField(verbose_name='Data/Hora')
    competition = models.CharField(max_length=100, verbose_name='Competição')
    competition_logo = models.URLField(blank=True, verbose_name='Logo Competição')
    venue = models.CharField(max_length=200, blank=True, verbose_name='Estádio')
    location = models.CharField(
        max_length=10,
        choices=LOCATION_CHOICES,
        verbose_name='Local (Bahia)'
    )
    round = models.CharField(max_length=50, blank=True, verbose_name='Rodada')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='upcoming',
        verbose_name='Status'
    )
    result_bahia = models.IntegerField(null=True, blank=True, verbose_name='Gols Bahia')
    result_opponent = models.IntegerField(null=True, blank=True, verbose_name='Gols Adversário')
    elapsed_time = models.IntegerField(null=True, blank=True, verbose_name='Tempo de Jogo')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        db_table = 'jampabet_match'
        verbose_name = 'Partida'
        verbose_name_plural = 'Partidas'
        ordering = ['-date']

    def __str__(self):
        return f"{self.home_team} x {self.away_team} - {self.date.strftime('%d/%m/%Y')}"

    @property
    def opponent(self):
        """Retorna o nome do adversário"""
        if self.location == 'home':
            return self.away_team
        return self.home_team

    @property
    def is_bahia_home(self):
        """Verifica se Bahia joga em casa"""
        return self.location == 'home'


class Bet(models.Model):
    """Apostas/Palpites dos usuários"""
    user = models.ForeignKey(
        JampabetUser,
        on_delete=models.CASCADE,
        related_name='bets',
        verbose_name='Usuário'
    )
    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name='bets',
        verbose_name='Partida'
    )
    # Palpite para vitória do Bahia
    home_win_bahia = models.IntegerField(verbose_name='Vitória Bahia - Gols Bahia')
    home_win_opponent = models.IntegerField(verbose_name='Vitória Bahia - Gols Adversário')
    # Palpite para empate
    draw_bahia = models.IntegerField(verbose_name='Empate - Gols Bahia')
    draw_opponent = models.IntegerField(verbose_name='Empate - Gols Adversário')
    # Pontos ganhos
    points_earned = models.IntegerField(default=0, verbose_name='Pontos Ganhos')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        db_table = 'jampabet_bet'
        verbose_name = 'Aposta'
        verbose_name_plural = 'Apostas'
        unique_together = ['user', 'match']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.name} - {self.match}"

    def clean(self):
        from django.core.exceptions import ValidationError
        # Validação: palpite de vitória deve ter Bahia com mais gols
        if self.home_win_bahia <= self.home_win_opponent:
            raise ValidationError({
                'home_win_bahia': 'No palpite de vitória, Bahia deve ter mais gols.'
            })
        # Validação: palpite de empate deve ter placares iguais
        if self.draw_bahia != self.draw_opponent:
            raise ValidationError({
                'draw_bahia': 'No palpite de empate, os placares devem ser iguais.'
            })


class BrazilianTeam(models.Model):
    """
    Mapeamento de times brasileiros com informacoes estaticas.
    Usado para cache local e evitar consultas excessivas a API.
    """
    external_id = models.IntegerField(
        unique=True,
        verbose_name='ID API-Football',
        help_text='ID do time na API-Football'
    )
    name = models.CharField(max_length=100, verbose_name='Nome completo')
    short_name = models.CharField(
        max_length=30,
        verbose_name='Nome curto',
        help_text='Nome abreviado para exibicao (ex: Sport, Bahia, Vitoria)'
    )
    display_name = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Nome de exibicao',
        help_text='Nome personalizado para exibicao (ex: Vicetoria para o Vitoria)'
    )
    logo_url = models.URLField(
        blank=True,
        verbose_name='Logo URL (API)',
        help_text='URL do logo fornecido pela API'
    )
    custom_logo_url = models.URLField(
        blank=True,
        verbose_name='Logo URL (personalizado)',
        help_text='URL de logo personalizado (sobrescreve o da API)'
    )
    code = models.CharField(
        max_length=5,
        blank=True,
        verbose_name='Codigo',
        help_text='Codigo de 3 letras (ex: BAH, VIT, SPT)'
    )
    country = models.CharField(
        max_length=50,
        default='Brazil',
        verbose_name='Pais'
    )
    city = models.CharField(max_length=100, blank=True, verbose_name='Cidade')
    state = models.CharField(max_length=50, blank=True, verbose_name='Estado')
    stadium = models.CharField(max_length=150, blank=True, verbose_name='Estadio')
    stadium_capacity = models.IntegerField(null=True, blank=True, verbose_name='Capacidade')
    founded = models.IntegerField(null=True, blank=True, verbose_name='Ano de fundacao')
    is_active = models.BooleanField(default=True, verbose_name='Ativo')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        db_table = 'jampabet_brazilian_team'
        verbose_name = 'Time Brasileiro'
        verbose_name_plural = 'Times Brasileiros'
        ordering = ['name']
        indexes = [
            models.Index(fields=['external_id']),
            models.Index(fields=['name']),
            models.Index(fields=['short_name']),
        ]

    def __str__(self):
        return self.name

    @property
    def get_display_name(self):
        """Retorna o nome de exibicao (personalizado ou curto)"""
        return self.display_name or self.short_name or self.name

    @property
    def get_logo(self):
        """Retorna o logo (personalizado ou da API)"""
        return self.custom_logo_url or self.logo_url

    @classmethod
    def get_by_api_id(cls, api_id):
        """Busca time pelo ID da API"""
        try:
            return cls.objects.get(external_id=api_id)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_display_info(cls, api_id, default_name='', default_logo=''):
        """
        Retorna nome e logo para exibicao.
        Se o time estiver cadastrado, usa os dados locais.
        Caso contrario, usa os valores default.
        """
        team = cls.get_by_api_id(api_id)
        if team:
            return {
                'name': team.get_display_name,
                'logo': team.get_logo or default_logo,
                'short_name': team.short_name,
            }
        return {
            'name': default_name,
            'logo': default_logo,
            'short_name': default_name,
        }


class Competition(models.Model):
    """
    Competicoes brasileiras de futebol.
    Armazena informacoes estaticas das competicoes.
    """
    COMPETITION_TYPES = [
        ('league', 'Liga/Campeonato'),
        ('cup', 'Copa'),
        ('state', 'Estadual'),
    ]

    external_id = models.IntegerField(
        unique=True,
        verbose_name='ID API-Football',
        help_text='ID da competicao na API-Football'
    )
    name = models.CharField(max_length=100, verbose_name='Nome')
    short_name = models.CharField(max_length=30, blank=True, verbose_name='Nome curto')
    logo_url = models.URLField(blank=True, verbose_name='Logo URL')
    competition_type = models.CharField(
        max_length=20,
        choices=COMPETITION_TYPES,
        default='league',
        verbose_name='Tipo'
    )
    country = models.CharField(max_length=50, default='Brazil', verbose_name='Pais')
    current_season = models.IntegerField(null=True, blank=True, verbose_name='Temporada atual')
    is_active = models.BooleanField(default=True, verbose_name='Ativa')
    is_tracked = models.BooleanField(
        default=False,
        verbose_name='Monitorada',
        help_text='Se True, as partidas desta competicao serao sincronizadas'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        db_table = 'jampabet_competition'
        verbose_name = 'Competicao'
        verbose_name_plural = 'Competicoes'
        ordering = ['name']
        indexes = [
            models.Index(fields=['external_id']),
            models.Index(fields=['is_tracked']),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def get_by_api_id(cls, api_id):
        """Busca competicao pelo ID da API"""
        try:
            return cls.objects.get(external_id=api_id)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_tracked_competitions(cls):
        """Retorna competicoes que devem ter partidas sincronizadas"""
        return cls.objects.filter(is_tracked=True, is_active=True)


class Fixture(models.Model):
    """
    Partidas de todas as competicoes brasileiras.
    Usado como cache para evitar consultas excessivas a API.
    """
    STATUS_CHOICES = [
        ('scheduled', 'Agendado'),
        ('live', 'Ao Vivo'),
        ('finished', 'Encerrado'),
        ('postponed', 'Adiado'),
        ('cancelled', 'Cancelado'),
        ('suspended', 'Suspenso'),
        ('interrupted', 'Interrompido'),
        ('abandoned', 'Abandonado'),
    ]

    external_id = models.IntegerField(
        unique=True,
        verbose_name='ID API-Football',
        help_text='ID da partida na API-Football'
    )
    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name='fixtures',
        verbose_name='Competicao'
    )
    season = models.IntegerField(verbose_name='Temporada')
    round = models.CharField(max_length=50, blank=True, verbose_name='Rodada')
    round_number = models.IntegerField(null=True, blank=True, verbose_name='Numero da rodada')

    # Times
    home_team = models.ForeignKey(
        BrazilianTeam,
        on_delete=models.SET_NULL,
        null=True,
        related_name='home_fixtures',
        verbose_name='Time da casa'
    )
    away_team = models.ForeignKey(
        BrazilianTeam,
        on_delete=models.SET_NULL,
        null=True,
        related_name='away_fixtures',
        verbose_name='Time visitante'
    )
    # IDs originais da API (caso o time nao esteja cadastrado)
    home_team_api_id = models.IntegerField(null=True, blank=True)
    away_team_api_id = models.IntegerField(null=True, blank=True)
    home_team_name = models.CharField(max_length=100, blank=True)
    away_team_name = models.CharField(max_length=100, blank=True)
    home_team_logo = models.URLField(blank=True)
    away_team_logo = models.URLField(blank=True)

    # Placar
    home_goals = models.IntegerField(null=True, blank=True, verbose_name='Gols casa')
    away_goals = models.IntegerField(null=True, blank=True, verbose_name='Gols visitante')
    home_goals_ht = models.IntegerField(null=True, blank=True, verbose_name='Gols casa (1T)')
    away_goals_ht = models.IntegerField(null=True, blank=True, verbose_name='Gols visitante (1T)')

    # Data e local
    date = models.DateTimeField(verbose_name='Data/Hora')
    venue = models.CharField(max_length=150, blank=True, verbose_name='Estadio')
    venue_city = models.CharField(max_length=100, blank=True, verbose_name='Cidade')

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled',
        verbose_name='Status'
    )
    elapsed_time = models.IntegerField(null=True, blank=True, verbose_name='Tempo decorrido')

    # Controle
    last_api_update = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Ultima atualizacao da API'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        db_table = 'jampabet_fixture'
        verbose_name = 'Partida'
        verbose_name_plural = 'Partidas'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['external_id']),
            models.Index(fields=['competition', 'season']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['home_team']),
            models.Index(fields=['away_team']),
            models.Index(fields=['round_number']),
        ]

    def __str__(self):
        home = self.home_team.get_display_name if self.home_team else self.home_team_name
        away = self.away_team.get_display_name if self.away_team else self.away_team_name
        return f"{home} x {away} - {self.date.strftime('%d/%m/%Y')}"

    @property
    def get_home_name(self):
        """Retorna nome do time da casa"""
        if self.home_team:
            return self.home_team.get_display_name
        return self.home_team_name

    @property
    def get_away_name(self):
        """Retorna nome do time visitante"""
        if self.away_team:
            return self.away_team.get_display_name
        return self.away_team_name

    @property
    def get_home_logo(self):
        """Retorna logo do time da casa"""
        if self.home_team:
            return self.home_team.get_logo
        return self.home_team_logo

    @property
    def get_away_logo(self):
        """Retorna logo do time visitante"""
        if self.away_team:
            return self.away_team.get_logo
        return self.away_team_logo

    @property
    def is_bahia_match(self):
        """Verifica se e partida do Bahia"""
        bahia_id = 118  # ID do Bahia na API
        return (
            (self.home_team and self.home_team.external_id == bahia_id) or
            (self.away_team and self.away_team.external_id == bahia_id) or
            self.home_team_api_id == bahia_id or
            self.away_team_api_id == bahia_id
        )

    @classmethod
    def get_by_api_id(cls, api_id):
        """Busca partida pelo ID da API"""
        try:
            return cls.objects.get(external_id=api_id)
        except cls.DoesNotExist:
            return None


class APIConfig(models.Model):
    """
    Configuracoes da API-Football e polling de partidas ao vivo.
    Deve existir apenas um registro (singleton).
    """
    # Configuracoes da API
    api_key = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Chave da API',
        help_text='Chave de acesso da API-Football'
    )
    api_enabled = models.BooleanField(
        default=True,
        verbose_name='API Habilitada',
        help_text='Se desabilitado, nao fara consultas a API externa'
    )

    # Configuracoes de polling
    polling_interval = models.IntegerField(
        default=60,
        verbose_name='Intervalo de Polling (segundos)',
        help_text='Intervalo em segundos para consultar partidas ao vivo (minimo 30s)'
    )
    auto_start_matches = models.BooleanField(
        default=True,
        verbose_name='Iniciar Partidas Automaticamente',
        help_text='Mudar status para "live" quando chegar o horario de inicio'
    )
    auto_update_scores = models.BooleanField(
        default=True,
        verbose_name='Atualizar Placares Automaticamente',
        help_text='Buscar placares em tempo real via API'
    )

    # Configuracoes de notificacao
    minutes_before_match = models.IntegerField(
        default=10,
        verbose_name='Minutos antes para bloquear palpites',
        help_text='Bloquear palpites X minutos antes do inicio'
    )

    # Configuracoes de pontuacao
    points_exact_victory = models.IntegerField(
        default=3,
        verbose_name='Pontos por placar exato de triunfo',
        help_text='Pontuacao para quem acertar o placar exato em caso de vitoria do Bahia'
    )
    points_exact_draw = models.IntegerField(
        default=1,
        verbose_name='Pontos por placar exato de empate',
        help_text='Pontuacao para quem acertar o placar exato em caso de empate'
    )
    round_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Valor por rodada',
        help_text='Valor que o usuario deve pagar por rodada com palpite feito'
    )

    # Logs e controle
    last_poll_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Ultimo polling'
    )
    last_poll_status = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Status do ultimo polling'
    )
    last_poll_message = models.TextField(
        blank=True,
        verbose_name='Mensagem do ultimo polling'
    )
    total_api_calls_today = models.IntegerField(
        default=0,
        verbose_name='Chamadas API hoje'
    )
    last_api_call_reset = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data do ultimo reset de chamadas'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        db_table = 'jampabet_api_config'
        verbose_name = 'Configuracao da API'
        verbose_name_plural = 'Configuracoes da API'

    def __str__(self):
        return f"Configuracao da API (Polling: {self.polling_interval}s)"

    def save(self, *args, **kwargs):
        # Garante que polling_interval seja no minimo 30 segundos
        if self.polling_interval < 30:
            self.polling_interval = 30
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        """Retorna a configuracao singleton (cria se nao existir)"""
        config, created = cls.objects.get_or_create(pk=1)
        return config

    def increment_api_calls(self):
        """Incrementa contador de chamadas e reseta se mudou o dia"""
        from django.utils import timezone
        today = timezone.now().date()

        if self.last_api_call_reset != today:
            self.total_api_calls_today = 0
            self.last_api_call_reset = today

        self.total_api_calls_today += 1
        self.save(update_fields=['total_api_calls_today', 'last_api_call_reset'])

    def update_poll_status(self, status, message=''):
        """Atualiza status do ultimo polling"""
        from django.utils import timezone
        self.last_poll_at = timezone.now()
        self.last_poll_status = status
        self.last_poll_message = message
        self.save(update_fields=['last_poll_at', 'last_poll_status', 'last_poll_message'])


class AuditLog(models.Model):
    """Log de auditoria para ações importantes"""
    ACTION_CHOICES = [
        ('register', 'Registro'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('create_bet', 'Criar Aposta'),
        ('update_bet', 'Atualizar Aposta'),
        ('delete_bet', 'Excluir Aposta'),
        ('register_result', 'Registrar Resultado'),
    ]

    user = models.ForeignKey(
        JampabetUser,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Usuário'
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, verbose_name='Ação')
    entity_type = models.CharField(max_length=50, blank=True, verbose_name='Tipo de Entidade')
    entity_id = models.IntegerField(null=True, blank=True, verbose_name='ID da Entidade')
    old_value = models.JSONField(null=True, blank=True, verbose_name='Valor Anterior')
    new_value = models.JSONField(null=True, blank=True, verbose_name='Novo Valor')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP')
    user_agent = models.TextField(blank=True, verbose_name='User Agent')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Data/Hora')

    class Meta:
        db_table = 'jampabet_audit_log'
        verbose_name = 'Log de Auditoria'
        verbose_name_plural = 'Logs de Auditoria'
        ordering = ['-created_at']

    def __str__(self):
        user_name = self.user.name if self.user else 'Sistema'
        return f"{user_name} - {self.get_action_display()} - {self.created_at}"
