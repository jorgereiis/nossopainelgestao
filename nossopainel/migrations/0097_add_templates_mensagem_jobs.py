# Generated migration - Adiciona templates de mensagem aos jobs

from django.db import migrations


def add_templates_mensagem(apps, schema_editor):
    """
    Adiciona templates de mensagem padrão aos jobs que não possuem.
    Isso permite que as mensagens sejam editadas via interface de Agendamentos.
    """
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')

    # Templates para gp_vendas
    gp_vendas = ConfiguracaoAgendamento.objects.filter(nome='gp_vendas').first()
    if gp_vendas and not gp_vendas.templates_mensagem:
        gp_vendas.templates_mensagem = {
            'mensagem_vendas': (
                "🔹 A *Star Max Streaming* se trata de um serviço onde através da sua TV Smart "
                "poderá ter acesso aos canais da TV Fechada brasileira e internacional.\n\n"
                "🎬 Conteúdos de Filmes, Séries e Novelas das maiores plataformas de streaming, "
                "como _Amazon, Netflix, Globo Play, Disney+ e outras._\n\n"
                "* Tudo isso usando apenas a sua TV Smart e internet, sem precisar outros aparelhos;\n"
                "* Um excelente serviço por um custo baixíssimo;\n"
                "* Pague com *PIX ou Cartão de Crédito.*\n"
                "* 💰Planos a partir de R$ 25.00\n\n"
                "‼️ Entre em contato conosco aqui mesmo no WhatsApp: +55 83 99332-9190"
            )
        }
        gp_vendas.save(update_fields=['templates_mensagem'])

    # Templates para gp_futebol
    # Nota: Use {data} como placeholder para a data formatada
    gp_futebol = ConfiguracaoAgendamento.objects.filter(nome='gp_futebol').first()
    if gp_futebol and not gp_futebol.templates_mensagem:
        gp_futebol.templates_mensagem = {
            'mensagem_futebol': (
                "⚽️ *AGENDA FUTEBOL DO DIA!*\n"
                "📅 *DATA:* {data}\n\n"
                "Transmissão completa de todos os campeonatos apenas aqui 😉\n\n"
                "Chamaaaaa!! 🔥"
            )
        }
        gp_futebol.save(update_fields=['templates_mensagem'])

    # Templates para mensalidades_canceladas
    # Nota: Use {saudacao} e {nome} como placeholders
    mensalidades_canceladas = ConfiguracaoAgendamento.objects.filter(nome='mensalidades_canceladas').first()
    if mensalidades_canceladas and not mensalidades_canceladas.templates_mensagem:
        mensalidades_canceladas.templates_mensagem = {
            'feedback_20_dias': (
                "*{saudacao}, {nome}* 🫡\n\n"
                "Tudo bem? Espero que sim.\n\n"
                "Faz um tempo que você deixou de ser nosso cliente ativo e ficamos preocupados. "
                "Houve algo que não agradou em nosso sistema?\n\n"
                "Pergunto, pois se algo não agradou, nos informe para fornecermos uma plataforma "
                "melhor para você, tá bom?\n\n"
                "Estamos à disposição! 🙏🏼"
            ),
            'oferta_1_60_dias': (
                "*Opa.. {saudacao}, {nome}!! Tudo bacana?*\n\n"
                "Como você já foi nosso cliente, trago uma notícia que talvez você goste muuuiito!!\n\n"
                "Você pode renovar a sua mensalidade conosco pagando *APENAS R$ 24.90* nos próximos "
                "3 meses. Olha só que bacana?!?!\n\n"
                "Esse tipo de desconto não oferecemos a qualquer um, viu? rsrs\n\n"
                "Caso tenha interesse, avise aqui, pois iremos garantir essa oferta apenas essa semana. 👏🏼👏🏼"
            ),
            'oferta_2_240_dias': (
                "*{saudacao}, {nome}!* 😊\n\n"
                "Sentimos muito a sua falta por aqui!\n\n"
                "Que tal voltar para a nossa família com uma *SUPER OFERTA EXCLUSIVA*?\n\n"
                "Estamos oferecendo *os próximos 3 meses por apenas R$ 24,90 cada* para você "
                "que já foi nosso cliente! 🎉\n\n"
                "Esta é uma oportunidade única de retornar com um preço especial. Não perca!\n\n"
                "Tem interesse? É só responder aqui! 🙌"
            ),
            'oferta_3_420_dias': (
                "*{saudacao}, {nome}!* 🌟\n\n"
                "Esta é a nossa *ÚLTIMA OFERTA ESPECIAL* para você!\n\n"
                "Sabemos que você já foi parte da nossa família e queremos muito ter você de volta.\n\n"
                "✨ *OFERTA FINAL: R$ 24,90 para os próximos 3 meses* ✨\n\n"
                "Esta é realmente a última oportunidade de aproveitar este preço exclusivo.\n\n"
                "O que acha? Vamos renovar essa parceria? 🤝"
            )
        }
        mensalidades_canceladas.save(update_fields=['templates_mensagem'])


def remove_templates_mensagem(apps, schema_editor):
    """
    Remove os templates de mensagem adicionados (rollback).
    """
    ConfiguracaoAgendamento = apps.get_model('nossopainel', 'ConfiguracaoAgendamento')

    for nome in ['gp_vendas', 'gp_futebol', 'mensalidades_canceladas']:
        job = ConfiguracaoAgendamento.objects.filter(nome=nome).first()
        if job:
            job.templates_mensagem = {}
            job.save(update_fields=['templates_mensagem'])


class Migration(migrations.Migration):

    dependencies = [
        ('nossopainel', '0096_add_cobranca_pix_valores_financeiros'),
    ]

    operations = [
        migrations.RunPython(add_templates_mensagem, remove_templates_mensagem),
    ]
