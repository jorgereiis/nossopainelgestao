"""
Formulários do JampaBet
"""
from django import forms
from .models import Bet


class LoginForm(forms.Form):
    """Formulário de login"""
    email = forms.EmailField(
        label='E-mail',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'seu@email.com',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Sua senha',
            'autocomplete': 'current-password'
        })
    )


class RegisterForm(forms.Form):
    """Formulário de registro"""
    name = forms.CharField(
        label='Nome',
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Seu nome',
            'autocomplete': 'name'
        })
    )
    email = forms.EmailField(
        label='E-mail',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'seu@email.com',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        label='Senha',
        min_length=6,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mínimo 6 caracteres',
            'autocomplete': 'new-password'
        })
    )
    confirm_password = forms.CharField(
        label='Confirmar Senha',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Repita a senha',
            'autocomplete': 'new-password'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError('As senhas não conferem')

        return cleaned_data


class BetForm(forms.Form):
    """Formulário de aposta"""
    home_win_bahia = forms.IntegerField(
        label='Gols Bahia (Vitória)',
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={
            'class': 'form-control score-input',
            'min': '0',
            'max': '20'
        })
    )
    home_win_opponent = forms.IntegerField(
        label='Gols Adversário (Vitória)',
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={
            'class': 'form-control score-input',
            'min': '0',
            'max': '20'
        })
    )
    draw_bahia = forms.IntegerField(
        label='Gols Bahia (Empate)',
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={
            'class': 'form-control score-input',
            'min': '0',
            'max': '20'
        })
    )
    draw_opponent = forms.IntegerField(
        label='Gols Adversário (Empate)',
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={
            'class': 'form-control score-input',
            'min': '0',
            'max': '20'
        })
    )

    def clean(self):
        cleaned_data = super().clean()

        home_win_bahia = cleaned_data.get('home_win_bahia')
        home_win_opponent = cleaned_data.get('home_win_opponent')
        draw_bahia = cleaned_data.get('draw_bahia')
        draw_opponent = cleaned_data.get('draw_opponent')

        # Valida palpite de vitória
        if home_win_bahia is not None and home_win_opponent is not None:
            if home_win_bahia <= home_win_opponent:
                raise forms.ValidationError(
                    'No palpite de vitória, Bahia deve ter mais gols que o adversário'
                )

        # Valida palpite de empate
        if draw_bahia is not None and draw_opponent is not None:
            if draw_bahia != draw_opponent:
                raise forms.ValidationError(
                    'No palpite de empate, os placares devem ser iguais'
                )

        return cleaned_data
