import re
from django import template

register = template.Library()

@register.filter
def formatar_telefone(wpp):
    if not wpp:
        return ''

    numero = re.sub(r'\D+', '', wpp)

    # Detecta país pelo DDI (ordenado do mais específico ao menos)
    pais = None
    if numero.startswith('595'):
        pais, numero = 'py', numero[3:]
    elif numero.startswith('598'):
        pais, numero = 'uy', numero[3:]
    elif numero.startswith('351'):
        pais, numero = 'pt', numero[3:]
    elif numero.startswith('55'):
        pais, numero = 'br', numero[2:]
    elif numero.startswith('54'):
        pais, numero = 'ar', numero[2:]
    elif numero.startswith('57'):
        pais, numero = 'co', numero[2:]
    elif numero.startswith('56'):
        pais, numero = 'cl', numero[2:]
    elif numero.startswith('52'):
        pais, numero = 'mx', numero[2:]
    elif numero.startswith('51'):
        pais, numero = 'pe', numero[2:]
    elif numero.startswith('49'):
        pais, numero = 'de', numero[2:]
    elif numero.startswith('44'):
        pais, numero = 'gb', numero[2:]
    elif numero.startswith('41'):
        pais, numero = 'ch', numero[2:]
    elif numero.startswith('39'):
        pais, numero = 'it', numero[2:]
    elif numero.startswith('34'):
        pais, numero = 'es', numero[2:]
    elif numero.startswith('33'):
        pais, numero = 'fr', numero[2:]
    elif numero.startswith('32'):
        pais, numero = 'be', numero[2:]
    elif numero.startswith('31'):
        pais, numero = 'nl', numero[2:]
    elif numero.startswith('1') and len(numero) == 11:
        pais, numero = 'us', numero[1:]
    else:
        return '+' + numero

    # --- Américas ---
    if pais == 'br':
        if len(numero) == 11:
            return f'({numero[:2]}) {numero[2:7]}-{numero[7:]}'
        elif len(numero) == 10:
            return f'({numero[:2]}) {numero[2:6]}-{numero[6:]}'
        return numero
    elif pais == 'us' and len(numero) == 10:
        return f'({numero[:3]}) {numero[3:6]}-{numero[6:]}'
    elif pais == 'mx' and len(numero) == 10:
        return f'{numero[:2]} {numero[2:6]} {numero[6:]}'
    elif pais == 'ar' and len(numero) == 10:
        return f'{numero[:2]} {numero[2:6]}-{numero[6:]}'
    elif pais == 'co' and len(numero) == 10:
        return f'{numero[:3]} {numero[3:6]} {numero[6:]}'
    elif pais == 'cl' and len(numero) == 9:
        return f'{numero[:1]} {numero[1:5]} {numero[5:]}'
    elif pais == 'pe' and len(numero) == 9:
        return f'{numero[:3]} {numero[3:6]} {numero[6:]}'
    elif pais == 'py' and len(numero) == 9:
        return f'{numero[:3]} {numero[3:6]} {numero[6:]}'
    elif pais == 'uy' and len(numero) >= 8:
        return f'{numero[:2]} {numero[2:5]} {numero[5:]}'

    # --- Europa ---
    elif pais == 'pt' and len(numero) == 9:
        return f'{numero[:3]} {numero[3:6]} {numero[6:]}'
    elif pais == 'es' and len(numero) == 9:
        return f'{numero[:3]} {numero[3:5]} {numero[5:7]} {numero[7:]}'
    elif pais == 'it' and len(numero) >= 9:
        return f'{numero[:3]} {numero[3:6]} {numero[6:]}'
    elif pais == 'fr' and len(numero) == 9:
        return f'{numero[:2]} {numero[2:4]} {numero[4:6]} {numero[6:8]} {numero[8:]}'
    elif pais == 'de' and len(numero) >= 10:
        return f'{numero[:4]} {numero[4:8]} {numero[8:]}'
    elif pais == 'gb' and len(numero) == 10:
        return f'{numero[:5]} {numero[5:]}'
    elif pais == 'nl' and len(numero) == 9:
        return f'{numero[:2]} {numero[2:]}'
    elif pais == 'be' and len(numero) == 9:
        return f'{numero[:4]} {numero[4:6]} {numero[6:8]} {numero[8:]}'
    elif pais == 'ch' and len(numero) == 9:
        return f'{numero[:3]} {numero[3:6]} {numero[6:8]} {numero[8:]}'

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


@register.filter
def first_name(value):
    """
    Retorna apenas o primeiro nome de uma string.

    Exemplo:
        {{ cliente.nome|first_name }}
        "João da Silva" -> "João"
    """
    if not value:
        return ""
    return str(value).split()[0] if value else ""
