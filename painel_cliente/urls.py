"""
URLs do Painel do Cliente.

Este modulo define as rotas para:
- Cliente Final: login, dashboard, perfil, pagamento, historico
- Painel Admin: gestao de subdominios, personalizacao, estatisticas
"""

from django.urls import path

from .views import cliente as cliente_views
from .views import admin as admin_views

app_name = 'painel_cliente'

urlpatterns = [
    # ==================== CLIENTE FINAL ====================
    # Acessado via subdominio.pagar.cc

    # Autenticacao
    path('', cliente_views.LoginView.as_view(), name='login'),
    path('logout/', cliente_views.logout_view, name='logout'),

    # Perfil (obrigatorio na primeira vez)
    path('perfil/', cliente_views.PerfilView.as_view(), name='perfil'),

    # Dashboard principal
    path('dashboard/', cliente_views.DashboardView.as_view(), name='dashboard'),

    # Pagamento
    path(
        'pagamento/<int:mensalidade_id>/',
        cliente_views.PagamentoView.as_view(),
        name='pagamento'
    ),
    path(
        'pagamento/<int:mensalidade_id>/gerar-pix/',
        cliente_views.gerar_pix,
        name='gerar_pix'
    ),
    path(
        'pagamento/<uuid:cobranca_id>/status/',
        cliente_views.status_pix,
        name='status_pix'
    ),

    # Historico de mensalidades
    path('historico/', cliente_views.HistoricoView.as_view(), name='historico'),

    # ==================== PAINEL ADMIN ====================
    # Acessado via subdominio.pagar.cc/painel-admin/

    # Login/Logout do Admin
    path(
        'painel-admin/login/',
        admin_views.AdminLoginView.as_view(),
        name='admin_login'
    ),
    path(
        'painel-admin/logout/',
        admin_views.admin_logout_view,
        name='admin_logout'
    ),

    # Dashboard administrativo
    path(
        'painel-admin/',
        admin_views.DashboardAdminView.as_view(),
        name='admin_dashboard'
    ),

    # Gestao de Subdominios (apenas Admin Superior)
    path(
        'painel-admin/subdominios/',
        admin_views.SubdominioListView.as_view(),
        name='admin_subdominios'
    ),
    path(
        'painel-admin/subdominios/criar/',
        admin_views.SubdominioCriarView.as_view(),
        name='admin_subdominio_criar'
    ),
    path(
        'painel-admin/subdominios/<int:pk>/editar/',
        admin_views.SubdominioEditarView.as_view(),
        name='admin_subdominio_editar'
    ),
    path(
        'painel-admin/subdominios/<int:pk>/excluir/',
        admin_views.SubdominioExcluirView.as_view(),
        name='admin_subdominio_excluir'
    ),

    # Personalizacao (Admin Comum e Superior)
    path(
        'painel-admin/personalizacao/',
        admin_views.PersonalizacaoView.as_view(),
        name='admin_personalizacao'
    ),
    path(
        'painel-admin/personalizacao/remover-logo/',
        admin_views.remover_logo_view,
        name='admin_remover_logo'
    ),

    # Estatisticas
    path(
        'painel-admin/estatisticas/',
        admin_views.EstatisticasView.as_view(),
        name='admin_estatisticas'
    ),
]
