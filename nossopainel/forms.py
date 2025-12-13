from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox


class LoginForm(AuthenticationForm):
    """
    Formulário de login com reCAPTCHA v2.

    NOTA: v3 requer chaves específicas. Para usar v3:
    1. Gerar novas chaves em https://www.google.com/recaptcha/admin
    2. Selecionar "reCAPTCHA v3"
    3. Atualizar RECAPTCHA_PUBLIC_KEY e RECAPTCHA_PRIVATE_KEY no .env
    4. Trocar ReCaptchaV2Checkbox por ReCaptchaV3
    """
    captcha = ReCaptchaField(
        widget=ReCaptchaV2Checkbox()
    )


class EnvioWhatsAppForm(forms.Form):
    """
    Formulário para validação de envios em massa via WhatsApp.

    Valida:
    - Tipo de envio (ativos, cancelados, avulso)
    - Mensagem (1-4096 caracteres)
    - Arquivo de telefones .txt (máx 100KB, apenas para avulso)
    - Imagem opcional (PNG/JPG/JPEG, máx 5MB)

    SEGURANÇA:
    - Sanitização automática de inputs via Django Forms
    - Validação de tamanho de arquivo (DoS prevention)
    - Validação de extensão de arquivo (upload malicioso)
    - Limite de caracteres em mensagem
    """

    TIPO_ENVIO_CHOICES = [
        ('', 'Selecione um tipo de envio'),
        ('ativos', 'Para todos os meus clientes ativos'),
        ('cancelados', 'Apenas para clientes cancelados'),
        ('avulso', 'Avulso'),
    ]

    options = forms.ChoiceField(
        choices=TIPO_ENVIO_CHOICES,
        required=True,
        error_messages={
            'required': 'Tipo de envio é obrigatório',
            'invalid_choice': 'Tipo de envio inválido'
        },
        label='Tipo de Envio'
    )

    mensagem = forms.CharField(
        max_length=4096,
        min_length=1,
        required=True,
        strip=True,
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': 'Digite sua mensagem aqui...',
            'class': 'form-control'
        }),
        error_messages={
            'required': 'Mensagem é obrigatória',
            'max_length': 'Mensagem muito longa (máximo 4096 caracteres)',
            'min_length': 'Mensagem não pode estar vazia'
        },
        label='Mensagem'
    )

    telefones = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['txt'])],
        error_messages={
            'invalid_extension': 'Apenas arquivos .txt são permitidos'
        },
        label='Arquivo de Telefones'
    )

    imagem = forms.ImageField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg'])],
        error_messages={
            'invalid_extension': 'Apenas imagens PNG, JPG ou JPEG são permitidas',
            'invalid_image': 'Arquivo de imagem inválido'
        },
        label='Imagem'
    )

    def clean_telefones(self):
        """
        Valida arquivo de telefones.

        Regras:
        - Tamanho máximo: 100KB (previne DoS)
        - Obrigatório apenas se tipo_envio = 'avulso'
        - Formato: um número por linha
        """
        file = self.cleaned_data.get('telefones')
        tipo_envio = self.cleaned_data.get('options')

        # Se tipo é avulso, arquivo é obrigatório
        if tipo_envio == 'avulso' and not file:
            raise ValidationError('Arquivo de telefones é obrigatório para envios avulsos')

        if file:
            # Limite de tamanho: 100KB
            if file.size > 102400:  # 100 * 1024
                raise ValidationError('Arquivo muito grande (máximo 100KB)')

            # Valida conteúdo (pelo menos uma linha não-vazia)
            try:
                content = file.read().decode('utf-8')
                file.seek(0)  # Reset para leitura posterior

                lines = [line.strip() for line in content.splitlines() if line.strip()]
                if not lines:
                    raise ValidationError('Arquivo de telefones está vazio')

            except UnicodeDecodeError:
                raise ValidationError('Arquivo deve estar em formato UTF-8')

        return file

    def clean_imagem(self):
        """
        Valida imagem.

        Regras:
        - Tamanho máximo: 5MB
        - Formatos: PNG, JPG, JPEG
        """
        imagem = self.cleaned_data.get('imagem')

        if imagem:
            # Limite de tamanho: 5MB
            if imagem.size > 5242880:  # 5 * 1024 * 1024
                raise ValidationError('Imagem muito grande (máximo 5MB)')

        return imagem

    def clean(self):
        """
        Validação global do formulário.

        Garante consistência entre campos relacionados.
        """
        cleaned_data = super().clean()
        tipo_envio = cleaned_data.get('options')
        telefones = cleaned_data.get('telefones')

        # Validação cruzada já feita em clean_telefones
        # Aqui poderíamos adicionar outras validações globais se necessário

        return cleaned_data


