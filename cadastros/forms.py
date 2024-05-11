from django.contrib.auth.forms import AuthenticationForm
from captcha.fields import CaptchaField
from captcha.widgets import CaptchaV2Checkbox

"""class LoginForm(AuthenticationForm):
    captcha = ReCaptchaField(
        widget=ReCaptchaV2Checkbox()
    )
"""