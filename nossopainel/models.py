"""
Módulo de definição das models principais da aplicação.
Inclui entidades como Cliente, Plano, Mensalidade, Aplicativo, Sessão WhatsApp, entre outras.
"""

from datetime import date, timedelta, time as dt_time
from decimal import Decimal
from typing import Optional
import re
import os
import time
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.db import models
from django.utils import timezone

# Importação lazy para evitar circular import
def _get_encrypt_decrypt():
    """Retorna funções de encriptação de forma lazy."""
    from nossopainel.utils import encrypt_value, decrypt_value
    return encrypt_value, decrypt_value

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

# Mapeamento de DDIs (códigos internacionais) para código de país ISO 3166-1 alpha-2.
DDI_PAIS_MAP = {
    # América do Sul
    '55': 'BR',    # Brasil
    '54': 'AR',    # Argentina
    '56': 'CL',    # Chile
    '57': 'CO',    # Colômbia
    '58': 'VE',    # Venezuela
    '51': 'PE',    # Peru
    '591': 'BO',   # Bolívia
    '593': 'EC',   # Equador
    '595': 'PY',   # Paraguai
    '598': 'UY',   # Uruguai
    '592': 'GY',   # Guiana
    '594': 'GF',   # Guiana Francesa
    '597': 'SR',   # Suriname

    # América Central e Caribe
    '52': 'MX',    # México
    '506': 'CR',   # Costa Rica
    '507': 'PA',   # Panamá
    '502': 'GT',   # Guatemala
    '503': 'SV',   # El Salvador
    '504': 'HN',   # Honduras
    '505': 'NI',   # Nicarágua
    '501': 'BZ',   # Belize
    '53': 'CU',    # Cuba
    '509': 'HT',   # Haiti
    '1809': 'DO',  # República Dominicana
    '1787': 'PR',  # Porto Rico
    '1876': 'JM',  # Jamaica
    '1868': 'TT',  # Trinidad e Tobago

    # América do Norte
    '1': 'US',     # Estados Unidos / Canadá

    # Europa Ocidental
    '351': 'PT',   # Portugal
    '34': 'ES',    # Espanha
    '33': 'FR',    # França
    '39': 'IT',    # Itália
    '44': 'GB',    # Reino Unido
    '49': 'DE',    # Alemanha
    '31': 'NL',    # Países Baixos
    '32': 'BE',    # Bélgica
    '41': 'CH',    # Suíça
    '43': 'AT',    # Áustria
    '353': 'IE',   # Irlanda
    '352': 'LU',   # Luxemburgo
    '377': 'MC',   # Mônaco
    '376': 'AD',   # Andorra

    # Europa do Norte
    '45': 'DK',    # Dinamarca
    '46': 'SE',    # Suécia
    '47': 'NO',    # Noruega
    '358': 'FI',   # Finlândia
    '354': 'IS',   # Islândia

    # Europa do Leste
    '48': 'PL',    # Polônia
    '420': 'CZ',   # República Tcheca
    '421': 'SK',   # Eslováquia
    '36': 'HU',    # Hungria
    '40': 'RO',    # Romênia
    '359': 'BG',   # Bulgária
    '380': 'UA',   # Ucrânia
    '375': 'BY',   # Bielorrússia
    '373': 'MD',   # Moldávia
    '7': 'RU',     # Rússia / Cazaquistão

    # Bálticos
    '370': 'LT',   # Lituânia
    '371': 'LV',   # Letônia
    '372': 'EE',   # Estônia

    # Balcãs
    '385': 'HR',   # Croácia
    '386': 'SI',   # Eslovênia
    '381': 'RS',   # Sérvia
    '387': 'BA',   # Bósnia
    '389': 'MK',   # Macedônia do Norte
    '382': 'ME',   # Montenegro
    '383': 'XK',   # Kosovo
    '355': 'AL',   # Albânia
    '30': 'GR',    # Grécia

    # Ásia Oriental
    '81': 'JP',    # Japão
    '82': 'KR',    # Coreia do Sul
    '86': 'CN',    # China
    '852': 'HK',   # Hong Kong
    '853': 'MO',   # Macau
    '886': 'TW',   # Taiwan
    '850': 'KP',   # Coreia do Norte
    '976': 'MN',   # Mongólia

    # Sudeste Asiático
    '66': 'TH',    # Tailândia
    '84': 'VN',    # Vietnã
    '62': 'ID',    # Indonésia
    '60': 'MY',    # Malásia
    '65': 'SG',    # Singapura
    '63': 'PH',    # Filipinas
    '95': 'MM',    # Mianmar
    '855': 'KH',   # Camboja
    '856': 'LA',   # Laos
    '673': 'BN',   # Brunei
    '670': 'TL',   # Timor-Leste

    # Sul da Ásia
    '91': 'IN',    # Índia
    '92': 'PK',    # Paquistão
    '880': 'BD',   # Bangladesh
    '94': 'LK',    # Sri Lanka
    '977': 'NP',   # Nepal
    '975': 'BT',   # Butão
    '960': 'MV',   # Maldivas
    '93': 'AF',    # Afeganistão

    # Ásia Central
    '998': 'UZ',   # Uzbequistão
    '996': 'KG',   # Quirguistão
    '992': 'TJ',   # Tajiquistão
    '993': 'TM',   # Turcomenistão

    # Oriente Médio
    '90': 'TR',    # Turquia
    '972': 'IL',   # Israel
    '970': 'PS',   # Palestina
    '961': 'LB',   # Líbano
    '962': 'JO',   # Jordânia
    '963': 'SY',   # Síria
    '964': 'IQ',   # Iraque
    '98': 'IR',    # Irã
    '966': 'SA',   # Arábia Saudita
    '971': 'AE',   # Emirados Árabes
    '974': 'QA',   # Catar
    '973': 'BH',   # Bahrein
    '965': 'KW',   # Kuwait
    '968': 'OM',   # Omã
    '967': 'YE',   # Iêmen
    '357': 'CY',   # Chipre

    # África do Norte
    '20': 'EG',    # Egito
    '212': 'MA',   # Marrocos
    '213': 'DZ',   # Argélia
    '216': 'TN',   # Tunísia
    '218': 'LY',   # Líbia

    # África Ocidental
    '234': 'NG',   # Nigéria
    '233': 'GH',   # Gana
    '225': 'CI',   # Costa do Marfim
    '221': 'SN',   # Senegal
    '223': 'ML',   # Mali
    '226': 'BF',   # Burkina Faso
    '227': 'NE',   # Níger
    '228': 'TG',   # Togo
    '229': 'BJ',   # Benin
    '220': 'GM',   # Gâmbia
    '224': 'GN',   # Guiné
    '232': 'SL',   # Serra Leoa
    '231': 'LR',   # Libéria
    '238': 'CV',   # Cabo Verde
    '245': 'GW',   # Guiné-Bissau

    # África Oriental
    '254': 'KE',   # Quênia
    '255': 'TZ',   # Tanzânia
    '256': 'UG',   # Uganda
    '250': 'RW',   # Ruanda
    '257': 'BI',   # Burundi
    '251': 'ET',   # Etiópia
    '252': 'SO',   # Somália
    '253': 'DJ',   # Djibuti
    '291': 'ER',   # Eritreia
    '211': 'SS',   # Sudão do Sul
    '249': 'SD',   # Sudão

    # África Austral
    '27': 'ZA',    # África do Sul
    '263': 'ZW',   # Zimbábue
    '260': 'ZM',   # Zâmbia
    '265': 'MW',   # Malawi
    '258': 'MZ',   # Moçambique
    '267': 'BW',   # Botswana
    '264': 'NA',   # Namíbia
    '266': 'LS',   # Lesoto
    '268': 'SZ',   # Essuatíni
    '261': 'MG',   # Madagascar

    # África Central
    '237': 'CM',   # Camarões
    '243': 'CD',   # Congo (RDC)
    '242': 'CG',   # Congo
    '241': 'GA',   # Gabão
    '236': 'CF',   # República Centro-Africana
    '235': 'TD',   # Chade
    '244': 'AO',   # Angola
    '240': 'GQ',   # Guiné Equatorial
    '239': 'ST',   # São Tomé e Príncipe

    # Oceania
    '61': 'AU',    # Austrália
    '64': 'NZ',    # Nova Zelândia
    '675': 'PG',   # Papua Nova Guiné
    '679': 'FJ',   # Fiji
    '685': 'WS',   # Samoa
    '676': 'TO',   # Tonga
    '678': 'VU',   # Vanuatu
    '677': 'SB',   # Ilhas Salomão
    '686': 'KI',   # Kiribati
    '691': 'FM',   # Micronésia
    '692': 'MH',   # Ilhas Marshall
    '680': 'PW',   # Palau
    '674': 'NR',   # Nauru
    '688': 'TV',   # Tuvalu
}


def extrair_pais_do_telefone(telefone: str) -> Optional[str]:
    """
    Extrai o código do país (ISO 3166-1 alpha-2) a partir do DDI do telefone.

    Args:
        telefone: Número no formato internacional (+DDINNNNNNNN)

    Returns:
        Código do país (ex: 'BR', 'US', 'PT') ou None se não identificado

    Exemplos:
        extrair_pais_do_telefone('+5583996239140') → 'BR'
        extrair_pais_do_telefone('+1555123456') → 'US'
        extrair_pais_do_telefone('+351912345678') → 'PT'
        extrair_pais_do_telefone('+18095551234') → 'DO' (Rep. Dominicana)
    """
    if not telefone:
        return None

    # Remove caracteres não numéricos
    telefone_limpo = re.sub(r'\D', '', telefone)

    if not telefone_limpo:
        return None

    # Tenta encontrar DDI do maior para o menor (4, 3, 2, 1 dígitos)
    # DDIs de 4 dígitos: 1809 (Rep. Dominicana), 1787 (Porto Rico), etc.
    for ddi_len in [4, 3, 2, 1]:
        ddi = telefone_limpo[:ddi_len]
        if ddi in DDI_PAIS_MAP:
            return DDI_PAIS_MAP[ddi]

    return None


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
        db_table = 'cadastros_servidor'
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
        db_table = 'cadastros_servidorimagem'
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
    """
    Define os tipos de pagamento disponíveis para o cliente.
    Para PIX, pode estar associado a uma conta bancária específica.
    """
    PIX = "PIX"
    CARTAO = "Cartão de Crédito"
    BOLETO = "Boleto"

    CHOICES = ((PIX, PIX), (CARTAO, CARTAO), (BOLETO, BOLETO))

    nome = models.CharField(max_length=255, choices=CHOICES, default=PIX)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    # Conta bancária associada (obrigatório para PIX)
    conta_bancaria = models.ForeignKey(
        'ContaBancaria',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='formas_pagamento',
        verbose_name="Conta Bancária",
        help_text="Conta bancária para recebimento (obrigatório para PIX)"
    )

    # Dados bancários legados (para formas de pagamento antigas sem conta bancária)
    dados_bancarios = models.ForeignKey(
        'DadosBancarios',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='formas_pagamento',
        verbose_name="Dados Bancários"
    )

    # Campos para formas de pagamento antigas (sem conta bancária)
    nome_identificacao = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Nome de Identificação",
        help_text="Nome para identificar esta forma de pagamento (ex: PIX NuBank)"
    )
    tipo_conta = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        choices=[('pf', 'Pessoa Física'), ('mei', 'MEI')],
        default='pf',
        verbose_name="Tipo de Conta"
    )

    class Meta:
        db_table = 'cadastros_tipos_pgto'
        verbose_name = "Tipo de Pagamento"
        verbose_name_plural = "Tipos de Pagamentos"
        # Permite múltiplos PIX com diferentes contas
        unique_together = [['usuario', 'nome', 'conta_bancaria']]

    def __str__(self):
        if self.conta_bancaria and self.conta_bancaria.nome_identificacao:
            return f"{self.nome} ({self.conta_bancaria.nome_identificacao})"
        return f"{self.nome} (sem identificação)"

    def clean(self):
        """Validações customizadas."""
        from django.core.exceptions import ValidationError

        # PIX deve ter conta bancária associada
        if self.nome == self.PIX and not self.conta_bancaria:
            raise ValidationError({
                'conta_bancaria': 'Formas de pagamento PIX devem ter uma conta bancária associada.'
            })

    @property
    def tem_integracao_api(self):
        """Verifica se tem integração com API de pagamento."""
        if self.conta_bancaria:
            return self.conta_bancaria.tem_integracao_api
        return False

    def calcular_status_limite(self):
        """
        Calcula o status de limite da forma de pagamento.

        Retorna um dicionário com:
        - bloqueado: True se não pode receber novos clientes
        - percentual_utilizado: percentual do limite já utilizado
        - margem_disponivel: valor ainda disponível
        - motivo_bloqueio: motivo do bloqueio (se houver)
        - status: 'disponivel', 'proximo_limite' ou 'bloqueado'
        """
        from decimal import Decimal

        # Mapeamento de tipo de plano para quantidade de pagamentos por ano
        PAGAMENTOS_POR_ANO = {
            'Mensal': 12,
            'Bimestral': 6,
            'Trimestral': 4,
            'Semestral': 2,
            'Anual': 1,
        }

        resultado = {
            'bloqueado': False,
            'percentual_utilizado': 0,
            'margem_disponivel': 0,
            'motivo_bloqueio': None,
            'status': 'disponivel',
        }

        conta = self.conta_bancaria
        instituicao = conta.instituicao if conta else None
        tipo_integracao = instituicao.tipo_integracao if instituicao else None

        # FastDePix não tem limite de faturamento
        if tipo_integracao == 'fastdepix':
            return resultado

        # Obter configuração de limites
        config = ConfiguracaoLimite.get_config()
        limite_mei = float(config.valor_anual)
        limite_pf = float(config.valor_anual_pf)

        # Determinar limite aplicável
        if conta:
            tipo_conta = conta.tipo_conta
        elif hasattr(self, 'tipo_conta') and self.tipo_conta:
            tipo_conta = self.tipo_conta
        else:
            tipo_conta = 'pf'

        if tipo_conta == 'mei':
            limite_aplicavel = limite_mei
            tipo_label = 'MEI'
        else:
            limite_aplicavel = limite_pf
            tipo_label = 'Pessoa Física'

        # Calcular total projetado dos clientes associados
        total_projetado = Decimal('0')
        clientes_ids = set()

        # Buscar via ClienteContaBancaria (se tiver conta bancária)
        if conta:
            from nossopainel.models import ClienteContaBancaria
            clientes_conta = ClienteContaBancaria.objects.filter(
                conta_bancaria=conta,
                ativo=True,
                cliente__cancelado=False
            ).select_related('cliente__plano')

            for cc in clientes_conta:
                clientes_ids.add(cc.cliente_id)
                if cc.cliente.plano:
                    pagamentos = PAGAMENTOS_POR_ANO.get(cc.cliente.plano.nome, 12)
                    total_projetado += cc.cliente.plano.valor * pagamentos

        # Também buscar clientes associados diretamente via forma_pgto
        from nossopainel.models import Cliente
        clientes_forma = Cliente.objects.filter(
            forma_pgto=self,
            cancelado=False
        ).exclude(id__in=clientes_ids).select_related('plano')

        for cliente in clientes_forma:
            clientes_ids.add(cliente.id)
            if cliente.plano:
                pagamentos = PAGAMENTOS_POR_ANO.get(cliente.plano.nome, 12)
                total_projetado += cliente.plano.valor * pagamentos

        # Calcular percentual e margem
        if limite_aplicavel > 0:
            percentual = (float(total_projetado) / limite_aplicavel) * 100
            margem = limite_aplicavel - float(total_projetado)
        else:
            percentual = 0
            margem = 0

        resultado['percentual_utilizado'] = round(percentual, 1)
        resultado['margem_disponivel'] = max(0, margem)

        # Determinar status baseado no percentual
        if percentual >= 98:
            resultado['bloqueado'] = True
            resultado['motivo_bloqueio'] = f'Limite {tipo_label} atingido ({percentual:.1f}%)'
            resultado['status'] = 'bloqueado'
        elif percentual >= 80:
            resultado['status'] = 'proximo_limite'

        return resultado

    @property
    def esta_bloqueada(self):
        """Atalho para verificar se a forma de pagamento está bloqueada."""
        return self.calcular_status_limite()['bloqueado']


