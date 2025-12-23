"""
Modelos do Painel do Cliente.

Este app permite que clientes finais acessem suas mensalidades,
realizem pagamentos via PIX e gerenciem seus dados cadastrais.
"""

import uuid
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


def painel_logo_upload_path(instance, filename):
    """
    Gera caminho de upload com UUID para logos do painel.
    Formato: painel_cliente/logos/<uuid>.<ext>
    """
    ext = filename.split('.')[-1].lower()
    return f'painel_cliente/logos/{uuid.uuid4()}.{ext}'


class SubdominioPainelCliente(models.Model):
    """
    Configuracao de subdominio para o Painel do Cliente.

    Gerenciado pelo Admin Superior (superuser).
    Cada subdominio e vinculado a um usuario do NossoPainel (Admin Comum)
    que pode personalizar o visual e configuracoes.
    """

    # Identificacao do subdominio
    subdominio = models.CharField(
        max_length=63,
        unique=True,
        help_text="Nome do subdominio (ex: meunegocio para meunegocio.pagar.cc)"
    )
    dominio_completo = models.CharField(
        max_length=255,
        unique=True,
        help_text="Dominio completo (ex: meunegocio.pagar.cc)"
    )

    # Vinculo com usuario do NossoPainel (Admin Comum)
    admin_responsavel = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='subdominios_painel',
        help_text="Usuario do NossoPainel que administra este subdominio"
    )

    # Personalizacao visual (editavel pelo Admin Comum)
    nome_exibicao = models.CharField(
        max_length=100,
        help_text="Nome exibido no painel (ex: Meu Negocio IPTV)"
    )
    logo = models.ImageField(
        upload_to=painel_logo_upload_path,
        null=True,
        blank=True,
        help_text="Logo do painel (recomendado: 200x200px)"
    )
    cor_primaria = models.CharField(
        max_length=7,
        default='#8B5CF6',
        help_text="Cor primaria em hexadecimal (ex: #8B5CF6)"
    )
    cor_secundaria = models.CharField(
        max_length=7,
        default='#06B6D4',
        help_text="Cor secundaria em hexadecimal (ex: #06B6D4)"
    )

    # Contato para suporte
    whatsapp_suporte = models.CharField(
        max_length=20,
        blank=True,
        help_text="Numero do WhatsApp para suporte (ex: 5571999999999)"
    )
    mensagem_suporte = models.TextField(
        default="Ola! Preciso de ajuda com minha assinatura.",
        help_text="Mensagem padrao para o WhatsApp"
    )

    # Textos personalizaveis
    texto_boas_vindas = models.CharField(
        max_length=255,
        default="Bem-vindo ao seu painel!",
        help_text="Mensagem de boas-vindas exibida no dashboard"
    )

    # Conta FastDePix vinculada (para gerar cobrancas)
    conta_bancaria = models.ForeignKey(
        'nossopainel.ContaBancaria',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='subdominios_painel',
        help_text="Conta FastDePix para processar pagamentos"
    )

    # Controle (gerenciado pelo Admin Superior)
    ativo = models.BooleanField(
        default=True,
        help_text="Se desativado, o painel nao estara acessivel"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='subdominios_criados',
        null=True,
        blank=True,
        help_text="Admin Superior que criou este subdominio"
    )

    class Meta:
        db_table = 'painel_cliente_subdominio'
        verbose_name = 'Subdominio do Painel'
        verbose_name_plural = 'Subdominios do Painel'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['subdominio']),
            models.Index(fields=['ativo']),
            models.Index(fields=['admin_responsavel']),
        ]

    def __str__(self):
        return f"{self.subdominio}.pagar.cc - {self.nome_exibicao}"

    def save(self, *args, **kwargs):
        """Garante que o dominio completo esteja sempre atualizado."""
        self.dominio_completo = f"{self.subdominio}.pagar.cc"
        super().save(*args, **kwargs)

    def get_whatsapp_url(self):
        """Retorna URL do WhatsApp com DDI 55 hardcoded."""
        if not self.whatsapp_suporte:
            return None

        from urllib.parse import quote

        # Remove qualquer formatacao, mantem apenas digitos
        numero = ''.join(filter(str.isdigit, self.whatsapp_suporte))

        # Adiciona DDI 55 se nao comecar com 55
        if not numero.startswith('55'):
            numero = '55' + numero

        mensagem = quote(self.mensagem_suporte or "")
        return f"https://wa.me/{numero}?text={mensagem}"

    def get_logo_url(self):
        """Retorna URL do logo ou None se nao houver."""
        if self.logo:
            return self.logo.url
        return None


