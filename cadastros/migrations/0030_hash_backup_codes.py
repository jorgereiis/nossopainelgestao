# Generated manually for security enhancement
# Hashear códigos de backup 2FA existentes

from django.db import migrations
from django.contrib.auth.hashers import make_password


def hash_existing_backup_codes(apps, schema_editor):
    """
    Hashear todos os códigos de backup existentes no banco de dados.

    ✅ SEGURANÇA: Códigos de backup são equivalentes a senhas e devem ser hasheados.
    Esta migração converte códigos em plaintext para hashes seguros.
    """
    UserProfile = apps.get_model('cadastros', 'UserProfile')

    profiles_updated = 0
    codes_hashed = 0

    for profile in UserProfile.objects.all():
        if profile.two_factor_backup_codes:
            # Verificar se já estão hasheados (começam com hash identifier)
            # Hash Django começam com algoritmo$ (ex: pbkdf2_sha256$...)
            first_code = profile.two_factor_backup_codes[0] if profile.two_factor_backup_codes else ''

            if first_code and not first_code.startswith('pbkdf2_'):
                # Códigos ainda em plaintext, hashear
                original_codes = profile.two_factor_backup_codes.copy()
                hashed_codes = [make_password(code) for code in original_codes]
                profile.two_factor_backup_codes = hashed_codes
                profile.save(update_fields=['two_factor_backup_codes'])

                profiles_updated += 1
                codes_hashed += len(original_codes)

                print(f'  ✅ Hasheados {len(original_codes)} códigos para usuário {profile.user.username}')

    if profiles_updated > 0:
        print(f'\n🔐 Migração de segurança concluída:')
        print(f'   - {profiles_updated} perfis atualizados')
        print(f'   - {codes_hashed} códigos hasheados')
    else:
        print('\n✅ Nenhum código em plaintext encontrado. Todos já estão hasheados.')


def reverse_hash_backup_codes(apps, schema_editor):
    """
    ATENÇÃO: Não é possível reverter hashes para plaintext!
    Esta função apenas exibe um aviso.
    """
    print('\n⚠️  AVISO: Não é possível reverter hashes de backup codes!')
    print('   Os códigos originais em plaintext foram perdidos permanentemente.')
    print('   Se necessário, gere novos códigos de backup.')


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0029_loginlog'),
    ]

    operations = [
        migrations.RunPython(
            hash_existing_backup_codes,
            reverse_code=reverse_hash_backup_codes
        ),
    ]
