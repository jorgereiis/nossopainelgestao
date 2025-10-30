"""
Módulo de definição das models principais da aplicação.
Inclui entidades como Cliente, Plano, Mensalidade, Aplicativo, Sessão WhatsApp, entre outras.
"""

from datetime import date, timedelta
import re
import os
import uuid

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.db import models
from django.utils import timezone

# Mapeamento de DDDs nacionais para a unidade federativa correspondente.
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


def servidor_upload_path(instance, filename):
    """
    Gera caminho de upload com UUID para imagens de servidor.

    SEGURANÇA: UUID previne information disclosure via filenames.
    Preserva extensão do arquivo para correto MIME type.

    Formato: servidores/<uuid>.<ext>
    Exemplo: servidores/c3d4e5f6-a7b8-9012-cdef-123456789012.png
    """
    ext = filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('servidores', filename)


class Servidor(models.Model):
    """Representa os servidores associados aos clientes."""
    CLUB = "CLUB"
    PLAY = "PLAY"
    PLAYON = "PlayON"
    ALPHA = "ALPHA"
    SEVEN = "SEVEN"
    FIVE = "FIVE"
    GF = "GF"
    WAREZ = "WAREZ"

    CHOICES = (
        (CLUB, CLUB),
        (PLAY, PLAY),
        (PLAYON, PLAYON),
        (ALPHA, ALPHA),
        (SEVEN, SEVEN),
        (FIVE, FIVE),
        (GF, GF),
        (WAREZ, WAREZ)
    )

    nome = models.CharField(max_length=255, choices=CHOICES)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    imagem_admin = models.ImageField(
        upload_to=servidor_upload_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'gif', 'webp'])],
        help_text='Imagem padrão do servidor (adminuser). Tamanho máximo: 5MB. Formatos: JPG, PNG, GIF, WEBP'
    )

    class Meta:
        verbose_name_plural = "Servidores"

    def get_imagem_url(self, usuario_atual=None):
        """
        Retorna a URL da imagem do servidor com fallback hierárquico:
        1. Imagem específica do usuário atual (ServidorImagem)
        2. Imagem do adminuser (ServidorImagem - usuário com is_superuser=True)
        3. Imagem padrão do servidor (campo imagem_admin)
        4. Imagem genérica estática baseada no nome do servidor

        Args:
            usuario_atual: User object do usuário atual (opcional)

        Returns:
            str: URL da imagem do servidor
        """
        from django.conf import settings

        # 1. Tentar imagem do usuário atual
        if usuario_atual:
            try:
                imagem_usuario = ServidorImagem.objects.filter(
                    servidor=self,
                    usuario=usuario_atual
                ).first()
                if imagem_usuario and imagem_usuario.imagem:
                    return imagem_usuario.imagem.url
            except:
                pass

        # 2. Tentar imagem do adminuser
        try:
            adminuser = User.objects.filter(is_superuser=True).first()
            if adminuser:
                imagem_admin = ServidorImagem.objects.filter(
                    servidor=self,
                    usuario=adminuser
                ).first()
                if imagem_admin and imagem_admin.imagem:
                    return imagem_admin.imagem.url
        except:
            pass

        # 3. Tentar imagem_admin do modelo Servidor
        if self.imagem_admin:
            return self.imagem_admin.url

        # 4. Fallback para imagem estática genérica
        nome_lower = self.nome.lower()
        return f'{settings.STATIC_URL}assets/images/logo-apps/{nome_lower}.png'

    def __str__(self):
        return self.nome


