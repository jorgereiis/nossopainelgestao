from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
from django.utils import timezone


def backfill_historico(apps, schema_editor):
    Cliente = apps.get_model('cadastros', 'Cliente')
    Plano = apps.get_model('cadastros', 'Plano')
    Historico = apps.get_model('cadastros', 'ClientePlanoHistorico')

    for cliente in Cliente.objects.all().iterator():
        inicio = cliente.data_adesao or timezone.localdate()
        fim = cliente.data_cancelamento if cliente.cancelado else None
        plano = cliente.plano
        nome = getattr(plano, 'nome', '')
        valor = getattr(plano, 'valor', 0)
        telas = getattr(plano, 'telas', 1)
        Historico.objects.create(
            cliente_id=cliente.id,
            usuario_id=cliente.usuario_id,
            plano_id=getattr(plano, 'id', None),
            plano_nome=str(nome),
            telas=int(telas or 1),
            valor_plano=valor or 0,
            inicio=inicio,
            fim=fim,
            motivo='create',
        )


class Migration(migrations.Migration):
    dependencies = [
        ('cadastros', '0024_alter_plano_nome'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientePlanoHistorico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plano_nome', models.CharField(max_length=255)),
                ('telas', models.IntegerField(default=1)),
                ('valor_plano', models.DecimalField(decimal_places=2, max_digits=7)),
                ('inicio', models.DateField()),
                ('fim', models.DateField(blank=True, null=True)),
                ('motivo', models.CharField(choices=[('create', 'Criação'), ('plan_change', 'Troca de plano'), ('cancel', 'Cancelamento'), ('reactivate', 'Reativação')], default='create', max_length=32)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historico_planos', to='cadastros.cliente')),
                ('plano', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='cadastros.plano')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Histórico de Plano do Cliente',
                'verbose_name_plural': 'Históricos de Plano dos Clientes',
                'ordering': ['cliente', '-inicio', '-criado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='clienteplanohistorico',
            index=models.Index(fields=['usuario', 'inicio'], name='cadastros_c_usuario_07f805_idx'),
        ),
        migrations.AddIndex(
            model_name='clienteplanohistorico',
            index=models.Index(fields=['cliente', 'inicio'], name='cadastros_c_cliente_9a7e3f_idx'),
        ),
        migrations.AddIndex(
            model_name='clienteplanohistorico',
            index=models.Index(fields=['cliente', 'fim'], name='cadastros_c_cliente_2a7d1b_idx'),
        ),
        migrations.RunPython(backfill_historico, migrations.RunPython.noop),
    ]

