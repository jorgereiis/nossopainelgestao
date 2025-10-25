from django.contrib.auth.forms import AuthenticationForm
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
