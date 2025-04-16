import re
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


# funcão para definir o dia de pagamento
def definir_dia_pagamento(dia_adesao):
    if dia_adesao in range(3, 8):
        dia_pagamento = 5
    elif dia_adesao in range(8, 13):
        dia_pagamento = 10
    elif dia_adesao in range(13, 18):
        dia_pagamento = 15
    elif dia_adesao in range(18, 23):
        dia_pagamento = 20
    elif dia_adesao in range(23, 28):
        dia_pagamento = 25
    else:
        dia_pagamento = 30
    return dia_pagamento


# Cadastro de novos servidores
class Servidor(models.Model):
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


# Tipos de pagamentos disponíveis no sistema
class Tipos_pgto(models.Model):
    PIX = "PIX"
    CARTAO = "Cartão de Crédito"
    BOLETO = "Boleto"

    CHOICES = ((PIX, PIX), (CARTAO, CARTAO), (BOLETO, BOLETO))

    nome = models.CharField(max_length=255, choices=CHOICES, default=PIX)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Tipo de pagamento"
        verbose_name_plural = "Tipos de pagamentos"

    def __str__(self):
        return self.nome


# Dispositivos utilizados pelos clientes (TVs, TVBOX, celulares, etc.)
class Dispositivo(models.Model):
    nome = models.CharField(max_length=255, null=False, blank=False)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.nome


class Aplicativo(models.Model):
    nome = models.CharField(max_length=255)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.nome


# Quantidade de telas que o cliente utilizará em seu plano
class Qtd_tela(models.Model):
    telas = models.PositiveSmallIntegerField("Quantidade de telas", unique=True)

    class Meta:
        verbose_name_plural = "Quantidade de telas"

    def __str__(self):
        return "{} tela(s)".format(self.telas)


# Planos de mensalidades ofertados
class Plano(models.Model):
    MENSAL = "Mensal"
    TRIMESTRAL = "Trimestral"
    SEMESTRAL = "Semestral"
    ANUAL = "Anual"

    CHOICES = ((MENSAL, MENSAL), (TRIMESTRAL, TRIMESTRAL), (SEMESTRAL, SEMESTRAL), (ANUAL, ANUAL))

    nome = models.CharField(
        "Nome do plano", max_length=255, choices=CHOICES, default=MENSAL
    )
    valor = models.DecimalField("Valor", max_digits=5, decimal_places=2)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return "{} - {}".format(self.nome, self.valor)


