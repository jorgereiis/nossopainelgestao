# Generated migration - Encripta campos sensíveis de API com FERNET

from django.db import migrations
from django.conf import settings


def encrypt_existing_values(apps, schema_editor):
    """
    Encripta valores existentes em texto plano.

    Esta migração percorre todos os registros de ContaBancaria e CredencialAPI
    e encripta os campos sensíveis que ainda estão em texto plano.
    """
    from cryptography.fernet import Fernet

    fernet_key = getattr(settings, 'FERNET_KEY', None)
    if not fernet_key:
        print("[AVISO] FERNET_KEY não configurada. Pulando encriptação.")
        return

    try:
        cipher = Fernet(fernet_key.encode())
    except Exception as e:
        print(f"[ERRO] FERNET_KEY inválida: {e}")
        return

    def encrypt_value(value):
        """Encripta um valor se ainda não estiver encriptado."""
        if not value:
            return ''
        # Verifica se já está encriptado (formato Fernet começa com 'gAAAAA')
        if value.startswith('gAAAAA'):
            return value
        try:
            encrypted = cipher.encrypt(value.encode('utf-8'))
            return encrypted.decode('utf-8')
        except Exception as e:
            print(f"[ERRO] Falha ao encriptar: {e}")
            return value

    # Encriptar ContaBancaria
    ContaBancaria = apps.get_model('nossopainel', 'ContaBancaria')
    contas = ContaBancaria.objects.all()
    count_contas = 0

    for conta in contas:
        updated = False

        if conta.api_key and not conta.api_key.startswith('gAAAAA'):
            conta.api_key = encrypt_value(conta.api_key)
            updated = True

        if conta.api_client_secret and not conta.api_client_secret.startswith('gAAAAA'):
            conta.api_client_secret = encrypt_value(conta.api_client_secret)
            updated = True

        if conta.api_access_token and not conta.api_access_token.startswith('gAAAAA'):
            conta.api_access_token = encrypt_value(conta.api_access_token)
            updated = True

        if conta.webhook_secret and not conta.webhook_secret.startswith('gAAAAA'):
            conta.webhook_secret = encrypt_value(conta.webhook_secret)
            updated = True

        if updated:
            conta.save(update_fields=['api_key', 'api_client_secret', 'api_access_token', 'webhook_secret'])
            count_contas += 1

    print(f"[OK] ContaBancaria: {count_contas} registros encriptados")

    # Encriptar CredencialAPI
    CredencialAPI = apps.get_model('nossopainel', 'CredencialAPI')
    credenciais = CredencialAPI.objects.all()
    count_creds = 0

    for cred in credenciais:
        updated = False

        if cred.api_key and not cred.api_key.startswith('gAAAAA'):
            cred.api_key = encrypt_value(cred.api_key)
            updated = True

        if cred.api_client_secret and not cred.api_client_secret.startswith('gAAAAA'):
            cred.api_client_secret = encrypt_value(cred.api_client_secret)
            updated = True

        if cred.api_access_token and not cred.api_access_token.startswith('gAAAAA'):
            cred.api_access_token = encrypt_value(cred.api_access_token)
            updated = True

        if updated:
            cred.save(update_fields=['api_key', 'api_client_secret', 'api_access_token'])
            count_creds += 1

    print(f"[OK] CredencialAPI: {count_creds} registros encriptados")


def decrypt_existing_values(apps, schema_editor):
    """
    Rollback: Descriptografa valores encriptados.

    CUIDADO: Esta operação só funciona se a FERNET_KEY for a mesma
    usada para encriptar os dados.
    """
    from cryptography.fernet import Fernet

    fernet_key = getattr(settings, 'FERNET_KEY', None)
    if not fernet_key:
        print("[AVISO] FERNET_KEY não configurada. Pulando descriptografia.")
        return

    try:
        cipher = Fernet(fernet_key.encode())
    except Exception as e:
        print(f"[ERRO] FERNET_KEY inválida: {e}")
        return

    def decrypt_value(value):
        """Descriptografa um valor se estiver encriptado."""
        if not value:
            return ''
        if not value.startswith('gAAAAA'):
            return value
        try:
            decrypted = cipher.decrypt(value.encode('utf-8'))
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"[ERRO] Falha ao descriptografar: {e}")
            return value

    # Descriptografar ContaBancaria
    ContaBancaria = apps.get_model('nossopainel', 'ContaBancaria')
    contas = ContaBancaria.objects.all()
    count_contas = 0

    for conta in contas:
        updated = False

        if conta.api_key and conta.api_key.startswith('gAAAAA'):
            conta.api_key = decrypt_value(conta.api_key)
            updated = True

        if conta.api_client_secret and conta.api_client_secret.startswith('gAAAAA'):
            conta.api_client_secret = decrypt_value(conta.api_client_secret)
            updated = True

        if conta.api_access_token and conta.api_access_token.startswith('gAAAAA'):
            conta.api_access_token = decrypt_value(conta.api_access_token)
            updated = True

        if conta.webhook_secret and conta.webhook_secret.startswith('gAAAAA'):
            conta.webhook_secret = decrypt_value(conta.webhook_secret)
            updated = True

        if updated:
            conta.save(update_fields=['api_key', 'api_client_secret', 'api_access_token', 'webhook_secret'])
            count_contas += 1

    print(f"[OK] ContaBancaria: {count_contas} registros descriptografados")

    # Descriptografar CredencialAPI
    CredencialAPI = apps.get_model('nossopainel', 'CredencialAPI')
    credenciais = CredencialAPI.objects.all()
    count_creds = 0

    for cred in credenciais:
        updated = False

        if cred.api_key and cred.api_key.startswith('gAAAAA'):
            cred.api_key = decrypt_value(cred.api_key)
            updated = True

        if cred.api_client_secret and cred.api_client_secret.startswith('gAAAAA'):
            cred.api_client_secret = decrypt_value(cred.api_client_secret)
            updated = True

        if cred.api_access_token and cred.api_access_token.startswith('gAAAAA'):
            cred.api_access_token = decrypt_value(cred.api_access_token)
            updated = True

        if updated:
            cred.save(update_fields=['api_key', 'api_client_secret', 'api_access_token'])
            count_creds += 1

    print(f"[OK] CredencialAPI: {count_creds} registros descriptografados")


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0100_add_sync_pix_agendamento'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_values, decrypt_existing_values),
    ]