class ServidorImagem(models.Model):
    """
    Armazena imagens personalizadas de servidores por usuário.

    Permite que cada usuário tenha sua própria imagem para um servidor específico,
    sobrescrevendo a imagem padrão definida no modelo Servidor.
    """
    servidor = models.ForeignKey(Servidor, on_delete=models.CASCADE, related_name='imagens_customizadas')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    imagem = models.ImageField(
        upload_to=servidor_upload_path,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'gif', 'webp'])],
        help_text='Imagem personalizada do servidor. Tamanho máximo: 5MB. Formatos: JPG, PNG, GIF, WEBP'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Imagem de Servidor"
        verbose_name_plural = "Imagens de Servidores"
        unique_together = ('servidor', 'usuario')
        indexes = [
            models.Index(fields=['servidor', 'usuario']),
        ]

    def save(self, *args, **kwargs):
        """Otimiza a imagem antes de salvar."""
        super().save(*args, **kwargs)

        if self.imagem and os.path.isfile(self.imagem.path):
            try:
                from PIL import Image
                img = Image.open(self.imagem.path)

                # Redimensionar se muito grande
                if img.height > 500 or img.width > 500:
                    output_size = (500, 500)
                    img.thumbnail(output_size, Image.Resampling.LANCZOS)
                    img.save(self.imagem.path, quality=85, optimize=True)
            except ImportError:
                pass

    def __str__(self):
        return f"{self.servidor.nome} - {self.usuario.username}"


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
    BIMESTRAL = "Bimestral"
    TRIMESTRAL = "Trimestral"
    SEMESTRAL = "Semestral"
    ANUAL = "Anual"

    CHOICES = ((MENSAL, MENSAL), (BIMESTRAL, BIMESTRAL), (TRIMESTRAL, TRIMESTRAL), (SEMESTRAL, SEMESTRAL), (ANUAL, ANUAL))

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
        """Garante vencimento inicial e sincroniza a UF a partir do telefone."""
        if self.data_adesao and self.data_vencimento is None:
            self.data_vencimento = self.data_adesao

        self.definir_uf()
        super().save(*args, **kwargs)

    def definir_uf(self):
        """Define a unidade federativa (UF) com base no DDD do telefone apenas se for nacional."""
        if not self.telefone.startswith('+55') or len(self.telefone) < 5:
            self.uf = None
            return

        ddd = self.telefone[3:5]
        self.uf = DDD_UF_MAP.get(ddd)

    def __str__(self):
        return self.nome


class OfertaPromocionalEnviada(models.Model):
    """
    Rastreia o histórico de ofertas promocionais enviadas para clientes cancelados.

    Garante que cada cliente receba no máximo 3 ofertas em toda a vida:
    - Oferta 1: 60 dias após cancelamento
    - Oferta 2: 240 dias após cancelamento (8 meses)
    - Oferta 3: 420 dias após cancelamento (14 meses)

    A contagem de dias é sempre a partir da data_cancelamento atual do cliente,
    permitindo que clientes reativados recebam ofertas subsequentes em futuros cancelamentos.
    """
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='ofertas_enviadas',
        verbose_name="Cliente"
    )
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    data_envio = models.DateTimeField("Data de Envio", auto_now_add=True)
    numero_oferta = models.IntegerField(
        "Número da Oferta",
        choices=[(1, "Primeira Oferta"), (2, "Segunda Oferta"), (3, "Terceira Oferta")],
        help_text="Sequência da oferta (1, 2 ou 3)"
    )
    dias_apos_cancelamento = models.IntegerField(
        "Dias Após Cancelamento",
        help_text="Quantidade de dias após o cancelamento (60, 240 ou 420)"
    )
    data_cancelamento_ref = models.DateField(
        "Data de Cancelamento (Referência)",
        help_text="Data de cancelamento do cliente no momento do envio"
    )
    mensagem_enviada = models.TextField("Mensagem Enviada", blank=True)

    class Meta:
        verbose_name = "Oferta Promocional Enviada"
        verbose_name_plural = "Ofertas Promocionais Enviadas"
        ordering = ['-data_envio']
        indexes = [
            models.Index(fields=['cliente', '-data_envio'], name='oferta_cliente_idx'),
            models.Index(fields=['usuario', '-data_envio'], name='oferta_usuario_idx'),
            models.Index(fields=['numero_oferta'], name='oferta_numero_idx'),
        ]

    def __str__(self):
        return f"Oferta {self.numero_oferta} - {self.cliente.nome} ({self.data_envio.strftime('%d/%m/%Y')})"


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