class Dispositivo(models.Model):
    """Define o nome de um dispositivo utilizado por clientes."""
    nome = models.CharField(max_length=255, null=False, blank=False)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        db_table = 'cadastros_dispositivo'

    def __str__(self):
        return self.nome


class Aplicativo(models.Model):
    """Modela os aplicativos utilizados na conta do cliente."""
    nome = models.CharField(max_length=255)
    device_has_mac = models.BooleanField(default=False)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    def tem_automacao_implementada(self):
        """Verifica se este aplicativo possui automação DNS implementada."""
        return self.nome.lower() == 'dreamtv'

    def get_logo_url(self):
        """
        Retorna o caminho da logo do aplicativo usando matching inteligente com 3 níveis de prioridade.

        Sistema de matching que elimina falsos positivos:
        - Nível 1 (Exato): "duplexplay" == "duplexplay" → duplexplay.png 
        - Nível 2 (Início): "duplexplayiptv" começa com "duplexplay" → duplexplay.png 
        - Nível 3 (Contém): "smartersplayer" contém "smarters" → Validação contra blacklist

        Apps sem logo específica retornam default.png corretamente.
        """
        import re

        # Normalização agressiva: remove espaços, acentos, caracteres especiais
        nome_normalizado = re.sub(r'[^a-z0-9]', '', self.nome.lower())

        # Blacklist: palavras muito genéricas que causam falsos positivos
        # Não podem ser usadas sozinhas para matching por "contém"
        GENERIC_WORDS = {'play', 'player', 'tv', 'iptv', 'app', 'mobile'}

        # Mapeamento de logos para suas palavras-chave
        # Organizadas por especificidade (mais específicas primeiro)
        logo_keywords = {
            # Multiplayers
            'multiplayer.png': ['multiplayerxc', 'multiplayeribo', 'multiplayer', 'multi'],

            # Duplex family
            'duplextv.png': ['duplextv'],
            'duplecast.png': ['duplecast',],
            'duplexplay.png': ['duplexplayer', 'duplexplay', 'duplex'],

            # Players diversos
            'xp.png': ['xpplayer', 'xp'],
            'vizzion.png': ['vizzion', 'viz'],
            'maximus.png': ['maximus', 'maxi'],
            'dreamtv.png': ['dreamtv', 'dream'],
            'quick.png': ['quickplayer', 'quick'],
            'iboplayer.png': ['iboplayer', 'ibo'],
            'bobplayer.png': ['bobplayer', 'bob'],
            'webplayer.png': ['webplayer', 'dns'],
            'lazerplay.png': ['lazerplay', 'lazer'],
            'phoenix.png': ['phoenixp2p', 'phoenix'],
            'metaplayer.png': ['metaplayer', 'meta'],
            'ninjaplayer.png': ['ninjaplayer', 'ninja'],
            'vuplayer.png': ['vuplayer', 'vuplay', 'vu'],
            'capplayer.png': ['capplayer', 'capp', 'cap'],
            'xtreamplayer.png': ['xtreamplayer', 'xtream'],
            'smarters.png': ['smartersplayer', 'smarters'],
            'ultraplayer.png': ['ultraplayer', 'ultraplay', 'ultra'],
            'webcastvideo.png': ['webcastvideo', 'castvideo', 'cast'],
            
            # Smart family
            'smartup.png': ['smartup'],
            'smartone.png': ['smartone'],
            'stb.png': ['smartstb', 'stb'],

            # SS IPTV
            'ssiptv.png': ['ssiptv', 'ss'],

            # Cloud/XCloud/XCIPTV
            'xciptv.png': ['xciptv'],
            'xcloud.png': ['xcloud'],
            'clouddy.png': ['clouddy', 'cloud'],

            # Servers
            'five.png': ['five'],
            'prime.png': ['prime'],
            'alpha.png': ['alpha'],
            'warez.png': ['warez'],
            'playon.png': ['playon'],
            'gf.png': ['globalfilmes', 'gf'],
            'club.png': ['club', 'cplayer', 'clite'],
            'seven.png': ['sevenxc', 'seven', '7flix'],
        }

        # Matching por prioridade (3 níveis)
        for logo_file, keywords in logo_keywords.items():
            # Ordena keywords por tamanho (desc) para priorizar matches específicos
            for keyword in sorted(keywords, key=len, reverse=True):

                # NÍVEL 1: Match Exato (prioridade máxima)
                if nome_normalizado == keyword:
                    return f'/static/assets/images/logo-apps/{logo_file}'

                # NÍVEL 2: Match por Início (prioridade alta)
                # Nome começa com keyword e keyword tem pelo menos 3 caracteres
                if nome_normalizado.startswith(keyword) and len(keyword) >= 3:
                    return f'/static/assets/images/logo-apps/{logo_file}'

                # NÍVEL 3: Match por Contém (prioridade baixa, com validação)
                # Keyword está contida no nome, mas NÃO pode ser palavra genérica
                if keyword in nome_normalizado and keyword not in GENERIC_WORDS:
                    return f'/static/assets/images/logo-apps/{logo_file}'

        # Fallback para logo padrão
        return '/static/assets/images/logo-apps/default.png'

    class Meta:
        db_table = 'cadastros_aplicativo'

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

    # ⭐ FASE 1: Controle de recursos (Dispositivos = Telas)
    max_dispositivos = models.IntegerField(
        "Máximo de dispositivos",
        default=1,
        help_text="Quantidade máxima de dispositivos (sempre igual ao número de telas)"
    )

    # ⭐ FASE 2: Campanhas Promocionais (Redesign)
    campanha_ativa = models.BooleanField(
        "Campanha Ativa",
        default=False,
        help_text="Define se este plano possui uma campanha promocional ativa"
    )

    DESCONTO_FIXO = "FIXO"
    DESCONTO_PERSONALIZADO = "PERSONALIZADO"
    CAMPANHA_TIPO_CHOICES = (
        (DESCONTO_FIXO, "Desconto Fixo"),
        (DESCONTO_PERSONALIZADO, "Desconto Personalizado"),
    )

    campanha_tipo = models.CharField(
        "Tipo de Campanha",
        max_length=20,
        choices=CAMPANHA_TIPO_CHOICES,
        null=True,
        blank=True,
        help_text="Tipo de desconto da campanha"
    )

    campanha_data_inicio = models.DateField(
        "Campanha - Data Início",
        null=True,
        blank=True,
        help_text="Data de início da validade (controla adesão de NOVOS clientes)"
    )

    campanha_data_fim = models.DateField(
        "Campanha - Data Fim",
        null=True,
        blank=True,
        help_text="Data de fim da validade (controla adesão de NOVOS clientes)"
    )

    campanha_duracao_meses = models.IntegerField(
        "Campanha - Duração (meses)",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Quantos meses a campanha dura para clientes inscritos (1-12)"
    )

    # Para DESCONTO_FIXO
    campanha_valor_fixo = models.DecimalField(
        "Campanha - Valor Fixo",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor fixo da mensalidade durante a campanha (DESCONTO_FIXO)"
    )

    # Para DESCONTO_PERSONALIZADO (valores progressivos)
    campanha_valor_mes_1 = models.DecimalField(
        "Campanha - Valor Mês 1",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor da 1ª mensalidade (DESCONTO_PERSONALIZADO)"
    )
    campanha_valor_mes_2 = models.DecimalField(
        "Campanha - Valor Mês 2",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_3 = models.DecimalField(
        "Campanha - Valor Mês 3",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_4 = models.DecimalField(
        "Campanha - Valor Mês 4",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_5 = models.DecimalField(
        "Campanha - Valor Mês 5",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_6 = models.DecimalField(
        "Campanha - Valor Mês 6",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_7 = models.DecimalField(
        "Campanha - Valor Mês 7",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_8 = models.DecimalField(
        "Campanha - Valor Mês 8",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_9 = models.DecimalField(
        "Campanha - Valor Mês 9",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_10 = models.DecimalField(
        "Campanha - Valor Mês 10",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_11 = models.DecimalField(
        "Campanha - Valor Mês 11",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    campanha_valor_mes_12 = models.DecimalField(
        "Campanha - Valor Mês 12",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )

    def save(self, *args, **kwargs):
        """Garante que max_dispositivos sempre seja igual ao número de telas."""
        self.max_dispositivos = self.telas
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome} - {self.telas} tela(s) - R$ {self.valor}"

    def get_descricao_completa(self):
        """Retorna descrição completa do plano para exibição."""
        return (
            f"{self.nome} - R$ {self.valor}\n"
            f"• {self.telas} tela(s) simultânea(s) e dispositivo(s)"
        )

    def get_campanha_duracao_display(self):
        """
        Retorna informações sobre a duração da campanha considerando o tipo de plano.

        Como o sistema rastreia PAGAMENTOS (não meses calendário), a duração real
        em meses varia de acordo com a periodicidade do plano:
        - Mensal: 1 pagamento = 1 mês
        - Bimestral: 1 pagamento = 2 meses
        - Trimestral: 1 pagamento = 3 meses
        - Semestral: 1 pagamento = 6 meses
        - Anual: 1 pagamento = 12 meses

        Returns:
            dict: Dicionário com informações formatadas da campanha
                {
                    'pagamentos': int - Número de pagamentos com desconto,
                    'meses_reais': int - Duração aproximada em meses,
                    'texto_curto': str - "3 pagtos" para tabelas,
                    'texto_completo': str - "3 pagamentos (~9 meses)" para tooltips,
                    'multiplicador': int - Fator de multiplicação (1, 2, 3, 6, 12)
                }
        """
        if not self.campanha_duracao_meses:
            return {
                'pagamentos': 0,
                'meses_reais': 0,
                'texto_curto': '-',
                'texto_completo': 'Sem campanha',
                'multiplicador': 1
            }

        # Mapeamento de multiplicadores por tipo de plano
        multiplicadores = {
            'mensal': 1,
            'bimestral': 2,
            'trimestral': 3,
            'semestral': 6,
            'anual': 12,
        }

        # Detecta o tipo de plano (case-insensitive)
        plano_tipo = self.nome.lower().split()[0] if self.nome else 'mensal'
        multiplicador = multiplicadores.get(plano_tipo, 1)

        pagamentos = self.campanha_duracao_meses
        meses_reais = pagamentos * multiplicador

        # Texto curto para tabelas
        texto_curto = f"{pagamentos} pagto{'s' if pagamentos != 1 else ''}"

        # Texto completo para tooltips e modais
        if multiplicador == 1:
            # Plano mensal: pagamentos = meses
            texto_completo = f"{pagamentos} pagamento{'s' if pagamentos != 1 else ''}"
        else:
            # Outros planos: mostrar equivalência
            texto_completo = f"{pagamentos} pagamento{'s' if pagamentos != 1 else ''} (~{meses_reais} meses)"

        return {
            'pagamentos': pagamentos,
            'meses_reais': meses_reais,
            'texto_curto': texto_curto,
            'texto_completo': texto_completo,
            'multiplicador': multiplicador
        }

    def get_campanha_valores_tooltip(self):
        """
        Retorna HTML formatado com os valores de cada pagamento da campanha
        para exibição em tooltip.
        """
        if not self.campanha_ativa or not self.campanha_duracao_meses:
            return "Sem campanha configurada"

        linhas = []
        duracao = self.campanha_duracao_meses

        if self.campanha_tipo == 'FIXO':
            # Valor fixo para todos os pagamentos
            valor = self.campanha_valor_fixo or 0
            for i in range(1, duracao + 1):
                valor_fmt = f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                linhas.append(f"Pagamento {i}: R$ {valor_fmt}")
        else:
            # Valores personalizados por mês
            for i in range(1, duracao + 1):
                valor = getattr(self, f'campanha_valor_mes_{i}', None) or 0
                valor_fmt = f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                linhas.append(f"Pagamento {i}: R$ {valor_fmt}")

        return "<br>".join(linhas)

    class Meta:
        db_table = 'cadastros_plano'


class Cliente(models.Model):
    """Modela o cliente da plataforma com todos os seus dados cadastrais e plano."""

    # ===== DADOS BÁSICOS DO CLIENTE (Cadastro) =====
    nome = models.CharField(max_length=255)
    telefone = models.CharField(max_length=20)
    email = models.EmailField(max_length=255, blank=True, null=True)
    uf = models.CharField(max_length=2, blank=True, null=True)
    pais = models.CharField("País", max_length=2, blank=True, null=True)
    notas = models.TextField("Notas", blank=True, null=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    # ===== DADOS DA ASSINATURA (Opcionais - preenchidos ao criar assinatura) =====
    servidor = models.ForeignKey(Servidor, on_delete=models.CASCADE, null=True, blank=True)
    # Campos opcionais - representam o dispositivo/aplicativo "principal" (primeiro cadastrado)
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE, null=True, blank=True, default=None)
    sistema = models.ForeignKey(Aplicativo, on_delete=models.CASCADE, null=True, blank=True, default=None)
    plano = models.ForeignKey(Plano, on_delete=models.CASCADE, null=True, blank=True)
    forma_pgto = models.ForeignKey(Tipos_pgto, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Forma de pagamento")
    indicado_por = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)

    # ===== DATAS E STATUS =====
    data_adesao = models.DateField("Data de adesão", default=date.today)
    data_vencimento = models.DateField("Data de vencimento inicial", blank=True, null=True)
    data_cancelamento = models.DateField("Data de cancelamento", blank=True, null=True)
    ultimo_pagamento = models.DateField("Último pagamento realizado", blank=True, null=True)
    cancelado = models.BooleanField("Cancelado", default=False)
    tem_assinatura = models.BooleanField("Possui assinatura", default=True)

    # ===== FLAGS DE CONTROLE =====
    nao_enviar_msgs = models.BooleanField("Não enviar", default=False)
    enviado_oferta_promo = models.BooleanField("Oferta PROMO", default=False)

    # Campos para o Painel do Cliente (painel_cliente app)
    dados_atualizados_painel = models.BooleanField(
        "Dados atualizados no painel",
        default=False,
        help_text="Indica se o cliente ja atualizou seus dados no painel de pagamentos"
    )
    ultimo_acesso_painel = models.DateTimeField(
        "Ultimo acesso ao painel",
        null=True,
        blank=True,
        help_text="Data/hora do ultimo acesso do cliente ao painel de pagamentos"
    )
    cpf = models.CharField(
        "CPF",
        max_length=14,
        null=True,
        blank=True,
        help_text="CPF do cliente (opcional, util para pagamentos)"
    )

    # ===== INTEGRAÇÃO WHATSAPP =====
    whatsapp_lid = models.CharField(
        "WhatsApp LID",
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="Linked ID do contato no WhatsApp (preenchido automaticamente via webhook)"
    )

    class Meta:
        db_table = 'cadastros_cliente'
        ordering = ['-data_adesao']

    def save(self, *args, **kwargs):
        """Garante vencimento inicial e sincroniza UF e País a partir do telefone."""
        if self.data_adesao and self.data_vencimento is None:
            self.data_vencimento = self.data_adesao

        self.definir_uf()
        self.definir_pais()
        super().save(*args, **kwargs)

    def definir_uf(self):
        """Define a unidade federativa (UF) com base no DDD do telefone apenas se for nacional."""
        if not self.telefone or not self.telefone.startswith('+55') or len(self.telefone) < 5:
            self.uf = None
            return

        ddd = self.telefone[3:5]
        self.uf = DDD_UF_MAP.get(ddd)

    def definir_pais(self):
        """Define o país (código ISO 3166-1 alpha-2) com base no DDI do telefone."""
        if not self.telefone:
            self.pais = None
            return

        self.pais = extrair_pais_do_telefone(self.telefone)

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
        db_table = 'cadastros_ofertapromocionalenviada'
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
    forma_pgto = models.ForeignKey(
        'Tipos_pgto',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Forma de Pagamento",
        help_text="Forma de pagamento registrada no momento do pagamento (histórico imutável)"
    )
    notificacao_wpp1 = models.BooleanField("Notificação PROMO", default=False)
    recebeu_pix_indicacao = models.BooleanField("PIX R$50", default=False)
    isencao_anuidade = models.BooleanField("Isenção por bônus anuidade", default=False)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    # ⭐ FASE 2.5: Rastreamento de Campanhas e Descontos
    gerada_em_campanha = models.BooleanField(
        "Gerada em Campanha",
        default=False,
        help_text="Indica se esta mensalidade foi gerada durante uma campanha promocional"
    )
    valor_base_plano = models.DecimalField(
        "Valor Base do Plano",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor original do plano no momento da criação (antes de descontos)"
    )
    desconto_campanha = models.DecimalField(
        "Desconto de Campanha",
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Valor de desconto aplicado por campanha promocional"
    )
    desconto_progressivo = models.DecimalField(
        "Desconto Progressivo",
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Valor de desconto aplicado por indicações progressivas"
    )
    tipo_campanha = models.CharField(
        "Tipo de Campanha",
        max_length=20,
        null=True,
        blank=True,
        help_text="FIXO ou PERSONALIZADO (se gerada em campanha)"
    )
    numero_mes_campanha = models.IntegerField(
        "Número do Mês na Campanha",
        null=True,
        blank=True,
        help_text="Qual mês/pagamento da campanha esta mensalidade representa (1, 2, 3...)"
    )
    dados_historicos_verificados = models.BooleanField(
        "Dados Históricos Verificados",
        default=True,
        help_text="False = dados estimados (mensalidades antigas). True = dados precisos (mensalidades novas)"
    )

    class Meta:
        db_table = 'cadastros_mensalidade'

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
        db_table = 'cadastros_clienteplanohistorico'
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


class AssinaturaCliente(models.Model):
    """
    Gerencia a assinatura ativa do cliente com controle de recursos.

    FASE 1: MVP - Controle de Dispositivos e Apps

    Este modelo serve como camada intermediária entre Cliente e Plano,
    permitindo:
    - Rastrear recursos utilizados (dispositivos, contas app)
    - Aplicar ofertas promocionais (Fase 2)
    - Aplicar valores progressivos (Fase 3)
    - Calcular valor da mensalidade dinamicamente
    - Emitir avisos de excesso de limites (não bloqueia)
    """

    cliente = models.OneToOneField(
        'Cliente',
        on_delete=models.CASCADE,
        related_name='assinatura',
        verbose_name="Cliente"
    )

    plano = models.ForeignKey(
        'Plano',
        on_delete=models.PROTECT,
        verbose_name="Plano"
    )

    data_inicio_assinatura = models.DateField(
        "Data de início da assinatura",
        help_text="Data em que o cliente aderiu ao plano atual"
    )

    # Contadores de recursos utilizados
    dispositivos_usados = models.IntegerField(
        "Dispositivos em uso",
        default=0,
        help_text="Quantidade atual de dispositivos cadastrados (informativo)"
    )

    # ⭐ FASE 2.5: Rastreamento de Campanhas Promocionais (Simplificado)
    em_campanha = models.BooleanField(
        "Em Campanha",
        default=False,
        help_text="Cliente está participando de uma campanha promocional"
    )

    campanha_data_adesao = models.DateField(
        "Data de Adesão à Campanha",
        null=True,
        blank=True,
        help_text="Quando o cliente se inscreveu na campanha"
    )

    campanha_mensalidades_pagas = models.IntegerField(
        "Mensalidades Pagas (Campanha)",
        default=0,
        help_text="Contador de mensalidades pagas durante a campanha"
    )

    campanha_duracao_total = models.IntegerField(
        "Duração Total da Campanha",
        null=True,
        blank=True,
        help_text="Snapshot da duração quando cliente aderiu (usado para calcular progresso)"
    )

    # Campos para Fase 3 (preparação futura)
    # valor_progressivo = FK PlanoValorProgressivo (Fase 3)

    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cadastros_assinaturacliente'
        verbose_name = "Assinatura de Cliente"
        verbose_name_plural = "Assinaturas de Clientes"
        indexes = [
            models.Index(fields=['cliente', 'ativo']),
        ]

    def __str__(self):
        return f"Assinatura: {self.cliente.nome} - {self.plano.nome}"

    # ===== MÉTODOS DE VALIDAÇÃO (FASE 1) =====

    def validar_limite_dispositivos(self):
        """
        Verifica se há excesso de dispositivos.
        Retorna dict com informações para exibir aviso.
        """
        limite = self.plano.max_dispositivos
        usado = self.dispositivos_usados

        return {
            'dentro_limite': usado < limite,
            'no_limite': usado == limite,
            'excedeu': usado > limite,
            'limite': limite,
            'usado': usado,
            'disponivel': max(0, limite - usado),
            'excesso': max(0, usado - limite),
            'percentual': (usado / limite * 100) if limite > 0 else 0
        }

    def obter_avisos_necessarios(self):
        """
        Retorna lista de avisos que devem ser exibidos ao usuário.
        Sistema NÃO BLOQUEIA, apenas avisa.
        """
        avisos = []

        # Verificar dispositivos
        disp = self.validar_limite_dispositivos()
        if disp['excedeu']:
            avisos.append({
                'tipo': 'dispositivos',
                'nivel': 'warning',
                'mensagem': f"Cliente possui {disp['excesso']} dispositivo(s) acima do limite ({disp['usado']}/{disp['limite']})"
            })
        elif disp['no_limite']:
            avisos.append({
                'tipo': 'dispositivos',
                'nivel': 'info',
                'mensagem': f"Limite de dispositivos atingido ({disp['usado']}/{disp['limite']})"
            })

        return avisos

    def obter_status_recursos(self):
        """Retorna dicionário completo com status de todos os recursos."""
        return {
            'telas': {
                'usado': None,  # Implementar futuramente com controle de streaming
                'maximo': self.plano.telas,
            },
            'dispositivos': self.validar_limite_dispositivos(),
        }

    # ===== MÉTODOS DE CÁLCULO DE VALOR (FASE 1, 2, 3) =====

    def calcular_valor_atual(self):
        """
        Calcula o valor atual da mensalidade do cliente.

        FASE 1: Retorna apenas valor base do plano
        FASE 2: Adicionará verificação de oferta promocional
        FASE 3: Adicionará verificação de valor progressivo

        Ordem de prioridade (implementação futura):
        1. Oferta promocional (se vigente) - Fase 2
        2. Valor progressivo (se configurado) - Fase 3
        3. Valor base do plano

        Returns:
            Decimal: Valor calculado para a próxima mensalidade
        """
        # FASE 1: Retorna apenas valor base
        return self.plano.valor


class OfertaPromocional(models.Model):
    """
    ⭐ FASE 2: Ofertas promocionais com valores progressivos por mensalidade.

    Permite criar ofertas com valores diferenciados por mês (ex: R$10, R$20, R$30)
    que expiram automaticamente após número definido de mensalidades pagas.
    """

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='ofertas_promocionais',
        verbose_name="Cliente"
    )

    plano_oferta = models.ForeignKey(
        Plano,
        on_delete=models.PROTECT,
        limit_choices_to={'permite_oferta_promocional': True},
        verbose_name="Plano Promocional",
        help_text="Apenas planos marcados como promocionais"
    )

    # Controle de duração
    numero_mensalidades = models.IntegerField(
        "Número de Mensalidades",
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Quantos meses a oferta dura (1-12)"
    )

    mensalidades_restantes = models.IntegerField(
        "Mensalidades Restantes",
        validators=[MinValueValidator(0)],
        help_text="Contador de meses restantes"
    )

    # Valores progressivos (até 6 meses - suficiente para maioria dos casos)
    valor_mes_1 = models.DecimalField(
        "Valor Mês 1",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor da 1ª mensalidade"
    )
    valor_mes_2 = models.DecimalField(
        "Valor Mês 2",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    valor_mes_3 = models.DecimalField(
        "Valor Mês 3",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    valor_mes_4 = models.DecimalField(
        "Valor Mês 4",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    valor_mes_5 = models.DecimalField(
        "Valor Mês 5",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )
    valor_mes_6 = models.DecimalField(
        "Valor Mês 6",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Datas
    data_inicio = models.DateField("Data de Início", default=date.today)
    data_fim = models.DateField("Data de Fim", null=True, blank=True)

    # Status
    ativo = models.BooleanField("Ativo", default=True)

    # Metadados
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cadastros_ofertapromocional'
        verbose_name = "Oferta Promocional"
        verbose_name_plural = "Ofertas Promocionais"
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['cliente', 'ativo']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(mensalidades_restantes__gte=0),
                name='mensalidades_restantes_nao_negativo'
            ),
        ]

    def clean(self):
        """Validações customizadas."""
        super().clean()

        # ✅ VALIDAÇÃO 1: Plano deve permitir ofertas promocionais
        if self.plano_oferta and not self.plano_oferta.permite_oferta_promocional:
            raise ValidationError({
                'plano_oferta':
                    'Este plano não está habilitado para ofertas promocionais. '
                    'Marque a opção "Plano Promocional" antes de usar em ofertas.'
            })

        # ✅ VALIDAÇÃO 2: Pelo menos um valor mensal deve ser definido
        valores_definidos = sum([
            1 for i in range(1, 7)
            if getattr(self, f'valor_mes_{i}') is not None
        ])

        if valores_definidos == 0:
            raise ValidationError(
                'Defina pelo menos um valor mensal para a oferta promocional.'
            )

    def calcular_valor_mensalidade(self, numero_mes):
        """
        Calcula valor da mensalidade baseado no mês da oferta.

        Args:
            numero_mes: Número do mês na oferta (1, 2, 3...)

        Returns:
            Decimal: Valor a cobrar ou valor do plano_oferta como fallback
        """
        # Tentar valor específico do mês
        if numero_mes <= 6:
            valor_campo = getattr(self, f'valor_mes_{numero_mes}', None)
            if valor_campo:
                return valor_campo

        # Fallback: valor do plano promocional
        return self.plano_oferta.valor

    def save(self, *args, **kwargs):
        """Executa validação antes de salvar."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Oferta {self.plano_oferta.nome} - {self.cliente.nome} "
            f"({self.mensalidades_restantes}/{self.numero_mensalidades})"
        )


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
        db_table = 'cadastros_horarioenvios'
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
        db_table = 'cadastros_planoindicacao'
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
        db_table = 'cadastros_descontoprogressivoindicacao'
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
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Tipo de Dispositivo", help_text="Em qual dispositivo esta conta está instalada")
    app = models.ForeignKey(Aplicativo, on_delete=models.CASCADE, related_name="aplicativos", verbose_name="Aplicativo")
    device_id = models.CharField("ID", max_length=255, blank=True, null=True)
    email = models.EmailField("E-mail", max_length=255, blank=True, null=True)
    device_key = models.CharField("Senha", max_length=255, blank=True, null=True)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    verificado = models.BooleanField(default=False)
    is_principal = models.BooleanField("Conta Principal", default=False, help_text="Define esta conta como principal. Os dados desta conta sincronizam com os campos Dispositivo e Aplicativo do cliente.")

    def save(self, *args, **kwargs):
        """Normaliza o identificador do dispositivo para formato MAC quando necessário."""
        if self.device_id and not len(self.device_id) <= 10:
            raw = re.sub(r'[^A-Fa-f0-9]', '', self.device_id).upper()
            self.device_id = ':'.join(raw[i:i+2] for i in range(0, len(raw), 2))
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'cadastros_contadoaplicativo'
        verbose_name = "Conta do Aplicativo"
        verbose_name_plural = "Contas dos Aplicativos"

        indexes = [
            models.Index(fields=['cliente', 'app']),
            models.Index(fields=['device_id']),
        ]

    def __str__(self):
        if self.dispositivo:
            return f"{self.app.nome} ({self.dispositivo.nome})"
        return self.app.nome

    def marcar_como_principal(self):
        """
        Marca esta conta como principal e desmarca todas as outras do mesmo cliente.
        Sincroniza os campos Cliente.dispositivo e Cliente.sistema com esta conta.
        """
        # Desmarca todas as outras contas do mesmo cliente
        ContaDoAplicativo.objects.filter(cliente=self.cliente).exclude(id=self.id).update(is_principal=False)

        # Marca esta conta como principal
        self.is_principal = True
        self.save(update_fields=['is_principal'])

        # Sincroniza com o Cliente
        self.cliente.dispositivo = self.dispositivo
        self.cliente.sistema = self.app
        self.cliente.save(update_fields=['dispositivo', 'sistema'])


class SessaoWpp(models.Model):
    """Armazena as informações da sessão do WhatsApp integrada."""
    usuario = models.CharField(max_length=255)  # Nome da sessão no WPPConnect
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sessoes_wpp',
        verbose_name='Usuário Django'
    )
    token = models.CharField(max_length=255)
    dt_inicio = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    # Configurações de Reject-Call
    reject_call_enabled = models.BooleanField(
        default=True,
        verbose_name='Rejeitar chamadas automaticamente'
    )
    reject_call_horario_inicio = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Horário início (rejeição ativa)'
    )
    reject_call_horario_fim = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Horário fim (rejeição ativa)'
    )

    class Meta:
        db_table = 'cadastros_sessaowpp'
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
        db_table = 'cadastros_secrettokenapi'
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
        if not self.wpp:
            return  # Não formatar se não houver telefone

        numero = re.sub(r'\D+', '', self.wpp)

        # Adiciona DDI Brasil se for nacional
        if len(numero) in (10, 11) and not numero.startswith('55'):
            numero = '55' + numero

        if len(numero) < 10:
            raise ValueError("Telefone inválido")

        self.wpp = '+' + numero  # Ex: +5500000000000

    def save(self, *args, **kwargs):
        """Normaliza o telefone antes de persistir os dados bancários."""
        if self.wpp:  # Só formata se houver telefone
            self.formatar_telefone()
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'cadastros_dadosbancarios'
        verbose_name_plural = "Dados Bancários"

    def __str__(self) -> str:
        return f'{self.usuario.first_name} {self.usuario.last_name}'


# ============================================================================
# MODELOS DE INTEGRAÇÃO BANCÁRIA (PIX, Boleto, Cartão)
# ============================================================================

def certificado_upload_path(instance, filename):
    """
    Gera caminho de upload seguro para certificados bancários.
    Formato: certificados/<user_id>/<uuid>.<ext>
    """
    ext = filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('certificados', str(instance.usuario.id), filename)


class InstituicaoBancaria(models.Model):
    """
    Cadastro de instituições bancárias pelo Admin.
    FastDePix, Efi Bank e Mercado Pago terão integração com API.
    Outras instituições funcionam no modo manual (sem geração automática de link).
    """
    TIPO_INTEGRACAO = [
        ('fastdepix', 'FastDePix (API)'),
        ('efi_bank', 'Efi Bank (API)'),
        ('mercado_pago', 'Mercado Pago (API)'),
        ('manual', 'Manual (sem API)'),
    ]

    nome = models.CharField(max_length=255, unique=True, verbose_name="Nome da Instituição")
    tipo_integracao = models.CharField(
        max_length=20,
        choices=TIPO_INTEGRACAO,
        default='manual',
        verbose_name="Tipo de Integração"
    )
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cadastros_instituicaobancaria'
        verbose_name = "Instituição Bancária"
        verbose_name_plural = "Instituições Bancárias"
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_integracao_display()})"

    @property
    def tem_api(self):
        """Verifica se a instituição tem integração com API."""
        return self.tipo_integracao in ['fastdepix', 'efi_bank', 'mercado_pago']


class ContaBancaria(models.Model):
    """
    Conta bancária do usuário em uma instituição.
    Pode ser PF (Pessoa Física) ou MEI com limite de recebimento mensal.
    """
    TIPO_CONTA = [
        ('pf', 'Pessoa Física'),
        ('mei', 'MEI'),
    ]

    TIPO_CHAVE_PIX = [
        ('cpf', 'CPF'),
        ('cnpj', 'CNPJ'),
        ('email', 'E-mail'),
        ('celular', 'Celular'),
        ('aleatoria', 'Chave Aleatória'),
    ]

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='contas_bancarias'
    )
    instituicao = models.ForeignKey(
        InstituicaoBancaria,
        on_delete=models.PROTECT,
        verbose_name="Instituição"
    )

    # Identificação da conta
    nome_identificacao = models.CharField(
        max_length=100,
        verbose_name="Nome de Identificação",
        help_text="Ex: Minha conta Efi Principal"
    )
    tipo_conta = models.CharField(
        max_length=10,
        choices=TIPO_CONTA,
        default='pf',
        verbose_name="Tipo de Conta"
    )

    # Dados bancários (opcionais para instituições com API)
    beneficiario = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Beneficiário"
    )
    tipo_chave_pix = models.CharField(
        max_length=50,
        choices=TIPO_CHAVE_PIX,
        blank=True,
        null=True,
        verbose_name="Tipo de Chave PIX"
    )
    chave_pix = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Chave PIX"
    )

    # Credenciais API (FastDePix, Efi Bank e Mercado Pago)
    # Campos encriptados com FERNET - use as properties para acessar
    _api_key = models.TextField(
        blank=True,
        default='',
        db_column='api_key',
        verbose_name="API Key (encriptado)",
        help_text="Token de autenticação (obrigatório para FastDePix - formato: fdpx_...)"
    )
    api_client_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Client ID",
        help_text="Credencial da API (Efi Bank ou Mercado Pago)"
    )
    _api_client_secret = models.TextField(
        blank=True,
        default='',
        db_column='api_client_secret',
        verbose_name="Client Secret (encriptado)",
        help_text="Armazenado de forma segura com FERNET"
    )
    api_certificado = models.FileField(
        upload_to=certificado_upload_path,
        blank=True,
        null=True,
        verbose_name="Certificado (.p12)",
        help_text="Obrigatório para Efi Bank"
    )
    _api_access_token = models.TextField(
        blank=True,
        default='',
        db_column='api_access_token',
        verbose_name="Access Token (encriptado)",
        help_text="Obrigatório para Mercado Pago"
    )
    ambiente_sandbox = models.BooleanField(
        default=True,
        verbose_name="Ambiente Sandbox",
        help_text="Marque para usar ambiente de testes"
    )

    # Webhook (FastDePix)
    _webhook_secret = models.TextField(
        blank=True,
        default='',
        db_column='webhook_secret',
        verbose_name="Webhook Secret (encriptado)",
        help_text="Chave secreta para validar webhooks HMAC-SHA256 (gerada ao registrar webhook)"
    )
    webhook_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Webhook ID",
        help_text="ID do webhook registrado na API (para atualizar/remover)"
    )

    # Configuração de Cobranças FastDePix
    TIPO_COBRANCA_FASTDEPIX = [
        ('painel_cliente', 'Painel do Cliente'),
        ('link_fastdepix', 'Link FastDePix'),
        ('qrcode', 'QR Code + Copia e Cola'),
    ]
    tipo_cobranca_fastdepix = models.CharField(
        max_length=30,
        choices=TIPO_COBRANCA_FASTDEPIX,
        null=True,
        blank=True,
        default='painel_cliente',
        verbose_name='Tipo de Cobrança FastDePix'
    )
    # NOTA: Links de planos agora estão no modelo PlanoLinkPagamento

    # Referência para credencial reutilizável (opcional)
    # Se preenchido, usa os dados da credencial salva ao invés dos campos diretos
    credencial = models.ForeignKey(
        'CredencialAPI',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contas_bancarias',
        verbose_name='Credencial API',
        help_text='Selecione uma credencial salva ou deixe vazio para usar credenciais específicas'
    )

    # Controle MEI - limite de recebimento
    limite_mensal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Limite Mensal (R$)",
        help_text="Limite de recebimento mensal para contas MEI"
    )

    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    # ==================== PROPERTIES ENCRIPTADAS ====================
    # Estas properties encriptam/descriptografam automaticamente os valores
    # usando FERNET. O código existente continua funcionando normalmente.

    @property
    def api_key(self):
        """Retorna a API key descriptografada."""
        if not self._api_key:
            return ''
        try:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            return decrypt_value(self._api_key)
        except Exception:
            # Fallback para valores não encriptados (migração pendente)
            return self._api_key

    @api_key.setter
    def api_key(self, value):
        """Encripta e armazena a API key."""
        if value:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            self._api_key = encrypt_value(value)
        else:
            self._api_key = ''

    @property
    def api_client_secret(self):
        """Retorna o client secret descriptografado."""
        if not self._api_client_secret:
            return ''
        try:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            return decrypt_value(self._api_client_secret)
        except Exception:
            return self._api_client_secret

    @api_client_secret.setter
    def api_client_secret(self, value):
        """Encripta e armazena o client secret."""
        if value:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            self._api_client_secret = encrypt_value(value)
        else:
            self._api_client_secret = ''

    @property
    def api_access_token(self):
        """Retorna o access token descriptografado."""
        if not self._api_access_token:
            return ''
        try:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            return decrypt_value(self._api_access_token)
        except Exception:
            return self._api_access_token

    @api_access_token.setter
    def api_access_token(self, value):
        """Encripta e armazena o access token."""
        if value:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            self._api_access_token = encrypt_value(value)
        else:
            self._api_access_token = ''

    @property
    def webhook_secret(self):
        """Retorna o webhook secret descriptografado."""
        if not self._webhook_secret:
            return ''
        try:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            return decrypt_value(self._webhook_secret)
        except Exception:
            return self._webhook_secret

    @webhook_secret.setter
    def webhook_secret(self, value):
        """Encripta e armazena o webhook secret."""
        if value:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            self._webhook_secret = encrypt_value(value)
        else:
            self._webhook_secret = ''

    class Meta:
        db_table = 'cadastros_contabancaria'
        verbose_name = "Conta Bancária"
        verbose_name_plural = "Contas Bancárias"
        ordering = ['-criado_em']
        # Impede mesma chave PIX duplicada para o mesmo usuário (apenas quando chave_pix não é NULL)
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'chave_pix'],
                name='unique_usuario_chave_pix',
                condition=models.Q(chave_pix__isnull=False)
            )
        ]

    def __str__(self):
        tipo = "MEI" if self.tipo_conta == 'mei' else "PF"
        return f"{self.nome_identificacao} ({self.instituicao.nome} - {tipo})"

    @property
    def limite_efetivo(self):
        """
        Retorna o limite efetivo com 10% de margem de segurança.
        Ex: Se limite_mensal = R$ 10.000, limite_efetivo = R$ 9.000
        """
        if self.limite_mensal:
            return self.limite_mensal * Decimal('0.90')
        return None

    @property
    def tem_integracao_api(self):
        """Verifica se a conta tem integração com API."""
        return self.instituicao.tipo_integracao in ['fastdepix', 'efi_bank', 'mercado_pago']

    @property
    def is_mei(self):
        """Verifica se é conta MEI."""
        return self.tipo_conta == 'mei'

    def get_clientes_associados_count(self):
        """Retorna a quantidade de clientes ATIVOS associados a esta conta."""
        return self.clientes_associados.filter(
            ativo=True,
            cliente__cancelado=False
        ).count()

    def clean(self):
        """Validações customizadas."""
        # MEI deve ter limite definido
        if self.tipo_conta == 'mei' and not self.limite_mensal:
            raise ValidationError({
                'limite_mensal': 'Contas MEI devem ter um limite mensal definido.'
            })

        # FastDePix deve ter API Key
        if (self.instituicao and
            self.instituicao.tipo_integracao == 'fastdepix' and
            not self.api_key):
            raise ValidationError({
                'api_key': 'API Key é obrigatória para FastDePix.'
            })

        # Efi Bank deve ter certificado
        if (self.instituicao and
            self.instituicao.tipo_integracao == 'efi_bank' and
            not self.api_certificado and
            self.api_client_id):
            raise ValidationError({
                'api_certificado': 'Certificado é obrigatório para Efi Bank.'
            })

        # Mercado Pago deve ter access token
        if (self.instituicao and
            self.instituicao.tipo_integracao == 'mercado_pago' and
            not self.api_access_token and
            self.api_client_id):
            raise ValidationError({
                'api_access_token': 'Access Token é obrigatório para Mercado Pago.'
            })

    def save(self, *args, **kwargs):
        """
        Garante que campos sensíveis sejam encriptados antes de salvar.
        Isso é necessário porque o admin atribui diretamente aos campos _*
        em vez de usar as properties.
        """
        encrypt_value, _ = _get_encrypt_decrypt()

        # Encriptar _api_key se não estiver encriptado
        if self._api_key and not self._api_key.startswith('gAAAAA'):
            self._api_key = encrypt_value(self._api_key)

        # Encriptar _api_client_secret se não estiver encriptado
        if self._api_client_secret and not self._api_client_secret.startswith('gAAAAA'):
            self._api_client_secret = encrypt_value(self._api_client_secret)

        # Encriptar _api_access_token se não estiver encriptado
        if self._api_access_token and not self._api_access_token.startswith('gAAAAA'):
            self._api_access_token = encrypt_value(self._api_access_token)

        # Encriptar _webhook_secret se não estiver encriptado
        if self._webhook_secret and not self._webhook_secret.startswith('gAAAAA'):
            self._webhook_secret = encrypt_value(self._webhook_secret)

        super().save(*args, **kwargs)


class PlanoLinkPagamento(models.Model):
    """
    Relaciona Plano com link de pagamento de uma ContaBancaria FastDePix.
    Permite monitorar alterações de valor e detectar planos sem link configurado.
    """
    plano = models.ForeignKey(
        'Plano',
        on_delete=models.CASCADE,
        related_name='links_pagamento',
        verbose_name='Plano de Adesão'
    )
    conta_bancaria = models.ForeignKey(
        ContaBancaria,
        on_delete=models.CASCADE,
        related_name='links_planos',
        verbose_name='Conta Bancária FastDePix'
    )
    url = models.URLField(
        'Link de Pagamento',
        help_text='URL do link FastDePix para este plano'
    )
    valor_configurado = models.DecimalField(
        'Valor quando configurado',
        max_digits=7,
        decimal_places=2,
        help_text='Valor do plano no momento em que o link foi configurado'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cadastros_planolinkpagamento'
        verbose_name = 'Link de Pagamento do Plano'
        verbose_name_plural = 'Links de Pagamento dos Planos'
        unique_together = ('plano', 'conta_bancaria')
        ordering = ['plano__nome', 'plano__telas']

    def __str__(self):
        return f"{self.plano.nome} ({self.plano.telas} tela(s)) - {self.conta_bancaria.nome_identificacao}"

    @property
    def valor_divergente(self):
        """Verifica se o valor do plano mudou desde a configuração do link."""
        return self.plano.valor != self.valor_configurado

    @property
    def diferenca_valor(self):
        """Retorna a diferença entre o valor atual e o configurado."""
        return self.plano.valor - self.valor_configurado


class CredencialAPI(models.Model):
    """
    Credenciais de API reutilizáveis entre formas de pagamento.
    Permite que o usuário cadastre credenciais uma vez e reutilize em múltiplas contas.
    """
    TIPO_INTEGRACAO_CHOICES = [
        ('fastdepix', 'FastDePix'),
        ('mercado_pago', 'Mercado Pago'),
        ('efi_bank', 'Efi Bank'),
    ]

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='credenciais_api'
    )
    nome_identificacao = models.CharField(
        max_length=100,
        verbose_name='Nome de Identificação',
        help_text='Ex: Minha Credencial FastDePix'
    )
    tipo_integracao = models.CharField(
        max_length=20,
        choices=TIPO_INTEGRACAO_CHOICES,
        verbose_name='Tipo de Integração'
    )

    # FastDePix - Encriptado com FERNET
    _api_key = models.TextField(
        blank=True,
        default='',
        db_column='api_key',
        verbose_name='API Key (encriptado)',
        help_text='Token de autenticação (formato: fdpx_...)'
    )

    # Mercado Pago / Efi Bank
    api_client_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Client ID'
    )
    _api_client_secret = models.TextField(
        blank=True,
        default='',
        db_column='api_client_secret',
        verbose_name='Client Secret (encriptado)'
    )

    # Mercado Pago apenas - Encriptado com FERNET
    _api_access_token = models.TextField(
        blank=True,
        default='',
        db_column='api_access_token',
        verbose_name='Access Token (encriptado)'
    )

    # Efi Bank apenas
    api_certificado = models.FileField(
        upload_to=certificado_upload_path,
        blank=True,
        null=True,
        verbose_name='Certificado (.p12)'
    )

    # Ambiente (visível apenas para admin em desenvolvimento)
    ambiente_sandbox = models.BooleanField(
        default=False,
        verbose_name='Ambiente Sandbox'
    )

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    # ==================== PROPERTIES ENCRIPTADAS ====================

    @property
    def api_key(self):
        """Retorna a API key descriptografada."""
        if not self._api_key:
            return ''
        try:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            return decrypt_value(self._api_key)
        except Exception:
            return self._api_key

    @api_key.setter
    def api_key(self, value):
        """Encripta e armazena a API key."""
        if value:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            self._api_key = encrypt_value(value)
        else:
            self._api_key = ''

    @property
    def api_client_secret(self):
        """Retorna o client secret descriptografado."""
        if not self._api_client_secret:
            return ''
        try:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            return decrypt_value(self._api_client_secret)
        except Exception:
            return self._api_client_secret

    @api_client_secret.setter
    def api_client_secret(self, value):
        """Encripta e armazena o client secret."""
        if value:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            self._api_client_secret = encrypt_value(value)
        else:
            self._api_client_secret = ''

    @property
    def api_access_token(self):
        """Retorna o access token descriptografado."""
        if not self._api_access_token:
            return ''
        try:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            return decrypt_value(self._api_access_token)
        except Exception:
            return self._api_access_token

    @api_access_token.setter
    def api_access_token(self, value):
        """Encripta e armazena o access token."""
        if value:
            encrypt_value, decrypt_value = _get_encrypt_decrypt()
            self._api_access_token = encrypt_value(value)
        else:
            self._api_access_token = ''

    class Meta:
        db_table = 'cadastros_credencialapi'
        verbose_name = 'Credencial API'
        verbose_name_plural = 'Credenciais API'
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.nome_identificacao} ({self.get_tipo_integracao_display()})"

    @property
    def is_configured(self):
        """Verifica se a credencial está configurada corretamente."""
        if self.tipo_integracao == 'fastdepix':
            return bool(self.api_key)
        elif self.tipo_integracao == 'mercado_pago':
            return all([self.api_client_id, self.api_client_secret, self.api_access_token])
        elif self.tipo_integracao == 'efi_bank':
            return all([self.api_client_id, self.api_client_secret, self.api_certificado])
        return False

    def clean(self):
        """Validações customizadas."""
        if self.tipo_integracao == 'fastdepix' and not self.api_key:
            raise ValidationError({
                'api_key': 'API Key é obrigatória para FastDePix.'
            })

        if self.tipo_integracao == 'mercado_pago':
            if not all([self.api_client_id, self.api_client_secret, self.api_access_token]):
                raise ValidationError(
                    'Client ID, Client Secret e Access Token são obrigatórios para Mercado Pago.'
                )

        if self.tipo_integracao == 'efi_bank':
            if not all([self.api_client_id, self.api_client_secret]):
                raise ValidationError(
                    'Client ID e Client Secret são obrigatórios para Efi Bank.'
                )

    def save(self, *args, **kwargs):
        """
        Garante que campos sensíveis sejam encriptados antes de salvar.
        Isso é necessário porque o admin atribui diretamente aos campos _*
        em vez de usar as properties.
        """
        encrypt_value, _ = _get_encrypt_decrypt()

        # Encriptar _api_key se não estiver encriptado
        if self._api_key and not self._api_key.startswith('gAAAAA'):
            self._api_key = encrypt_value(self._api_key)

        # Encriptar _api_client_secret se não estiver encriptado
        if self._api_client_secret and not self._api_client_secret.startswith('gAAAAA'):
            self._api_client_secret = encrypt_value(self._api_client_secret)

        # Encriptar _api_access_token se não estiver encriptado
        if self._api_access_token and not self._api_access_token.startswith('gAAAAA'):
            self._api_access_token = encrypt_value(self._api_access_token)

        super().save(*args, **kwargs)


class ConfiguracaoLimite(models.Model):
    """
    Configuração global de limites de faturamento (singleton).
    Define os valores máximos anuais permitidos para contas MEI e Pessoa Física.
    """
    valor_anual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('81000.00'),
        verbose_name='Limite Anual MEI (R$)',
        help_text='Valor máximo anual permitido para contas MEI'
    )
    valor_anual_pf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('60000.00'),
        verbose_name='Limite Anual Pessoa Física (R$)',
        help_text='Valor máximo anual permitido para contas Pessoa Física'
    )
    margem_seguranca = models.IntegerField(
        default=10,
        verbose_name='Margem de Segurança (%)',
        help_text='Percentual de margem (ex: 10 = alerta em 90%)'
    )
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'cadastros_configuracaolimite'
        verbose_name = 'Configuração de Limite'
        verbose_name_plural = 'Configurações de Limite'

    def save(self, *args, **kwargs):
        # Garante singleton - sempre usa pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        """Retorna a configuração atual ou cria com valores padrão."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def valor_alerta(self):
        """Valor que dispara alerta MEI (ex: 90% para margem de 10%)."""
        return self.valor_anual * Decimal(str(100 - self.margem_seguranca)) / 100

    @property
    def valor_bloqueio(self):
        """Valor que bloqueia adições MEI (99%)."""
        return self.valor_anual * Decimal('0.99')

    @property
    def valor_alerta_pf(self):
        """Valor que dispara alerta PF (ex: 90% para margem de 10%)."""
        return self.valor_anual_pf * Decimal(str(100 - self.margem_seguranca)) / 100

    @property
    def valor_bloqueio_pf(self):
        """Valor que bloqueia adições PF (99%)."""
        return self.valor_anual_pf * Decimal('0.99')

    def __str__(self):
        return f"Limite MEI: R$ {self.valor_anual:,.2f} | PF: R$ {self.valor_anual_pf:,.2f}"


class NotificacaoSistema(models.Model):
    """
    Notificações do sistema para alertar usuários sobre eventos importantes.
    Ex: Limite MEI atingido, mudança de plano afetando limite, etc.
    """
    TIPO_CHOICES = [
        ('alerta_limite', 'Alerta de Limite'),
        ('limite_atingido', 'Limite Atingido'),
        ('mudanca_plano', 'Mudança de Plano'),
        ('pagamento_confirmado', 'Pagamento Confirmado'),
        ('info', 'Informação'),
        ('aviso', 'Aviso'),
    ]

    PRIORIDADE_CHOICES = [
        ('baixa', 'Baixa'),
        ('media', 'Média'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ]

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notificacoes_sistema'
    )
    tipo = models.CharField(
        max_length=30,
        choices=TIPO_CHOICES,
        default='info'
    )
    prioridade = models.CharField(
        max_length=10,
        choices=PRIORIDADE_CHOICES,
        default='media'
    )
    titulo = models.CharField(max_length=200)
    mensagem = models.TextField()

    # Dados adicionais em JSON (ex: conta_id, cliente_id, valores)
    dados_extras = models.JSONField(default=dict, blank=True)

    lida = models.BooleanField(default=False)
    data_leitura = models.DateTimeField(null=True, blank=True)

    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cadastros_notificacaosistema'
        verbose_name = 'Notificação do Sistema'
        verbose_name_plural = 'Notificações do Sistema'
        ordering = ['-criada_em']

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.titulo}"

    def marcar_como_lida(self):
        """Marca a notificação como lida."""
        if not self.lida:
            self.lida = True
            self.data_leitura = timezone.now()
            self.save(update_fields=['lida', 'data_leitura'])

    @classmethod
    def criar_alerta_limite(cls, usuario, conta_bancaria, percentual_atual, valor_atual, valor_limite):
        """Cria uma notificação de alerta de limite."""
        return cls.objects.create(
            usuario=usuario,
            tipo='alerta_limite',
            prioridade='alta' if percentual_atual >= 95 else 'media',
            titulo=f'Alerta: Limite MEI em {percentual_atual:.1f}%',
            mensagem=(
                f'A conta "{conta_bancaria.beneficiario or conta_bancaria.instituicao}" '
                f'atingiu {percentual_atual:.1f}% do limite MEI. '
                f'Valor atual: R$ {valor_atual:,.2f} / Limite: R$ {valor_limite:,.2f}'
            ),
            dados_extras={
                'conta_id': conta_bancaria.id,
                'percentual': float(percentual_atual),
                'valor_atual': float(valor_atual),
                'valor_limite': float(valor_limite),
            }
        )

    @classmethod
    def criar_alerta_mudanca_plano(cls, usuario, cliente, plano_antigo, plano_novo, impacto_valor,
                                   faturamento_conta_anterior=0, faturamento_conta_atual=0, conta_info=None,
                                   is_novo_cliente=False):
        """Cria uma notificação de mudança ou criação de plano que afeta o limite."""
        direcao = 'aumentou' if impacto_valor > 0 else 'diminuiu'

        if is_novo_cliente:
            # Novo cliente adicionado com plano
            titulo = f'Novo cliente: {cliente.nome}'
            mensagem = f'O cliente "{cliente.nome}" foi adicionado com o plano {plano_novo}. '

            if conta_info:
                mensagem += (
                    f'O faturamento anual previsto para a conta "{conta_info}" aumentou '
                    f'para R$ {faturamento_conta_atual:,.2f}.'
                )
            else:
                mensagem += f'O faturamento anual previsto aumentou em R$ {abs(impacto_valor):,.2f}.'
        else:
            # Cliente existente mudou de plano
            titulo = f'Mudança de plano: {cliente.nome}'
            mensagem = f'O cliente "{cliente.nome}" mudou do plano {plano_antigo} para {plano_novo}. '

            if conta_info:
                mensagem += (
                    f'O faturamento anual previsto para a conta "{conta_info}" {direcao} '
                    f'em R$ {abs(impacto_valor):,.2f}, saindo de R$ {faturamento_conta_anterior:,.2f} '
                    f'para R$ {faturamento_conta_atual:,.2f}.'
                )
            else:
                mensagem += f'O faturamento anual previsto {direcao} em R$ {abs(impacto_valor):,.2f}.'

        return cls.objects.create(
            usuario=usuario,
            tipo='mudanca_plano',
            prioridade='alta' if impacto_valor > 0 else 'baixa',
            titulo=titulo,
            mensagem=mensagem,
            dados_extras={
                'cliente_id': cliente.id,
                'cliente_nome': cliente.nome,
                'plano_antigo': plano_antigo,
                'plano_novo': plano_novo,
                'impacto_valor': float(impacto_valor),
                'faturamento_conta_anterior': float(faturamento_conta_anterior),
                'faturamento_conta_atual': float(faturamento_conta_atual),
                'conta_info': conta_info,
                'is_novo_cliente': is_novo_cliente,
            }
        )


class PushSubscription(models.Model):
    """
    Armazena subscriptions de Web Push Notifications para cada usuário/dispositivo.

    Permite enviar notificações push para o navegador do usuário mesmo
    quando ele não está com a página aberta.
    """
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='push_subscriptions'
    )
    endpoint = models.TextField(
        help_text='URL do endpoint de push do navegador'
    )
    p256dh = models.CharField(
        max_length=255,
        help_text='Chave pública p256dh do cliente'
    )
    auth = models.CharField(
        max_length=255,
        help_text='Chave de autenticação do cliente'
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='User-Agent do navegador (para identificação)'
    )
    ativo = models.BooleanField(
        default=True,
        help_text='Se False, a subscription expirou ou foi cancelada'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cadastros_pushsubscription'
        verbose_name = 'Push Subscription'
        verbose_name_plural = 'Push Subscriptions'
        unique_together = ('usuario', 'endpoint')
        indexes = [
            models.Index(fields=['usuario', 'ativo']),
        ]

    def __str__(self):
        return f"Push: {self.usuario.username} ({self.endpoint[:50]}...)"


class ClienteContaBancaria(models.Model):
    """
    Associação de clientes a contas bancárias (formas de pagamento com API).

    REGRA IMPORTANTE: Um cliente só pode estar associado a UMA conta bancária ativa por vez.
    Isso garante controle financeiro adequado para limites MEI e evita duplicidade de cobranças.
    """
    cliente = models.ForeignKey(
        'Cliente',
        on_delete=models.CASCADE,
        related_name='contas_bancarias_associadas'
    )
    conta_bancaria = models.ForeignKey(
        ContaBancaria,
        on_delete=models.CASCADE,
        related_name='clientes_associados'
    )
    ativo = models.BooleanField(
        default=True,
        verbose_name='Ativo',
        help_text='Indica se esta associação está ativa. Cliente só pode ter UMA associação ativa.'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cadastros_clientecontabancaria'
        verbose_name = "Cliente - Conta Bancária"
        verbose_name_plural = "Clientes - Contas Bancárias"
        unique_together = [['cliente', 'conta_bancaria']]

    def __str__(self):
        status = "✓" if self.ativo else "✗"
        return f"{status} {self.cliente.nome} → {self.conta_bancaria.nome_identificacao}"

    def clean(self):
        """Validações customizadas."""
        from django.core.exceptions import ValidationError

        # REGRA: Cliente só pode ter UMA associação ATIVA
        if self.ativo:
            associacao_existente = ClienteContaBancaria.objects.filter(
                cliente=self.cliente,
                ativo=True
            ).exclude(pk=self.pk).first()

            if associacao_existente:
                raise ValidationError({
                    'cliente': f'Este cliente já está associado à conta "{associacao_existente.conta_bancaria.nome_identificacao}". '
                               f'Desative a associação existente antes de criar uma nova.'
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def transferir_cliente(cls, cliente, nova_conta, usuario=None):
        """
        Transfere um cliente de uma conta bancária para outra.
        Desativa associação anterior e cria nova associação.

        Retorna: (nova_associacao, associacao_antiga ou None)
        """
        from .models import NotificacaoSistema
        from decimal import Decimal

        # Mapear pagamentos por ano
        PAGAMENTOS_POR_ANO = {
            'Mensal': 12,
            'Bimestral': 6,
            'Trimestral': 4,
            'Semestral': 2,
            'Anual': 1,
        }

        # Buscar associação ativa existente
        associacao_antiga = cls.objects.filter(
            cliente=cliente,
            ativo=True
        ).first()

        # Desativar associação antiga
        conta_antiga_nome = None
        conta_antiga = None
        if associacao_antiga:
            conta_antiga = associacao_antiga.conta_bancaria
            conta_antiga_nome = conta_antiga.nome_identificacao
            associacao_antiga.ativo = False
            associacao_antiga.save(update_fields=['ativo', 'atualizado_em'])

        # Criar ou reativar associação com nova conta
        nova_associacao, created = cls.objects.update_or_create(
            cliente=cliente,
            conta_bancaria=nova_conta,
            defaults={'ativo': True}
        )

        # Criar notificação de transferência (se houver mudança)
        if usuario and associacao_antiga and conta_antiga != nova_conta:
            try:
                # Calcular valor anual do cliente
                valor_cliente_anual = Decimal('0')
                if cliente.plano:
                    pagamentos = PAGAMENTOS_POR_ANO.get(cliente.plano.nome, 12)
                    valor_cliente_anual = cliente.plano.valor * pagamentos

                # Calcular faturamento da conta antiga (após remoção do cliente)
                faturamento_conta_antiga = Decimal('0')
                clientes_conta_antiga = cls.objects.filter(
                    conta_bancaria=conta_antiga,
                    ativo=True,
                    cliente__cancelado=False
                ).select_related('cliente__plano')
                for cc in clientes_conta_antiga:
                    if cc.cliente.plano:
                        pagamentos = PAGAMENTOS_POR_ANO.get(cc.cliente.plano.nome, 12)
                        faturamento_conta_antiga += cc.cliente.plano.valor * pagamentos

                # Calcular faturamento da conta nova (após adição do cliente)
                faturamento_conta_nova = Decimal('0')
                clientes_conta_nova = cls.objects.filter(
                    conta_bancaria=nova_conta,
                    ativo=True,
                    cliente__cancelado=False
                ).select_related('cliente__plano')
                for cc in clientes_conta_nova:
                    if cc.cliente.plano:
                        pagamentos = PAGAMENTOS_POR_ANO.get(cc.cliente.plano.nome, 12)
                        faturamento_conta_nova += cc.cliente.plano.valor * pagamentos

                mensagem = (
                    f'O cliente "{cliente.nome}" foi transferido de '
                    f'"{conta_antiga_nome}" para "{nova_conta.nome_identificacao}". '
                    f'O faturamento anual da conta "{conta_antiga_nome}" diminuiu em '
                    f'R$ {valor_cliente_anual:,.2f} e agora é R$ {faturamento_conta_antiga:,.2f}. '
                    f'O faturamento anual da conta "{nova_conta.nome_identificacao}" aumentou em '
                    f'R$ {valor_cliente_anual:,.2f} e agora é R$ {faturamento_conta_nova:,.2f}.'
                )

                NotificacaoSistema.objects.create(
                    usuario=usuario,
                    tipo='info',
                    prioridade='baixa',
                    titulo=f'Cliente transferido: {cliente.nome}',
                    mensagem=mensagem,
                    dados_extras={
                        'cliente_id': cliente.id,
                        'cliente_nome': cliente.nome,
                        'conta_antiga': conta_antiga_nome,
                        'conta_nova': nova_conta.nome_identificacao,
                        'valor_cliente_anual': float(valor_cliente_anual),
                        'faturamento_conta_antiga': float(faturamento_conta_antiga),
                        'faturamento_conta_nova': float(faturamento_conta_nova),
                    }
                )
            except Exception:
                pass  # Não falhar se notificação der erro

        return nova_associacao, associacao_antiga


class CobrancaPix(models.Model):
    """
    Armazena cobranças PIX geradas via integração com APIs.
    Relaciona com mensalidades e permite rastreamento de pagamentos.
    """
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('paid', 'Pago'),
        ('expired', 'Expirado'),
        ('cancelled', 'Cancelado'),
        ('refunded', 'Estornado'),
        ('error', 'Erro'),
    ]

    # Identificação
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(
        max_length=255,
        verbose_name="ID da Transação",
        help_text="ID retornado pela API de pagamento"
    )

    # Relacionamentos
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='cobrancas_pix'
    )
    conta_bancaria = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name='cobrancas_pix',
        verbose_name="Conta Bancária"
    )
    mensalidade = models.ForeignKey(
        'Mensalidade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cobrancas_pix',
        verbose_name="Mensalidade"
    )
    cliente = models.ForeignKey(
        'Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cobrancas_pix',
        verbose_name="Cliente"
    )

    # Dados da cobrança
    valor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Valor (R$)"
    )
    descricao = models.CharField(
        max_length=255,
        verbose_name="Descrição"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Status"
    )

    # Dados PIX
    qr_code = models.TextField(
        blank=True,
        verbose_name="QR Code",
        help_text="Código EMV para gerar imagem do QR Code"
    )
    qr_code_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="URL do QR Code",
        help_text="Link para visualizar/compartilhar o QR Code"
    )
    qr_code_base64 = models.TextField(
        blank=True,
        verbose_name="QR Code Base64",
        help_text="Imagem do QR Code em base64"
    )
    pix_copia_cola = models.TextField(
        blank=True,
        verbose_name="PIX Copia e Cola",
        help_text="Código para copiar e colar"
    )

    # Datas
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    expira_em = models.DateTimeField(
        verbose_name="Expira em",
        help_text="Data/hora de expiração da cobrança"
    )
    pago_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Pago em"
    )

    # Dados do pagador (preenchidos após pagamento)
    pagador_nome = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Nome do Pagador"
    )
    pagador_documento = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="CPF/CNPJ do Pagador"
    )

    # Valores financeiros (preenchidos após pagamento)
    valor_recebido = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Valor Recebido (R$)",
        help_text="Valor líquido após taxas"
    )
    valor_taxa = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Taxa (R$)",
        help_text="Taxa cobrada pela integração"
    )

    # Metadados
    integracao = models.CharField(
        max_length=50,
        verbose_name="Integração",
        help_text="fastdepix, mercado_pago, efi_bank"
    )
    raw_response = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Resposta Raw",
        help_text="Resposta completa da API"
    )
    webhook_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Dados Webhook",
        help_text="Dados recebidos via webhook"
    )

    class Meta:
        db_table = 'pagamentos_cobranca_pix'
        verbose_name = "Cobrança PIX"
        verbose_name_plural = "Cobranças PIX"
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['status']),
            models.Index(fields=['usuario', 'status']),
            models.Index(fields=['mensalidade']),
        ]

    def __str__(self):
        return f"PIX {self.transaction_id[:8]}... - R$ {self.valor} ({self.get_status_display()})"

    @property
    def is_expired(self):
        """Verifica se a cobrança está expirada."""
        if self.status == 'expired':
            return True
        if self.status == 'pending' and self.expira_em:
            return timezone.now() > self.expira_em
        return False

    @property
    def is_paid(self):
        """Verifica se a cobrança foi paga."""
        return self.status == 'paid'

    @property
    def can_cancel(self):
        """Verifica se a cobrança pode ser cancelada."""
        return self.status == 'pending' and not self.is_expired

    def mark_as_paid(self, paid_at=None, payer_name=None, payer_document=None, webhook_data=None, valor_recebido=None, valor_taxa=None):
        """
        Marca a cobrança como paga e atualiza a mensalidade relacionada.

        Aplica o pagamento na mensalidade:
        - Define dt_pagamento com a data do pagamento
        - Define pgto = True

        O save() da mensalidade dispara os signals:
        - pre_save: criar_nova_mensalidade (cria próxima mensalidade)
        - post_save: atualiza_ultimo_pagamento (atualiza cliente.ultimo_pagamento)
        """
        import logging
        from decimal import Decimal
        logger = logging.getLogger(__name__)

        self.status = 'paid'
        self.pago_em = paid_at or timezone.now()
        if payer_name:
            self.pagador_nome = payer_name
        if payer_document:
            self.pagador_documento = payer_document
        if webhook_data:
            self.webhook_data = webhook_data

        # Extrair valores financeiros do webhook_data se não fornecidos diretamente
        if webhook_data and isinstance(webhook_data, dict):
            data = webhook_data.get('data', webhook_data)

            # Tentar extrair valor recebido (líquido)
            if valor_recebido is None:
                # FastDePix usa commission_amount como valor líquido real
                for key in ['commission_amount', 'net_amount', 'amount_received', 'liquid_value', 'valor_liquido']:
                    if key in data and data[key] is not None:
                        try:
                            valor_recebido = Decimal(str(data[key]))
                        except (ValueError, TypeError):
                            pass
                        break

            # Tentar extrair taxa
            if valor_taxa is None:
                for key in ['fee', 'tax', 'taxa', 'fee_amount', 'valor_taxa']:
                    if key in data and data[key] is not None:
                        try:
                            valor_taxa = Decimal(str(data[key]))
                        except (ValueError, TypeError):
                            pass
                        break

        # Se temos valor_recebido mas não valor_taxa, calcular taxa
        if valor_recebido is not None and valor_taxa is None and self.valor:
            valor_taxa = self.valor - valor_recebido

        # Se temos valor_taxa mas não valor_recebido, calcular valor_recebido
        if valor_taxa is not None and valor_recebido is None and self.valor:
            valor_recebido = self.valor - valor_taxa

        # Salvar valores financeiros
        if valor_recebido is not None:
            self.valor_recebido = valor_recebido
        if valor_taxa is not None:
            self.valor_taxa = valor_taxa

        self.save()

        # Atualizar mensalidade se existir
        if self.mensalidade_id:
            # Buscar mensalidade fresca do banco com relacionamentos necessários
            # Isso garante que os signals tenham acesso a cliente.plano, etc.
            # Usa select_for_update para evitar processamento duplicado (race condition)
            from nossopainel.models import Mensalidade
            from django.db import transaction

            try:
                with transaction.atomic():
                    # Bloqueia a mensalidade para evitar processamento duplicado
                    try:
                        mensalidade = Mensalidade.objects.select_for_update(nowait=True).select_related(
                            'cliente',
                            'cliente__plano',
                            'usuario'
                        ).get(pk=self.mensalidade_id)
                    except Exception as lock_error:
                        # Se não conseguiu obter lock, outra requisição está processando
                        if 'lock' in str(lock_error).lower():
                            logger.info(
                                f'[CobrancaPix] Mensalidade {self.mensalidade_id} está sendo processada '
                                f'por outra requisição. Ignorando (cobrança {self.id})'
                            )
                            return
                        raise

                    # Verifica se a mensalidade ainda não foi paga
                    if not mensalidade.pgto:
                        # PROTEÇÃO ADICIONAL: Verificar se já existe mensalidade futura
                        # Isso indica que o pagamento já foi processado por outra requisição
                        mensalidade_futura_existe = Mensalidade.objects.filter(
                            cliente=mensalidade.cliente,
                            dt_vencimento__gt=mensalidade.dt_vencimento,
                            pgto=False,
                            cancelado=False
                        ).exists()

                        if mensalidade_futura_existe:
                            logger.warning(
                                f'[CobrancaPix] Mensalidade futura já existe para cliente {mensalidade.cliente.nome}. '
                                f'Pagamento já foi processado por outra requisição (cobrança {self.id})'
                            )
                            # Marca a mensalidade como paga mesmo assim para manter consistência
                            mensalidade.dt_pagamento = self.pago_em.date()
                            mensalidade.pgto = True
                            # Registra a forma de pagamento usada (histórico imutável)
                            if not mensalidade.forma_pgto:
                                mensalidade.forma_pgto = mensalidade.cliente.forma_pgto
                            mensalidade.save()
                            return

                        mensalidade.dt_pagamento = self.pago_em.date()
                        mensalidade.pgto = True
                        # Registra a forma de pagamento usada (histórico imutável)
                        if not mensalidade.forma_pgto:
                            mensalidade.forma_pgto = mensalidade.cliente.forma_pgto
                        mensalidade.save()  # Dispara signals: criar_nova_mensalidade, atualiza_ultimo_pagamento

                        logger.info(
                            f'[CobrancaPix] Mensalidade {mensalidade.id} marcada como PAGA '
                            f'via PIX (cobrança {self.id}) - '
                            f'Cliente: {mensalidade.cliente.nome} - '
                            f'Signals de criação de nova mensalidade disparados'
                        )

                        # === NOTIFICAÇÕES DE PAGAMENTO CONFIRMADO ===
                        self._enviar_notificacoes_pagamento(mensalidade, logger)

                    else:
                        logger.warning(
                            f'[CobrancaPix] Mensalidade {mensalidade.id} já estava paga, '
                            f'ignorando atualização (cobrança {self.id})'
                        )

            except Mensalidade.DoesNotExist:
                logger.error(
                    f'[CobrancaPix] Mensalidade {self.mensalidade_id} não encontrada '
                    f'ao marcar cobrança {self.id} como paga'
                )

    def mark_as_expired(self):
        """Marca a cobrança como expirada."""
        if self.status == 'pending':
            self.status = 'expired'
            self.save()

    def mark_as_cancelled(self):
        """Marca a cobrança como cancelada."""
        if self.status == 'pending':
            self.status = 'cancelled'
            self.save()

    def _enviar_notificacoes_pagamento(self, mensalidade, logger):
        """
        Envia notificações após confirmação de pagamento via PIX.

        1. Cria notificação interna no sistema (NotificacaoSistema)
        2. Envia mensagem WhatsApp de confirmação
        3. Envia push notification no browser (se configurado)
        """
        cliente = mensalidade.cliente
        primeiro_nome = cliente.nome.split()[0] if cliente.nome else "Cliente"

        # 1. Criar notificação interna no sistema
        try:
            NotificacaoSistema.objects.create(
                usuario=self.usuario,
                tipo='pagamento_confirmado',
                prioridade='media',
                titulo='Pagamento PIX Confirmado',
                mensagem=f'Pagamento de R$ {self.valor:.2f} confirmado para {cliente.nome}',
                dados_extras={
                    'cobranca_id': str(self.id),
                    'cliente_id': cliente.id,
                    'cliente_nome': cliente.nome,
                    'valor': str(self.valor),
                    'mensalidade_id': mensalidade.id,
                    'pago_em': self.pago_em.isoformat() if self.pago_em else None,
                }
            )
            logger.info(f'[CobrancaPix] Notificação interna criada para pagamento {self.id}')
        except Exception as e:
            logger.error(f'[CobrancaPix] Erro ao criar notificação interna: {e}')

        # 2. Enviar mensagem WhatsApp de confirmação
        if cliente.telefone and not cliente.nao_enviar_msgs:
            try:
                # Verificar se é a primeira mensalidade paga do cliente
                qtd_mensalidades_pagas = Mensalidade.objects.filter(
                    cliente=cliente,
                    pgto=True
                ).count()

                if qtd_mensalidades_pagas == 1:
                    # Primeira mensalidade paga - enviar mensagem de boas-vindas
                    logger.info(f'[CobrancaPix] Primeira mensalidade paga - enviando boas-vindas para {cliente.nome}')
                    from nossopainel.utils import envio_apos_novo_cadastro
                    envio_apos_novo_cadastro(cliente)
                else:
                    # Mensalidades subsequentes - enviar confirmação padrão
                    from nossopainel.services.wpp import send_message, MessageSendConfig, get_active_token, LogTemplates

                    token = get_active_token(self.usuario.username)
                    if token:
                        mensagem_wpp = (
                            f"Obrigado, {primeiro_nome}. O seu pagamento foi confirmado!"
                            f"\nConfira o seu acesso ao nosso sistema e nos informe se pudermos "
                            f"ajudar com qualquer dificuldade!"
                        )

                        # Configurar log_writer e templates para MessageSendConfig
                        log_writer = lambda msg: logger.info(f'[WhatsApp] {msg}')
                        log_templates = LogTemplates(
                            success="[{0}] Mensagem {1} enviada com sucesso para {3}",
                            failure="[{0}] Falha ao enviar {1} para {3}: {6}",
                            invalid="[{0}] Telefone inválido para {1} - {3}",
                        )

                        config = MessageSendConfig(
                            usuario=self.usuario.username,
                            token=token,
                            telefone=cliente.telefone,
                            mensagem=mensagem_wpp,
                            tipo_envio='confirmacao_pagamento',
                            cliente=cliente,
                            log_writer=log_writer,
                            log_templates=log_templates,
                        )
                        time.sleep(5)  # Aguarda 5 segundos antes de enviar a confirmação
                        send_message(config)
                        logger.info(f'[CobrancaPix] Mensagem WhatsApp enviada para {cliente.telefone}')
                    else:
                        logger.warning(f'[CobrancaPix] Token WPP não encontrado para usuário {self.usuario.username}')
            except Exception as e:
                logger.error(f'[CobrancaPix] Erro ao enviar WhatsApp: {e}')

        # 3. Enviar push notification (se houver subscriptions ativas)
        try:
            from nossopainel.services.push_notifications import enviar_push_pagamento
            enviar_push_pagamento(
                usuario=self.usuario,
                titulo='Pagamento PIX Confirmado',
                mensagem=f'R$ {self.valor:.2f} - {cliente.nome}',
                dados={
                    'url': f'/admin/clientes/{cliente.id}/',
                    'cobranca_id': str(self.id),
                }
            )
            logger.info(f'[CobrancaPix] Push notification enviado para usuário {self.usuario.id}')
        except ImportError:
            # Serviço de push ainda não implementado
            pass
        except Exception as e:
            logger.error(f'[CobrancaPix] Erro ao enviar push notification: {e}')


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
        db_table = 'cadastros_userprofile'
        verbose_name = "Perfil de Usuário"
        verbose_name_plural = "Perfis de Usuários"

    def __str__(self):
        return f'Perfil de {self.user.username}'


