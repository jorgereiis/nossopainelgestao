"""
Módulo de definição das models principais da aplicação.
Inclui entidades como Cliente, Plano, Mensalidade, Aplicativo, Sessão WhatsApp, entre outras.
"""

import re
from django.db import models
from django.utils import timezone
from datetime import timedelta, date
from django.contrib.auth.models import User
from django.utils.timezone import localtime, now
from django.core.validators import MinValueValidator

DDD_UF_MAP = {
    '11': 'SP', '12': 'SP', '13': 'SP', '14': 'SP', '15': 'SP', '16': 'SP', '17': 'SP', '18': 'SP', '19': 'SP',
    '21': 'RJ', '22': 'RJ', '24': 'RJ',
    '27': 'ES', '28': 'ES',
    '31': 'MG', '32': 'MG', '33': 'MG', '34': 'MG', '35': 'MG', '37': 'MG', '38': 'MG',
    '41': 'PR', '42': 'PR', '43': 'PR', '44': 'PR', '45': 'PR', '46': 'PR',
    '47': 'SC', '48': 'SC', '49': 'SC',
    '51': 'RS', '53': 'RS', '54': 'RS', '55': 'RS',
    '61': 'DF',
    '62': 'GO', '64': 'GO',
    '63': 'TO',
    '65': 'MT', '66': 'MT',
    '67': 'MS',
    '68': 'AC',
    '69': 'RO',
    '71': 'BA', '73': 'BA', '74': 'BA', '75': 'BA', '77': 'BA',
    '79': 'SE',
    '81': 'PE', '87': 'PE',
    '82': 'AL',
    '83': 'PB',
    '84': 'RN',
    '85': 'CE', '88': 'CE',
    '86': 'PI', '89': 'PI',
    '91': 'PA', '93': 'PA', '94': 'PA',
    '92': 'AM', '97': 'AM',
    '95': 'RR',
    '96': 'AP',
    '98': 'MA', '99': 'MA',
}

def default_vencimento():
    """Retorna a data de vencimento padrão: 30 dias a partir da data atual."""
    return timezone.now().date() + timedelta(days=30)


class Servidor(models.Model):
    """Representa os servidores associados aos clientes."""
    CLUB = "CLUB"
    PLAY = "PlayON"
    ALPHA = "ALPHA"
    SEVEN = "SEVEN"
    FIVE = "FIVE"

    CHOICES = ((CLUB, CLUB), (PLAY, PLAY), (ALPHA, ALPHA), (SEVEN, SEVEN), (FIVE, FIVE))

    nome = models.CharField(max_length=255, choices=CHOICES)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        verbose_name_plural = "Servidores"

    def __str__(self):
        return self.nome


class Tipos_pgto(models.Model):
    """Define os tipos de pagamento disponíveis para o cliente."""
    PIX = "PIX"
    CARTAO = "Cartão de Crédito"
    BOLETO = "Boleto"

    CHOICES = ((PIX, PIX), (CARTAO, CARTAO), (BOLETO, BOLETO))

    nome = models.CharField(max_length=255, choices=CHOICES, default=PIX)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Tipo de Pagamento"
        verbose_name_plural = "Tipos de Pagamentos"

    def __str__(self):
        return self.nome


class Dispositivo(models.Model):
    """Define o nome de um dispositivo utilizado por clientes."""
    nome = models.CharField(max_length=255, null=False, blank=False)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.nome


class Aplicativo(models.Model):
    """Modela os aplicativos utilizados na conta do cliente."""
    nome = models.CharField(max_length=255)
    device_has_mac = models.BooleanField(default=False)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.nome


class Plano(models.Model):
    """Modela os planos de mensalidade disponíveis para os clientes."""
    MENSAL = "Mensal"
    TRIMESTRAL = "Trimestral"
    SEMESTRAL = "Semestral"
    ANUAL = "Anual"

    CHOICES = ((MENSAL, MENSAL), (TRIMESTRAL, TRIMESTRAL), (SEMESTRAL, SEMESTRAL), (ANUAL, ANUAL))

    nome = models.CharField("Nome do plano", max_length=255, choices=CHOICES, default=MENSAL)
    telas = models.IntegerField("Número de telas", default=1)
    valor = models.DecimalField("Valor", max_digits=5, decimal_places=2)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.nome} - {self.valor}"


