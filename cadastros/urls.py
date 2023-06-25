from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    Login,
    Teste,
    SessionWpp,
    ObterLogsWpp,
    EditarCliente,
    ListaClientes,
    DeleteServidor,
    EditarServidor,
    TabelaDashboard,
    ObterSessionWpp,
    CadastroCliente,
    cancelar_cliente,
    reativar_cliente,
    CadastroServidor,
    ImportarClientes,
    DeleteAplicativo,
    EditarAplicativo,
    EnviarMensagemWpp,
    pagar_mensalidade,
    EditarPlanoAdesao,
    DeletePlanoAdesao,
    DeleteDispositivo,
    EditarDispositivo,
    CadastroAplicativo,
    CadastroPlanoAdesao,
    CadastroDispositivo,
    DeleteFormaPagamento,
    DeleteContaAplicativo,
    CadastroFormaPagamento,
    CadastroContaAplicativo,
    CarregarContasDoAplicativo,
    CarregarQuantidadesMensalidades,
)

urlpatterns = [
    ############ Authentication ###########
    path("", Login.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    ############ List and Dashboard ###########
    path("dashboard/", TabelaDashboard.as_view(), name="dashboard"),
    path("listagem-clientes/", ListaClientes.as_view(), name="listagem-clientes"),
    path("cancelar-cliente/<int:cliente_id>/", cancelar_cliente, name="cancelar-cliente"),
    path("pagar-mensalidade/<int:mensalidade_id>/", pagar_mensalidade, name="pagar-mensalidade"),

    ########### Create ###########
    path("cadastro-cliente/", CadastroCliente, name="cadastro-cliente"),
    path("importar-clientes/", ImportarClientes, name="importar-cliente"),
    path("cadastro-servidor/", CadastroServidor, name='cadastro-servidor'),
    path("cadastro-aplicativo/", CadastroAplicativo, name="cadastro-aplicativo"),
    path("cadastro-app-conta/", CadastroContaAplicativo, name="cadastro-app-conta"),
    path("cadastro-dispositivo/", CadastroDispositivo, name="cadastro-dispositivo"),
    path("cadastro-plano-adesao/", CadastroPlanoAdesao, name="cadastro-plano-adesao"),
    path("cadastro-forma-pagamento/", CadastroFormaPagamento, name="cadastro-forma-pagamento"),

    ########### Edit ############    
    path("editar-cliente/<int:cliente_id>/", EditarCliente, name="editar-cliente"),
    path('editar-servidor/<int:servidor_id>/', EditarServidor, name='editar-servidor'),
    path("reativar-cliente/<int:cliente_id>/", reativar_cliente, name="reativar-cliente" ),
    path("editar-aplicativo/<int:aplicativo_id>/", EditarAplicativo,name="editar-aplicativo"),
    path("editar-plano-adesao/<int:plano_id>/", EditarPlanoAdesao, name="editar-plano-adesao"),
    path("editar-dispositivo/<int:dispositivo_id>/", EditarDispositivo, name="editar-dispositivo"),
    
    ########## Delete ###########
    path('deletar-servidor/<int:pk>/', DeleteServidor, name='deletar_servidor'),
    path("deletar-aplicativo/<int:pk>/", DeleteAplicativo, name="deletar-aplicativo"),
    path("deletar-formapgto/<int:pk>/", DeleteFormaPagamento, name="deletar-formapgto"),
    path('deletar-app-conta/<int:pk>/', DeleteContaAplicativo, name='deletar-app-conta'),
    path("deletar-dispositivo/<int:pk>/", DeleteDispositivo, name="deletar-dispositivo"),
    path('deletar-plano-adesao/<int:pk>/', DeletePlanoAdesao, name='deletar-plano-adesao'),
    
    ########## Others ###########
    path("teste/", Teste, name="teste"),
    path("session_wpp/", SessionWpp, name="session_wpp"),
    path("contas_apps/", CarregarContasDoAplicativo.as_view()),
    path("enviar_mensagem/", EnviarMensagemWpp, name="enviar_mensagem"),
    path("qtds_mensalidades/", CarregarQuantidadesMensalidades.as_view()),
    path("obter_session_wpp/", ObterSessionWpp, name="obter_session_wpp"),
    path("obter_logs_wpp/", ObterLogsWpp, name="obter_logs_wpp")
]
