import re
from django import template

register = template.Library()

@register.filter
def formatar_telefone(wpp):
    if not wpp:
        return ''

    numero = re.sub(r'\D+', '', wpp)

    # Detecta país
    if numero.startswith('55'):
        pais = 'br'
        numero = numero[2:]
    elif numero.startswith('1'):
        pais = 'us'
        numero = numero[1:]
    elif numero.startswith('351'):
        pais = 'pt'
        numero = numero[3:]
    else:
        return '+' + numero  # Exibe como está para outros países

    # --- Brasil ---
    if pais == 'br':
        if len(numero) == 11:
            return f'({numero[:2]}) {numero[2:7]}-{numero[7:]}'
        elif len(numero) == 10:
            return f'({numero[:2]}) {numero[2:6]}-{numero[6:]}'
        return numero

    # --- EUA ---
    if pais == 'us' and len(numero) == 10:
        return f'({numero[:3]}) {numero[3:6]}-{numero[6:]}'

    # --- Portugal ---
    if pais == 'pt' and len(numero) == 9:
        return f'{numero[:3]} {numero[3:6]} {numero[6:]}'

    return '+' + numero


@register.filter
def servidor_imagem_url(servidor, user=None):
    """
    Retorna a URL da imagem do servidor considerando o usuário atual.

    Uso no template:
        {{ servidor|servidor_imagem_url:request.user }}
    """
    if hasattr(servidor, 'get_imagem_url'):
        return servidor.get_imagem_url(usuario_atual=user)
    return ''