class MensagemEnviadaWpp(models.Model):
    """
    Registra o histórico de mensagens enviadas ao WhatsApp.

    CONSTRAINT UNIQUE:
    Previne envio duplicado para o mesmo telefone no mesmo dia pelo mesmo usuário.
    Protege contra race conditions em requests concorrentes.
    """
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    telefone = models.CharField(max_length=20)
    data_envio = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'cadastros_mensagemenviadawpp'
        verbose_name = "Mensagem Enviada ao WhatsApp"
        verbose_name_plural = "Mensagens Enviadas ao WhatsApp"
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'telefone', 'data_envio'],
                name='unique_msg_por_usuario_telefone_dia'
            )
        ]

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
        db_table = 'cadastros_conteudom3u8'
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
        db_table = 'cadastros_dominiosdns'
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
    valido = models.BooleanField(
        default=True,
        verbose_name='Válido',
        help_text='Indica se o número foi validado no WhatsApp. Números inválidos são marcados como False ao invés de deletados.'
    )
    data_validacao = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Data da Validação',
        help_text='Data/hora da última validação do número'
    )
    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado Em'
    )

    class Meta:
        db_table = 'cadastros_telefoneleads'
        verbose_name = 'Telefone Lead'
        verbose_name_plural = 'Telefones Leads'
        indexes = [
            models.Index(fields=['usuario', 'valido'], name='lead_usr_valido_idx'),
        ]

    def __str__(self):
        status = "✓" if self.valido else "✗"
        return f"[{status}] {self.telefone}"
    

