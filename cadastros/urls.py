from django.urls import path
from .views import (
    Login,
    pagar_mensalidade,
    cancelar_cliente,
    TabelaDashboard,
    CadastroCliente,
    ImportarClientes,
    CadastroFormaPagamento,
    CadastroServidor,
    CadastroPlanoIndicacao,
    CadastroPlanoMensal,
    CadastroDispositivo,
    CadastroAplicativo,
    DeleteServidor,
    EditarServidor,
    DeletePlanoMensal,
    EditarPlanoMensal,
    Teste,
)

urlpatterns = [
    path(
        "pagar_mensalidade/<int:mensalidade_id>/",
        pagar_mensalidade,
        name="pagar_mensalidade",
    ),
    path(
        "cancelar_cliente/<int:cliente_id>", cancelar_cliente, name="cancelar_cliente"
    ),
    path("editar_plano/<int:plano_id>/", EditarPlanoMensal, name="editar-plano-mensal"),
    path('editar_servidor/<int:servidor_id>/', EditarServidor, name='editar_servidor'),
    path("plano-mensalidade/", CadastroPlanoMensal, name="cadastro-plano-mensal"),
    path("cadastro-aplicativos/",CadastroAplicativo, name="cadastro-aplicativos"),
    path('deletar_servidor/<int:pk>/', DeleteServidor, name='deletar_servidor'),
    path('deletar_plano_mensal/<int:pk>/',DeletePlanoMensal, name='deletar-plano-mensal'),
    path("forma-pagamento/", CadastroFormaPagamento, name="forma-pagamento"),
    path("plano-indicacao/", CadastroPlanoIndicacao, name="plano-indicacao"),
    path("dispositivos/", CadastroDispositivo, name="cadastro-dispositivos"),
    path("dashboard/", TabelaDashboard.as_view(), name="dashboard"),
    path("importar/", ImportarClientes, name="importar-cliente"),
    path("cadastro/", CadastroCliente, name="cadastro-cliente"),
    path("servidores/", CadastroServidor, name='servidores'),
    path("teste/", Teste, name="teste"),
    path("", Login, name="login"),
]