# Cadastro do cliente
class Cliente(models.Model):
    servidor = models.ForeignKey(Servidor, on_delete=models.CASCADE)
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE, default=None)
    sistema = models.ForeignKey(Aplicativo, on_delete=models.CASCADE, default=None)
    nome = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True, null=True)
    telefone = models.CharField(max_length=16)
    uf = models.CharField(max_length=2, blank=True, null=True)
    indicado_por = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True
    )
    data_pagamento = models.IntegerField(
        "Data de pagamento", default=None, blank=True, null=True
    )
    forma_pgto = models.ForeignKey(
        Tipos_pgto,
        on_delete=models.CASCADE,
        default=1,
        verbose_name="Forma de pagamento",
    )
    plano = models.ForeignKey(Plano, on_delete=models.CASCADE, default=1)
    telas = models.ForeignKey(Qtd_tela, on_delete=models.CASCADE, default=1)
    data_adesao = models.DateField(
        "Data de adesão", default=timezone.now
    )
    data_cancelamento = models.DateField("Data de cancelamento", blank=True, null=True)
    ultimo_pagamento = models.DateField(
        "Último pagamento realizado", blank=True, null=True
    )
    cancelado = models.BooleanField("Cancelado", default=False)
    nao_enviar_msgs = models.BooleanField("Não enviar", default=False)
    enviado_oferta_promo = models.BooleanField("Oferta PROMO", default=False)
    notas = models.TextField("Notas", blank=True, null=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def save(self, *args, **kwargs):
        if self.data_adesao and self.data_pagamento == None:
            dia = self.data_adesao.day
            self.data_pagamento = dia

        self.formatar_telefone()

        super().save(*args, **kwargs)

    def formatar_telefone(self):
        self.telefone = re.sub(r'\D+', '', self.telefone)  # Remove caracteres especiais

        if self.telefone.startswith('55'):
            self.telefone = self.telefone[2:]  # Remove o prefixo '55' do início do número

        if len(self.telefone) <= 11:
            ddd = self.telefone[:2]  # Obtém os 2 primeiros dígitos após remover o DDI
            numero = self.telefone[2:]  # Obtém o restante do número

            if len(numero) == 9 and numero.startswith('9'):
                numero = numero[1:]  # remove o dígito '9' do início caso possua 9 dígitos

            if numero.startswith(('6', '7', '8', '9')):  # Verifica se o número começa com algum valor entre '6' e '9'
                if int(ddd) > 30:
                    self.telefone = f'({ddd}) {numero[:4]}-{numero[4:]}'  # Formato (DD) DDDD-DDDD
                else:
                    self.telefone = f'({ddd}) 9{numero[:4]}-{numero[4:]}'  # Formato (DD) DDDDD-DDDD
            else:
                if int(ddd) > 30:
                    self.telefone = f'({ddd}) {numero[:4]}-{numero[4:]}'  # Formato (DD) DDDD-DDDD
                else:
                    self.telefone = f'({ddd}) 9{numero[:4]}-{numero[4:]}'  # Formato (DD) DDDDD-DDDD

    def __str__(self):
        return self.nome


# Cadastro das mensalidades de cada cliente
class Mensalidade(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    valor = models.DecimalField("Valor", max_digits=5, decimal_places=2, default=None)
    dt_vencimento = models.DateField(
        "Data do vencimento",
        default=timezone.localtime().date() + timezone.timedelta(days=30),
    )
    dt_pagamento = models.DateField(
        "Data do pagamento", default=None, null=True, blank=True
    )
    dt_cancelamento = models.DateField(
        "Data do cancelamento", default=None, null=True, blank=True
    )
    dt_notif_wpp1 = models.DateField(
        "Data envio notificação PROMO", default=None, null=True, blank=True
    )
    pgto = models.BooleanField("Pago", default=False)
    cancelado = models.BooleanField(default=False)
    notificacao_wpp1 = models.BooleanField(
        "Notificação PROMO", default=False
    )
    recebeu_pix_indicacao = models.BooleanField(
        "PIX R$50", default=False
    )
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return str(
            "[{}] {} - {}".format(
                self.dt_vencimento.strftime("%d/%m/%Y"), self.valor, self.cliente
            )
        )


class PlanoIndicacao(models.Model):
    TIPOS_PLANO = [
        ("desconto", "Desconto na mensalidade"),
        ("dinheiro", "Valor em dinheiro"),
    ]
    nome = models.CharField(max_length=255, default="Desconto na mensalidade")
    tipo_plano = models.CharField(max_length=10, choices=TIPOS_PLANO)
    valor = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(0)]
    )
    ativo = models.BooleanField(default=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        verbose_name_plural = "Planos de Indicação"

    def __str__(self):
        return self.nome


class ContaDoAplicativo(models.Model):
    cliente = models.ForeignKey(
        Cliente, on_delete=models.CASCADE, related_name="conta_aplicativo"
    )
    app = models.ForeignKey(
        Aplicativo,
        on_delete=models.CASCADE,
        related_name="aplicativos",
        verbose_name="Aplicativo",
    )
    device_id = models.CharField("ID", max_length=255, blank=True, null=True)
    email = models.EmailField("E-mail", max_length=255, blank=True, null=True)
    device_key = models.CharField("Senha", max_length=255, blank=True, null=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    verificado = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if "xcloud" in self.app.nome.lower():
            # Não altera o device_id
            pass
        else:
            # Verifica se o valor está no formato desejado
            if self.device_id:
                if self.device_id[0] == ":":
                    # Remove o caractere ':' do começo se houver
                    self.device_id = self.device_id[1:]

                if self.device_id[-1] == ":":
                    # Remove o caractere ':' do final se houver
                    self.device_id = self.device_id[:-1]

                # Adiciona ':' a cada 2 caracteres se não houver ":"
                if ":" not in self.device_id[2:-2]:
                    self.device_id = ":".join(
                        [self.device_id[i : i + 2] for i in range(0, len(self.device_id), 2)]
                    )
        super(ContaDoAplicativo, self).save(*args, **kwargs)

    class Meta:
        verbose_name = "Conta do aplicativo"
        verbose_name_plural = "Contas dos aplicativos"

    def __str__(self):
        return super().__str__()


class SessaoWpp(models.Model):
    usuario = models.CharField(max_length=255)
    token = models.CharField(max_length=255)
    dt_inicio = models.DateTimeField()

    class Meta:
        verbose_name = "Sessão do WhatsApp"
        verbose_name_plural = "Sessões do WhatsApp"

    def __str__(self) -> str:
        return self.usuario
    

class SecretTokenAPI(models.Model):
    token = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Secret Token API"
        verbose_name_plural = "Secrets Tokens API"

    def __str__(self) -> str:
        return self.token
    

class DadosBancarios(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    beneficiario = models.CharField(max_length=255)
    instituicao = models.CharField(max_length=255)
    tipo_chave = models.CharField(max_length=255)
    chave = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = "Dados Bancários"

    def __str__(self) -> str:
        return '{} {}'.format(self.usuario.first_name, self.usuario.last_name)
    

class HorarioEnvios(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, unique=True)
    horario = models.TimeField(null=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Horário de Envio"
        verbose_name_plural = "Horarios de Envio"

    def __str__(self) -> str:
        return self.usuario


class MensagemEnviadaWpp(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    telefone = models.CharField(max_length=20)
    data_envio = models.DateField(auto_now_add=True)

    def __str__(self) -> str:
        return self.telefone