class EnviosLeads(models.Model):
    """Registra os envios de mensagens para os leads coletados."""
    telefone = models.CharField(max_length=20)
    data_envio = models.DateTimeField(auto_now_add=True)
    mensagem = models.TextField()
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        db_table = 'cadastros_enviosleads'
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
        db_table = 'cadastros_mensagensleads'
        verbose_name_plural = "Mensagens Leads"

    def __str__(self):
        return self.tipo


class NotificationRead(models.Model):
    """Registra notificações de mensalidade marcadas como lidas."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications_read")
    mensalidade = models.ForeignKey(Mensalidade, on_delete=models.CASCADE, related_name="notifications_read")
    marcado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cadastros_notificationread'
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
    ACTION_MIGRATION = "migration"
    ACTION_OTHER = "other"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Criação"),
        (ACTION_UPDATE, "Atualização"),
        (ACTION_DELETE, "Exclusão"),
        (ACTION_IMPORT, "Importação"),
        (ACTION_CANCEL, "Cancelamento"),
        (ACTION_REACTIVATE, "Reativação"),
        (ACTION_PAYMENT, "Pagamento"),
        (ACTION_MIGRATION, "Migração"),
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
        db_table = 'cadastros_useractionlog'
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
        db_table = 'cadastros_loginlog'
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


class ContaReseller(models.Model):
    """
    Armazena credenciais e sessão de autenticação para painéis reseller de aplicativos IPTV.

    Suporta login manual com reCAPTCHA e reutilização de sessão para evitar logins repetidos.
    A senha é criptografada usando Fernet antes de ser armazenada no banco.
    """

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='contas_reseller',
        help_text='Usuário proprietário desta conta reseller'
    )
    aplicativo = models.ForeignKey(
        Aplicativo,
        on_delete=models.CASCADE,
        related_name='contas_reseller',
        help_text='Aplicativo/plataforma do reseller (ex: DreamTV, NetFlox)'
    )
    email_login = models.EmailField(
        max_length=255,
        verbose_name='Email/Usuário',
        help_text='Email ou username usado para login no painel reseller'
    )
    senha_login = models.CharField(
        max_length=500,
        verbose_name='Senha',
        help_text='Senha criptografada com Fernet'
    )
    session_data = models.TextField(
        blank=True,
        verbose_name='Dados de Sessão',
        help_text='JSON contendo cookies e localStorage para reutilização de sessão'
    )
    ultimo_login = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Último Login',
        help_text='Data/hora do último login manual bem-sucedido'
    )
    sessao_valida = models.BooleanField(
        default=False,
        verbose_name='Sessão Válida',
        help_text='Indica se a sessão armazenada ainda está ativa'
    )
    login_progresso = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='Progresso do Login',
        help_text='Etapa atual do processo de login automático',
        choices=[
            ('', 'Não iniciado'),
            ('conectando', 'Conectando ao painel'),
            ('pagina_carregada', 'Página carregada'),
            ('resolvendo_captcha', 'Resolvendo reCAPTCHA'),
            ('captcha_resolvido', 'reCAPTCHA resolvido'),
            ('validando', 'Validando credenciais'),
            ('concluido', 'Login concluído'),
            ('erro', 'Erro no login'),
        ]
    )
    data_criacao = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Data de Criação'
    )
    data_atualizacao = models.DateTimeField(
        auto_now=True,
        verbose_name='Última Atualização'
    )

    class Meta:
        db_table = 'cadastros_contareseller'
        verbose_name = 'Conta de Reseller'
        verbose_name_plural = 'Contas de Reseller'
        unique_together = [['usuario', 'aplicativo']]
        ordering = ['-data_atualizacao']
        indexes = [
            models.Index(fields=['usuario', 'aplicativo'], name='conta_reseller_user_app_idx'),
        ]

    def __str__(self):
        return f"{self.usuario.username} - {self.aplicativo.nome} ({self.email_login})"


class TarefaMigracaoDNS(models.Model):
    """
    Registra execuções de migração de domínios DNS para dispositivos IPTV.

    Cada tarefa pode atualizar um dispositivo específico ou todos os dispositivos
    do usuário no painel reseller.
    """

    STATUS_AGUARDANDO_LOGIN = 'aguardando_login'
    STATUS_INICIANDO = 'iniciando'
    STATUS_EM_ANDAMENTO = 'em_andamento'
    STATUS_CONCLUIDA = 'concluida'
    STATUS_ERRO_LOGIN = 'erro_login'
    STATUS_CANCELADA = 'cancelada'

    STATUS_CHOICES = [
        (STATUS_AGUARDANDO_LOGIN, 'Aguardando Login'),
        (STATUS_INICIANDO, 'Iniciando'),
        (STATUS_EM_ANDAMENTO, 'Em Andamento'),
        (STATUS_CONCLUIDA, 'Concluída'),
        (STATUS_ERRO_LOGIN, 'Erro no Login'),
        (STATUS_CANCELADA, 'Cancelada'),
    ]

    TIPO_TODOS = 'todos'
    TIPO_ESPECIFICO = 'especifico'

    TIPO_CHOICES = [
        (TIPO_TODOS, 'Todos os Dispositivos'),
        (TIPO_ESPECIFICO, 'Dispositivo Específico'),
    ]

    # Relacionamentos
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tarefas_migracao_dns',
        help_text='Usuário que iniciou a migração'
    )
    aplicativo = models.ForeignKey(
        Aplicativo,
        on_delete=models.CASCADE,
        related_name='tarefas_migracao_dns',
        help_text='Aplicativo/plataforma onde a migração será executada'
    )
    conta_reseller = models.ForeignKey(
        ContaReseller,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tarefas_migracao',
        help_text='Conta reseller usada para executar a migração'
    )

    # Configuração da migração
    tipo_migracao = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default=TIPO_ESPECIFICO,
        verbose_name='Tipo de Migração',
        help_text='Se migração é para todos os dispositivos ou apenas um específico'
    )
    mac_alvo = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='MAC Alvo',
        help_text='MAC Address do dispositivo específico (se tipo_migracao=especifico)'
    )

    # Domínios DNS (protocolo + host + porta opcional)
    dominio_origem = models.CharField(
        max_length=255,
        verbose_name='Domínio Origem',
        help_text='Domínio DNS atual (protocolo + host + porta, ex: http://dominio.com:8080)'
    )
    dominio_destino = models.CharField(
        max_length=255,
        verbose_name='Domínio Destino',
        help_text='Novo domínio DNS (protocolo + host + porta, ex: http://dominio-novo.com)'
    )

    # Status e progresso
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_INICIANDO,
        db_index=True
    )
    total_dispositivos = models.IntegerField(
        default=0,
        verbose_name='Total de Dispositivos',
        help_text='Quantidade total de dispositivos a serem migrados'
    )
    processados = models.IntegerField(
        default=0,
        verbose_name='Dispositivos Processados',
        help_text='Quantidade de dispositivos já processados'
    )
    sucessos = models.IntegerField(
        default=0,
        verbose_name='Sucessos',
        help_text='Quantidade de dispositivos migrados com sucesso'
    )
    falhas = models.IntegerField(
        default=0,
        verbose_name='Falhas',
        help_text='Quantidade de dispositivos com erro na migração'
    )

    pulados = models.IntegerField(
        default=0,
        verbose_name='Pulados',
        help_text='Quantidade de dispositivos pulados (DNS não corresponde ao domínio origem)'
    )

    # Campos de progresso em tempo real (UX)
    etapa_atual = models.CharField(
        max_length=50,
        default='iniciando',
        verbose_name='Etapa Atual',
        help_text='Etapa atual da execução (iniciando, analisando, processando, concluida, cancelada)'
    )
    mensagem_progresso = models.TextField(
        blank=True,
        verbose_name='Mensagem de Progresso',
        help_text='Mensagem dinâmica exibida durante a execução'
    )
    progresso_percentual = models.IntegerField(
        default=0,
        verbose_name='Progresso (%)',
        help_text='Percentual de conclusão da tarefa (0-100)'
    )

    # Timestamps
    criada_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Data de Criação'
    )
    iniciada_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Data de Início',
        help_text='Quando a execução efetivamente começou'
    )
    concluida_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Data de Conclusão'
    )

    # Erro geral (não específico de dispositivo)
    erro_geral = models.TextField(
        blank=True,
        verbose_name='Erro Geral',
        help_text='Mensagem de erro que impediu a execução da tarefa inteira'
    )

    # Otimização: cache temporário de devices (v2.0)
    cached_devices = models.TextField(
        null=True,
        blank=True,
        verbose_name='Cache de Devices',
        help_text='JSON temporário com devices do frontend (evita chamadas à API)'
    )

    class Meta:
        db_table = 'cadastros_tarefamigracaodns'
        verbose_name = 'Tarefa de Migração DNS'
        verbose_name_plural = 'Tarefas de Migração DNS'
        ordering = ['-criada_em']
        indexes = [
            models.Index(fields=['usuario', '-criada_em'], name='tarefa_dns_user_created_idx'),
            models.Index(fields=['status', '-criada_em'], name='tarefa_dns_status_idx'),
        ]

    def __str__(self):
        tipo_display = 'Todos' if self.tipo_migracao == self.TIPO_TODOS else f'MAC:{self.mac_alvo}'
        return f"Migração DNS #{self.id} - {tipo_display} - {self.get_status_display()}"

    def get_progresso_percentual(self):
        """Retorna o progresso em percentual (0-100)."""
        if self.total_dispositivos == 0:
            return 0
        return int((self.processados / self.total_dispositivos) * 100)

    def esta_concluida(self):
        """Verifica se a tarefa está em um estado final."""
        return self.status in [
            self.STATUS_CONCLUIDA,
            self.STATUS_ERRO_LOGIN,
            self.STATUS_CANCELADA
        ]


class DispositivoMigracaoDNS(models.Model):
    """
    Registra o status individual de cada dispositivo em uma tarefa de migração DNS.

    Permite rastrear exatamente quais dispositivos foram migrados com sucesso
    e quais falharam (com mensagens de erro específicas).
    """

    STATUS_PENDENTE = 'pendente'
    STATUS_PROCESSANDO = 'processando'
    STATUS_SUCESSO = 'sucesso'
    STATUS_ERRO = 'erro'
    STATUS_PULADO = 'pulado'

    STATUS_CHOICES = [
        (STATUS_PENDENTE, 'Pendente'),
        (STATUS_PROCESSANDO, 'Processando'),
        (STATUS_SUCESSO, 'Sucesso'),
        (STATUS_ERRO, 'Erro'),
        (STATUS_PULADO, 'Pulado'),
    ]

    tarefa = models.ForeignKey(
        TarefaMigracaoDNS,
        on_delete=models.CASCADE,
        related_name='dispositivos',
        help_text='Tarefa de migração à qual este dispositivo pertence'
    )
    device_id = models.CharField(
        max_length=100,
        verbose_name='MAC Address',
        help_text='Identificador do dispositivo (MAC Address)'
    )
    nome_dispositivo = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Nome/Comentário',
        help_text='Nome ou comentário do dispositivo no painel reseller'
    )

    # URLs DNS
    dns_encontrado = models.URLField(
        max_length=500,
        blank=True,
        verbose_name='DNS Encontrado',
        help_text='URL do DNS que estava configurada no painel antes da migração'
    )
    dns_atualizado = models.URLField(
        max_length=500,
        blank=True,
        verbose_name='DNS Atualizado',
        help_text='URL do DNS que foi configurada após a migração'
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDENTE,
        db_index=True
    )
    mensagem_erro = models.TextField(
        blank=True,
        verbose_name='Mensagem de Erro',
        help_text='Detalhes do erro ocorrido (se status=erro)'
    )
    processado_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Data de Processamento',
        help_text='Quando este dispositivo foi processado'
    )

    class Meta:
        db_table = 'cadastros_dispositivomigracaodns'
        verbose_name = 'Dispositivo em Migração'
        verbose_name_plural = 'Dispositivos em Migração'
        ordering = ['id']
        indexes = [
            models.Index(fields=['tarefa', 'status'], name='disp_dns_tarefa_status_idx'),
        ]

    def get_dns_encontrado_formatado(self):
        """Retorna apenas protocolo + domínio + porta do DNS encontrado."""
        from .utils import extrair_dominio_de_url
        return extrair_dominio_de_url(self.dns_encontrado) if self.dns_encontrado else '-'

    def get_dns_atualizado_formatado(self):
        """Retorna apenas protocolo + domínio + porta do DNS atualizado."""
        from .utils import extrair_dominio_de_url
        return extrair_dominio_de_url(self.dns_atualizado) if self.dns_atualizado else '-'

    def __str__(self):
        return f"{self.device_id} - {self.get_status_display()}"


class ConfiguracaoAutomacao(models.Model):
    """
    Configurações de automação por usuário (principalmente para debug).
    Permite controlar comportamento do Playwright (headless mode, etc).
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='config_automacao',
        verbose_name='Usuário'
    )
    debug_headless_mode = models.BooleanField(
        default=False,
        verbose_name='Modo Debug (Navegador Visível)',
        help_text='Quando ativado, o navegador Playwright ficará visível durante automações (útil para debug)'
    )
    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado Em'
    )
    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado Em'
    )

    class Meta:
        db_table = 'cadastros_configuracaoautomacao'
        verbose_name = 'Configuração de Automação'
        verbose_name_plural = 'Configurações de Automação'

    def __str__(self):
        status = "Debug ON" if self.debug_headless_mode else "Debug OFF"
        return f"{self.user.username} - {status}"


