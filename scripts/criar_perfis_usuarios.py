#!/usr/bin/env python
"""
Script para criar UserProfile para todos os usuários existentes no sistema.

Este script deve ser executado após a criação do modelo UserProfile
para garantir que todos os usuários tenham um perfil associado.

Uso:
    python scripts/criar_perfis_usuarios.py
"""

import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
django.setup()

from django.contrib.auth.models import User
from cadastros.models import UserProfile


def criar_perfis():
    """Cria UserProfile para todos os usuários que ainda não possuem."""

    print("🔍 Verificando usuários sem perfil...")

    usuarios_sem_perfil = User.objects.filter(profile__isnull=True)
    total_usuarios = User.objects.count()
    sem_perfil_count = usuarios_sem_perfil.count()

    print(f"📊 Total de usuários: {total_usuarios}")
    print(f"📊 Usuários sem perfil: {sem_perfil_count}")

    if sem_perfil_count == 0:
        print("✅ Todos os usuários já possuem perfil!")
        return

    print(f"\n🔨 Criando perfis para {sem_perfil_count} usuário(s)...")

    criados = 0
    erros = 0

    for usuario in usuarios_sem_perfil:
        try:
            UserProfile.objects.create(user=usuario)
            criados += 1
            print(f"  ✓ Perfil criado para: {usuario.username} (ID: {usuario.id})")
        except Exception as e:
            erros += 1
            print(f"  ✗ Erro ao criar perfil para {usuario.username}: {str(e)}")

    print(f"\n📈 Resumo:")
    print(f"  ✅ Perfis criados com sucesso: {criados}")
    if erros > 0:
        print(f"  ❌ Erros: {erros}")

    print("\n✨ Processo concluído!")


if __name__ == '__main__':
    criar_perfis()