class TarefaEnvioForm(forms.ModelForm):
    """
    Formulário para criar/editar tarefas de envio de mensagens WhatsApp.

    Campos personalizados:
    - dias_semana: MultipleChoiceField com checkboxes
    - horario: TimeInput com widget HTML5
    - mensagem: Textarea (preenchido via Quill.js no frontend)
    """

    DIAS_SEMANA_CHOICES = [
        (0, 'Segunda'),
        (1, 'Terça'),
        (2, 'Quarta'),
        (3, 'Quinta'),
        (4, 'Sexta'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]

    # Lista de UFs brasileiras
    UF_CHOICES = [
        ('AC', 'Acre'), ('AL', 'Alagoas'), ('AP', 'Amapá'), ('AM', 'Amazonas'),
        ('BA', 'Bahia'), ('CE', 'Ceará'), ('DF', 'Distrito Federal'),
        ('ES', 'Espírito Santo'), ('GO', 'Goiás'), ('MA', 'Maranhão'),
        ('MT', 'Mato Grosso'), ('MS', 'Mato Grosso do Sul'), ('MG', 'Minas Gerais'),
        ('PA', 'Pará'), ('PB', 'Paraíba'), ('PR', 'Paraná'), ('PE', 'Pernambuco'),
        ('PI', 'Piauí'), ('RJ', 'Rio de Janeiro'), ('RN', 'Rio Grande do Norte'),
        ('RS', 'Rio Grande do Sul'), ('RO', 'Rondônia'), ('RR', 'Roraima'),
        ('SC', 'Santa Catarina'), ('SP', 'São Paulo'), ('SE', 'Sergipe'), ('TO', 'Tocantins'),
    ]

    dias_semana = forms.MultipleChoiceField(
        choices=DIAS_SEMANA_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        required=True,
        error_messages={
            'required': 'Selecione pelo menos um dia da semana'
        },
        label='Dias da Semana'
    )

    filtro_estados = forms.MultipleChoiceField(
        choices=UF_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        required=False,
        label='Filtrar por Estados',
        help_text='Deixe vazio para enviar para todos os estados'
    )

    pausado_ate = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local'
        }),
        label='Pausar Até',
        help_text='Opcional: data/hora para reativar a tarefa automaticamente'
    )

    tipo_agendamento = forms.ChoiceField(
        choices=[
            ('recorrente', 'Recorrente'),
            ('unico', 'Envio Único'),
        ],
        initial='recorrente',
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        }),
        label='Tipo de Agendamento',
        help_text='Recorrente repete nos dias selecionados. Único executa apenas uma vez.'
    )

    data_envio_unico = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control form-control-lg',
            'type': 'date'
        }),
        label='Data do Envio',
        help_text='Selecione a data específica para envio único'
    )

    class Meta:
        from .models import TarefaEnvio
        model = TarefaEnvio
        fields = [
            'nome',
            'tipo_envio',
            'tipo_agendamento',
            'dias_semana',
            'periodo_mes',
            'data_envio_unico',
            'horario',
            'imagem',
            'mensagem',
            'filtro_estados',
            'pausado_ate',
            'ativo',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Ex: Promoção de Natal'
            }),
            'tipo_envio': forms.Select(attrs={
                'class': 'form-select form-select-lg'
            }),
            'periodo_mes': forms.Select(attrs={
                'class': 'form-select'
            }),
            'horario': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'mensagem': forms.Textarea(attrs={
                'class': 'form-control d-none',
                'rows': 5
            }),
            'ativo': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch'
            }),
        }
        labels = {
            'nome': 'Nome da Tarefa',
            'tipo_envio': 'Tipo de Envio',
            'periodo_mes': 'Período do Mês',
            'horario': 'Horário',
            'imagem': 'Imagem',
            'mensagem': 'Mensagem',
            'ativo': 'Tarefa Ativa',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Se editando, converte dias_semana de list para strings (para o widget)
        if self.instance and self.instance.pk:
            if self.instance.dias_semana:
                self.initial['dias_semana'] = [str(d) for d in self.instance.dias_semana]
            # Converte filtro_estados para strings (para o widget)
            if self.instance.filtro_estados:
                self.initial['filtro_estados'] = self.instance.filtro_estados

    def clean_dias_semana(self):
        """Converte strings para inteiros."""
        dias = self.cleaned_data.get('dias_semana', [])
        return [int(d) for d in dias]

    def clean_imagem(self):
        """Valida tamanho da imagem (máximo 5MB)."""
        import logging
        logger = logging.getLogger(__name__)

        imagem = self.cleaned_data.get('imagem')
        logger.info(f"TarefaEnvioForm clean_imagem - imagem: {imagem}, type: {type(imagem)}")

        if imagem and hasattr(imagem, 'size'):
            logger.info(f"TarefaEnvioForm clean_imagem - size: {imagem.size}, name: {imagem.name}")
            if imagem.size > 5 * 1024 * 1024:  # 5MB
                raise ValidationError('Imagem muito grande (máximo 5MB)')

        return imagem

    def clean_periodo_mes(self):
        """Valida que o período do mês foi selecionado."""
        periodo = self.cleaned_data.get('periodo_mes', '').strip()

        if not periodo:
            raise ValidationError('Selecione um período do mês')

        return periodo

    def clean_mensagem(self):
        """Valida que a mensagem não está vazia."""
        mensagem = self.cleaned_data.get('mensagem', '').strip()

        if not mensagem:
            raise ValidationError('A mensagem é obrigatória')

        # Remove tags HTML para verificar se há conteúdo real
        import re
        texto_limpo = re.sub(r'<[^>]+>', '', mensagem).strip()
        if not texto_limpo:
            raise ValidationError('A mensagem não pode estar vazia')

        return mensagem

    def clean(self):
        """Validação global com logging para debug."""
        import logging
        from django.utils import timezone
        logger = logging.getLogger(__name__)

        cleaned_data = super().clean()
        logger.info(f"TarefaEnvioForm clean - cleaned_data keys: {list(cleaned_data.keys())}")
        logger.info(f"TarefaEnvioForm clean - imagem: {cleaned_data.get('imagem')}")
        logger.info(f"TarefaEnvioForm clean - form errors: {self.errors}")

        # Validação do tipo de agendamento
        tipo_agendamento = cleaned_data.get('tipo_agendamento')
        data_envio_unico = cleaned_data.get('data_envio_unico')
        dias_semana = cleaned_data.get('dias_semana', [])

        if tipo_agendamento == 'unico':
            # Para envio único, a data é obrigatória
            if not data_envio_unico:
                self.add_error('data_envio_unico', 'Para envio único, selecione uma data.')
            elif data_envio_unico < timezone.now().date():
                self.add_error('data_envio_unico', 'A data de envio não pode ser no passado.')
        elif tipo_agendamento == 'recorrente':
            # Para envio recorrente, dias da semana são obrigatórios
            if not dias_semana:
                self.add_error('dias_semana', 'Selecione pelo menos um dia da semana.')

        return cleaned_data
