from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0122_perfilatendente_add_horario'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='registroatendimento',
            name='resolvido_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Resolvido em'),
        ),
        migrations.AddField(
            model_name='registroatendimento',
            name='resolvido_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='atendimentos_resolvidos',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Resolvido por',
            ),
        ),
    ]
