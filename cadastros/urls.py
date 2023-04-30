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
    path("plano-mensalidade/", CadastroPlanoMensal, name="cadastro-plano-mensal"),
    path("cadastro-aplicativos/",CadastroAplicativo, name="cadastro-aplicativos"),
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

