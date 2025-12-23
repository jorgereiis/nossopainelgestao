import os
from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.http import HttpResponse
from django.conf import settings
from .views_webhook import webhook_wppconnect
from .views_chat import (
    ChatPageView,
    api_chat_list,
    api_chat_messages,
    api_load_earlier_messages,
    api_profile_picture,
    api_send_message,
    api_send_file,
    api_download_media,
    api_mark_as_read,
)
from .views_sse import sse_chat_stream
from .views import (
    test,
    Login,
    verify_2fa_code,
    whatsapp,
    create_app,
    editar_app,
    status_wpp,
    delete_app,
    edit_device,
    edit_server,
    session_wpp,
    profile_page,
    upload_avatar,
    remove_avatar,
    change_password,
    change_theme,
    update_notification_preferences,
    update_privacy_settings,
    profile_activity_history,
    setup_2fa,
    enable_2fa,
    disable_2fa,
    regenerate_backup_codes,
    get_2fa_qr_code,
    exportar_clientes_excel,
    conectar_wpp,
    get_logs_wpp,
    parar_envio,
    status_envio,
    limpar_log_wpp,
    edit_profile,
    edit_customer,
    api_cliente_contas,
    delete_server,
    delete_device,
    create_device,
    create_server,
    desconectar_wpp,
    TabelaDashboard,
    get_session_wpp,
    create_customer,
    cancel_customer,
    pay_monthly_fee,
    import_customers,
    LogFilesListView,
    ModalDNSJsonView,
    send_message_wpp,
    secret_token_api,
    edit_payment_plan,
    LogFileContentView,
    UserActionLogListView,
    ClientesCancelados,
    edit_referral_plan,
    delete_app_account,
    create_app_account,
    cancelar_sessao_wpp,
    reactivate_customer,
    CarregarInidicacoes,
    TabelaDashboardAjax,
    edit_horario_envios,
    edit_reject_call_config,
    create_payment_plan,
    delete_payment_plan,
    check_connection_wpp,
    delete_payment_method,
    MensalidadeDetailView,
    notifications_dropdown,
    NotificationsModalView,
    CarregarContasDoAplicativo,
    notifications_mark_all_read,
    mapa_clientes_data,
    CarregarQuantidadesMensalidades,
    generate_graphic_columns_per_year,
    generate_graphic_columns_per_month,
    notifications_count,
    evolucao_patrimonio,
    adesoes_cancelamentos_api,
    clientes_servidor_data,
    internal_send_whatsapp,
    # Migração de clientes
    MigrationClientesListView,
    MigrationValidationView,
    MigrationExecuteView,
    # Gestão de Domínios DNS (Reseller Automation)
    gestao_dns_page,
    obter_dispositivos_paginados_api,
    verificar_conta_reseller_api,
    iniciar_login_manual_api,
    iniciar_migracao_dns_api,
    consultar_progresso_migracao_api,
    listar_dominios_api,
    buscar_dispositivo_api,
    # API Debug Headless (Admin)
    toggle_debug_headless,
    get_debug_status,
    # Tarefas de Envio WhatsApp
    TarefaEnvioListView,
    TarefaEnvioCreateView,
    TarefaEnvioUpdateView,
    TarefaEnvioDeleteView,
    TarefaEnvioHistoricoView,
    tarefa_envio_toggle,
    tarefa_envio_duplicar,
    tarefa_envio_preview,
    tarefa_envio_sugestao_horarios,
    tarefa_envio_excluir_ajax,
    tarefas_envio_stats_api,
    tarefa_envio_preview_alcance,
    tarefa_envio_verificar_conflito,
    tarefa_envio_listar_templates,
    tarefa_envio_salvar_template,
    tarefa_envio_historico_api,
    # Integração Bancária
    api_instituicoes_bancarias,
    api_contas_bancarias,
    criar_conta_bancaria,
    excluir_conta_bancaria,
    criar_instituicao_bancaria,
    toggle_instituicao_bancaria,
    excluir_instituicao_bancaria,
    # Configuração de Limite MEI
    api_config_limite,
    api_config_limite_atualizar,
    # Credenciais API
    api_credenciais_por_tipo,
    # Clientes para Associação
    api_clientes_ativos_associacao,
    # Planos de Adesão
    api_planos,
    # Notificações do Sistema
    api_notificacoes_listar,
    api_notificacao_marcar_lida,
    api_notificacoes_marcar_todas_lidas,
    # Push Notifications
    api_push_subscribe,
    api_push_unsubscribe,
    api_push_vapid_public_key,
    # Cobrança PIX
    gerar_cobranca_pix,
    consultar_cobranca_pix,
    webhook_pagamento_pix,
    cancelar_cobranca_pix,
    # Admin - Testes
    create_payment_method_admin,
    # API Forma de Pagamento
    api_forma_pagamento_detalhes,
    api_forma_pagamento_atualizar,
    api_forma_pagamento_antiga_atualizar,
    api_forma_pagamento_clientes_count,
    # Integrações API
    integracoes_api_index,
    integracoes_fastdepix,
    integracoes_fastdepix_testar,
    integracoes_fastdepix_conta_dados,
    integracoes_fastdepix_webhook_registrar,
    integracoes_fastdepix_webhook_atualizar,
    integracoes_fastdepix_webhook_remover,
    integracoes_fastdepix_webhook_salvar_url,
    integracoes_fastdepix_sincronizar,
    # Configuração de Agendamentos
    config_agendamentos,
    # Relatório de Pagamentos
    relatorio_pagamentos,
    api_cliente_mensalidades,
)

