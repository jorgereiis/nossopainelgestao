from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0125_populate_planos_assinatura'),
    ]

    operations = [
        migrations.CreateModel(
            name='ControleAcessoPagina',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chave', models.CharField(max_length=80, unique=True)),
                ('nome_exibicao', models.CharField(max_length=120)),
                ('descricao', models.TextField(blank=True)),
                ('icone', models.CharField(default='layout', max_length=60)),
                ('rota_nome', models.CharField(max_length=120)),
                ('ativo', models.BooleanField(default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Controle de Acesso a Página',
                'db_table': 'cadastros_controleacessopagina',
                'ordering': ['nome_exibicao'],
            },
        ),
    ]
