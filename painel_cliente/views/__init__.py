"""
Views do Painel do Cliente.

Modulos:
- cliente: Views do cliente final (login, dashboard, pagamento)
- admin: Views do painel administrativo (subdominios, personalizacao)
"""

from . import cliente
from . import admin

__all__ = ['cliente', 'admin']