def tarefa_envio_imagem_upload_path(instance, filename):
    """
    Gera caminho de upload com UUID para imagens de tarefas de envio.
    Formato: tarefas_envio/<tipo_envio>/<uuid>.<ext>
    """
    ext = filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('tarefas_envio', instance.tipo_envio, filename)


class TarefaEnvio(models.Model):
    """
    Armazena as configurações de tarefas de envio de mensagens WhatsApp.
    Permite gerenciar envios programados por dia da semana, período do mês e horário.
    """

    # Choices para tipo de envio
    TIPO_ENVIO_CHOICES = [
        ('ativos', 'Clientes Ativos'),
        ('cancelados', 'Clientes Cancelados'),
        ('avulso', 'Leads (Avulso)'),
    ]

    # Choices para tipo de agendamento
    TIPO_AGENDAMENTO_CHOICES = [
        ('recorrente', 'Recorrente'),
        ('unico', 'Envio Único'),
    ]

    # Choices para período do mês
    PERIODO_CHOICES = [
        ('', 'Selecione o período'),
        ('1-10', 'Dias 1 a 10'),
        ('11-20', 'Dias 11 a 20'),
        ('21-31', 'Dias 21 a 31'),
        ('1-15', 'Primeira quinzena (1-15)'),
        ('16-31', 'Segunda quinzena (16-31)'),
        ('todos', 'Todos os dias do mês'),
    ]

    # Mapeamento de dias da semana (compatível com weekday() do Python)
    DIAS_SEMANA_MAP = {
        0: 'Segunda-feira',
        1: 'Terça-feira',
        2: 'Quarta-feira',
        3: 'Quinta-feira',
        4: 'Sexta-feira',
        5: 'Sábado',
        6: 'Domingo',
    }

    # Campos principais
    nome = models.CharField(
        max_length=100,
        verbose_name='Nome da Tarefa',
        help_text='Nome identificador da tarefa (ex: "Promoção Natal Ativos")'
    )

    tipo_envio = models.CharField(
        max_length=20,
        choices=TIPO_ENVIO_CHOICES,
        verbose_name='Tipo de Envio',
        help_text='Público-alvo do envio'
    )

    # Dias da semana - armazenado como JSON array [0,1,2,3,4,5,6]
    dias_semana = models.JSONField(
        default=list,
        verbose_name='Dias da Semana',
        help_text='Lista de dias da semana para execução (0=Segunda, 6=Domingo)'
    )

    # Período do mês
    periodo_mes = models.CharField(
        max_length=10,
        choices=PERIODO_CHOICES,
        blank=False,
        verbose_name='Período do Mês',
        help_text='Intervalo de dias do mês para execução'
    )

    # Horário de envio
    horario = models.TimeField(
        verbose_name='Horário',
        help_text='Horário do dia para início dos envios'
    )

    # Imagem (opcional)
    imagem = models.ImageField(
        upload_to=tarefa_envio_imagem_upload_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'gif', 'webp'])],
        verbose_name='Imagem',
        help_text='Imagem a ser enviada (opcional). Max 5MB. Formatos: JPG, PNG, GIF, WEBP'
    )

    # Mensagem com formatação HTML (Quill)
    mensagem = models.TextField(
        verbose_name='Mensagem',
        help_text='Texto da mensagem (suporta negrito e itálico)'
    )

    # Mensagem em formato plaintext para envio WhatsApp
    mensagem_plaintext = models.TextField(
        blank=True,
        verbose_name='Mensagem (Plaintext)',
        help_text='Versão plaintext da mensagem com formatação WhatsApp (gerada automaticamente)'
    )

    # Status e controle
    ativo = models.BooleanField(
        default=True,
        verbose_name='Ativo',
        help_text='Se desativado, a tarefa não será executada'
    )

    em_execucao = models.BooleanField(
        default=False,
        verbose_name='Em Execução',
        help_text='Indica se a tarefa está sendo executada no momento'
    )

    execucao_iniciada_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Execução Iniciada Em',
        help_text='Data/hora do início da execução atual'
    )

    ultimo_envio = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Último Envio',
        help_text='Data/hora da última execução'
    )

    total_envios = models.PositiveIntegerField(
        default=0,
        verbose_name='Total de Envios',
        help_text='Contador total de mensagens enviadas'
    )

    # Segmentação geográfica
    filtro_estados = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Filtro por Estados',
        help_text='Lista de UFs para filtrar clientes (vazio = todos)'
    )

    filtro_cidades = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Filtro por Cidades',
        help_text='Lista de cidades para filtrar clientes (vazio = todas)'
    )

    # Dias mínimos de cancelamento (apenas para tipo_envio='cancelados')
    dias_cancelamento = models.PositiveIntegerField(
        default=10,
        verbose_name='Dias de Cancelamento',
        help_text='Quantidade mínima de dias desde o cancelamento para incluir o cliente (apenas para tipo "Cancelados")'
    )

    # Pausa temporária
    pausado_ate = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Pausado Até',
        help_text='Data/hora até quando a tarefa está pausada'
    )

    # Tipo de agendamento (recorrente ou único)
    tipo_agendamento = models.CharField(
        max_length=20,
        choices=TIPO_AGENDAMENTO_CHOICES,
        default='recorrente',
        verbose_name='Tipo de Agendamento',
        help_text='Recorrente: repete nos dias selecionados. Único: executa apenas uma vez na data específica.'
    )

    # Data para envio único
    data_envio_unico = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data do Envio Único',
        help_text='Data específica para envio único (ignora dias da semana)'
    )

    # Metadados
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tarefas_envio',
        verbose_name='Usuário'
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado Em'
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado Em'
    )

    class Meta:
        db_table = 'cadastros_tarefaenvio'
        verbose_name = 'Tarefa de Envio'
        verbose_name_plural = 'Tarefas de Envio'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['usuario', 'tipo_envio', 'ativo'], name='tarefa_usr_tipo_ativo_idx'),
            models.Index(fields=['ativo', 'horario'], name='tarefa_ativo_horario_idx'),
        ]

    def __str__(self):
        status = "✓" if self.ativo else "✗"
        return f"[{status}] {self.nome} ({self.get_tipo_envio_display()})"

    def get_dias_semana_display(self):
        """Retorna lista legível dos dias selecionados."""
        if not self.dias_semana:
            return []
        return [self.DIAS_SEMANA_MAP.get(d, '') for d in self.dias_semana if d in self.DIAS_SEMANA_MAP]

    def get_dias_semana_abrev(self):
        """Retorna lista abreviada dos dias (Seg, Ter, Qua...)."""
        abrev = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sáb', 6: 'Dom'}
        if not self.dias_semana:
            return []
        return [abrev.get(d, '') for d in self.dias_semana if d in abrev]

    def esta_pausada(self):
        """Verifica se a tarefa está temporariamente pausada."""
        if self.pausado_ate:
            return timezone.localtime() < self.pausado_ate
        return False

    def get_pausado_ate_display(self):
        """Retorna a data de retorno formatada."""
        if self.pausado_ate:
            return self.pausado_ate.strftime('%d/%m/%Y %H:%M')
        return None

    def deve_executar_hoje(self):
        """Verifica se a tarefa deve executar no dia atual."""
        # Verifica se está pausada
        if self.esta_pausada():
            return False

        agora = timezone.localtime()
        hoje = agora.date()

        # ============================================
        # TIPO AGENDAMENTO ÚNICO
        # ============================================
        if self.tipo_agendamento == 'unico':
            # Para envio único, verifica apenas se a data é hoje
            if not self.data_envio_unico:
                return False
            return self.data_envio_unico == hoje

        # ============================================
        # TIPO AGENDAMENTO RECORRENTE
        # ============================================
        dia_semana = agora.weekday()  # 0=segunda, 6=domingo
        dia_mes = agora.day

        # Verifica dia da semana
        if dia_semana not in self.dias_semana:
            return False

        # Verifica período do mês
        if self.periodo_mes == 'todos':
            return True
        elif self.periodo_mes == '1-10':
            return 1 <= dia_mes <= 10
        elif self.periodo_mes == '11-20':
            return 11 <= dia_mes <= 20
        elif self.periodo_mes == '21-31':
            return dia_mes >= 21
        elif self.periodo_mes == '1-15':
            return 1 <= dia_mes <= 15
        elif self.periodo_mes == '16-31':
            return dia_mes >= 16

        return False

    def get_filtro_estados_display(self):
        """Retorna lista legível dos estados selecionados."""
        if not self.filtro_estados:
            return 'Todos'
        return ', '.join(self.filtro_estados)

    def get_filtro_cidades_display(self):
        """Retorna lista legível das cidades selecionadas."""
        if not self.filtro_cidades:
            return 'Todas'
        if len(self.filtro_cidades) > 3:
            return f"{', '.join(self.filtro_cidades[:3])} +{len(self.filtro_cidades) - 3}"
        return ', '.join(self.filtro_cidades)

    def converter_html_para_whatsapp(self):
        """
        Converte formatação HTML (Quill) para formato WhatsApp.
        <strong>texto</strong> -> *texto*
        <em>texto</em> -> _texto_
        """
        from html import unescape

        texto = self.mensagem

        # Remove tags de parágrafo
        texto = re.sub(r'<p>', '', texto)
        texto = re.sub(r'</p>', '\n', texto)

        # Converte negrito
        texto = re.sub(r'<strong>(.*?)</strong>', r'*\1*', texto)
        texto = re.sub(r'<b>(.*?)</b>', r'*\1*', texto)

        # Converte itálico
        texto = re.sub(r'<em>(.*?)</em>', r'_\1_', texto)
        texto = re.sub(r'<i>(.*?)</i>', r'_\1_', texto)

        # Remove outras tags HTML
        texto = re.sub(r'<[^>]+>', '', texto)

        # Decodifica entidades HTML
        texto = unescape(texto)

        # Remove linhas em branco extras
        texto = re.sub(r'\n{3,}', '\n\n', texto)

        return texto.strip()

    def save(self, *args, **kwargs):
        # Gera versão plaintext automaticamente
        if self.mensagem:
            self.mensagem_plaintext = self.converter_html_para_whatsapp()
        super().save(*args, **kwargs)


