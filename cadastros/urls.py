from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    test,
    Login,
    whatsapp,
    create_app,
    editar_app,
    status_wpp,
    delete_app,
    edit_device,
    edit_server,
    session_wpp,
    profile_page,
    conectar_wpp,
    get_logs_wpp,
    edit_profile,
    edit_customer,
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
    ClientesCancelados,
    edit_referral_plan,
    delete_app_account,
    create_app_account,
    cancelar_sessao_wpp,
    reactivate_customer,
    CarregarInidicacoes,
    TabelaDashboardAjax,
    edit_horario_envios,
    create_payment_plan,
    delete_payment_plan,
    check_connection_wpp,
    delete_payment_method,
    create_payment_method,
    CarregarContasDoAplicativo,
    generate_graphic_map_customers,
    CarregarQuantidadesMensalidades,
    generate_graphic_columns_per_year,
    generate_graphic_columns_per_month,
)

urlpatterns = [
    ############ Authentication ###########
    path("", Login.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    ########### Profile ###########
    path("perfil/", profile_page, name="perfil"),

    ############ List and Dashboard ###########
    path("dashboard/", TabelaDashboard.as_view(), name="dashboard"),
    path("logs/list/", LogFilesListView.as_view(), name="logs-list"),
    path("indicacoes/", CarregarInidicacoes.as_view(), name="indicacoes"),
    path("logs/content/", LogFileContentView.as_view(), name="logs-content"),
    path("modal-dns-json/", ModalDNSJsonView.as_view(), name="modal-dns-json"),
    path("contas-apps/", CarregarContasDoAplicativo.as_view(), name="contas-apps"),
    path("dashboard/busca/", TabelaDashboardAjax.as_view(), name="dashboard-busca"),
    path("clientes-cancelados/", ClientesCancelados.as_view(), name="clientes-cancelados"),
    path("qtds-mensalidades/", CarregarQuantidadesMensalidades.as_view(), name="qtds-mensalidades"),

    ############ Graphics ###########
    path("grafico/anual/", generate_graphic_columns_per_year, name="grafico-anual"),
    path("grafico/mensal/", generate_graphic_columns_per_month, name="grafico-mensal"),
    path("grafico/mapa-clientes/", generate_graphic_map_customers, name="grafico-mapa-clientes"),

    ############ Create ###########
    path("cadastro-cliente/", create_customer, name="cadastro-cliente"),
    path("cadastro-servidor/", create_server, name="cadastro-servidor"),
    path("cadastro-aplicativo/", create_app, name="cadastro-aplicativo"),
    path("importar-clientes/", import_customers, name="importar-clientes"),
    path("cadastro-dispositivo/", create_device, name="cadastro-dispositivo"),
    path("cadastro-app-conta/", create_app_account, name="cadastro-app-conta"),
    path("cadastro-plano-adesao/", create_payment_plan, name="cadastro-plano-adesao"),
    path("cadastro-forma-pagamento/", create_payment_method, name="cadastro-forma-pagamento"),

    ############ Edit ############
    path("editar-perfil/", edit_profile, name="editar-perfil"),
    path('edit-referral-plan/', edit_referral_plan, name='edit-referral-plan'),
    path('edit-horario-envios/', edit_horario_envios, name='edit-horario-envios'),
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
    path("obter-session-wpp/", get_session_wpp, name="obter-session-wpp"),

    ############## Whatsapp API (new) ###########
    path("status-wpp/", status_wpp, name="status_wpp"),
    path("conectar-wpp/", conectar_wpp, name="conectar_wpp"),
    path("desconectar-wpp/", desconectar_wpp, name="desconectar_wpp"),
    path("cancelar-sessao-wpp/", cancelar_sessao_wpp, name="cancelar_sessao_wpp"),
    path("check-connection-wpp/", check_connection_wpp, name="check_connection_wpp"),
    
    ########### Tests ###########
    path("teste/", test, name="teste"),
]
