from django.db import models
from django.utils import timezone


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

    nome = models.CharField(max_length=255, choices=CHOICES, unique=True)
    logotipo = models.CharField(max_length=255, unique=True, null=True, blank=True)

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

    nome = models.CharField(max_length=255, choices=CHOICES, default=PIX, unique=True)

    class Meta:
        verbose_name = "Tipo de pagamento"
        verbose_name_plural = "Tipos de pagamentos"

    def __str__(self):
        return self.nome


# Dispositivos utilizados pelos clientes (TVs, TVBOX, celulares, etc.)
class Dispositivo(models.Model):
    nome = models.CharField(max_length=255, unique=True)
    modelo = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.nome


class Aplicativo(models.Model):
    nome = models.CharField(max_length=255, unique=True)

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
    SEMESTRAL = "Semestral"
    ANUAL = "Anual"

    CHOICES = ((MENSAL, MENSAL), (SEMESTRAL, SEMESTRAL), (ANUAL, ANUAL))

    nome = models.CharField(
        "Nome do plano", max_length=255, choices=CHOICES, default=MENSAL
    )
    valor = models.DecimalField("Valor", max_digits=5, decimal_places=2)

    def __str__(self):
        return "{} - {}".format(self.nome, self.valor)


# Cadastro do cliente
class Cliente(models.Model):
    servidor = models.ForeignKey(Servidor, on_delete=models.CASCADE)
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE, default=None)
    sistema = models.ForeignKey(Aplicativo, on_delete=models.CASCADE, default=None)
    nome = models.CharField(max_length=255)
    telefone = models.CharField(max_length=15, unique=True)
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
        "Data de adesão", default=timezone.localtime().date()
    )
    data_cancelamento = models.DateField("Data de cancelamento", blank=True, null=True)
    ultimo_pagamento = models.DateField(
        "Último pagamento realizado", blank=True, null=True
    )
    cancelado = models.BooleanField("Cancelado", default=False)
    notas = models.TextField("Notas", blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.data_adesao and self.data_pagamento == None:
            dia = self.data_adesao.day
            self.data_pagamento = definir_dia_pagamento(dia)

        self.definir_data_cancelamento()

        self.formatar_telefone()

        super().save(*args, **kwargs)

    def definir_data_cancelamento(self):
        if self.pk:
            old_value = Cliente.objects.get(pk=self.pk).cancelado
            if old_value == False and self.cancelado == True:
                # Se o cliente foi cancelado, atualiza todas as mensalidades relacionadas
                mensalidades = self.mensalidade_set.all()
                for mensalidade in mensalidades:
                    mensalidade.cancelado = True
                    mensalidade.dt_cancelamento = timezone.localtime().date()
                    mensalidade.save()

    def formatar_telefone(self):
        if not self.telefone.startswith("55"):
            self.telefone = "55" + self.telefone

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
    pgto = models.BooleanField("Pago", default=False)
    cancelado = models.BooleanField(default=False)

    def __str__(self):
        return str(
            "[{}] {} - {}".format(
                self.dt_vencimento.strftime("%d/%m/%Y"), self.valor, self.cliente
            )
        )


from django.core.validators import MinValueValidator


class PlanoIndicacao(models.Model):
    TIPOS_PLANO = [
        ("desconto", "Desconto na mensalidade"),
        ("dinheiro", "Valor em dinheiro"),
    ]
    nome = models.CharField(max_length=255, default="Desconto na mensalidade")
    tipo_plano = models.CharField(max_length=10, choices=TIPOS_PLANO, unique=True)
    valor = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(0)]
    )
    ativo = models.BooleanField(default=True)

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

    def save(self, *args, **kwargs):
        # Verifica se o valor está no formato desejado
        if self.device_id:
            if len(self.device_id) % 2 != 0:
                # Adiciona um caractere no final se o tamanho for ímpar
                if not self.device_id:
                    self.device_id = "X"
                else:
                    self.device_id += "X"
            if self.device_id[0] == ":":
                # Remove o caractere ':' do começo se houver
                self.device_id = self.device_id[1:]
            if self.device_id[-1] == ":":
                # Remove o caractere ':' do final se houver
                self.device_id = self.device_id[:-1]
            # Adiciona ':' a cada 2 caracteres
            self.device_id = ":".join(
                [self.device_id[i : i + 2] for i in range(0, len(self.device_id), 2)]
            )
        super(ContaDoAplicativo, self).save(*args, **kwargs)

    class Meta:
        verbose_name = "Conta do aplicativo"
        verbose_name_plural = "Contas dos aplicativos"

    def __str__(self):
        return super().__str__()
