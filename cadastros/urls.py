from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    Login,
    pagar_mensalidade,
    cancelar_cliente,
    reativar_cliente,
    TabelaDashboard,
    CadastroCliente,
    ImportarClientes,
    CadastroFormaPagamento,
    CadastroServidor,
    CadastroPlanoAdesao,
    CadastroDispositivo,
    CadastroAplicativo,
    DeleteServidor,
    EditarServidor,
    DeletePlanoAdesao,
    EditarPlanoAdesao,
    DeleteAplicativo,
    DeleteFormaPagamento,
    EditarAplicativo,
    EditarDispositivo,
    DeleteDispositivo,
    EditarCliente,
    ListaClientes,
    CarregarQuantidadesMensalidades,
    Teste,
)

urlpatterns = [
    ############ Authentication ###########
    path("", Login.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    ############ List and Dashboard ###########
    path("dashboard/", TabelaDashboard.as_view(), name="dashboard"),
    path("listagem-clientes/", ListaClientes.as_view(), name="listagem-clientes"),
    path("pagar-mensalidade/<int:mensalidade_id>/", pagar_mensalidade, name="pagar-mensalidade"),
    path("cancelar-cliente/<int:cliente_id>/", cancelar_cliente, name="cancelar-cliente"),

    ########### Create ###########
    path("cadastro-plano-adesao/", CadastroPlanoAdesao, name="cadastro-plano-adesao"),
    path("cadastro-forma-pagamento/", CadastroFormaPagamento, name="cadastro-forma-pagamento"),
    path("cadastro-aplicativo/", CadastroAplicativo, name="cadastro-aplicativo"),
    path("cadastro-dispositivo/", CadastroDispositivo, name="cadastro-dispositivo"),
    path("cadastro-cliente/", CadastroCliente, name="cadastro-cliente"),
    path("cadastro-servidor/", CadastroServidor, name='cadastro-servidor'),
    path("importar-clientes/", ImportarClientes, name="importar-cliente"),

    ########### Edit ############    
    path("editar-plano-adesao/<int:plano_id>/", EditarPlanoAdesao, name="editar-plano-adesao"),
    path('editar-servidor/<int:servidor_id>/', EditarServidor, name='editar-servidor'),
    path("editar-aplicativo/<int:aplicativo_id>/", EditarAplicativo,name="editar-aplicativo"),
    path("editar-dispositivo/<int:dispositivo_id>/", EditarDispositivo, name="editar-dispositivo"),
    path("editar-cliente/<int:cliente_id>/", EditarCliente, name="editar-cliente"),
    path("reativar-cliente/<int:cliente_id>/", reativar_cliente, name="reativar-cliente" ),
    
    ########## Delete ###########
    path('deletar-servidor/<int:pk>/', DeleteServidor, name='deletar_servidor'),
    path('deletar-plano-adesao/<int:pk>/', DeletePlanoAdesao, name='deletar-plano-adesao'),
    path("deletar-aplicativo/<int:pk>/", DeleteAplicativo, name="deletar-aplicativo"),
    path("deletar-formapgto/<int:pk>/", DeleteFormaPagamento, name="deletar-formapgto"),
    path("deletar-dispositivo/<int:pk>/", DeleteDispositivo, name="deletar-dispositivo"),
    
    ########## Others ###########
    path("teste/", Teste, name="teste"),
    path("qtds_mensalidades/", CarregarQuantidadesMensalidades.as_view()),
]
