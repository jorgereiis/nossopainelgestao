from django.conf import settings
from django.db import migrations, models


def create_useractionlog_table(apps, schema_editor):
    table = "cadastros_useractionlog"
    existing_tables = schema_editor.connection.introspection.table_names()
    if table in existing_tables:
        return

    class HistoricalUserActionLog(models.Model):
        ACTION_CHOICES = [
            ("create", "Criação"),
            ("update", "Atualização"),
            ("delete", "Exclusão"),
            ("import", "Importação"),
            ("cancel", "Cancelamento"),
            ("reactivate", "Reativação"),
            ("payment", "Pagamento"),
            ("other", "Ação"),
        ]

        usuario = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            on_delete=models.CASCADE,
            related_name="action_logs",
        )
        acao = models.CharField(max_length=32, choices=ACTION_CHOICES, default="other")
        entidade = models.CharField(max_length=100, blank=True)
        objeto_id = models.CharField(max_length=64, blank=True)
        objeto_repr = models.CharField(max_length=255, blank=True)
        mensagem = models.TextField(blank=True)
        extras = models.JSONField(blank=True, null=True)
        ip = models.GenericIPAddressField(blank=True, null=True)
        request_path = models.CharField(max_length=255, blank=True)
        criado_em = models.DateTimeField(auto_now_add=True)

        class Meta:
            app_label = "nossopainel"
            db_table = table
            managed = False
            indexes = [
                models.Index(
                    fields=["usuario", "-criado_em"],
                    name="cadastros_u_usuario_966dcb_idx",
                ),
                models.Index(
                    fields=["entidade", "acao"],
                    name="cadastros_u_entidad_4d2aba_idx",
                ),
            ]

    schema_editor.create_model(HistoricalUserActionLog)


def drop_useractionlog_table(apps, schema_editor):
    table = "cadastros_useractionlog"
    existing_tables = schema_editor.connection.introspection.table_names()
    if table not in existing_tables:
        return

    class HistoricalUserActionLog(models.Model):
        class Meta:
            app_label = "nossopainel"
            db_table = table
            managed = False

    schema_editor.delete_model(HistoricalUserActionLog)


class Migration(migrations.Migration):
    dependencies = [
        ("nossopainel", "0025_clienteplanohistorico"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(create_useractionlog_table, drop_useractionlog_table),
            ],
            state_operations=[
                migrations.CreateModel(
                    name="UserActionLog",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "acao",
                            models.CharField(
                                choices=[
                                    ("create", "Criação"),
                                    ("update", "Atualização"),
                                    ("delete", "Exclusão"),
                                    ("import", "Importação"),
                                    ("cancel", "Cancelamento"),
                                    ("reactivate", "Reativação"),
                                    ("payment", "Pagamento"),
                                    ("other", "Ação"),
                                ],
                                default="other",
                                max_length=32,
                            ),
                        ),
                        ("entidade", models.CharField(blank=True, max_length=100)),
                        ("objeto_id", models.CharField(blank=True, max_length=64)),
                        ("objeto_repr", models.CharField(blank=True, max_length=255)),
                        ("mensagem", models.TextField(blank=True)),
                        ("extras", models.JSONField(blank=True, null=True)),
                        ("ip", models.GenericIPAddressField(blank=True, null=True)),
                        ("request_path", models.CharField(blank=True, max_length=255)),
                        ("criado_em", models.DateTimeField(auto_now_add=True)),
                        (
                            "usuario",
                            models.ForeignKey(
                                on_delete=models.CASCADE,
                                related_name="action_logs",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Log de ação de usuário",
                        "verbose_name_plural": "Logs de ações de usuários",
                        "ordering": ["-criado_em"],
                    },
                ),
                migrations.AddIndex(
                    model_name="useractionlog",
                    index=models.Index(
                        fields=["usuario", "-criado_em"],
                        name="cadastros_u_usuario_966dcb_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="useractionlog",
                    index=models.Index(
                        fields=["entidade", "acao"],
                        name="cadastros_u_entidad_4d2aba_idx",
                    ),
                ),
            ],
        ),
    ]

