from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cadastros", "0022_enviosleads_mensagensleads_telefoneleads"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationRead",
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
                ("marcado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "mensalidade",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications_read",
                        to="cadastros.mensalidade",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications_read",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Notificação lida",
                "verbose_name_plural": "Notificações lidas",
                "unique_together": {("usuario", "mensalidade")},
            },
        ),
    ]