class ClientePlanoHistorico(models.Model):
    """Mantém o histórico do plano/valor por cliente para cálculo de patrimônio.

    Cada registro representa um período contínuo em que o cliente esteve com um
    determinado plano e valor. Ao mudar de plano, cancelar ou reativar, abrimos
    ou encerramos registros para manter a linha do tempo sem sobreposição.
    """

    MOTIVO_CREATE = "create"
    MOTIVO_PLAN_CHANGE = "plan_change"
    MOTIVO_CANCEL = "cancel"
    MOTIVO_REACTIVATE = "reactivate"

    MOTIVO_CHOICES = [
        (MOTIVO_CREATE, "Criação"),
        (MOTIVO_PLAN_CHANGE, "Troca de plano"),
        (MOTIVO_CANCEL, "Cancelamento"),
        (MOTIVO_REACTIVATE, "Reativação"),
    ]

    cliente = models.ForeignKey('Cliente', on_delete=models.CASCADE, related_name='historico_planos')
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    plano = models.ForeignKey('Plano', on_delete=models.SET_NULL, null=True, blank=True)
    plano_nome = models.CharField(max_length=255)
    telas = models.IntegerField(default=1)
    valor_plano = models.DecimalField(max_digits=7, decimal_places=2)
    inicio = models.DateField()
    fim = models.DateField(null=True, blank=True)
    motivo = models.CharField(max_length=32, choices=MOTIVO_CHOICES, default=MOTIVO_CREATE)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Histórico de Plano do Cliente"
        verbose_name_plural = "Históricos de Plano dos Clientes"
        ordering = ["cliente", "-inicio", "-criado_em"]
        indexes = [
            models.Index(fields=["usuario", "inicio"], name="cadastros_c_usuario_07f805_idx"),
            models.Index(fields=["cliente", "inicio"], name="cadastros_c_cliente_9a7e3f_idx"),
            models.Index(fields=["cliente", "fim"], name="cadastros_c_cliente_2a7d1b_idx"),
        ]

    def __str__(self):
        return f"{self.cliente} - {self.plano_nome} ({self.valor_plano}) {self.inicio} -> {self.fim or '...'}"


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
        indexes = [
            # Índice composto para queries de envios agendados (melhora performance do select_for_update)
            models.Index(fields=['status', 'ativo', 'horario', 'ultimo_envio'], name='horarioenvios_agendados_idx'),
            # Índice para filtros por usuário e tipo de envio
            models.Index(fields=['usuario', 'tipo_envio'], name='horarioenvios_usuario_tipo_idx'),
        ]

    def __str__(self):
        return self.get_nome_display()

    @property
    def descricao(self):
        """Retorna a descrição exibida no painel para o tipo de envio."""
        return self.DESCRICOES.get(self.tipo_envio, "")

    @property
    def exemplo(self):
        """Apresenta um exemplo do fluxo disparado para o tipo."""
        return self.EXEMPLOS.get(self.tipo_envio, "")

    
