# Generated manually to remove orphaned CapSolver Extension fields
# These fields were added in deleted migrations and need to be cleaned up
#
# Using RunPython to handle SQLite table recreation (no ALTER TABLE DROP COLUMN support)

from django.db import migrations


def remove_captcha_solves_count(apps, schema_editor):
    """
    Remove orphaned column from SQLite database.

    SQLite doesn't support DROP COLUMN, so we:
    1. Create new table without the column
    2. Copy data
    3. Drop old table
    4. Rename new table
    """
    db_alias = schema_editor.connection.alias

    with schema_editor.connection.cursor() as cursor:
        # Check if column exists before trying to remove it
        cursor.execute("PRAGMA table_info(cadastros_contareseller)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        # Columns to remove (orphaned from deleted migrations)
        orphaned_columns = ['captcha_solves_count', 'metodo_ultimo_login', 'ultimo_solve_captcha']

        # Check if any orphaned column exists
        has_orphaned = any(col in column_names for col in orphaned_columns)
        if not has_orphaned:
            # No orphaned columns, nothing to do
            return

        # Get all columns except the ones we want to remove
        keep_columns = [col for col in column_names if col not in orphaned_columns]
        keep_columns_str = ', '.join(keep_columns)

        # Create new table without the orphaned column
        cursor.execute(f"""
            CREATE TABLE cadastros_contareseller_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED,
                aplicativo_id INTEGER NOT NULL REFERENCES cadastros_aplicativo(id) DEFERRABLE INITIALLY DEFERRED,
                email_login VARCHAR(255) NOT NULL,
                senha_login VARCHAR(500) NOT NULL,
                session_data TEXT NOT NULL,
                ultimo_login DATETIME NULL,
                sessao_valida BOOLEAN NOT NULL,
                data_criacao DATETIME NOT NULL,
                data_atualizacao DATETIME NOT NULL
            )
        """)

        # Copy data from old table to new table
        cursor.execute(f"""
            INSERT INTO cadastros_contareseller_new ({keep_columns_str})
            SELECT {keep_columns_str}
            FROM cadastros_contareseller
        """)

        # Drop old table
        cursor.execute("DROP TABLE cadastros_contareseller")

        # Rename new table
        cursor.execute("ALTER TABLE cadastros_contareseller_new RENAME TO cadastros_contareseller")

        # Recreate indexes
        cursor.execute("""
            CREATE INDEX conta_reseller_user_app_idx
            ON cadastros_contareseller (usuario_id, aplicativo_id)
        """)

        # Recreate unique constraint (if it exists)
        cursor.execute("""
            CREATE UNIQUE INDEX cadastros_contareseller_usuario_id_aplicativo_id_uniq
            ON cadastros_contareseller (usuario_id, aplicativo_id)
        """)


def reverse_migration(apps, schema_editor):
    # No reverse - this is cleanup of orphaned data
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0046_add_progress_fields'),
    ]

    operations = [
        migrations.RunPython(remove_captcha_solves_count, reverse_migration),
    ]