class TemplateMensagem(models.Model):
    """
    Templates pré-definidos de mensagens para reutilização nas tarefas de envio.
    Permite salvar mensagens frequentes para uso posterior.
    """

    CATEGORIA_CHOICES = [
        ('promocao', 'Promoção'),
        ('lembrete', 'Lembrete'),
        ('boas_vindas', 'Boas-vindas'),
        ('cobranca', 'Cobrança'),
        ('geral', 'Geral'),
    ]

    nome = models.CharField(
        max_length=100,
        verbose_name='Nome do Template',
        help_text='Nome identificador do template'
    )

    descricao = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Descrição',
        help_text='Descrição breve do template'
    )

    categoria = models.CharField(
        max_length=50,
        choices=CATEGORIA_CHOICES,
        default='geral',
        verbose_name='Categoria',
        help_text='Categoria para organização'
    )

    mensagem_html = models.TextField(
        verbose_name='Mensagem (HTML)',
        help_text='Conteúdo da mensagem com formatação'
    )

    imagem = models.ImageField(
        upload_to='templates_mensagem/',
        null=True,
        blank=True,
        verbose_name='Imagem',
        help_text='Imagem associada ao template (opcional)'
    )

    ativo = models.BooleanField(
        default=True,
        verbose_name='Ativo'
    )

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='templates_mensagem',
        verbose_name='Usuário'
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado Em'
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado Em'
    )

    class Meta:
        db_table = 'cadastros_templatemensagem'
        verbose_name = 'Template de Mensagem'
        verbose_name_plural = 'Templates de Mensagem'
        ordering = ['categoria', 'nome']

    def __str__(self):
        return f"[{self.get_categoria_display()}] {self.nome}"


