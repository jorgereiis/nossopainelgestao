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
