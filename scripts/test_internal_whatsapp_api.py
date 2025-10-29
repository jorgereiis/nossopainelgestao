#!/usr/bin/env python3
"""
Script de teste para o endpoint interno de notificações WhatsApp.

Uso:
    python scripts/test_internal_whatsapp_api.py

Este script testa o endpoint /api/internal/send-whatsapp/ que envia
notificações WhatsApp ao admin (MEU_NUM_TIM) a partir de scripts do servidor MySQL.
"""

import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Carrega variáveis de ambiente
from dotenv import load_dotenv
load_dotenv()

# Configurações
BASE_URL = os.getenv('BASE_URL', 'http://127.0.0.1:8000')
ENDPOINT = f'{BASE_URL}/api/internal/send-whatsapp/'
TELEFONE_ADMIN = os.getenv('MEU_NUM_TIM', '558396239140')


def test_endpoint(mensagem: str, tipo: str = 'test'):
    """
    Testa o endpoint de notificações WhatsApp.

    Args:
        mensagem: Texto da mensagem
        tipo: Tipo da notificação para logging (default: 'test')
    """
    print(f"\n{'='*60}")
    print(f"🧪 TESTE DO ENDPOINT INTERNO WHATSAPP")
    print(f"{'='*60}\n")

    # Payload (apenas mensagem e tipo)
    payload = {
        'mensagem': mensagem,
        'tipo': tipo
    }

    print(f"📡 Endpoint: {ENDPOINT}")
    print(f"📱 Telefone destino (MEU_NUM_TIM): {TELEFONE_ADMIN}")
    print(f"📝 Tipo: {tipo}")
    print(f"\n💬 Mensagem:")
    print(f"   {mensagem.replace(chr(10), chr(10) + '   ')}")
    print(f"\n📦 Payload:")
    print(f"   {json.dumps(payload, indent=2, ensure_ascii=False)}")
    print(f"\n🔄 Enviando requisição...")

    try:
        response = requests.post(
            ENDPOINT,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )

        print(f"\n✅ Resposta recebida:")
        print(f"   Status Code: {response.status_code}")

        # Tenta parsear JSON
        try:
            response_data = response.json()
            print(f"   Response JSON:")
            print(f"   {json.dumps(response_data, indent=6, ensure_ascii=False)}")

            # Analisa resultado
            if response.status_code == 200:
                print(f"\n🎉 SUCESSO! Mensagem enviada ao WhatsApp do admin.")
                return True
            elif response.status_code == 403:
                print(f"\n❌ ERRO: Acesso negado (IP não permitido)")
                print(f"   Verifique se está executando de um IP na whitelist:")
                print(f"   - 127.0.0.1 (localhost)")
                print(f"   - 172.18.0.0/16 (Docker network)")
                return False
            elif response.status_code == 503:
                print(f"\n❌ ERRO: Sessão WhatsApp não encontrada ou inativa")
                print(f"   Conecte uma sessão WhatsApp no painel admin")
                return False
            elif response.status_code == 400:
                print(f"\n❌ ERRO: Payload inválido")
                return False
            else:
                print(f"\n⚠️ AVISO: Status inesperado {response.status_code}")
                return False

        except json.JSONDecodeError:
            print(f"   Response Text: {response.text}")
            return False

    except requests.Timeout:
        print(f"\n❌ ERRO: Timeout após 30 segundos")
        print(f"   Verifique se o servidor Django está rodando")
        return False

    except requests.ConnectionError as e:
        print(f"\n❌ ERRO: Falha na conexão")
        print(f"   Verifique se o servidor está acessível em: {BASE_URL}")
        print(f"   Erro: {e}")
        return False

    except Exception as e:
        print(f"\n❌ ERRO: Exceção inesperada")
        print(f"   {type(e).__name__}: {e}")
        return False


def test_invalid_payload():
    """Testa com payload inválido (mensagem faltando)."""
    print(f"\n{'='*60}")
    print(f"🧪 TESTE: Payload Inválido (mensagem faltando)")
    print(f"{'='*60}\n")

    # Payload sem mensagem (só tipo)
    payload = {
        'tipo': 'test_invalid'
        # 'mensagem' está faltando propositalmente
    }

    print(f"📡 Endpoint: {ENDPOINT}")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")
    print(f"\n🔄 Enviando requisição...")

    try:
        response = requests.post(
            ENDPOINT,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )

        print(f"\n✅ Resposta recebida:")
        print(f"   Status Code: {response.status_code}")

        if response.status_code == 400:
            print(f"   ✅ Validação funcionando corretamente!")
            response_data = response.json()
            print(f"   Response: {json.dumps(response_data, indent=6, ensure_ascii=False)}")
            return True
        else:
            print(f"   ⚠️ Esperado 400, recebido {response.status_code}")
            return False

    except Exception as e:
        print(f"\n❌ ERRO: {type(e).__name__}: {e}")
        return False


def main():
    """Executa todos os testes."""
    print(f"\n")
    print(f"╔{'═'*58}╗")
    print(f"║  TESTE DA API INTERNA DE NOTIFICAÇÕES WHATSAPP          ║")
    print(f"╚{'═'*58}╝")

    # Verifica se servidor está rodando
    print(f"\n🔍 Verificando servidor Django em {BASE_URL}...")
    try:
        response = requests.get(BASE_URL, timeout=5)
        print(f"   ✅ Servidor respondendo (status {response.status_code})")
    except requests.RequestException:
        print(f"   ❌ Servidor não está acessível em {BASE_URL}")
        print(f"   💡 Inicie o servidor: python manage.py runserver")
        return

    # Verifica MEU_NUM_TIM
    print(f"\n🔍 Verificando configuração MEU_NUM_TIM...")
    if TELEFONE_ADMIN:
        print(f"   ✅ MEU_NUM_TIM configurado: {TELEFONE_ADMIN}")
    else:
        print(f"   ⚠️ MEU_NUM_TIM não encontrado no .env")

    # Teste 1: Envio válido
    mensagem_teste = f"""🧪 Teste de Notificação MySQL

📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
🔧 Tipo: Teste automatizado
✨ Status: Endpoint funcionando

Este é um teste do endpoint interno de notificações WhatsApp.
As notificações são enviadas ao admin (MEU_NUM_TIM) via scripts cron."""

    resultado1 = test_endpoint(
        mensagem=mensagem_teste,
        tipo='test_automated'
    )

    # Teste 2: Payload inválido
    resultado2 = test_invalid_payload()

    # Sumário
    print(f"\n{'='*60}")
    print(f"📊 SUMÁRIO DOS TESTES")
    print(f"{'='*60}\n")
    print(f"   Teste 1 (Envio válido): {'✅ PASSOU' if resultado1 else '❌ FALHOU'}")
    print(f"   Teste 2 (Payload inválido): {'✅ PASSOU' if resultado2 else '❌ FALHOU'}")

    total = 2
    passou = sum([resultado1, resultado2])
    print(f"\n   Total: {passou}/{total} testes passaram")

    if passou == total:
        print(f"\n   🎉 Todos os testes passaram com sucesso!\n")
    else:
        print(f"\n   ⚠️ Alguns testes falharam. Verifique os logs acima.\n")

    # Informação sobre logs
    print(f"{'='*60}")
    print(f"📝 VERIFICAR LOGS")
    print(f"{'='*60}\n")
    print(f"   Logs do endpoint: logs/MySQL_Triggers/whatsapp_notifications.log")
    print(f"   Django console: Verifique o terminal onde rodou 'runserver'\n")


if __name__ == '__main__':
    main()
