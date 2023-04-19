from django.urls import path
from .views import Index, pagar_mensalidade, cancelar_cliente

urlpatterns = [
    path('', Index, name='index'),
    path('pagar_mensalidade/<int:mensalidade_id>/', pagar_mensalidade, name='pagar_mensalidade'),
    path('cancelar_cliente/<int:cliente_id>', cancelar_cliente, name='cancelar_cliente'),
]