class PlanoIndicacao(models.Model):
    """Representa um plano de indicação que oferece desconto ou valor em dinheiro."""
    TITULO = [
        ("desconto", "Desconto por Indicação"),
        ("dinheiro", "Bônus por Indicações"),
        ("anuidade", "Bônus por Anuidade"),
        ("desconto_progressivo", "Desconto Progressivo Por Indicação"),
    ]
    DESCRICOES = {
        "desconto": "Permite que o sistema aplique desconto à mensalidade do cliente que fez indicação de um novo cliente no mês.",
        "dinheiro": "Permite que o sistema bonifique o cliente com um valor a receber após realizar indicações de pelo menos 2 novos clientes no mesmo mês.",
        "anuidade": "Permite que o sistema aplique desconto à mensalidade dos clientes que completarem 12 meses consecutivos como clientes.",
        "desconto_progressivo": "Aplica desconto permanente e cumulativo na mensalidade do cliente indicador enquanto seus indicados permanecerem ativos. O desconto é aplicado automaticamente em todas as mensalidades futuras.",
    }
    EXEMPLOS = {
        "desconto": "Indicou 1 novo cliente neste mês, terá R$ 20.00 de desconto no próximo pagamento.",
        "dinheiro": "Indicou 2 novos clientes no mês de Janeiro, o sistema enviará uma mensagem por WhatsApp informando ao cliente que ele tem um valor a receber como bonificação e agradecimento pelas indicações feitas.",
        "anuidade": "Aderiu em Jan/23 e terá desconto do valor definido na mensalidade de Jan/24, desde que não tenha passado ao menos 30 dias com uma das suas mensalidades CANCELADAS. Uma mensagem será enviada por WhatsApp para informar o cliente sobre a bonificação.",
        "desconto_progressivo": "Cliente indicou 3 novos clientes ativos. Com desconto de R$ 2.00 por indicação e limite de 5 indicações, terá R$ 6.00 de desconto permanente em todas as suas mensalidades. Se um indicado cancelar, o desconto será reduzido para R$ 4.00.",
    }
    nome = models.CharField(max_length=255, choices=TITULO)
    tipo_plano = models.CharField(max_length=255, choices=TITULO)
    valor = models.DecimalField('Valor para desconto ou bonificação', max_digits=6, decimal_places=2, validators=[MinValueValidator(0)], default=0)
    valor_minimo_mensalidade = models.DecimalField('Valor mínimo a ser mantido na mensalidade', max_digits=6, decimal_places=2, validators=[MinValueValidator(0)], default=0)
    limite_indicacoes = models.IntegerField('Limite máximo de indicações com desconto', validators=[MinValueValidator(0)], default=0, help_text="Apenas para Desconto Progressivo. Define quantas indicações contam para desconto (0 = ilimitado).")
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
        """Sintetiza a finalidade do plano de indicação escolhido."""
        return self.DESCRICOES.get(self.tipo_plano, "")

    @property
    def exemplo(self):
        """Fornece um cenário ilustrativo da bonificação."""
        return self.EXEMPLOS.get(self.tipo_plano, "")