class SessaoCliente(models.Model):
    """
    Sessao de autenticacao do cliente (sem senha).

    O cliente faz login via telefone (lookup direto).
    A sessao e permanente ate que o cliente faca logout.
    Opcionalmente, pode expirar apos 90 dias de inatividade.
    """

    # Configuracao de inatividade (dias)
    DIAS_INATIVIDADE_MAX = 90

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # Vinculo com cliente do NossoPainel
    cliente = models.ForeignKey(
        'nossopainel.Cliente',
        on_delete=models.CASCADE,
        related_name='sessoes_painel'
    )

    # Vinculo com subdominio
    subdominio = models.ForeignKey(
        SubdominioPainelCliente,
        on_delete=models.CASCADE,
        related_name='sessoes'
    )

    # Token de sessao (armazenado em cookie HTTP-only)
    token = models.CharField(
        max_length=64,
        unique=True,
        help_text="Token seguro da sessao"
    )

    # Informacoes de seguranca
    ip_address = models.GenericIPAddressField(
        help_text="IP do cliente no momento do login"
    )
    user_agent = models.TextField(
        help_text="User-Agent do navegador"
    )

    # Timestamps
    criado_em = models.DateTimeField(auto_now_add=True)
    ultimo_acesso = models.DateTimeField(
        auto_now=True,
        help_text="Atualizado a cada acesso para controle de inatividade"
    )

    # Expiracao opcional (null = sessao permanente)
    expira_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Data/hora de expiracao (null = sessao permanente)"
    )

    # Status
    ativo = models.BooleanField(
        default=True,
        help_text="Sessao ativa ou encerrada"
    )

    # Metodo de autenticacao usado
    metodo_auth = models.CharField(
        max_length=20,
        default='telefone',
        help_text="Metodo de autenticacao usado (telefone, etc)"
    )

    class Meta:
        db_table = 'painel_cliente_sessao'
        verbose_name = 'Sessao do Cliente'
        verbose_name_plural = 'Sessoes dos Clientes'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['cliente', 'ativo']),
            models.Index(fields=['ultimo_acesso']),
        ]

    def __str__(self):
        return f"Sessao {self.id} - {self.cliente.nome}"

    def save(self, *args, **kwargs):
        """Gera token se nao existir."""
        if not self.token:
            self.token = secrets.token_urlsafe(48)  # 64 caracteres
        super().save(*args, **kwargs)

    def is_valid(self):
        """
        Verifica se a sessao ainda e valida.

        A sessao e valida se:
        - Estiver ativa
        - Nao estiver expirada (se tiver data de expiracao)
        - Nao estiver inativa por mais de DIAS_INATIVIDADE_MAX dias
        """
        if not self.ativo:
            return False

        # Verifica expiracao explicita
        if self.expira_em and timezone.now() >= self.expira_em:
            return False

        # Verifica inatividade (90 dias sem acesso)
        limite_inatividade = timezone.now() - timedelta(days=self.DIAS_INATIVIDADE_MAX)
        if self.ultimo_acesso < limite_inatividade:
            return False

        return True

    def atualizar_acesso(self):
        """Atualiza timestamp de ultimo acesso."""
        self.ultimo_acesso = timezone.now()
        self.save(update_fields=['ultimo_acesso'])

    def encerrar(self):
        """Encerra a sessao (logout)."""
        self.ativo = False
        self.save(update_fields=['ativo'])

    def renovar(self):
        """Alias para atualizar_acesso() - mantem compatibilidade."""
        self.atualizar_acesso()

    @classmethod
    def criar_sessao(cls, cliente, subdominio, ip_address, user_agent, metodo_auth='telefone'):
        """
        Cria uma nova sessao permanente para o cliente.

        Args:
            cliente: Instancia do modelo Cliente
            subdominio: Instancia do modelo SubdominioPainelCliente
            ip_address: IP do cliente
            user_agent: User-Agent do navegador
            metodo_auth: Metodo de autenticacao usado

        Returns:
            SessaoCliente: Nova sessao criada
        """
        # Encerra sessoes anteriores do mesmo cliente neste subdominio
        cls.objects.filter(
            cliente=cliente,
            subdominio=subdominio,
            ativo=True
        ).update(ativo=False)

        # Cria nova sessao (sem data de expiracao = permanente)
        return cls.objects.create(
            cliente=cliente,
            subdominio=subdominio,
            ip_address=ip_address,
            user_agent=user_agent,
            metodo_auth=metodo_auth
        )


class TentativaLogin(models.Model):
    """
    Registra tentativas de login para rate limiting.

    Limite: 5 tentativas por IP a cada 15 minutos.
    """

    ip_address = models.GenericIPAddressField()
    subdominio = models.ForeignKey(
        SubdominioPainelCliente,
        on_delete=models.CASCADE,
        related_name='tentativas_login'
    )
    identificador = models.CharField(
        max_length=255,
        help_text="Telefone tentado"
    )
    sucesso = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'painel_cliente_tentativa_login'
        verbose_name = 'Tentativa de Login'
        verbose_name_plural = 'Tentativas de Login'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['ip_address', 'criado_em']),
            models.Index(fields=['subdominio', 'criado_em']),
        ]

    @classmethod
    def verificar_bloqueio(cls, ip_address, subdominio):
        """
        Verifica se o IP esta bloqueado por excesso de tentativas.

        Args:
            ip_address: IP a verificar
            subdominio: Subdominio da tentativa

        Returns:
            tuple: (bloqueado: bool, tentativas_restantes: int)
        """
        limite_minutos = 15
        limite_tentativas = 5

        desde = timezone.now() - timedelta(minutes=limite_minutos)

        tentativas = cls.objects.filter(
            ip_address=ip_address,
            subdominio=subdominio,
            sucesso=False,
            criado_em__gte=desde
        ).count()

        bloqueado = tentativas >= limite_tentativas
        restantes = max(0, limite_tentativas - tentativas)

        return bloqueado, restantes

    @classmethod
    def registrar(cls, ip_address, subdominio, identificador, sucesso=False):
        """Registra uma tentativa de login."""
        return cls.objects.create(
            ip_address=ip_address,
            subdominio=subdominio,
            identificador=identificador,
            sucesso=sucesso
        )