class HistoricoExecucaoTarefa(models.Model):
    """
    Armazena o histórico de execuções das tarefas de envio.
    Permite rastrear sucesso, falhas e métricas de cada execução.
    """

    STATUS_CHOICES = [
        ('sucesso', 'Sucesso'),
        ('parcial', 'Parcial'),
        ('erro', 'Erro'),
    ]

    tarefa = models.ForeignKey(
        TarefaEnvio,
        on_delete=models.CASCADE,
        related_name='historico',
        verbose_name='Tarefa'
    )

    data_execucao = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Data da Execução'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        verbose_name='Status'
    )

    quantidade_enviada = models.PositiveIntegerField(
        default=0,
        verbose_name='Quantidade Enviada'
    )

    quantidade_erros = models.PositiveIntegerField(
        default=0,
        verbose_name='Quantidade de Erros'
    )

    detalhes = models.TextField(
        blank=True,
        verbose_name='Detalhes',
        help_text='JSON com detalhes da execução e eventuais erros'
    )

    duracao_segundos = models.PositiveIntegerField(
        default=0,
        verbose_name='Duração (segundos)'
    )

    class Meta:
        db_table = 'cadastros_historicoexecucaotarefa'
        verbose_name = 'Histórico de Execução'
        verbose_name_plural = 'Históricos de Execução'
        ordering = ['-data_execucao']
        indexes = [
            models.Index(fields=['tarefa', 'data_execucao'], name='hist_tarefa_data_idx'),
            models.Index(fields=['status'], name='hist_status_idx'),
        ]

    def __str__(self):
        return f"{self.tarefa.nome} - {self.data_execucao.strftime('%d/%m/%Y %H:%M')} - {self.get_status_display()}"

    def get_duracao_formatada(self):
        """Retorna duração formatada (ex: '2m 30s')."""
        minutos = self.duracao_segundos // 60
        segundos = self.duracao_segundos % 60
        if minutos > 0:
            return f"{minutos}m {segundos}s"
        return f"{segundos}s"

    def get_taxa_sucesso(self):
        """Retorna a taxa de sucesso em percentual."""
        total = self.quantidade_enviada + self.quantidade_erros
        if total == 0:
            return 0
        return round((self.quantidade_enviada / total) * 100, 1)


