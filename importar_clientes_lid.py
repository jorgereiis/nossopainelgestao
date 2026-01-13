#!/usr/bin/env python3
"""
Script para importar clientes do arquivo clientes_lid_resultado.json
para o usuário 'megatv'.

- Clientes novos: cadastrados com cancelado=True
- Clientes existentes: apenas atualiza o whatsapp_lid
"""

import os
import sys
import json
from pathlib import Path
from datetime import date

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

import django
django.setup()

from django.contrib.auth.models import User
from django.db import connection
from django.db.models.signals import pre_save, post_save
from nossopainel.models import Cliente


def formatar_telefone(telefone: str) -> str:
    """Adiciona + ao telefone se necessário."""
    if not telefone.startswith('+'):
        return f'+{telefone}'
    return telefone


def importar_clientes(dry_run: bool = False):
    """Importa clientes do arquivo JSON."""

    # Carregar arquivo JSON
    arquivo = Path(__file__).parent / 'clientes_lid_resultado.json'
    if not arquivo.exists():
        print(f"ERRO: Arquivo não encontrado: {arquivo}")
        sys.exit(1)

    with arquivo.open('r', encoding='utf-8') as f:
        contatos = json.load(f)

    print(f"Total de contatos no arquivo: {len(contatos)}")

    # Obter usuário megatv
    try:
        user = User.objects.get(username='megatv')
        print(f"Usuário: {user.username} (ID: {user.id})")
    except User.DoesNotExist:
        print("ERRO: Usuário 'megatv' não encontrado")
        sys.exit(1)

    # Estatísticas antes
    total_antes = Cliente.objects.filter(usuario=user).count()
    cancelados_antes = Cliente.objects.filter(usuario=user, cancelado=True).count()
    ativos_antes = Cliente.objects.filter(usuario=user, cancelado=False).count()
    com_lid_antes = Cliente.objects.filter(usuario=user).exclude(
        whatsapp_lid__isnull=True
    ).exclude(whatsapp_lid='').count()

    print(f"\n{'='*50}")
    print("ESTADO ANTES DA IMPORTAÇÃO")
    print('='*50)
    print(f"Total clientes: {total_antes}")
    print(f"  - Ativos: {ativos_antes}")
    print(f"  - Cancelados: {cancelados_antes}")
    print(f"Com whatsapp_lid: {com_lid_antes}")

    # Processar contatos
    stats = {
        'criados': 0,
        'atualizados': 0,
        'duplicados_telefone': 0,
        'erros': 0
    }

    telefones_processados = set()

    if dry_run:
        print(f"\n*** MODO DRY-RUN - Nenhuma alteração será feita ***\n")

    print(f"\nProcessando {len(contatos)} contatos...")

    # Desconectar signals para evitar erros durante importação em massa
    # Guardar receivers para reconectar depois
    pre_save_receivers = pre_save.receivers
    post_save_receivers = post_save.receivers

    if not dry_run:
        # Desconectar todos os signals do modelo Cliente
        pre_save.receivers = [r for r in pre_save.receivers if not (hasattr(r[1], '__self__') and isinstance(r[1].__self__, type) and issubclass(r[1].__self__, Cliente))]
        post_save.receivers = [r for r in post_save.receivers if not (hasattr(r[1], '__self__') and isinstance(r[1].__self__, type) and issubclass(r[1].__self__, Cliente))]

        # Forma mais segura: desconectar por sender
        from nossopainel import signals  # Importar para garantir que signals estão registrados
        pre_save.disconnect(sender=Cliente)
        post_save.disconnect(sender=Cliente)

    try:
        for i, contato in enumerate(contatos, 1):
            nome = contato['nome']
            lid = contato['lid']
            telefone = formatar_telefone(contato['telefone'])

            # Evitar processar mesmo telefone duas vezes
            if telefone in telefones_processados:
                stats['duplicados_telefone'] += 1
                continue
            telefones_processados.add(telefone)

            try:
                # Verificar se existe
                cliente_existente = Cliente.objects.filter(
                    telefone=telefone, usuario=user
                ).first()

                if cliente_existente:
                    # Atualizar LID diretamente no banco (sem signals)
                    if not dry_run:
                        Cliente.objects.filter(pk=cliente_existente.pk).update(
                            whatsapp_lid=lid
                        )
                    stats['atualizados'] += 1
                else:
                    # Criar novo usando INSERT direto (sem signals)
                    if not dry_run:
                        # Usar bulk_create com um item para evitar signals
                        novo_cliente = Cliente(
                            nome=nome,
                            telefone=telefone,
                            usuario=user,
                            cancelado=True,
                            tem_assinatura=False,
                            whatsapp_lid=lid,
                            data_adesao=date.today(),
                            data_vencimento=date.today(),
                        )
                        Cliente.objects.bulk_create([novo_cliente])
                    stats['criados'] += 1

            except Exception as e:
                stats['erros'] += 1
                print(f"  ERRO [{i}] {nome}: {e}")

            # Progresso a cada 500
            if i % 500 == 0:
                print(f"  Processados: {i}/{len(contatos)}")

    finally:
        # Reconectar signals
        if not dry_run:
            pre_save.receivers = pre_save_receivers
            post_save.receivers = post_save_receivers

    # Estatísticas depois
    total_depois = Cliente.objects.filter(usuario=user).count()
    cancelados_depois = Cliente.objects.filter(usuario=user, cancelado=True).count()
    ativos_depois = Cliente.objects.filter(usuario=user, cancelado=False).count()
    com_lid_depois = Cliente.objects.filter(usuario=user).exclude(
        whatsapp_lid__isnull=True
    ).exclude(whatsapp_lid='').count()

    # Verificar duplicados (mesmo telefone com status diferente)
    from django.db.models import Count
    duplicados = Cliente.objects.filter(usuario=user).values('telefone').annotate(
        total=Count('id')
    ).filter(total__gt=1)

    # Relatório final
    print(f"\n{'='*50}")
    print("RESULTADO DA IMPORTAÇÃO")
    print('='*50)
    print(f"Novos clientes criados: {stats['criados']}")
    print(f"LIDs atualizados: {stats['atualizados']}")
    print(f"Telefones duplicados no arquivo (ignorados): {stats['duplicados_telefone']}")
    print(f"Erros: {stats['erros']}")

    print(f"\n{'='*50}")
    print("ESTADO APÓS IMPORTAÇÃO")
    print('='*50)
    print(f"Total clientes: {total_depois} ({'+' if total_depois >= total_antes else ''}{total_depois - total_antes})")
    print(f"  - Ativos: {ativos_depois} ({'+' if ativos_depois >= ativos_antes else ''}{ativos_depois - ativos_antes})")
    print(f"  - Cancelados: {cancelados_depois} ({'+' if cancelados_depois >= cancelados_antes else ''}{cancelados_depois - cancelados_antes})")
    print(f"Com whatsapp_lid: {com_lid_depois} ({'+' if com_lid_depois >= com_lid_antes else ''}{com_lid_depois - com_lid_antes})")

    # Verificação de duplicados
    print(f"\n{'='*50}")
    print("VERIFICAÇÃO DE DUPLICADOS")
    print('='*50)
    if duplicados.exists():
        print(f"ATENÇÃO: Encontrados {duplicados.count()} telefones duplicados!")
        for dup in duplicados[:10]:
            clientes_dup = Cliente.objects.filter(usuario=user, telefone=dup['telefone'])
            print(f"  {dup['telefone']}: {dup['total']}x")
            for c in clientes_dup:
                status = "CANCELADO" if c.cancelado else "ATIVO"
                print(f"    - {c.nome} ({status})")
    else:
        print("OK: Nenhum telefone duplicado encontrado.")

    if dry_run:
        print(f"\n*** MODO DRY-RUN - Nenhuma alteração foi feita ***")


if __name__ == '__main__':
    # Verificar argumento --dry-run
    dry_run = '--dry-run' in sys.argv
    importar_clientes(dry_run=dry_run)
