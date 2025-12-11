"""
URLs do JampaBet
"""
from django.urls import path
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from . import views

app_name = 'jampabet'

urlpatterns = [
    # ==============================================
    # AUTENTICACAO (paginas publicas)
    # ==============================================

    # Pagina inicial -> login ou app
    path('', views.home, name='home'),

    # Login com splash screen + modal 2FA
    path('login/', views.login_view, name='login'),

    # Logout
    path('logout/', views.logout_view, name='logout'),

    # Ativacao de conta (link enviado por e-mail)
    path('activate/<str:token>/', views.activate_view, name='activate'),

    # ==============================================
    # APIs DE AUTENTICACAO (publicas, protegidas por sessao)
    # ==============================================

    # Etapa 1: valida email/senha, envia token 2FA
    path('api/auth/login/step1/', views.api_login_step1, name='api_login_step1'),

    # Etapa 2: valida token 2FA, cria sessao
    path('api/auth/login/step2/', views.api_login_step2, name='api_login_step2'),

    # Reenvia token 2FA
    path('api/auth/resend-token/', views.api_resend_token, name='api_resend_token'),

    # ==============================================
    # APP PRINCIPAL (requer autenticacao)
    # ==============================================

    # App completo (dashboard, ranking, jogos, etc)
    path('app/', views.app_view, name='app'),

    # ==============================================
    # ROTAS LEGADAS (redirecionam para /app/)
    # ==============================================

    path('dashboard/', views.dashboard, name='dashboard'),
    path('ranking/', views.ranking, name='ranking'),
    path('jogos/', views.matches, name='matches'),
    path('classificacao/', views.standings, name='standings'),
    path('meus-palpites/', views.my_bets, name='my_bets'),

    # ==============================================
    # API ENDPOINTS (JSON)
    # ==============================================

    # Partidas
    path('api/matches/', views.api_matches, name='api_matches'),
    path('api/matches/upcoming/', views.api_upcoming_matches, name='api_upcoming_matches'),
    path('api/matches/next/', views.api_next_bahia_match, name='api_next_bahia_match'),
    path('api/matches/<int:match_id>/', views.api_match_detail, name='api_match_detail'),

    # Historico de palpites do usuario
    path('api/bets/history/', views.api_user_bets_history, name='api_user_bets_history'),

    # Classificacao (proxy API-Football)
    path('api/standings/<int:league_id>/', views.api_standings, name='api_standings'),
    path('api/fixtures/<int:league_id>/', views.api_league_fixtures, name='api_league_fixtures'),
    path('api/rounds/<int:league_id>/', views.api_league_rounds, name='api_league_rounds'),

    # Ranking
    path('api/ranking/', views.api_ranking, name='api_ranking'),

    # Competicoes disponiveis (para o select)
    path('api/competitions/', views.api_competitions, name='api_competitions'),

    # Apostas
    path('api/bet/', views.api_place_bet, name='api_place_bet'),
    path('api/bet/<int:match_id>/', views.api_get_bet, name='api_get_bet'),

    # ==============================================
    # API ADMINISTRATIVAS (requer admin)
    # ==============================================

    # Debug/verificacao de auth
    path('api/admin/check/', views.api_admin_check, name='api_admin_check'),

    # Estatisticas
    path('api/admin/stats/', views.api_admin_stats, name='api_admin_stats'),

    # Sincronizacao
    path('api/admin/sync/teams/', views.api_admin_sync_teams, name='api_admin_sync_teams'),
    path('api/admin/sync/competitions/', views.api_admin_sync_competitions, name='api_admin_sync_competitions'),
    path('api/admin/sync/fixtures/', views.api_admin_sync_fixtures, name='api_admin_sync_fixtures'),

    # Gerenciamento
    path('api/admin/competitions/', views.api_admin_competitions, name='api_admin_competitions'),
    path('api/admin/competitions/<int:competition_id>/toggle/', views.api_admin_toggle_competition, name='api_admin_toggle_competition'),
    path('api/admin/teams/', views.api_admin_teams, name='api_admin_teams'),

    # ==============================================
    # GERENCIAMENTO DE PARTIDAS (DEV ONLY)
    # ==============================================

    # Verifica se pode gerenciar partidas
    path('api/admin/dev-mode/', views.api_admin_check_dev_mode, name='api_admin_check_dev_mode'),

    # CRUD de partidas (apenas em DEBUG=True)
    path('api/admin/matches/', views.api_admin_matches, name='api_admin_matches'),
    path('api/admin/matches/create/', views.api_admin_match_create, name='api_admin_match_create'),
    path('api/admin/matches/<int:match_id>/', views.api_admin_match_detail, name='api_admin_match_detail'),
    path('api/admin/matches/<int:match_id>/update/', views.api_admin_match_update, name='api_admin_match_update'),
    path('api/admin/matches/<int:match_id>/delete/', views.api_admin_match_delete, name='api_admin_match_delete'),

    # Busca para autocomplete (apenas em DEBUG=True)
    path('api/admin/search/teams/', views.api_admin_search_teams, name='api_admin_search_teams'),
    path('api/admin/search/competitions/', views.api_admin_search_competitions, name='api_admin_search_competitions'),

    # ==============================================
    # GERENCIAMENTO DE USUARIOS
    # ==============================================

    path('api/admin/users/', views.api_admin_users, name='api_admin_users'),
    path('api/admin/users/create/', views.api_admin_user_create, name='api_admin_user_create'),
    path('api/admin/users/<int:user_id>/', views.api_admin_user_detail, name='api_admin_user_detail'),
    path('api/admin/users/<int:user_id>/update/', views.api_admin_user_update, name='api_admin_user_update'),
    path('api/admin/users/<int:user_id>/delete/', views.api_admin_user_delete, name='api_admin_user_delete'),
    path('api/admin/users/<int:user_id>/toggle-status/', views.api_admin_user_toggle_status, name='api_admin_user_toggle_status'),
    path('api/admin/users/<int:user_id>/reset-password/', views.api_admin_user_reset_password, name='api_admin_user_reset_password'),

    # ==============================================
    # CONFIGURACOES DA API
    # ==============================================

    path('api/admin/config/', views.api_admin_config, name='api_admin_config'),
    path('api/admin/config/update/', views.api_admin_config_update, name='api_admin_config_update'),
]

# Adiciona URLs de arquivos estaticos em desenvolvimento
urlpatterns += staticfiles_urlpatterns()