class ConfiguracaoEnvio(models.Model):
    """
    Configurações globais de envio de mensagens.
    Singleton - apenas 1 registro deve existir.
    """
    limite_envios_por_execucao = models.PositiveIntegerField(
        default=100,
        verbose_name='Limite de Envios por Execução',
        help_text='Máximo de mensagens enviadas por execução de tarefa'
    )

    intervalo_entre_mensagens = models.PositiveIntegerField(
        default=5,
        verbose_name='Intervalo Entre Mensagens (seg)',
        help_text='Segundos de espera entre cada mensagem enviada'
    )

    horario_inicio_permitido = models.TimeField(
        default=dt_time(8, 0),
        verbose_name='Horário Início Permitido',
        help_text='Horário mínimo para iniciar envios'
    )

    horario_fim_permitido = models.TimeField(
        default=dt_time(20, 0),
        verbose_name='Horário Fim Permitido',
        help_text='Horário máximo para envios'
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado Em'
    )

    class Meta:
        db_table = 'cadastros_configuracaoenvio'
        verbose_name = 'Configuração de Envio'
        verbose_name_plural = 'Configurações de Envio'

    def save(self, *args, **kwargs):
        # Garante apenas 1 registro (Singleton)
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Impede exclusão do registro singleton
        pass

    @classmethod
    def get_config(cls):
        """Retorna a configuração, criando se não existir."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Configurações de Envio (Limite: {self.limite_envios_por_execucao})"


class VarianteMensagem(models.Model):
    """
    Variantes de mensagem para A/B Testing.
    Permite testar diferentes mensagens na mesma tarefa.
    """
    tarefa = models.ForeignKey(
        TarefaEnvio,
        on_delete=models.CASCADE,
        related_name='variantes',
        verbose_name='Tarefa'
    )

    nome = models.CharField(
        max_length=50,
        verbose_name='Nome da Variante',
        help_text='Ex: Variante A, Variante B'
    )

    imagem = models.ImageField(
        upload_to='tarefas_envio/variantes/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'gif', 'webp'])],
        verbose_name='Imagem',
        help_text='Imagem alternativa (opcional)'
    )

    mensagem = models.TextField(
        verbose_name='Mensagem',
        help_text='Texto alternativo da mensagem'
    )

    mensagem_plaintext = models.TextField(
        blank=True,
        verbose_name='Mensagem (Plaintext)',
        help_text='Versão plaintext gerada automaticamente'
    )

    peso = models.PositiveIntegerField(
        default=50,
        verbose_name='Peso (%)',
        help_text='Percentual de envios para esta variante (0-100)'
    )

    # Métricas
    total_envios = models.PositiveIntegerField(
        default=0,
        verbose_name='Total de Envios'
    )

    ativo = models.BooleanField(
        default=True,
        verbose_name='Ativo'
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado Em'
    )

    class Meta:
        db_table = 'cadastros_variantemensagem'
        verbose_name = 'Variante de Mensagem'
        verbose_name_plural = 'Variantes de Mensagem'
        ordering = ['tarefa', 'nome']

    def __str__(self):
        return f"{self.tarefa.nome} - {self.nome}"

    def get_taxa_envio(self):
        """Retorna a taxa de envio desta variante em relação ao total da tarefa."""
        total_tarefa = self.tarefa.total_envios
        if total_tarefa == 0:
            return 0
        return round((self.total_envios / total_tarefa) * 100, 1)


class ConfiguracaoAgendamento(models.Model):
    """
    Configuração centralizada de agendamentos do sistema.

    Permite gerenciar todos os jobs automatizados do sistema,
    visualizar status, ativar/desativar e configurar templates de mensagem.
    """

    # Identificação
    nome = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Nome do Job',
        help_text='Identificador único do job (ex: envios_vencimento)'
    )

    nome_exibicao = models.CharField(
        max_length=100,
        verbose_name='Nome de Exibição',
        help_text='Nome amigável para exibir na interface'
    )

    descricao = models.TextField(
        blank=True,
        verbose_name='Descrição',
        help_text='Descrição detalhada do job'
    )

    icone = models.CharField(
        max_length=50,
        default='calendar',
        verbose_name='Ícone',
        help_text='Nome do ícone (Lucide Icons)'
    )

    # Horário/Frequência
    horario = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Horário/Frequência',
        help_text='Horário de execução (ex: 08:00) ou frequência (ex: 1min, 60min)'
    )

    # Status
    ativo = models.BooleanField(
        default=True,
        verbose_name='Ativo',
        help_text='Se o job está ativo e será executado'
    )

    bloqueado = models.BooleanField(
        default=False,
        verbose_name='Bloqueado',
        help_text='Se True, não pode ser editado pela interface web'
    )

    # Templates de mensagem (JSON) - para jobs configuráveis
    templates_mensagem = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Templates de Mensagem',
        help_text='JSON com templates de mensagem personalizáveis'
    )

    # Metadados
    ordem = models.PositiveIntegerField(
        default=0,
        verbose_name='Ordem',
        help_text='Ordem de exibição na lista'
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado Em'
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado Em'
    )

    class Meta:
        db_table = 'cadastros_configuracaoagendamento'
        verbose_name = 'Configuração de Agendamento'
        verbose_name_plural = 'Configurações de Agendamentos'
        ordering = ['ordem', 'nome']

    def __str__(self):
        status = "Ativo" if self.ativo else "Inativo"
        bloqueio = " (Bloqueado)" if self.bloqueado else ""
        return f"{self.nome_exibicao} - {status}{bloqueio}"

    def get_status_display(self):
        """Retorna status formatado para exibição."""
        if not self.ativo:
            return "Inativo"
        if self.bloqueado:
            return "Bloqueado"
        return "Ativo"

    def get_status_class(self):
        """Retorna classe CSS para o status."""
        if not self.ativo:
            return "badge-danger"
        if self.bloqueado:
            return "badge-warning"
        return "badge-success"