class Cliente(models.Model):
    """Modela o cliente da plataforma com todos os seus dados cadastrais e plano."""
    servidor = models.ForeignKey(Servidor, on_delete=models.CASCADE)
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE, default=None)
    sistema = models.ForeignKey(Aplicativo, on_delete=models.CASCADE, default=None)
    nome = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True, null=True)
    telefone = models.CharField(max_length=20)
    uf = models.CharField(max_length=2, blank=True, null=True)
    indicado_por = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)
    data_vencimento = models.DateField("Data de vencimento inicial", blank=True, null=True)
    forma_pgto = models.ForeignKey(Tipos_pgto, on_delete=models.CASCADE, default=1, verbose_name="Forma de pagamento")
    plano = models.ForeignKey(Plano, on_delete=models.CASCADE, default=1)
    data_adesao = models.DateField("Data de adesão", default=date.today)
    data_cancelamento = models.DateField("Data de cancelamento", blank=True, null=True)
    ultimo_pagamento = models.DateField("Último pagamento realizado", blank=True, null=True)
    cancelado = models.BooleanField("Cancelado", default=False)
    nao_enviar_msgs = models.BooleanField("Não enviar", default=False)
    enviado_oferta_promo = models.BooleanField("Oferta PROMO", default=False)
    notas = models.TextField("Notas", blank=True, null=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        ordering = ['-data_adesao']

    def save(self, *args, **kwargs):
        """Salva o cliente ajustando a data de pagamento e formatando telefone/UF."""
        if self.data_adesao and self.data_vencimento is None:
            self.data_vencimento = self.data_adesao

        self.formatar_telefone()
        self.definir_uf()
        super().save(*args, **kwargs)

    def formatar_telefone(self):
        """Normaliza o telefone para o padrão internacional E.164: +55DDDNÚMERO."""
        numero = re.sub(r'\D+', '', self.telefone)

        # Adiciona DDI Brasil se for nacional
        if len(numero) in (10, 11) and not numero.startswith('55'):
            numero = '55' + numero

        if not numero.startswith('+'):
            numero = '+' + numero
        
        self.telefone = numero  # Ex: +5500000000000

    def definir_uf(self):
        """Define a unidade federativa (UF) com base no DDD do telefone."""
        raw_telefone = re.sub(r'\D+', '', self.telefone)
        if raw_telefone.startswith('55'):
            raw_telefone = raw_telefone[2:]
        self.uf = DDD_UF_MAP.get(raw_telefone[:2], None) if len(raw_telefone) >= 2 else None

    def __str__(self):
        return self.nome


class Mensalidade(models.Model):
    """Modela a mensalidade de um cliente com informações de pagamento, vencimento e status."""
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    valor = models.DecimalField("Valor", max_digits=5, decimal_places=2, default=None)
    dt_vencimento = models.DateField("Data do vencimento", default=default_vencimento)
    dt_pagamento = models.DateField("Data do pagamento", null=True, blank=True)
    dt_cancelamento = models.DateField("Data do cancelamento", null=True, blank=True)
    dt_notif_wpp1 = models.DateField("Data envio notificação PROMO", null=True, blank=True)
    pgto = models.BooleanField("Pago", default=False)
    cancelado = models.BooleanField(default=False)
    notificacao_wpp1 = models.BooleanField("Notificação PROMO", default=False)
    recebeu_pix_indicacao = models.BooleanField("PIX R$50", default=False)
    isencao_anuidade = models.BooleanField("Isenção por bônus anuidade", default=False)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return f"[{self.dt_vencimento.strftime('%d/%m/%Y')}] {self.valor} - {self.cliente}"


class HorarioEnvios(models.Model):
    """Define o horário preferencial de envio de mensagens automáticas."""
    TITULO = [
        ("mensalidades_a_vencer", "Notificação de vencimentos"),
        ("obter_mensalidades_vencidas", "Notificação de atrasos"),
    ]

    DESCRICOES = {
        "mensalidades_a_vencer": "Defina aqui o horário do dia em que deseja que as mensagens de Notificação de Vencimento sejam enviadas para os seus clientes.",
        "obter_mensalidades_vencidas": "Defina aqui o horário do dia em que deseja que as mensagens de Notificação de Atraso sejam enviadas para os seus clientes.",
    }

    EXEMPLOS = {
        "mensalidades_a_vencer": "Todos os clientes com mensalidades vencendo daqui há 2 dias receberão uma mensagem no WhatsApp informando sobre Data de Vencimento, Tipo do Plano, Valor e Dados de Pagamento.",
        "obter_mensalidades_vencidas": "Todos os clientes com mensalidades vencidas há 2 dias receberão uma mensagem no WhatsApp informando sobre a mensalidade pendentes para realizarem seus pagamentos antes que seja feito o cancelamento.",
    }

    nome = models.CharField(max_length=255, choices=TITULO)
    tipo_envio = models.CharField(max_length=255, choices=TITULO)
    horario = models.TimeField(null=True)
    ultimo_envio = models.DateField(null=True, blank=True)
    status = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Horário de Envio"
        verbose_name_plural = "Horarios de Envio"

    def __str__(self):
        return self.get_nome_display()

    @property
    def descricao(self):
        return self.DESCRICOES.get(self.tipo_envio, "")

    @property
    def exemplo(self):
        return self.EXEMPLOS.get(self.tipo_envio, "")

    
class PlanoIndicacao(models.Model):
    """Representa um plano de indicação que oferece desconto ou valor em dinheiro."""
    TITULO = [
        ("desconto", "Desconto por Indicação"),
        ("dinheiro", "Bônus por Indicações"),
        ("anuidade", "Bônus por Anuidade"),
    ]
    DESCRICOES = {
        "desconto": "Permite que o sistema aplique desconto à mensalidade do cliente que fez indicação de um novo cliente no mês.",
        "dinheiro": "Permite que o sistema bonifique o cliente com um valor a receber após realizar indicações de pelo menos 2 novos clientes no mesmo mês.",
        "anuidade": "Permite que o sistema aplique desconto à mensalidade dos clientes que completarem 12 meses consecutivos como clientes.",
    }
    EXEMPLOS = {
        "desconto": "Indicou 1 novo cliente neste mês, terá R$ 20.00 de desconto no próximo pagamento.",
        "dinheiro": "Indicou 2 novos clientes no mês de Janeiro, o sistema enviará uma mensagem por WhatsApp informando ao cliente que ele tem um valor a receber como bonificação e agradecimento pelas indicações feitas.",
        "anuidade": "Aderiu em Jan/23 e terá desconto do valor definido na mensalidade de Jan/24, desde que não tenha passado ao menos 30 dias com uma das suas mensalidades CANCELADAS. Uma mensagem será enviada por WhatsApp para informar o cliente sobre a bonificação.",
    }
    nome = models.CharField(max_length=255, choices=TITULO)
    tipo_plano = models.CharField(max_length=255, choices=TITULO)
    valor = models.DecimalField('Valor para desconto ou bonificação', max_digits=6, decimal_places=2, validators=[MinValueValidator(0)], default=0)
    valor_minimo_mensalidade = models.DecimalField('Valor mínimo a ser mantido na mensalidade', max_digits=6, decimal_places=2, validators=[MinValueValidator(0)], default=0)
    status = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        verbose_name_plural = "Planos de Indicação"
        unique_together = ('usuario', 'tipo_plano')

    def __str__(self):
        return self.get_nome_display()

    @property
    def descricao(self):
        return self.DESCRICOES.get(self.tipo_plano, "")

    @property
    def exemplo(self):
        return self.EXEMPLOS.get(self.tipo_plano, "")


class ContaDoAplicativo(models.Model):
    """Armazena as credenciais de acesso de um cliente a um determinado aplicativo."""
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="conta_aplicativo")
    app = models.ForeignKey(Aplicativo, on_delete=models.CASCADE, related_name="aplicativos", verbose_name="Aplicativo")
    device_id = models.CharField("ID", max_length=255, blank=True, null=True)
    email = models.EmailField("E-mail", max_length=255, blank=True, null=True)
    device_key = models.CharField("Senha", max_length=255, blank=True, null=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    verificado = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Formata device_id como MAC address: XX:XX:XX:XX:XX:XX
        if self.device_id and not len(self.device_id) <= 10:
            raw = re.sub(r'[^A-Fa-f0-9]', '', self.device_id).upper()
            self.device_id = ':'.join(raw[i:i+2] for i in range(0, len(raw), 2))
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Conta do Aplicativo"
        verbose_name_plural = "Contas dos Aplicativos"

        indexes = [
            models.Index(fields=['cliente', 'app']),
            models.Index(fields=['device_id']),
        ]

    def __str__(self):
        return self.app.nome


class SessaoWpp(models.Model):
    """Armazena as informações da sessão do WhatsApp integrada."""
    usuario = models.CharField(max_length=255)
    token = models.CharField(max_length=255)
    dt_inicio = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Sessão do WhatsApp"
        verbose_name_plural = "Sessões do WhatsApp"

    def __str__(self) -> str:
        return self.usuario


class SecretTokenAPI(models.Model):
    """Armazena tokens secretos para autenticação via API personalizada."""
    token = models.CharField(max_length=255)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    dt_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Secret Token API"
        verbose_name_plural = "Secrets Tokens API"

    def __str__(self) -> str:
        return self.token


class DadosBancarios(models.Model):
    """Modela os dados bancários do usuário para recebimentos."""
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    wpp = models.CharField(max_length=20, null=True, blank=True)
    beneficiario = models.CharField(max_length=255)
    instituicao = models.CharField(max_length=255)
    tipo_chave = models.CharField(max_length=255)
    chave = models.CharField(max_length=255)

    def formatar_telefone(self):
        """Normaliza o telefone para o padrão internacional E.164: +55DDDNÚMERO."""
        numero = re.sub(r'\D+', '', self.wpp)

        # Adiciona DDI Brasil se for nacional
        if len(numero) in (10, 11) and not numero.startswith('55'):
            numero = '55' + numero

        if len(numero) < 10:
            raise ValueError("Telefone inválido")

        self.wpp = '+' + numero  # Ex: +5500000000000

    def save(self, *args, **kwargs):
        """Salva o cliente ajustando a data de pagamento e formatando telefone/UF."""

        self.formatar_telefone()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Dados Bancários"

    def __str__(self) -> str:
        return f'{self.usuario.first_name} {self.usuario.last_name}'


class MensagemEnviadaWpp(models.Model):
    """Registra o histórico de mensagens enviadas ao WhatsApp."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    telefone = models.CharField(max_length=20)
    data_envio = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "Mensagem Enviada ao WhatsApp"
        verbose_name_plural = "Mensagens Enviadas ao WhatsApp"

    def __str__(self) -> str:
        return self.telefone


class ConteudoM3U8(models.Model):
    """Modela os conteúdos processados a partir de arquivos M3U8 (filmes, séries etc)."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    nome = models.CharField(max_length=255)
    capa = models.URLField()
    temporada = models.IntegerField(null=True, blank=True)
    episodio = models.IntegerField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    upload = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Conteúdo M3U8"
        verbose_name_plural = "Conteúdos M3U8"

    def __str__(self):
        return self.nome


class DominiosDNS(models.Model):
    """Modela os domínios DNS utilizados para verificar a disponibilidade de canais."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    servidor = models.ForeignKey(Servidor, on_delete=models.CASCADE)
    data_online = models.DateTimeField(blank=True, null=True)
    data_offline = models.DateTimeField(blank=True, null=True)
    acesso_canais = models.CharField(max_length=255, blank=True, null=True)
    data_ultima_verificacao = models.DateTimeField(blank=True, null=True)
    data_envio_alerta = models.DateTimeField(blank=True, null=True)
    dominio = models.CharField(max_length=255, unique=True)
    monitorado = models.BooleanField(default=True)
    status = models.CharField(max_length=20, default='online', choices=[('online', 'Online'), ('offline', 'Offline')])

    class Meta:
        verbose_name = "Domínio DNS"
        verbose_name_plural = "Domínios DNS"

    def save(self, *args, **kwargs):
        """Salva o domínio DNS, garantindo que o domínio seja formatado corretamente."""
        self.dominio = self.dominio.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.dominio


class TelefoneLeads(models.Model):
    """Modela os números de telefone coletados como leads para futuras campanhas."""
    telefone = models.CharField(max_length=20, unique=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Telefones Leads"

    def __str__(self):
        return self.telefone
    

class EnviosLeads(models.Model):
    """Registra os envios de mensagens para os leads coletados."""
    telefone = models.CharField(max_length=20)
    data_envio = models.DateTimeField(auto_now_add=True)
    mensagem = models.TextField()
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Envios de Mensagens Leads"

    def __str__(self):
        return self.telefone
    

class MensagensLeads(models.Model):
    """Armazena as mensagens enviadas para os leads."""
    nome = models.CharField(max_length=255)
    tipo = models.CharField(max_length=50, choices=[('ativos', 'Clientes ativos'), ('cancelados', 'Clientes cancelados'), ('avulso', 'Leads avulsos')])
    mensagem = models.TextField()
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Mensagens Leads"

    def __str__(self):
        return self.tipo