class DescontoProgressivoIndicacao(models.Model):
    """
    Rastreia descontos progressivos por indicação.

    Cada registro representa um desconto individual gerado por uma indicação específica.
    O desconto permanece ativo enquanto o cliente indicado estiver ativo no sistema.
    """
    cliente_indicador = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="descontos_progressivos_recebidos",
        verbose_name="Cliente Indicador"
    )
    cliente_indicado = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="desconto_progressivo_gerado",
        verbose_name="Cliente Indicado"
    )
    plano_indicacao = models.ForeignKey(
        'PlanoIndicacao',
        on_delete=models.CASCADE,
        verbose_name="Plano de Indicação"
    )
    valor_desconto = models.DecimalField(
        "Valor do Desconto",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    data_inicio = models.DateField("Data de Início", default=date.today)
    data_fim = models.DateField("Data de Fim", null=True, blank=True)
    ativo = models.BooleanField("Ativo", default=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Desconto Progressivo por Indicação"
        verbose_name_plural = "Descontos Progressivos por Indicação"
        ordering = ["-data_inicio", "-criado_em"]
        indexes = [
            models.Index(fields=["cliente_indicador", "ativo"], name="cadastros_d_cliente_idx"),
            models.Index(fields=["cliente_indicado", "ativo"], name="cadastros_d_indicado_idx"),
            models.Index(fields=["usuario", "ativo"], name="cadastros_d_usuario_idx"),
        ]

    def __str__(self):
        status = "✓" if self.ativo else "✗"
        return f"{status} {self.cliente_indicador.nome} ← {self.cliente_indicado.nome} (R$ {self.valor_desconto})"


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
        """Normaliza o identificador do dispositivo para formato MAC quando necessário."""
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
        """Normaliza o telefone antes de persistir os dados bancários."""
        self.formatar_telefone()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Dados Bancários"

    def __str__(self) -> str:
        return f'{self.usuario.first_name} {self.usuario.last_name}'


def avatar_upload_path(instance, filename):
    """
    Gera caminho de upload com UUID para avatares.

    SEGURANÇA: UUID previne information disclosure via filenames.
    Preserva extensão do arquivo para correto MIME type.

    Formato: avatars/<uuid>.<ext>
    Exemplo: avatars/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg
    """
    ext = filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('avatars', filename)


def cover_upload_path(instance, filename):
    """
    Gera caminho de upload com UUID para imagens de capa.

    SEGURANÇA: UUID previne information disclosure via filenames.
    Preserva extensão do arquivo para correto MIME type.

    Formato: covers/<uuid>.<ext>
    Exemplo: covers/b2c3d4e5-f6a7-8901-bcde-f12345678901.jpg
    """
    ext = filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('covers', filename)


class UserProfile(models.Model):
    """Estende o modelo User com informações adicionais de perfil (avatar, bio, etc)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(
        upload_to=avatar_upload_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'gif', 'webp'])],
        help_text='Tamanho máximo: 5MB. Formatos: JPG, PNG, GIF, WEBP'
    )
    bio = models.TextField(max_length=500, blank=True, null=True)
    cover_image = models.ImageField(
        upload_to=cover_upload_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])]
    )

    # Preferências de Notificação
    email_on_profile_change = models.BooleanField(default=True, verbose_name='Notificar por email alterações no perfil')
    email_on_password_change = models.BooleanField(default=True, verbose_name='Notificar por email alterações de senha')
    email_on_login = models.BooleanField(default=False, verbose_name='Notificar por email em novos logins')

    # Preferências de Tema
    THEME_LIGHT = 'light'
    THEME_DARK = 'dark'
    THEME_AUTO = 'auto'
    THEME_CHOICES = [
        (THEME_LIGHT, 'Claro'),
        (THEME_DARK, 'Escuro'),
        (THEME_AUTO, 'Automático'),
    ]
    theme_preference = models.CharField(max_length=10, choices=THEME_CHOICES, default=THEME_LIGHT, verbose_name='Tema preferido')

    # Configurações de Privacidade
    profile_public = models.BooleanField(default=False, verbose_name='Perfil público')
    show_email = models.BooleanField(default=False, verbose_name='Mostrar email publicamente')
    show_phone = models.BooleanField(default=False, verbose_name='Mostrar telefone publicamente')
    show_statistics = models.BooleanField(default=True, verbose_name='Mostrar estatísticas')

    # Autenticação em Dois Fatores
    two_factor_enabled = models.BooleanField(default=False, verbose_name='2FA ativado')
    two_factor_secret = models.CharField(max_length=32, blank=True, null=True, verbose_name='Chave secreta 2FA')
    two_factor_backup_codes = models.JSONField(blank=True, null=True, verbose_name='Códigos de backup 2FA')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Otimiza a imagem antes de salvar."""
        super().save(*args, **kwargs)

        if self.avatar and os.path.isfile(self.avatar.path):
            try:
                from PIL import Image
                img = Image.open(self.avatar.path)

                # Redimensionar se muito grande
                if img.height > 500 or img.width > 500:
                    output_size = (500, 500)
                    img.thumbnail(output_size, Image.Resampling.LANCZOS)
                    img.save(self.avatar.path, quality=85, optimize=True)
            except ImportError:
                pass

    def get_avatar_url(self):
        """Retorna URL do avatar ou imagem padrão."""
        if self.avatar:
            return self.avatar.url
        return '/static/assets/images/avatar/default-avatar.svg'

    def delete_old_avatar(self):
        """Remove avatar antigo do sistema de arquivos."""
        if self.avatar and os.path.isfile(self.avatar.path):
            try:
                os.remove(self.avatar.path)
            except OSError:
                pass

    def generate_2fa_secret(self):
        """Gera uma nova chave secreta para 2FA."""
        import pyotp
        self.two_factor_secret = pyotp.random_base32()
        return self.two_factor_secret

    def get_2fa_qr_code(self):
        """Retorna a URL para gerar o QR Code do 2FA."""
        if not self.two_factor_secret:
            self.generate_2fa_secret()
        import pyotp
        totp = pyotp.TOTP(self.two_factor_secret)
        return totp.provisioning_uri(
            name=self.user.email,
            issuer_name='Nosso Painel'
        )

    def verify_2fa_code(self, code):
        """Verifica se o código 2FA fornecido é válido.

        SEGURANÇA: Proteção contra timing attacks com delay fixo.
        """
        import time

        # Executar validação
        if not self.two_factor_enabled or not self.two_factor_secret:
            time.sleep(0.1)
            return False

        import pyotp
        totp = pyotp.TOTP(self.two_factor_secret)
        result = totp.verify(code, valid_window=1)

        # Delay fixo de 100ms para normalizar tempo de resposta
        # Previne que atacante descubra diferenças entre TOTP e backup code
        time.sleep(0.1)

        return result

    def generate_backup_codes(self):
        """Gera códigos de backup para 2FA e retorna códigos em plaintext.

        SEGURANÇA: Os códigos são hasheados antes de serem salvos no banco.
        Os códigos em plaintext são retornados APENAS uma vez para o usuário salvar.
        """
        import secrets
        from django.contrib.auth.hashers import make_password

        # Gerar códigos em plaintext
        codes = [secrets.token_hex(4).upper() for _ in range(10)]

        # Armazenar HASHES, não plaintext
        self.two_factor_backup_codes = [make_password(code) for code in codes]

        # Retornar codes em plaintext APENAS uma vez
        return codes

    def use_backup_code(self, code):
        """Usa um código de backup e o remove da lista.

        SEGURANÇA: Verifica o código contra hashes usando constant-time comparison.
        Proteção contra timing attacks com delay fixo.
        """
        import time

        if not self.two_factor_backup_codes:
            time.sleep(0.1)
            return False

        from django.contrib.auth.hashers import check_password

        code = code.upper().strip()

        # Verificar contra hashes usando constant-time comparison
        # check_password já usa constant-time internamente
        found_code = None
        for hashed_code in self.two_factor_backup_codes:
            if check_password(code, hashed_code):
                found_code = hashed_code
                break

        if found_code:
            # Código válido encontrado, remover do banco
            self.two_factor_backup_codes.remove(found_code)
            self.save()
            time.sleep(0.1)
            return True

        time.sleep(0.1)
        return False

    class Meta:
        verbose_name = "Perfil de Usuário"
        verbose_name_plural = "Perfis de Usuários"

    def __str__(self):
        return f'Perfil de {self.user.username}'


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


class NotificationRead(models.Model):
    """Registra notificações de mensalidade marcadas como lidas."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications_read")
    mensalidade = models.ForeignKey(Mensalidade, on_delete=models.CASCADE, related_name="notifications_read")
    marcado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notificação lida"
        verbose_name_plural = "Notificações lidas"
        unique_together = (("usuario", "mensalidade"),)

    def __str__(self):
        return f"{self.usuario} - {self.mensalidade_id}"


class UserActionLog(models.Model):
    """Armazena o histórico de ações feitas manualmente pelos usuários no sistema."""

    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_IMPORT = "import"
    ACTION_CANCEL = "cancel"
    ACTION_REACTIVATE = "reactivate"
    ACTION_PAYMENT = "payment"
    ACTION_OTHER = "other"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Criação"),
        (ACTION_UPDATE, "Atualização"),
        (ACTION_DELETE, "Exclusão"),
        (ACTION_IMPORT, "Importação"),
        (ACTION_CANCEL, "Cancelamento"),
        (ACTION_REACTIVATE, "Reativação"),
        (ACTION_PAYMENT, "Pagamento"),
        (ACTION_OTHER, "Ação"),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="action_logs")
    acao = models.CharField(max_length=32, choices=ACTION_CHOICES, default=ACTION_OTHER)
    entidade = models.CharField(max_length=100, blank=True)
    objeto_id = models.CharField(max_length=64, blank=True)
    objeto_repr = models.CharField(max_length=255, blank=True)
    mensagem = models.TextField(blank=True)
    extras = models.JSONField(blank=True, null=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    request_path = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de ação de usuário"
        verbose_name_plural = "Logs de ações de usuários"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["usuario", "-criado_em"], name="cadastros_u_usuario_966dcb_idx"),
            models.Index(fields=["entidade", "acao"], name="cadastros_u_entidad_4d2aba_idx"),
        ]

    def __str__(self):
        entidade = self.entidade or "Objeto"
        return f"{self.usuario} - {entidade} - {self.get_acao_display()} em {self.criado_em:%d/%m/%Y %H:%M}"


class LoginLog(models.Model):
    """
    Registra todos os logins (bem-sucedidos e falhados) dos usuários no sistema.

    Útil para:
    - Auditoria de acessos
    - Detecção de acessos suspeitos
    - Análise de padrões de uso
    - Compliance com LGPD/GDPR
    - Identificação de tentativas de brute force
    """

    # Tipos de método de login
    METHOD_PASSWORD = 'password'
    METHOD_2FA = '2fa'
    METHOD_BACKUP_CODE = 'backup_code'

    METHOD_CHOICES = [
        (METHOD_PASSWORD, 'Senha'),
        (METHOD_2FA, '2FA'),
        (METHOD_BACKUP_CODE, 'Código de Backup'),
    ]

    # Campos principais
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='login_logs',
        null=True,
        blank=True,
        help_text='Usuário que tentou fazer login (null se usuário não encontrado)'
    )
    username_tentado = models.CharField(
        max_length=150,
        blank=True,
        help_text='Username que foi tentado no login (útil para logins falhados)'
    )

    # Informações de rede
    ip = models.GenericIPAddressField(
        protocol='IPv4',
        null=True,
        blank=True,
        help_text='Endereço IPv4 do cliente'
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        help_text='User-Agent do navegador/dispositivo'
    )

    # Detalhes do login
    login_method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default=METHOD_PASSWORD,
        help_text='Método usado para fazer login'
    )
    success = models.BooleanField(
        default=True,
        help_text='Se o login foi bem-sucedido'
    )
    failure_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text='Motivo da falha (se success=False)'
    )

    # Informações geográficas
    location_country = models.CharField(max_length=100, blank=True)
    location_city = models.CharField(max_length=100, blank=True)

    # Metadados
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Log de Login'
        verbose_name_plural = 'Logs de Login'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['usuario', '-created_at'], name='loginlog_user_created_idx'),
            models.Index(fields=['-created_at'], name='loginlog_created_idx'),
            models.Index(fields=['success', '-created_at'], name='loginlog_success_idx'),
            models.Index(fields=['ip', '-created_at'], name='loginlog_ip_idx'),
        ]

    def __str__(self):
        status = '✓' if self.success else '✗'
        user_display = self.usuario.username if self.usuario else self.username_tentado
        return f"{status} {user_display} - {self.get_login_method_display()} - {self.created_at:%d/%m/%Y %H:%M}"

    def get_browser_info(self):
        """Extrai informações do navegador do user_agent."""
        if not self.user_agent:
            return {'browser': 'Desconhecido', 'os': 'Desconhecido', 'device': 'Desconhecido'}

        import re
        ua = self.user_agent.lower()

        # Detectar navegador
        if 'firefox' in ua:
            browser = 'Firefox'
        elif 'chrome' in ua and 'edg' not in ua:
            browser = 'Chrome'
        elif 'edg' in ua:
            browser = 'Edge'
        elif 'safari' in ua and 'chrome' not in ua:
            browser = 'Safari'
        elif 'opera' in ua or 'opr' in ua:
            browser = 'Opera'
        else:
            browser = 'Outro'

        # Detectar OS
        if 'windows' in ua:
            os_name = 'Windows'
        elif 'mac' in ua and 'iphone' not in ua and 'ipad' not in ua:
            os_name = 'macOS'
        elif 'linux' in ua:
            os_name = 'Linux'
        elif 'android' in ua:
            os_name = 'Android'
        elif 'iphone' in ua or 'ipad' in ua:
            os_name = 'iOS'
        else:
            os_name = 'Outro'

        # Detectar tipo de dispositivo
        if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
            device = 'Mobile'
        elif 'tablet' in ua or 'ipad' in ua:
            device = 'Tablet'
        else:
            device = 'Desktop'

        return {
            'browser': browser,
            'os': os_name,
            'device': device
        }


