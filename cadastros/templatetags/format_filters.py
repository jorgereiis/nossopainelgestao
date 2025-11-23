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


@register.filter
def format_valor_negocio(valor):
    """
    Formata valores usando padrões k (mil), mi (milhão), bi (bilhão).

    Exemplos:
        850 → 850,00
        1500 → 1,5 k
        50000 → 50 k
        1500000 → 1,5 mi
        1000000000 → 1 bi

    Uso no template:
        {{ receita_mensal|format_valor_negocio }}
    """
    if not valor:
        return '0'

    try:
        valor = float(valor)
    except (ValueError, TypeError):
        return '0'

    if valor >= 1_000_000_000:  # Bilhão
        resultado = valor / 1_000_000_000
        if resultado == int(resultado):
            return f"{int(resultado)} bi"
        return f"{resultado:,.1f} bi".replace(',', 'X').replace('.', ',').replace('X', '.')
    elif valor >= 1_000_000:  # Milhão
        resultado = valor / 1_000_000
        if resultado == int(resultado):
            return f"{int(resultado)} mi"
        return f"{resultado:,.1f} mi".replace(',', 'X').replace('.', ',').replace('X', '.')
    elif valor >= 1_000:  # Mil
        resultado = valor / 1_000
        if resultado == int(resultado):
            return f"{int(resultado)} k"
        return f"{resultado:,.1f} k".replace(',', 'X').replace('.', ',').replace('X', '.')
    else:
        return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