urlpatterns = [
    ############ Authentication ###########
    path("", Login.as_view(), name="login"),
    path("verify-2fa/", verify_2fa_code, name="verify-2fa"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    ########### Profile ###########
    path("perfil/", profile_page, name="perfil"),
    path("perfil/avatar/upload/", upload_avatar, name="upload-avatar"),
    path("perfil/avatar/remove/", remove_avatar, name="remove-avatar"),
    path("perfil/alterar-senha/", change_password, name="alterar-senha"),
    path("perfil/historico/", profile_activity_history, name="profile-historico"),
    path("perfil/tema/", change_theme, name="change-theme"),
    path("perfil/notificacoes/", update_notification_preferences, name="update-notifications"),
    path("perfil/privacidade/", update_privacy_settings, name="update-privacy"),
    path("perfil/2fa/setup/", setup_2fa, name="setup-2fa"),
    path("perfil/2fa/enable/", enable_2fa, name="enable-2fa"),
    path("perfil/2fa/disable/", disable_2fa, name="disable-2fa"),
    path("perfil/2fa/regenerate-codes/", regenerate_backup_codes, name="regenerate-backup-codes"),
    path("perfil/2fa/qr-code/", get_2fa_qr_code, name="get-2fa-qr-code"),
    path("perfil/exportar-clientes/", exportar_clientes_excel, name="exportar_clientes_excel"),

    ############ List and Dashboard ###########
    path("dashboard/", TabelaDashboard.as_view(), name="dashboard"),
    path("logs/list/", LogFilesListView.as_view(), name="logs-list"),
    path("indicacoes/", CarregarInidicacoes.as_view(), name="indicacoes"),
    path("logs/content/", LogFileContentView.as_view(), name="logs-content"),
    path("user-logs/", UserActionLogListView.as_view(), name="user-logs"),
    path("modal-dns-json/", ModalDNSJsonView.as_view(), name="modal-dns-json"),
    path("contas-apps/", CarregarContasDoAplicativo.as_view(), name="contas-apps"),
    path("dashboard/busca/", TabelaDashboardAjax.as_view(), name="dashboard-busca"),
    path("clientes-cancelados/", ClientesCancelados.as_view(), name="clientes-cancelados"),
    path("qtds-mensalidades/", CarregarQuantidadesMensalidades.as_view(), name="qtds-mensalidades"),

    ############ Notifications ###########
    path("notifications/dropdown/", notifications_dropdown, name="notifications_dropdown"),
    path("notificacoes/modal/", NotificationsModalView.as_view(), name="notifications_modal"),
    path("mensalidades/<int:pk>/", MensalidadeDetailView.as_view(), name="mensalidade_detalhe"),
    path("notifications/count/", notifications_count, name="notifications_count"),
    path("notifications/mark-all-read/", notifications_mark_all_read, name="notifications_mark_all_read"),

    ############ Graphics ###########
    path("grafico/anual/", generate_graphic_columns_per_year, name="grafico-anual"),
    path("grafico/mensal/", generate_graphic_columns_per_month, name="grafico-mensal"),
    path("api/mapa-clientes/", mapa_clientes_data, name="mapa-clientes"),
    path("api/clientes-por-servidor/", clientes_servidor_data, name="clientes-por-servidor"),
    path("api/evolucao-patrimonio/", evolucao_patrimonio, name="evolucao-patrimonio"),
    path("api/adesoes-cancelamentos/", adesoes_cancelamentos_api, name="adesoes-cancelamentos"),

    ############ Create ###########
    path("cadastro-cliente/", create_customer, name="cadastro-cliente"),
    path("cadastro-servidor/", create_server, name="cadastro-servidor"),
    path("cadastro-aplicativo/", create_app, name="cadastro-aplicativo"),
    path("importar-clientes/", import_customers, name="importar-clientes"),
    path("cadastro-dispositivo/", create_device, name="cadastro-dispositivo"),
    path("cadastro-app-conta/", create_app_account, name="cadastro-app-conta"),
    path("cadastro-plano-adesao/", create_payment_plan, name="cadastro-plano-adesao"),
    path("cadastro-forma-pagamento/", create_payment_method_admin, name="cadastro-forma-pagamento"),

    ############ Edit ############
    path("editar-perfil/", edit_profile, name="editar-perfil"),
    path('edit-referral-plan/', edit_referral_plan, name='edit-referral-plan'),
    path('edit-horario-envios/', edit_horario_envios, name='edit-horario-envios'),
    path('edit-reject-call-config/', edit_reject_call_config, name='edit-reject-call-config'),
    path("api/cliente/<int:cliente_id>/contas/", api_cliente_contas, name="api-cliente-contas"),
    path("editar-cliente/<int:cliente_id>/", edit_customer, name="editar-cliente"),
    path("editar-servidor/<int:servidor_id>/", edit_server, name="editar-servidor"),
    path("editar-aplicativo/<int:aplicativo_id>/", editar_app, name="editar-aplicativo"),
    path("editar-dispositivo/<int:dispositivo_id>/", edit_device, name="editar-dispositivo"),
    path("editar-plano-adesao/<int:plano_id>/", edit_payment_plan, name="editar-plano-adesao"),

    ############ Delete ###########
    path("deletar-servidor/<int:pk>/", delete_server, name="deletar-servidor"),
    path("deletar-aplicativo/<int:pk>/", delete_app, name="deletar-aplicativo"),
    path("deletar-dispositivo/<int:pk>/", delete_device, name="deletar-dispositivo"),
    path("deletar-app-conta/<int:pk>/", delete_app_account, name="deletar-app-conta"),
    path("deletar-formapgto/<int:pk>/", delete_payment_method, name="deletar-formapgto"),
    path("deletar-plano-adesao/<int:pk>/", delete_payment_plan, name="deletar-plano-adesao"),

    ############ Change status customer ###########
    path("cancelar-cliente/<int:cliente_id>/", cancel_customer, name="cancelar-cliente"),
    path("reativar-cliente/<int:cliente_id>/", reactivate_customer, name="reativar-cliente"),
    path("pagar-mensalidade/<int:mensalidade_id>/", pay_monthly_fee, name="pagar-mensalidade"),

    ############ WhatsApp API (old) ###########
    path("whatsapp/", whatsapp, name="whatsapp"),
    path("session-wpp/", session_wpp, name="session-wpp"),
    path("obter-stkn/", secret_token_api, name="obter-stkn"),
    path("obter-logs-wpp/", get_logs_wpp, name="obter-logs-wpp"),
    path("enviar-mensagem/", send_message_wpp, name="enviar-mensagem"),
    path("parar-envio/", parar_envio, name="parar-envio"),
    path("status-envio/", status_envio, name="status-envio"),
    path("limpar-log-wpp/", limpar_log_wpp, name="limpar-log-wpp"),
    path("obter-session-wpp/", get_session_wpp, name="obter-session-wpp"),

    ############## Whatsapp API (new) ###########
    path("status-wpp/", status_wpp, name="status_wpp"),
    path("conectar-wpp/", conectar_wpp, name="conectar_wpp"),
    path("desconectar-wpp/", desconectar_wpp, name="desconectar_wpp"),
    path("cancelar-sessao-wpp/", cancelar_sessao_wpp, name="cancelar_sessao_wpp"),
    path("check-connection-wpp/", check_connection_wpp, name="check_connection_wpp"),

    ############ Internal API (IP-restricted) ###########
    path("api/internal/send-whatsapp/", internal_send_whatsapp, name="internal-send-whatsapp"),

    ############ Webhook WPPConnect (externo) ###########
    path("webhook/wppconnect/", webhook_wppconnect, name="webhook_wppconnect"),

    ############ Chat WhatsApp (Admin) ###########
    path("chat-whatsapp/", ChatPageView.as_view(), name="chat-whatsapp"),
    path("api/chat/list/", api_chat_list, name="api-chat-list"),
    path("api/chat/messages/<str:phone>/", api_chat_messages, name="api-chat-messages"),
    path("api/chat/messages/<str:phone>/load-more/", api_load_earlier_messages, name="api-chat-load-more"),
    path("api/chat/profile-pic/<str:phone>/", api_profile_picture, name="api-chat-profile-pic"),
    path("api/chat/send-message/", api_send_message, name="api-chat-send-message"),
    path("api/chat/send-file/", api_send_file, name="api-chat-send-file"),
    path("api/chat/download/<str:message_id>/", api_download_media, name="api-chat-download"),
    path("api/chat/mark-as-read/", api_mark_as_read, name="api-chat-mark-as-read"),
    path("api/chat/sse/", sse_chat_stream, name="api-chat-sse"),

    ############ Migração de Clientes (Admin) ###########
    path("migration/clientes/list/", MigrationClientesListView.as_view(), name="migration-clientes-list"),
    path("migration/clientes/validate/", MigrationValidationView.as_view(), name="migration-clientes-validate"),
    path("migration/clientes/execute/", MigrationExecuteView.as_view(), name="migration-clientes-execute"),

    ############ Gestão de Domínios DNS (Reseller Automation) ###########
    path("gestao-dns/", gestao_dns_page, name="gestao-dns"),
    path("api/gestao-dns/verificar-conta/", verificar_conta_reseller_api, name="api-verificar-conta-reseller"),
    path("api/gestao-dns/login-manual/", iniciar_login_manual_api, name="api-login-manual-reseller"),
    path("api/gestao-dns/iniciar-migracao/", iniciar_migracao_dns_api, name="api-iniciar-migracao-dns"),
    path("api/gestao-dns/progresso/<int:tarefa_id>/", consultar_progresso_migracao_api, name="api-progresso-migracao-dns"),
    path("api/gestao-dns/dispositivos-paginados/", obter_dispositivos_paginados_api, name="api-dispositivos-paginados-dns"),
    path("api/gestao-dns/listar-dominios/", listar_dominios_api, name="api-listar-dominios-dns"),
    path("api/gestao-dns/buscar-dispositivo/", buscar_dispositivo_api, name="api-buscar-dispositivo-dns"),

    # Configuração Debug Headless (Admin)
    path("api/toggle-debug-headless/", toggle_debug_headless, name="api-toggle-debug-headless"),
    path("api/debug-status/", get_debug_status, name="api-debug-status"),

    ############ Tarefas de Envio WhatsApp (Admin) ###########
    path("tarefas-envio/", TarefaEnvioListView.as_view(), name="tarefas-envio-lista"),
    path("tarefas-envio/criar/", TarefaEnvioCreateView.as_view(), name="tarefas-envio-criar"),
    path("tarefas-envio/<int:pk>/editar/", TarefaEnvioUpdateView.as_view(), name="tarefas-envio-editar"),
    path("tarefas-envio/<int:pk>/deletar/", TarefaEnvioDeleteView.as_view(), name="tarefas-envio-deletar"),
    path("tarefas-envio/<int:pk>/historico/", TarefaEnvioHistoricoView.as_view(), name="tarefas-envio-historico"),
    path("tarefas-envio/<int:pk>/toggle/", tarefa_envio_toggle, name="tarefas-envio-toggle"),
    path("tarefas-envio/<int:pk>/duplicar/", tarefa_envio_duplicar, name="tarefas-envio-duplicar"),
    path("tarefas-envio/<int:pk>/excluir-ajax/", tarefa_envio_excluir_ajax, name="tarefas-envio-excluir-ajax"),
    path("tarefas-envio/preview/", tarefa_envio_preview, name="tarefas-envio-preview"),
    path("tarefas-envio/sugestao-horarios/", tarefa_envio_sugestao_horarios, name="tarefas-envio-sugestao-horarios"),
    path("tarefas-envio/stats/", tarefas_envio_stats_api, name="tarefas-envio-stats-api"),
    path("tarefas-envio/preview-alcance/", tarefa_envio_preview_alcance, name="tarefas-envio-preview-alcance"),
    path("tarefas-envio/verificar-conflito/", tarefa_envio_verificar_conflito, name="tarefas-envio-verificar-conflito"),
    path("tarefas-envio/templates/", tarefa_envio_listar_templates, name="tarefas-envio-templates"),
    path("tarefas-envio/templates/salvar/", tarefa_envio_salvar_template, name="tarefas-envio-template-salvar"),
    path("tarefas-envio/<int:pk>/historico/api/", tarefa_envio_historico_api, name="tarefas-envio-historico-api"),

    ############ Integração Bancária ###########
    path("api/instituicoes-bancarias/", api_instituicoes_bancarias, name="api-instituicoes-bancarias"),
    path("api/contas-bancarias/", api_contas_bancarias, name="api-contas-bancarias"),
    path("api/contas-bancarias/criar/", criar_conta_bancaria, name="api-criar-conta-bancaria"),
    path("api/contas-bancarias/<int:pk>/excluir/", excluir_conta_bancaria, name="api-excluir-conta-bancaria"),
    path("api/instituicoes-bancarias/criar/", criar_instituicao_bancaria, name="api-criar-instituicao"),
    path("api/instituicoes-bancarias/<int:pk>/toggle/", toggle_instituicao_bancaria, name="api-toggle-instituicao"),
    path("api/instituicoes-bancarias/<int:pk>/excluir/", excluir_instituicao_bancaria, name="api-excluir-instituicao"),

    ############ Configuração de Limite MEI ###########
    path("api/config-limite/", api_config_limite, name="api-config-limite"),
    path("api/config-limite/atualizar/", api_config_limite_atualizar, name="api-config-limite-atualizar"),

    ############ Credenciais API ###########
    path("api/credenciais/<str:tipo_integracao>/", api_credenciais_por_tipo, name="api-credenciais-por-tipo"),

    ############ Clientes para Associação ###########
    path("api/clientes-ativos-associacao/", api_clientes_ativos_associacao, name="api-clientes-ativos-associacao"),

    ############ Planos de Adesão ###########
    path("api/planos/", api_planos, name="api-planos"),

    ############ Notificações do Sistema ###########
    path("api/notificacoes/", api_notificacoes_listar, name="api-notificacoes-listar"),
    path("api/notificacoes/<int:notificacao_id>/marcar-lida/", api_notificacao_marcar_lida, name="api-notificacao-marcar-lida"),
    path("api/notificacoes/marcar-todas-lidas/", api_notificacoes_marcar_todas_lidas, name="api-notificacoes-marcar-todas-lidas"),

    ############ Push Notifications ###########
    path("api/push/subscribe/", api_push_subscribe, name="api-push-subscribe"),
    path("api/push/unsubscribe/", api_push_unsubscribe, name="api-push-unsubscribe"),
    path("api/push/vapid-key/", api_push_vapid_public_key, name="api-push-vapid-key"),

    ############ Cobrança PIX ###########
    path("api/pix/gerar/<int:mensalidade_id>/", gerar_cobranca_pix, name="api-pix-gerar"),
    path("api/pix/status/<uuid:cobranca_id>/", consultar_cobranca_pix, name="api-pix-status"),
    path("api/pix/cancelar/<uuid:cobranca_id>/", cancelar_cobranca_pix, name="api-pix-cancelar"),
    path("api/pix/webhook/", webhook_pagamento_pix, name="api-pix-webhook"),

    ############ Redirecionamentos (URLs legadas) ###########
    path("admin/forma-pagamento/", RedirectView.as_view(pattern_name='cadastro-forma-pagamento', permanent=True), name="admin-forma-pagamento"),

    ############ Configuração de Agendamentos (Admin) ###########
    path("admin/agendamentos/", config_agendamentos, name="config-agendamentos"),

    ############ Integrações API (Admin) ###########
    path("admin/integracoes-api/", integracoes_api_index, name="integracoes-api"),
    path("admin/integracoes-api/fastdepix/", integracoes_fastdepix, name="integracoes-fastdepix"),
    path("admin/integracoes-api/fastdepix/testar/", integracoes_fastdepix_testar, name="integracoes-fastdepix-testar"),
    path("admin/integracoes-api/fastdepix/webhook/registrar/", integracoes_fastdepix_webhook_registrar, name="integracoes-fastdepix-webhook-registrar"),
    path("admin/integracoes-api/fastdepix/webhook/atualizar/", integracoes_fastdepix_webhook_atualizar, name="integracoes-fastdepix-webhook-atualizar"),
    path("admin/integracoes-api/fastdepix/webhook/remover/", integracoes_fastdepix_webhook_remover, name="integracoes-fastdepix-webhook-remover"),
    path("admin/integracoes-api/fastdepix/webhook/salvar-url/", integracoes_fastdepix_webhook_salvar_url, name="integracoes-fastdepix-webhook-salvar-url"),
    path("admin/integracoes-api/fastdepix/sincronizar/", integracoes_fastdepix_sincronizar, name="integracoes-fastdepix-sincronizar"),
    path("admin/integracoes-api/fastdepix/conta/", integracoes_fastdepix_conta_dados, name="integracoes-fastdepix-conta-dados"),
    path("admin/integracoes-api/fastdepix/conta/<int:conta_id>/", integracoes_fastdepix_conta_dados, name="integracoes-fastdepix-conta-dados-id"),

    ############ API Forma de Pagamento ###########
    path("api/forma-pagamento/<int:pk>/", api_forma_pagamento_detalhes, name="api-forma-pagamento-detalhes"),
    path("api/forma-pagamento/<int:pk>/atualizar/", api_forma_pagamento_atualizar, name="api-forma-pagamento-atualizar"),
    path("api/forma-pagamento/<int:pk>/atualizar-antiga/", api_forma_pagamento_antiga_atualizar, name="api-forma-pagamento-antiga-atualizar"),
    path("api/forma-pagamento/<int:pk>/clientes-count/", api_forma_pagamento_clientes_count, name="api-forma-pagamento-clientes-count"),

    ############ Relatórios (Admin) ###########
    path("admin/relatorios/pagamentos/", relatorio_pagamentos, name="relatorio-pagamentos"),
    path("api/clientes/<int:cliente_id>/mensalidades/", api_cliente_mensalidades, name="api-cliente-mensalidades"),

    ########### Service Worker (Push Notifications) ###########
    path("sw.js", lambda request: HttpResponse(
        open(os.path.join(settings.STATICFILES_DIRS[0], 'sw.js')).read() if settings.STATICFILES_DIRS else '',
        content_type='application/javascript'
    ), name="service-worker"),

    ########### Tests ###########
    path("teste/", test, name="teste"),
]
