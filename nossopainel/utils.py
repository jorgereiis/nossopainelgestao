"""Funções auxiliares utilizadas nas rotinas de cadastros e automações."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import logging
import os
import re
import time

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import localtime, now
from .models import (
    Aplicativo,
    Cliente,
    ClientePlanoHistorico,
    DescontoProgressivoIndicacao,
    Dispositivo,
    Mensalidade,
    Plano,
    PlanoIndicacao,
    Servidor,
    SessaoWpp,
    UserActionLog,
)
from nossopainel.services.logging import append_line
from nossopainel.services.wpp import (
    LogTemplates,
    MessageSendConfig,
    send_message,
)
from wpp.api_connection import (
    check_number_status,
)

logger = logging.getLogger(__name__)

API_WPP_URL_PROD = os.getenv("API_WPP_URL_PROD")
USER_SESSION_WPP = os.getenv("USER_SESSION_WPP")
MEU_NUM_CLARO = os.getenv("MEU_NUM_CLARO")
DIR_LOGS_AGENDADOS = os.getenv("DIR_LOGS_AGENDADOS")
DIR_LOGS_INDICACOES = os.getenv("DIR_LOGS_INDICACOES")
TEMPLATE_LOG_MSG_SUCESSO = os.getenv("TEMPLATE_LOG_MSG_SUCESSO")
TEMPLATE_LOG_MSG_FALHOU = os.getenv("TEMPLATE_LOG_MSG_FALHOU")
TEMPLATE_LOG_TELEFONE_INVALIDO = os.getenv("TEMPLATE_LOG_TELEFONE_INVALIDO")


# =============================================================================
# NORMALIZAÇÃO DE NOMES (Dispositivos, Aplicativos, Servidores)
# =============================================================================

DISPOSITIVOS_MAP = {
    # =========================================================================
    # MARCAS DE TV (adiciona prefixo "TV " quando necessário)
    # =========================================================================
    # LG
    'lg': 'TV LG',
    'tv lg': 'TV LG',
    # Samsung
    'samsung': 'TV Samsung',
    'tv samsung': 'TV Samsung',
    # Philips
    'philips': 'TV Philips',
    'tv philips': 'TV Philips',
    # Philco
    'philco': 'TV Philco',
    'tv philco': 'TV Philco',
    # TCL
    'tcl': 'TV TCL',
    'tv tcl': 'TV TCL',
    'tcl android': 'TV TCL Android',
    'tv tcl android': 'TV TCL Android',
    # Roku
    'roku': 'TV Roku',
    'tv roku': 'TV Roku',
    'stick roku': 'Stick Roku',
    'roku stick': 'Stick Roku',
    # AOC
    'aoc': 'TV AOC',
    'tv aoc': 'TV AOC',
    # Sony
    'sony': 'TV Sony',
    'tv sony': 'TV Sony',
    # Panasonic
    'panasonic': 'TV Panasonic',
    'tv panasonic': 'TV Panasonic',
    # Hisense
    'hisense': 'TV Hisense',
    'tv hisense': 'TV Hisense',
    # Semp / Semp Toshiba
    'semp': 'TV Semp',
    'tv semp': 'TV Semp',
    'semp toshiba': 'TV Semp Toshiba',
    'tv semp toshiba': 'TV Semp Toshiba',
    # Toshiba
    'toshiba': 'TV Toshiba',
    'tv toshiba': 'TV Toshiba',
    # Audisat
    'audisat': 'TV Audisat',
    'tv audisat': 'TV Audisat',
    # HQ
    'hq': 'TV HQ',
    'tv hq': 'TV HQ',
    # Multilaser
    'multilaser': 'TV Multilaser',
    'tv multilaser': 'TV Multilaser',
    # VIDAA (sistema operacional Hisense)
    'vidaa': 'TV VIDAA',
    'tv vidaa': 'TV VIDAA',
    # Britânia
    'britania': 'TV Britânia',
    'britânia': 'TV Britânia',
    'tv britania': 'TV Britânia',
    'tv britânia': 'TV Britânia',
    # Aiwa
    'aiwa': 'TV Aiwa',
    'tv aiwa': 'TV Aiwa',
    # Sharp
    'sharp': 'TV Sharp',
    'tv sharp': 'TV Sharp',
    # JVC
    'jvc': 'TV JVC',
    'tv jvc': 'TV JVC',
    # CCE
    'cce': 'TV CCE',
    'tv cce': 'TV CCE',
    # Positivo
    'positivo': 'TV Positivo',
    'tv positivo': 'TV Positivo',
    # Vizio
    'vizio': 'TV Vizio',
    'tv vizio': 'TV Vizio',
    # Xiaomi
    'xiaomi': 'TV Xiaomi',
    'tv xiaomi': 'TV Xiaomi',
    'mi tv': 'TV Xiaomi',
    # Android (genérico)
    'android': 'TV Android',
    'tv android': 'TV Android',

    # =========================================================================
    # DISPOSITIVOS ESPECIAIS (sem prefixo TV)
    # =========================================================================
    # Fire Stick / Amazon
    'firestick': 'Fire Stick',
    'fire stick': 'Fire Stick',
    'amazon fire stick': 'Fire Stick',
    'fire tv stick': 'Fire Stick',
    'amazon fire tv': 'Fire Stick',
    # Chromecast
    'chromecast': 'Chromecast',
    'google chromecast': 'Chromecast',
    # Apple TV
    'apple tv': 'Apple TV',
    'appletv': 'Apple TV',
    # Xbox
    'xbox': 'Xbox',
    'xbox one': 'Xbox One',
    'xbox series': 'Xbox Series',
    # PlayStation
    'playstation': 'PlayStation',
    'ps4': 'PlayStation 4',
    'ps5': 'PlayStation 5',
    # TV Box
    'tvbox': 'TV Box',
    'tv box': 'TV Box',
    # Notebook/PC
    'notebook': 'Notebook',
    'pc': 'PC',
    'computador': 'Computador',
    'desktop': 'Desktop',
    # Tablets
    'tablet': 'Tablet',
    'tablet ios': 'Tablet iOS',
    'tablet android': 'Tablet Android',
    'ipad': 'iPad',
    # Celular/Smartphone
    'celular': 'Celular',
    'smartphone': 'Smartphone',
    'iphone': 'iPhone',
    # Projetor
    'projetor': 'Projetor',
    'projetor android': 'Projetor Android',
}

APLICATIVOS_MAP = {
    # =========================================================================
    # APLICATIVOS IPTV - Mapeamento de nomes normalizados
    # =========================================================================
    # 7Flix
    '7flix': '7Flix',
    '7 flix': '7Flix',
    # CAP Player
    'cap player': 'CAP Player',
    'capplayer': 'CAP Player',
    'cap': 'CAP Player',
    # CLite
    'clite': 'CLite',
    'c lite': 'CLite',
    # Clouddy
    'clouddy': 'Clouddy',
    # Club Smart
    'club smart': 'Club Smart',
    'clubsmart': 'Club Smart',
    # CPlayer Smart
    'cplayer smart': 'CPlayer Smart',
    'cplayer': 'CPlayer Smart',
    'c player smart': 'CPlayer Smart',
    # DNS Browser
    'dns browser': 'DNS Browser',
    'dnsbrowser': 'DNS Browser',
    # Dream TV
    'dream': 'Dream TV',
    'dream tv': 'Dream TV',
    'dreamtv': 'Dream TV',
    # Duplecast
    'duplecast': 'Duplecast',
    'duple cast': 'Duplecast',
    # DuplexPlay
    'duplexplay': 'DuplexPlay',
    'duplex play': 'DuplexPlay',
    'duplex': 'DuplexPlay',
    # DuplexTV
    'duplextv': 'DuplexTV',
    'duplex tv': 'DuplexTV',
    # Flix IPTV
    'flix iptv': 'Flix IPTV',
    'flixiptv': 'Flix IPTV',
    # IBO Player
    'ibo player': 'IBO Player',
    'iboplayer': 'IBO Player',
    'ibo': 'IBO Player',
    # ImPlayer
    'implayer': 'ImPlayer',
    'im player': 'ImPlayer',
    # Lazer Play
    'lazer play': 'Lazer Play',
    'lazerplay': 'Lazer Play',
    # Maximus
    'maximus': 'Maximus',
    # MetaPlayer
    'metaplayer': 'MetaPlayer',
    'meta player': 'MetaPlayer',
    # OTT Navigator
    'ottnavigator': 'OTT Navigator',
    'ott navigator': 'OTT Navigator',
    'ott': 'OTT Navigator',
    # Perfect Player
    'perfect player': 'Perfect Player',
    'perfectplayer': 'Perfect Player',
    # Prime IPTV
    'prime iptv': 'Prime IPTV',
    'primeiptv': 'Prime IPTV',
    # QuickPlayer
    'quickplayer': 'QuickPlayer',
    'quick player': 'QuickPlayer',
    # Smart STB
    'smartstb': 'Smart STB',
    'smart stb': 'Smart STB',
    'stb': 'Smart STB',
    # SmartOne
    'smartone': 'SmartOne',
    'smart one': 'SmartOne',
    # Smarters Player
    'smarters player': 'Smarters Player',
    'smartersplayer': 'Smarters Player',
    'smarters': 'Smarters Player',
    'iptv smarters': 'Smarters Player',
    'iptv smarters pro': 'Smarters Player',
    # Smarters Player Lite
    'smarters player lite': 'Smarters Player Lite',
    'smarters lite': 'Smarters Player Lite',
    'smarters player light': 'Smarters Player Lite',
    # Sparkle TV
    'sparkle': 'Sparkle TV',
    'sparkle tv': 'Sparkle TV',
    # SS IPTV
    'ssiptv': 'SS IPTV',
    'ss iptv': 'SS IPTV',
    # TiviMate
    'tivimate': 'TiviMate',
    'tivi mate': 'TiviMate',
    # Ultra Player
    'ultra player': 'Ultra Player',
    'ultraplayer': 'Ultra Player',
    # Vizzion Play
    'vizzion play': 'Vizzion Play',
    'vizzionplay': 'Vizzion Play',
    'vizzion': 'Vizzion Play',
    # Vu IPTV Player
    'vu iptv player': 'Vu IPTV Player',
    'vu iptv': 'Vu IPTV Player',
    'vuiptv': 'Vu IPTV Player',
    # Vu Player Pro
    'vu player pro': 'Vu Player Pro',
    'vuplayerpro': 'Vu Player Pro',
    'vu player': 'Vu Player Pro',
    # Warez TV
    'warez tv': 'Warez TV',
    'wareztv': 'Warez TV',
    'warez': 'Warez TV',
    # Web Cast Video
    'web cast video': 'Web Cast Video',
    'webcastvideo': 'Web Cast Video',
    'webcast video': 'Web Cast Video',
    # Web Player
    'web player': 'Web Player',
    'webplayer': 'Web Player',
    # XCIPTV
    'xciptv': 'XCIPTV',
    'xc iptv': 'XCIPTV',
    'xc': 'XCIPTV',
    # XCloud Mobile
    'xcloud mobile': 'XCloud Mobile',
    'xcloudmobile': 'XCloud Mobile',
    # XCloud TV
    'xcloud tv': 'XCloud TV',
    'xcloudtv': 'XCloud TV',
    'xcloud': 'XCloud TV',
    # XP IPTV
    'xp iptv': 'XP IPTV',
    'xpiptv': 'XP IPTV',
    # Xtream Player
    'xtream player': 'Xtream Player',
    'xtreamplayer': 'Xtream Player',
    'xtream': 'Xtream Player',
}


def normalizar_dispositivo(nome: str) -> str:
    """
    Normaliza nome do dispositivo.

    Exemplos:
        'lg' -> 'TV LG'
        'SAMSUNG' -> 'TV Samsung'
        'firestick' -> 'Fire Stick'
        'novo dispositivo' -> 'Novo Dispositivo' (fallback)
    """
    if not nome:
        return nome
    nome_lower = nome.strip().lower()
    # 1. Busca no mapeamento
    if nome_lower in DISPOSITIVOS_MAP:
        return DISPOSITIVOS_MAP[nome_lower]
    # 2. Fallback: Title Case
    return nome.strip().title()


def normalizar_aplicativo(nome: str) -> str:
    """
    Normaliza nome do aplicativo/sistema.

    Exemplos:
        'duplexplay' -> 'DuplexPlay'
        'XCIPTV' -> 'XCIPTV'
        'dream tv' -> 'Dream TV'
        'novo app' -> 'Novo App' (fallback)
    """
    if not nome:
        return nome
    nome_lower = nome.strip().lower()
    # 1. Busca no mapeamento
    if nome_lower in APLICATIVOS_MAP:
        return APLICATIVOS_MAP[nome_lower]
    # 2. Fallback: Title Case
    return nome.strip().title()


def normalizar_servidor(nome: str) -> str:
    """
    Normaliza nome do servidor (geralmente siglas em MAIÚSCULO).

    Exemplos:
        'club' -> 'CLUB'
        'play' -> 'PLAY'
        'alpha' -> 'ALPHA'
    """
    if not nome:
        return nome
    # Servidores são siglas, sempre em maiúsculo
    return nome.strip().upper()


# =============================================================================
# FUNÇÕES GET_OR_CREATE COM PREVENÇÃO DE DUPLICATAS
# =============================================================================

def get_or_create_dispositivo(nome: str, usuario):
    """
    Busca ou cria um Dispositivo com prevenção de duplicatas.

    1. Normaliza o nome recebido
    2. Busca por nome normalizado (case-insensitive)
    3. Se encontrar, retorna o existente
    4. Se não encontrar, cria com o nome normalizado

    Args:
        nome: Nome do dispositivo (será normalizado)
        usuario: Usuário proprietário

    Returns:
        tuple: (dispositivo, created) - objeto e flag se foi criado
    """
    if not nome:
        return None, False

    nome_normalizado = normalizar_dispositivo(nome)

    # Busca case-insensitive pelo nome normalizado
    dispositivo = Dispositivo.objects.filter(
        nome__iexact=nome_normalizado,
        usuario=usuario
    ).first()

    if dispositivo:
        return dispositivo, False

    # Cria novo com nome normalizado
    dispositivo = Dispositivo.objects.create(
        nome=nome_normalizado,
        usuario=usuario
    )
    return dispositivo, True


def get_or_create_aplicativo(nome: str, usuario, device_has_mac: bool = False):
    """
    Busca ou cria um Aplicativo com prevenção de duplicatas.

    1. Normaliza o nome recebido
    2. Busca por nome normalizado (case-insensitive)
    3. Se encontrar, retorna o existente (ignora device_has_mac na busca)
    4. Se não encontrar, cria com o nome normalizado

    Args:
        nome: Nome do aplicativo (será normalizado)
        usuario: Usuário proprietário
        device_has_mac: Se o app requer MAC/device_id (usado apenas na criação)

    Returns:
        tuple: (aplicativo, created) - objeto e flag se foi criado
    """
    if not nome:
        return None, False

    nome_normalizado = normalizar_aplicativo(nome)

    # Busca case-insensitive pelo nome normalizado
    aplicativo = Aplicativo.objects.filter(
        nome__iexact=nome_normalizado,
        usuario=usuario
    ).first()

    if aplicativo:
        return aplicativo, False

    # Cria novo com nome normalizado
    aplicativo = Aplicativo.objects.create(
        nome=nome_normalizado,
        device_has_mac=device_has_mac,
        usuario=usuario
    )
    return aplicativo, True


def get_or_create_servidor(nome: str, usuario):
    """
    Busca ou cria um Servidor com prevenção de duplicatas.

    1. Normaliza o nome recebido (UPPERCASE)
    2. Busca por nome normalizado (case-insensitive)
    3. Se encontrar, retorna o existente
    4. Se não encontrar, cria com o nome normalizado

    Args:
        nome: Nome do servidor (será normalizado para UPPERCASE)
        usuario: Usuário proprietário

    Returns:
        tuple: (servidor, created) - objeto e flag se foi criado
    """
    if not nome:
        return None, False

    nome_normalizado = normalizar_servidor(nome)

    # Busca case-insensitive pelo nome normalizado
    servidor = Servidor.objects.filter(
        nome__iexact=nome_normalizado,
        usuario=usuario
    ).first()

    if servidor:
        return servidor, False

    # Cria novo com nome normalizado
    servidor = Servidor.objects.create(
        nome=nome_normalizado,
        usuario=usuario
    )
    return servidor, True


def get_client_ip(request):
    """
    Extrai o endereço IPv4 do cliente a partir do request.

    Prioriza HTTP_X_FORWARDED_FOR (quando atrás de proxy/load balancer),
    depois tenta REMOTE_ADDR. Garante que sempre retorna IPv4.

    Se o cliente estiver usando IPv6, tenta converter ou retorna None.
    """
    # 1. Tentar HTTP_X_FORWARDED_FOR (proxy/load balancer)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Pode ter múltiplos IPs separados por vírgula (client, proxy1, proxy2, ...)
        # O primeiro é o IP real do cliente
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        # 2. Usar REMOTE_ADDR
        ip = request.META.get('REMOTE_ADDR', '')

    if not ip:
        return None

    # 3. Verificar se é IPv6 e tentar converter para IPv4
    import ipaddress

    try:
        ip_obj = ipaddress.ip_address(ip)

        # Se for IPv6
        if isinstance(ip_obj, ipaddress.IPv6Address):
            # Verificar se é IPv4 mapeado em IPv6 (::ffff:192.168.1.1)
            if ip_obj.ipv4_mapped:
                return str(ip_obj.ipv4_mapped)

            # Verificar se é IPv6 loopback (::1)
            if ip_obj.is_loopback:
                return '127.0.0.1'

            # IPv6 puro - não podemos converter, retornar None
            # (o campo GenericIPAddressField aceita IPv6, mas queremos apenas IPv4)
            logger.warning(f'Cliente usando IPv6 puro: {ip}. Não será registrado no log.')
            return None

        # Se for IPv4, retornar como string
        return str(ip_obj)

    except ValueError:
        # IP inválido
        logger.warning(f'IP inválido detectado: {ip}')
        return None


def get_saudacao_por_hora(hora_referencia=None):
    """Retorna saudação contextual de acordo com a hora informada ou atual."""
    if not hora_referencia:
        hora_referencia = localtime(now()).time()

    if hora_referencia < datetime.strptime("12:00:00", "%H:%M:%S").time():
        return "Bom dia"
    elif hora_referencia < datetime.strptime("18:00:00", "%H:%M:%S").time():
        return "Boa tarde"
    return "Boa noite"


def calcular_desconto_progressivo_total(cliente):
    """
    Calcula o valor total de desconto progressivo ativo para um cliente.

    Retorna um dicionário com:
    - valor_total: Decimal - Valor total do desconto aplicável
    - qtd_descontos_ativos: int - Quantidade de descontos ativos
    - qtd_descontos_aplicados: int - Quantidade de descontos realmente aplicados (respeitando limite)
    - limite_indicacoes: int - Limite configurado no plano (0 = ilimitado)
    - descontos: QuerySet - Lista dos descontos ativos

    Regras:
    - Só considera descontos ativos (ativo=True)
    - Respeita o limite de indicações configurado no plano
    - Ordena por data_inicio (descontos mais antigos primeiro)
    """
    from django.db.models import Sum

    # Buscar plano progressivo ativo do usuário
    plano_progressivo = PlanoIndicacao.objects.filter(
        usuario=cliente.usuario,
        tipo_plano="desconto_progressivo",
        ativo=True,
        status=True
    ).first()

    # Se não há plano ativo, retorna zero
    if not plano_progressivo:
        return {
            "valor_total": Decimal("0.00"),
            "qtd_descontos_ativos": 0,
            "qtd_descontos_aplicados": 0,
            "limite_indicacoes": 0,
            "descontos": DescontoProgressivoIndicacao.objects.none(),
            "plano": None,
        }

    # Buscar todos os descontos ativos deste cliente como indicador
    descontos_ativos = DescontoProgressivoIndicacao.objects.filter(
        cliente_indicador=cliente,
        ativo=True,
        plano_indicacao__tipo_plano="desconto_progressivo"
    ).order_by("data_inicio", "criado_em")

    qtd_descontos_ativos = descontos_ativos.count()
    limite = plano_progressivo.limite_indicacoes

    # Se limite = 0, significa ilimitado
    if limite == 0 or limite >= qtd_descontos_ativos:
        descontos_aplicados = descontos_ativos
        qtd_descontos_aplicados = qtd_descontos_ativos
    else:
        # Aplicar apenas até o limite (os mais antigos primeiro)
        descontos_aplicados = descontos_ativos[:limite]
        qtd_descontos_aplicados = limite

    # Calcular valor total
    valor_total = descontos_aplicados.aggregate(
        total=Sum("valor_desconto")
    )["total"] or Decimal("0.00")

    return {
        "valor_total": valor_total,
        "qtd_descontos_ativos": qtd_descontos_ativos,
        "qtd_descontos_aplicados": qtd_descontos_aplicados,
        "limite_indicacoes": limite,
        "descontos": descontos_ativos,
        "plano": plano_progressivo,
    }


def calcular_valor_mensalidade(cliente, numero_mensalidade_oferta=None):
    """
    ⭐ FASE 2.5: Calcula valor final da mensalidade considerando campanhas promocionais (Simplificado).

    Prioridade de aplicação:
    1. Campanha promocional ativa (se cliente está inscrito) - PRIORIDADE MÁXIMA
    2. Desconto progressivo por indicação (existente)
    3. Valor base do plano

    Args:
        cliente: Instância do Cliente
        numero_mensalidade_oferta: Número da mensalidade dentro da campanha (1, 2, 3...)
                                    Se None, usa o contador da assinatura

    Returns:
        Decimal: Valor final calculado para a mensalidade
    """
    from .models import AssinaturaCliente

    # 1. Verificar se cliente está em campanha
    try:
        assinatura = AssinaturaCliente.objects.get(cliente=cliente, ativo=True)

        # ⭐ SIMPLIFICAÇÃO: Sempre usa o plano atual do cliente, não precisa buscar por ID
        if assinatura.em_campanha and cliente.plano.campanha_ativa:
            # Determine which month of campaign
            numero_mes_campanha = assinatura.campanha_mensalidades_pagas + 1

            # Check if campaign is still valid (hasn't exceeded duration)
            if assinatura.campanha_duracao_total and numero_mes_campanha <= assinatura.campanha_duracao_total:
                # Calculate value based on campaign type
                if cliente.plano.campanha_tipo == 'FIXO':
                    if cliente.plano.campanha_valor_fixo:
                        return cliente.plano.campanha_valor_fixo
                else:  # PERSONALIZADO
                    # Get value for specific month (up to 12 months)
                    campo_valor = f'campanha_valor_mes_{min(numero_mes_campanha, 12)}'
                    valor_mes = getattr(cliente.plano, campo_valor, None)
                    if valor_mes:
                        return valor_mes
    except AssinaturaCliente.DoesNotExist:
        pass  # No subscription record, fallback to regular pricing

    # 2. Sem oferta - usar valor base do plano
    valor_base = cliente.plano.valor

    # 3. Aplicar desconto progressivo (sistema existente)
    desconto_info = calcular_desconto_progressivo_total(cliente)

    if desconto_info["valor_total"] > Decimal("0.00") and desconto_info["plano"]:
        valor_com_desconto = valor_base - desconto_info["valor_total"]
        valor_minimo = desconto_info["plano"].valor_minimo_mensalidade
        return max(valor_com_desconto, valor_minimo)

    return valor_base


def enroll_client_in_campaign_if_eligible(cliente):
    """
    ⭐ FASE 2: Verifica se o cliente é elegível para uma campanha e inscreve-o automaticamente.

    Regras de elegibilidade:
    - O plano do cliente deve ter uma campanha ativa (campanha_ativa=True)
    - A data atual deve estar dentro do período de validade (campanha_data_inicio <= hoje <= campanha_data_fim)
    - O cliente deve ter um registro de AssinaturaCliente

    Args:
        cliente: Instância do Cliente

    Returns:
        bool: True se foi inscrito na campanha, False caso contrário
    """
    from .models import AssinaturaCliente
    import logging

    logger = logging.getLogger(__name__)
    hoje = timezone.localdate()

    try:
        plano = cliente.plano

        # Check if plan has an active campaign
        if not plano.campanha_ativa:
            return False

        # Check if campaign is within validity period
        if plano.campanha_data_inicio and hoje < plano.campanha_data_inicio:
            return False

        if plano.campanha_data_fim and hoje > plano.campanha_data_fim:
            return False

        # Check if campaign has required data
        if not plano.campanha_duracao_meses:
            return False

        # Get or create subscription record
        assinatura, created = AssinaturaCliente.objects.get_or_create(
            cliente=cliente,
            defaults={
                'plano': plano,
                'data_inicio_assinatura': hoje,
                'ativo': True
            }
        )

        # ⭐ SIMPLIFICAÇÃO: Enroll in campaign (sem persistência de plano_id)
        assinatura.ativo = True  # Garantir que a assinatura está ativa
        assinatura.plano = plano  # Sincronizar com o plano atual do cliente
        assinatura.em_campanha = True
        assinatura.campanha_data_adesao = hoje
        assinatura.campanha_mensalidades_pagas = 0
        assinatura.campanha_duracao_total = plano.campanha_duracao_meses
        assinatura.save()

        logger.info(
            f"[CAMPANHA] Cliente {cliente.nome} inscrito na campanha do plano {plano.nome} "
            f"(duração: {plano.campanha_duracao_meses} meses)"
        )

        return True

    except Exception as e:
        logger.error(f"[CAMPANHA] Erro ao inscrever cliente {cliente.nome} na campanha: {e}")
        return False


def registrar_log(mensagem: str, usuario: str, log_directory: str) -> None:
    """Anexa ``mensagem`` ao arquivo de log associado ao ``usuario``."""
    if not log_directory:
        logger.warning("Log directory not configured for usuario=%s. Mensagem: %s", usuario, mensagem)
        return

    log_filename = Path(log_directory) / f"{usuario}.log"
    append_line(log_filename, mensagem)


def historico_obter_vigente(cliente: Cliente):
    """Retorna o registro de histórico vigente (sem fim) do cliente, se existir."""
    return (
        ClientePlanoHistorico.objects
        .filter(cliente=cliente, usuario=cliente.usuario, fim__isnull=True)
        .order_by('-inicio', '-criado_em')
        .first()
    )


def historico_encerrar_vigente(cliente: Cliente, fim: date) -> None:
    """Fecha o histórico ativo do cliente na data fornecida, respeitando o início."""
    vigente = historico_obter_vigente(cliente)
    if not vigente:
        return
    if fim < vigente.inicio:
        fim = vigente.inicio
    vigente.fim = fim
    vigente.save(update_fields=["fim"])


def historico_iniciar(
    cliente: Cliente,
    plano: Plano = None,
    inicio: date = None,
    motivo: str = ClientePlanoHistorico.MOTIVO_CREATE,
) -> ClientePlanoHistorico:
    """Cria um novo registro de histórico ajustando valores padrão quando necessários."""
    if inicio is None:
        inicio = timezone.localdate()
    if plano is None:
        plano = cliente.plano
    return ClientePlanoHistorico.objects.create(
        cliente=cliente,
        usuario=cliente.usuario,
        plano=plano,
        plano_nome=getattr(plano, 'nome', ''),
        telas=getattr(plano, 'telas', 1) or 1,
        valor_plano=getattr(plano, 'valor', 0) or 0,
        inicio=inicio,
        motivo=motivo,
    )



def _prepare_extra_payload(value):
    """Normaliza payloads extras para serem serializados em ``JSONField``."""
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {str(key): _prepare_extra_payload(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_prepare_extra_payload(item) for item in value]

    return str(value)


def log_user_action(
    request,
    action: str,
    instance=None,
    message: str = "",
    extra=None,
    entity: str = None,
    object_id=None,
    object_repr: str = None,
) -> None:
    """Registra uma ação manual do usuário autenticado no ``UserActionLog``."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return

    try:
        if entity is None and instance is not None:
            entity = instance.__class__.__name__

        if object_id is None and instance is not None:
            object_id = getattr(instance, "pk", "") or ""

        if object_repr is None and instance is not None:
            object_repr = str(instance)

        # Obter IPv4 do cliente
        ip_address = get_client_ip(request)

        payload = {
            "usuario": user,
            "acao": action if action in dict(UserActionLog.ACTION_CHOICES) else UserActionLog.ACTION_OTHER,
            "entidade": entity or "",
            "objeto_id": str(object_id) if object_id not in (None, "") else "",
            "objeto_repr": (object_repr or "")[:255],
            "mensagem": message or "",
            "extras": _prepare_extra_payload(extra),
            "ip": ip_address,
            "request_path": (getattr(request, "path", "") or "")[:255],
        }

        UserActionLog.objects.create(**payload)

    except Exception as exc:
        logger.exception("Falha ao registrar log de ação do usuário: %s", exc)


def gerar_variacoes_telefone2(telefone: str) -> list:
    """Retorna variações comuns de números nacionais para pesquisa em banco."""
    variacoes = set()
    tel = re.sub(r'\D+', '', telefone)
    logger.debug("[TEL_VARIACOES] Gerando variações para: %s", tel)

    if len(tel) < 8:
        logger.debug("[TEL_VARIACOES] Telefone muito curto, retornando: %s", tel)
        return [tel]
    if len(tel) == 11 and tel[2] == '9':
        variacoes.add(tel)
        variacoes.add(tel[2:])
        variacoes.add(tel[3:])
        variacoes.add('55' + tel)
        variacoes.add('55' + tel[:2] + tel[3:])
        logger.debug("[TEL_VARIACOES] Variações (celular atual): %s", variacoes)
    elif len(tel) == 10:
        variacoes.add(tel)
        variacoes.add(tel[2:])
        variacoes.add('9' + tel[2:])
        variacoes.add('55' + tel)
        variacoes.add('55' + tel[:2] + '9' + tel[2:])
        logger.debug("[TEL_VARIACOES] Variações (fixo/cel sem 9): %s", variacoes)
    elif len(tel) == 9 and tel[0] == '9':
        variacoes.add(tel)
        variacoes.add(tel[1:])
        logger.debug("[TEL_VARIACOES] Variações (9 + NNNNNNNN): %s", variacoes)
    elif len(tel) == 8:
        variacoes.add(tel)
        logger.debug("[TEL_VARIACOES] Variações (NNNNNNNN): %s", variacoes)
    elif len(tel) == 13 and tel.startswith('55'):
        variacoes.add(tel)
        variacoes.add(tel[:4] + tel[5:])
        logger.debug("[TEL_VARIACOES] Variações (55DD9NNNNNNNN): %s", variacoes)
    elif len(tel) == 12 and tel.startswith('55'):
        variacoes.add(tel)
        variacoes.add(tel[:4] + '9' + tel[4:])
        logger.debug("[TEL_VARIACOES] Variações (55DDNNNNNNNN): %s", variacoes)
    if len(tel) > 8:
        variacoes.add(tel)
    logger.debug("[TEL_VARIACOES] Variações finais: %s", variacoes)
    return sorted(variacoes)


def gerar_variacoes_telefone(telefone: str) -> set:
    """
    Gera variações básicas (com/sem +) utilizadas na busca de clientes existentes.

    NÃO adiciona DDI automaticamente - preserva o DDI original do número.
    """
    tel = re.sub(r'\D+', '', telefone)
    variacoes = set()

    # Base sempre com e sem +
    variacoes.add(tel)
    variacoes.add('+' + tel)

    # Variações específicas para números brasileiros (com 9º dígito)
    # Formato BR com DDI: 55 + DDD(2) + 9 + número(8) = 13 dígitos
    if len(tel) == 13 and tel.startswith('55') and tel[4] == '9':
        sem_nove = tel[:4] + tel[5:]
        variacoes.add(sem_nove)
        variacoes.add('+' + sem_nove)

    return variacoes


def existe_cliente_variacoes(telefone_variacoes, user):
    """Confere se alguma variação pertence a clientes cadastrados do usuário."""
    q = Q()
    for var in telefone_variacoes:
        telefone_formatado = var if str(var).startswith('+') else f'+{str(var)}'
        q |= Q(telefone=telefone_formatado)
    
    cliente = Cliente.objects.filter(q, usuario=user).first()
    if cliente:
        cliente_telefone = cliente.telefone
    else:
        cliente_telefone = None

    return cliente_telefone

def normalizar_telefone(telefone: str) -> str:
    """
    Normaliza telefone removendo caracteres especiais e corrigindo DDI duplicado.

    NÃO adiciona DDI automaticamente - o telefone deve vir com DDI do frontend
    (intl-tel-input) ou da importação.

    Exemplos:
        +55558396239140 -> 5583996239140 (remove 55 duplicado para BR)
        +5583996239140  -> 5583996239140
        +33751085604    -> 33751085604 (preserva DDI internacional)
        5583996239140   -> 5583996239140
    """
    # Remove tudo exceto dígitos
    tel = re.sub(r'\D+', '', telefone)

    # Corrige DDI duplicado brasileiro: 5555... -> 55...
    # Telefone BR válido com DDI tem 12-13 dígitos (55 + DDD + número)
    # Se tem 14+ dígitos e começa com 5555, provavelmente é DDI duplicado
    if len(tel) >= 14 and tel.startswith('5555'):
        tel = tel[2:]  # Remove os primeiros 55
        logger.debug("[normalizar_telefone] DDI duplicado corrigido: %s -> %s", telefone, tel)

    return tel


# Alias para compatibilidade com código existente
normalizar_telefone_br = normalizar_telefone


def validar_tel_whatsapp(telefone: str, token: str, user=None) -> dict:
    """
    Valida um telefone contra a base de clientes e a API do WhatsApp.

    Retorna um dicionário contendo o telefone original, o telefone formatado
    para WhatsApp (quando válido), a existência de cliente associado e se o
    número está apto a receber mensagens.
    """
    func_name = validar_tel_whatsapp.__name__

    # Normaliza o telefone antes de validar (corrige DDI duplicado, etc)
    telefone_original = telefone
    telefone = normalizar_telefone_br(telefone)

    if telefone != re.sub(r'\D+', '', telefone_original):
        logger.info(
            "[%s] Telefone normalizado: %s -> %s",
            func_name, telefone_original, telefone
        )

    telefone_variacoes = gerar_variacoes_telefone(telefone)
    resultado = {
        "telefone_cadastro": telefone_original,
        "telefone_validado_wpp": None,
        "cliente_existe_telefone": None,
        "wpp": False,
    }
    wpp_valido = False

    try:
        check = check_number_status(telefone, token, user)
        if isinstance(check, dict):
            if check.get("status"):
                wpp_valido = True
                telefone = str(check.get("user") or telefone)
            elif check.get("error"):
                logger.error(
                    "[VALIDAR][ERRO] Falha ao checar %s no WhatsApp: %s",
                    telefone,
                    check["error"],
                )
        else:
            logger.error("[VALIDAR][ERRO] Retorno inesperado ao checar %s: %s", telefone, check)
    except Exception as exc:
        logger.error("[VALIDAR][ERRO] Erro ao checar %s no WhatsApp: %s", telefone, exc)

    if not wpp_valido:
        numero_formatado = telefone if str(telefone).startswith('+') else f'+{telefone}'
        resultado["telefone_validado_wpp"] = numero_formatado
        return resultado

    numero_formatado = telefone if str(telefone).startswith('+') else f'+{telefone}'
    resultado["telefone_validado_wpp"] = numero_formatado
    resultado["wpp"] = True
    resultado["cliente_existe_telefone"] = existe_cliente_variacoes(telefone_variacoes, user)

    logger.info("[%s] [%s] Resultado da validação: %s", func_name, user, resultado)
    return resultado


def envio_apos_novo_cadastro(cliente):
    """
    Após cadastrar um novo cliente, envia mensagem de boas-vindas e, se houver indicação,
    avalia bônus para o cliente indicador.
    """
    usuario = cliente.usuario
    nome_cliente = str(cliente)
    primeiro_nome = nome_cliente.split(' ')[0]

    tipo_envio = "Cadastro"
    token_user = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    if not token_user:
        return

    telefone = str(cliente.telefone or "").strip()

    if not telefone:
        return

    mensagem = (
        f"Obrigado, {primeiro_nome}. O seu pagamento foi confirmado e o seu acesso já foi disponibilizado!\n\n"
        "A partir daqui, caso precise de algum auxílio pode entrar em contato.\n"
        "Peço que salve o nosso contato para que receba as nossas notificações aqui no WhatsApp."
    )

    try:
        time.sleep(5)  # Aguarda 5 segundos antes de enviar a confirmação
        enviar_mensagem(
            telefone,
            mensagem,
            usuario,
            token_user.token,
            nome_cliente,
            tipo_envio
        )
    except Exception as e:
        logger.error(f"[WPP] Falha ao enviar mensagem para {telefone}: {e}", exc_info=True)

    # Verifica se há planos do tipo 'desconto' ou 'dinheiro' ativos e habilitados
    planos_desconto_dinheiro = PlanoIndicacao.objects.filter(
        usuario=usuario,
        tipo_plano__in=["desconto", "dinheiro"],
        ativo=True,
        status=True
    ).exists()

    if cliente.indicado_por and planos_desconto_dinheiro:
        envio_apos_nova_indicacao(usuario, cliente, cliente.indicado_por)

    # Verifica se há plano de desconto progressivo ativo e envia notificação ao indicador
    plano_progressivo = PlanoIndicacao.objects.filter(
        usuario=usuario,
        tipo_plano="desconto_progressivo",
        ativo=True,
        status=True
    ).exists()

    if cliente.indicado_por and plano_progressivo:
        try:
            envio_desconto_progressivo_indicacao(usuario, cliente, cliente.indicado_por)
        except Exception as e:
            logger.error(f"[WPP] Falha ao enviar notificação de desconto progressivo: {e}", exc_info=True)


def envio_apos_nova_indicacao(usuario, novo_cliente, cliente_indicador):
    """
    Avalia a quantidade de indicações feitas por um cliente e envia mensagem de bonificação com descontos ou prêmios.

    - 1 indicação: aplica desconto na mensalidade atual em aberto (com valor cheio), ou na próxima disponível.
    - 2 indicações: bonificação em dinheiro (deduzindo eventual desconto já concedido se a mensalidade foi paga).

    Regras:
    - Para aplicar desconto, deve haver PlanoIndicacao ativo do tipo 'desconto'.
    - Para aplicar bonificação, deve haver PlanoIndicacao ativo do tipo 'dinheiro'.
    - Valor final da mensalidade não pode ser inferior ao valor mínimo definido no plano.
    - Caso a mensalidade com desconto ainda esteja em aberto ao receber a segunda indicação, ela será ajustada de volta ao valor original, e o bônus será pago integralmente.
    """
    nome_cliente = str(cliente_indicador)
    telefone_cliente = str(cliente_indicador.telefone)
    primeiro_nome = nome_cliente.split(' ')[0]
    tipo_envio = "Indicação"
    now = datetime.now()

    try:
        token_user = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    except SessaoWpp.DoesNotExist:
        return

    if not telefone_cliente:
        return

    # Planos ativos e habilitados
    plano_desconto = PlanoIndicacao.objects.filter(
        tipo_plano="desconto",
        usuario=usuario,
        ativo=True,
        status=True
    ).first()
    plano_dinheiro = PlanoIndicacao.objects.filter(
        tipo_plano="dinheiro",
        usuario=usuario,
        ativo=True,
        status=True
    ).first()

    if not plano_desconto and not plano_dinheiro:
        return # Nenhum plano ativo e habilitado, então não há benefício

    # Mensalidades
    mensalidades_em_aberto = Mensalidade.objects.filter(
        cliente=cliente_indicador,
        dt_pagamento=None,
        dt_cancelamento=None,
        pgto=False,
        cancelado=False
    ).order_by('dt_vencimento')

    mensalidade_mes_atual_paga = Mensalidade.objects.filter(
        cliente=cliente_indicador,
        dt_pagamento__month=now.month,
        dt_pagamento__year=now.year,
        pgto=True
    ).first()

    qtd_indicacoes = Cliente.objects.filter(
        indicado_por=cliente_indicador,
        data_adesao__gte=now.replace(day=1)
    ).count()

    saudacao = get_saudacao_por_hora()

    # 1 INDICAÇÃO - DESCONTO
    if qtd_indicacoes == 1 and plano_desconto:
        mensalidade_alvo = None
        for m in mensalidades_em_aberto:
            if m.valor == cliente_indicador.plano.valor:
                mensalidade_alvo = m
                break
        if not mensalidade_alvo:
            for m in mensalidades_em_aberto:
                if m.valor > plano_desconto.valor_minimo_mensalidade:
                    mensalidade_alvo = m
                    break

        if mensalidade_alvo:
            novo_valor = max(mensalidade_alvo.valor - plano_desconto.valor, plano_desconto.valor_minimo_mensalidade)
            vencimento = mensalidade_alvo.dt_vencimento.strftime("%d/%m")
            valor_formatado = f"{novo_valor:.2f}"

            mensagem = (
                f"Olá, {primeiro_nome}. {saudacao}!\n\n"
                f"Agradeço pela indicação do(a) *{novo_cliente.nome}*.\n"
                f"A adesão dele(a) foi concluída e por isso estamos lhe bonificando com desconto.\n\n"
                f"⚠ *FIQUE ATENTO AO SEU VENCIMENTO:*\n\n- [{vencimento}] R$ {valor_formatado}\n\nObrigado! 😁"
            )

            mensalidade_alvo.valor = novo_valor
            mensalidade_alvo.save()
            enviar_mensagem(telefone_cliente, mensagem, usuario, token_user.token, nome_cliente, tipo_envio)

    # 2 INDICAÇÕES - BONIFICAÇÃO
    elif qtd_indicacoes == 2 and plano_dinheiro:
        bonus_total = plano_dinheiro.valor
        desconto_aplicado = Decimal("0.00")
        mensagem_extra = ""
        aplicar_deducao = False

        mensalidade_aberta_com_desconto = None
        for m in mensalidades_em_aberto:
            if m.valor < cliente_indicador.plano.valor:
                mensalidade_aberta_com_desconto = m
                break

        if mensalidade_aberta_com_desconto:
            desconto_aplicado = cliente_indicador.plano.valor - mensalidade_aberta_com_desconto.valor
            mensalidade_aberta_com_desconto.valor = cliente_indicador.plano.valor
            mensalidade_aberta_com_desconto.save()
            # Não aplica dedução no bônus
            aplicar_deducao = False

        elif mensalidade_mes_atual_paga and mensalidade_mes_atual_paga.valor < cliente_indicador.plano.valor:
            desconto_aplicado = cliente_indicador.plano.valor - mensalidade_mes_atual_paga.valor
            aplicar_deducao = True

        if aplicar_deducao:
            bonus_final = max(bonus_total - desconto_aplicado, Decimal("0.00"))
            mensagem_extra = (
                f"💡 Como você já havia recebido R$ {desconto_aplicado:.2f} de desconto em sua mensalidade deste mês, este valor foi deduzido do bônus.\n"
                f"Seu bônus total é de R$ {bonus_total:.2f}, e após a dedução você receberá R$ {bonus_final:.2f}.\n\n"
            )
        else:
            bonus_final = bonus_total

        indicacoes = Cliente.objects.filter(
            indicado_por=cliente_indicador,
            data_adesao__gte=now.replace(day=1)
        )
        linhas = [f"- [{c.data_adesao.strftime('%d/%m')}] [{c.nome}]" for c in indicacoes]

        mensagem = (
            f"🎉 *PARABÉNS PELAS INDICAÇÕES!* 🎉\n\nOlá, {primeiro_nome}. {saudacao}! Tudo bem?\n\n"
            f"Agradecemos muito pela sua parceria e confiança em nossos serviços. Este mês, registramos as seguintes indicações feitas por você:\n\n"
            + "\n".join(linhas) +
            f"\n\n{mensagem_extra}"
            "Agora, você pode escolher como prefere:\n\n"
            "- *Receber o valor via PIX* em sua conta.\n"
            "- *Aplicar como desconto* nas suas próximas mensalidades.\n\n"
            "Nos avise aqui qual opção prefere, e nós registraremos a sua bonificação."
        )

        enviar_mensagem(telefone_cliente, mensagem, usuario, token_user.token, nome_cliente, tipo_envio)


def envio_desconto_progressivo_indicacao(usuario, novo_cliente, cliente_indicador):
    """
    Envia mensagem WhatsApp informando sobre desconto progressivo ativo.

    Informa ao cliente indicador:
    - Novo desconto recebido
    - Valor total de desconto acumulado
    - Quantidade de indicações ativas
    - Valor da próxima mensalidade com desconto
    """
    nome_cliente = str(cliente_indicador)
    telefone_cliente = str(cliente_indicador.telefone)
    primeiro_nome = nome_cliente.split(' ')[0]
    tipo_envio = "Desconto Progressivo"

    try:
        token_user = SessaoWpp.objects.filter(usuario=usuario, is_active=True).first()
    except SessaoWpp.DoesNotExist:
        return

    if not telefone_cliente:
        return

    # Calcular desconto total atual
    desconto_info = calcular_desconto_progressivo_total(cliente_indicador)

    if desconto_info["valor_total"] <= Decimal("0.00"):
        return

    saudacao = get_saudacao_por_hora()
    valor_desconto_total = desconto_info["valor_total"]
    qtd_indicacoes_ativas = desconto_info["qtd_descontos_ativos"]
    qtd_aplicadas = desconto_info["qtd_descontos_aplicados"]
    limite = desconto_info["limite_indicacoes"]

    # Calcular valor da próxima mensalidade
    valor_plano = cliente_indicador.plano.valor
    valor_mensalidade = valor_plano - valor_desconto_total
    if desconto_info["plano"]:
        valor_minimo = desconto_info["plano"].valor_minimo_mensalidade
        valor_mensalidade = max(valor_mensalidade, valor_minimo)

    # Montar informação sobre limite
    if limite > 0:
        info_limite = f"Limite de indicações com desconto: *{qtd_aplicadas}/{limite}*"
        if qtd_indicacoes_ativas > limite:
            info_limite += f" (você tem {qtd_indicacoes_ativas} indicações ativas, mantendo margem de segurança)"
    else:
        info_limite = f"Total de indicações ativas: *{qtd_indicacoes_ativas}*"

    # Buscar mensalidade em aberto para informar vencimento
    mensalidade_aberta = Mensalidade.objects.filter(
        cliente=cliente_indicador,
        pgto=False,
        cancelado=False,
        dt_cancelamento=None
    ).order_by('dt_vencimento').first()

    if mensalidade_aberta:
        vencimento_info = f"📅 *Próximo vencimento:* {mensalidade_aberta.dt_vencimento.strftime('%d/%m/%Y')}"
        valor_info = f"💰 *Valor com desconto:* R$ {mensalidade_aberta.valor:.2f}"
    else:
        vencimento_info = ""
        valor_info = f"💰 *Próximas mensalidades:* R$ {valor_mensalidade:.2f}"

    mensagem = (
        f"✨ *NOVO DESCONTO PROGRESSIVO!* ✨\n\n"
        f"Olá, {primeiro_nome}. {saudacao}!\n\n"
        f"Parabéns! Você acaba de receber um novo desconto permanente por ter indicado *{novo_cliente.nome}*.\n\n"
        f"📊 *Resumo dos seus descontos:*\n"
        f"• Desconto total acumulado: *R$ {valor_desconto_total:.2f}*\n"
        f"• {info_limite}\n\n"
        f"{vencimento_info}\n"
        f"{valor_info}\n\n"
        f"💡 *Como funciona:*\n"
        f"Enquanto seus indicados permanecerem ativos, você mantém esse desconto em TODAS as suas mensalidades!\n\n"
        f"Obrigado pela confiança! 🙏"
    )

    enviar_mensagem(telefone_cliente, mensagem, usuario, token_user.token, nome_cliente, tipo_envio)


def enviar_mensagem(telefone: str, mensagem: str, usuario: str, token: str, cliente: str, tipo_envio: str) -> None:
    """
    Envia uma mensagem via API WPP para um número validado.
    Registra logs de sucesso, falha e número inválido.
    """
    log_writer = lambda mensagem_log: registrar_log(mensagem_log, usuario, DIR_LOGS_INDICACOES)

    templates = LogTemplates(
        success=TEMPLATE_LOG_MSG_SUCESSO,
        failure=TEMPLATE_LOG_MSG_FALHOU,
        invalid=TEMPLATE_LOG_TELEFONE_INVALIDO,
    )

    config = MessageSendConfig(
        usuario=usuario,
        token=token,
        telefone=telefone,
        mensagem=mensagem,
        tipo_envio=tipo_envio,
        cliente=cliente,
        log_writer=log_writer,
        log_templates=templates,
        retry_wait=(5.0, 10.0),
    )
    resultado = send_message(config)

    if not resultado.success and resultado.reason == "missing_phone":
        timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
        log_line = templates.invalid.format(timestamp, tipo_envio.upper(), usuario, cliente)
        logger.warning(log_line.strip())


def definir_dia_pagamento(dia_adesao):
    """
    Define o dia padrão de pagamento com base no dia de adesão.
    Utiliza faixas de dias para arredondar a data de pagamento para dias fixos do mês.
    """
    if dia_adesao in range(3, 8):
        return 5
    elif dia_adesao in range(8, 13):
        return 10
    elif dia_adesao in range(13, 18):
        return 15
    elif dia_adesao in range(18, 23):
        return 20
    elif dia_adesao in range(23, 28):
        return 25
    return 30


# CRIA NOVA MENSALIDADE APÓS CADASTRO DE NOVO CLIENTE
def criar_mensalidade(cliente):
    """
    Cria automaticamente uma nova mensalidade ao cadastrar um novo cliente.
    A data de vencimento é calculada com base em:
    - Último pagamento (se houver)
    - Data de adesão (se houver)
    - Data de vencimento definida manualmente (fallback)
    O vencimento sempre aponta para o próximo ciclo válido, conforme o tipo do plano.
    """
    hoje = timezone.localdate()

    if cliente.ultimo_pagamento:
        dia_pagamento = definir_dia_pagamento(cliente.ultimo_pagamento.day)
    elif cliente.data_adesao and cliente.data_vencimento is None:
        dia_pagamento = definir_dia_pagamento(cliente.data_adesao.day)
    else:
        dia_pagamento = cliente.data_vencimento.day if cliente.data_vencimento else hoje.day

    mes = hoje.month
    ano = hoje.year

    try:
        vencimento = datetime(ano, mes, dia_pagamento)
    except ValueError:
        vencimento = (datetime(ano, mes, 1) + relativedelta(months=1)) - timedelta(days=1)

    if vencimento.date() < hoje:
        plano_nome = cliente.plano.nome.lower()
        if "mensal" in plano_nome:
            vencimento += relativedelta(months=1)
        elif "bimestral" in plano_nome:
            vencimento += relativedelta(months=2)
        elif "trimestral" in plano_nome:
            vencimento += relativedelta(months=3)
        elif "semestral" in plano_nome:
            vencimento += relativedelta(months=6)
        elif "anual" in plano_nome:
            vencimento += relativedelta(years=1)

    # ⭐ FASE 2.5: Calcular valor com rastreamento detalhado de campanha e descontos
    valor_base = cliente.plano.valor
    gerada_em_campanha = False
    desconto_campanha = Decimal("0.00")
    desconto_progressivo = Decimal("0.00")
    tipo_campanha = None
    numero_mes_campanha = None

    # Verificar se há campanha ativa
    try:
        from nossopainel.models import AssinaturaCliente
        assinatura = AssinaturaCliente.objects.get(cliente=cliente, ativo=True)

        if assinatura.em_campanha and cliente.plano.campanha_ativa:
            numero_mes = assinatura.campanha_mensalidades_pagas + 1

            if numero_mes <= assinatura.campanha_duracao_total:
                gerada_em_campanha = True
                tipo_campanha = cliente.plano.campanha_tipo
                numero_mes_campanha = numero_mes

                # Calcular valor com campanha
                if tipo_campanha == 'FIXO':
                    valor_com_campanha = cliente.plano.campanha_valor_fixo
                else:  # PERSONALIZADO
                    campo = f'campanha_valor_mes_{min(numero_mes, 12)}'
                    valor_com_campanha = getattr(cliente.plano, campo, None)

                if valor_com_campanha:
                    desconto_campanha = valor_base - valor_com_campanha
                    valor_final = valor_com_campanha
    except:
        pass

    # Se não tem campanha, verificar desconto progressivo
    if not gerada_em_campanha:
        desconto_info = calcular_desconto_progressivo_total(cliente)
        desconto_progressivo = desconto_info["valor_total"]

        if desconto_progressivo > Decimal("0.00"):
            valor_com_desconto = valor_base - desconto_progressivo
            valor_minimo = desconto_info["plano"].valor_minimo_mensalidade if desconto_info["plano"] else valor_base
            valor_final = max(valor_com_desconto, valor_minimo)
        else:
            valor_final = valor_base
    else:
        # Se tem campanha, não aplica desconto progressivo
        desconto_progressivo = Decimal("0.00")

    # ⭐ FASE 2.5: Criar mensalidade com rastreamento completo
    Mensalidade.objects.create(
        cliente=cliente,
        valor=valor_final,
        dt_vencimento=vencimento.date(),
        usuario=cliente.usuario,
        # Novos campos de rastreamento
        gerada_em_campanha=gerada_em_campanha,
        valor_base_plano=valor_base,
        desconto_campanha=desconto_campanha,
        desconto_progressivo=desconto_progressivo,
        tipo_campanha=tipo_campanha,
        numero_mes_campanha=numero_mes_campanha,
        dados_historicos_verificados=True,  # Dados precisos (mensalidade nova)
    )


def mask_phone_number(phone):
    """
    Mascara número de telefone para proteção em logs.

    Formato entrada: +5511987654321
    Formato saída: +55XX****4321

    SEGURANÇA:
    - Logs de arquivo contêm números mascarados
    - Console do modal exibe números completos (para conferência do usuário)
    - Proteção contra vazamento de dados sensíveis em logs persistentes

    Args:
        phone (str): Número de telefone completo

    Returns:
        str: Número mascarado

    Examples:
        >>> mask_phone_number('+5511987654321')
        '+55XX****4321'
        >>> mask_phone_number('5511987654321')
        '55XX****4321'
    """
    if not phone:
        return phone

    # Remove espaços e caracteres especiais (exceto +)
    clean_phone = re.sub(r'[^\d+]', '', str(phone))

    # Se começa com +, preserva
    prefix = '+' if clean_phone.startswith('+') else ''
    digits = clean_phone.lstrip('+')

    # Formato: +55 (2) + XX (mask DDD) + **** (mask middle) + 4321 (last 4)
    if len(digits) >= 10:
        country_code = digits[:2]  # 55
        last_four = digits[-4:]    # 4321
        masked = f"{prefix}{country_code}XX****{last_four}"
        return masked
    else:
        # Número muito curto, mascara apenas middle
        if len(digits) >= 4:
            return f"{prefix}{digits[:-4]}****{digits[-4:]}"
        else:
            return f"{prefix}{'*' * len(digits)}"


def get_envios_hoje(usuario):
    """
    Retorna quantidade de envios realizados hoje pelo usuário.

    Usado para:
    - Exibir contador no modal (ex: "47/150 envios hoje")
    - Determinar delay incremental (> 200 envios = +10s)
    - Exibir warnings de limite recomendado

    Args:
        usuario (User): Usuário Django

    Returns:
        int: Quantidade de envios hoje

    Examples:
        >>> user = User.objects.get(username='admin')
        >>> get_envios_hoje(user)
        47
    """
    from .models import MensagemEnviadaWpp

    hoje = timezone.now().date()
    return MensagemEnviadaWpp.objects.filter(
        usuario=usuario,
        data_envio=hoje
    ).count()


# ==================== CRIPTOGRAFIA (RESELLER PASSWORDS) ====================

def get_cipher():
    """
    Retorna uma instância do cipher Fernet usando a chave configurada em .env.

    Returns:
        Fernet: Instância do cipher para criptografia/descriptografia

    Raises:
        ValueError: Se FERNET_KEY não estiver configurada ou for inválida
    """
    from cryptography.fernet import Fernet
    from django.conf import settings

    fernet_key = getattr(settings, 'FERNET_KEY', None)

    if not fernet_key:
        raise ValueError(
            "FERNET_KEY não configurada. "
            "Adicione FERNET_KEY ao arquivo .env. "
            "Gere uma chave com: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )

    try:
        return Fernet(fernet_key.encode())
    except Exception as e:
        raise ValueError(f"FERNET_KEY inválida: {e}")


def encrypt_password(plaintext):
    """
    Criptografa uma senha em texto plano.

    Args:
        plaintext (str): Senha em texto plano

    Returns:
        str: Senha criptografada em formato string

    Raises:
        ValueError: Se plaintext for vazio ou None
        Exception: Se houver erro na criptografia

    Example:
        >>> senha_criptografada = encrypt_password("senha123")
        >>> print(senha_criptografada)
        'gAAAAABhj...'
    """
    if not plaintext:
        raise ValueError("Senha não pode ser vazia")

    try:
        cipher = get_cipher()
        encrypted_bytes = cipher.encrypt(plaintext.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        raise Exception(f"Erro ao criptografar senha: {e}")


def decrypt_password(ciphertext):
    """
    Descriptografa uma senha criptografada.

    Args:
        ciphertext (str): Senha criptografada

    Returns:
        str: Senha em texto plano

    Raises:
        ValueError: Se ciphertext for vazio ou None
        Exception: Se houver erro na descriptografia (chave inválida ou dados corrompidos)

    Example:
        >>> senha_original = decrypt_password('gAAAAABhj...')
        >>> print(senha_original)
        'senha123'
    """
    if not ciphertext:
        raise ValueError("Senha criptografada não pode ser vazia")

    try:
        cipher = get_cipher()
        decrypted_bytes = cipher.decrypt(ciphertext.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        raise Exception(f"Erro ao descriptografar senha: {e}")


def test_encryption():
    """
    Função de teste para verificar se a criptografia está funcionando corretamente.

    Retorna True se os testes passarem, caso contrário levanta uma exceção.

    Example:
        >>> test_encryption()
        True
    """
    test_password = "test_password_123!@#"

    # Teste 1: Encriptar e decriptar
    encrypted = encrypt_password(test_password)
    decrypted = decrypt_password(encrypted)

    if decrypted != test_password:
        raise AssertionError(
            f"Teste de criptografia falhou: "
            f"senha original '{test_password}' != senha descriptografada '{decrypted}'"
        )

    # Teste 2: Garantir que senhas diferentes geram outputs diferentes
    encrypted2 = encrypt_password(test_password + "_different")
    if encrypted == encrypted2:
        raise AssertionError("Senhas diferentes geraram o mesmo hash criptografado")

    return True


# Aliases genéricos para uso em campos que não são senhas
# (API keys, tokens, secrets, etc.)
encrypt_value = encrypt_password
decrypt_value = decrypt_password


# ==================== MANIPULAÇÃO DE DOMÍNIOS DNS ====================

def validar_formato_dominio(dominio: str) -> bool:
    """
    Valida se o domínio possui formato correto (protocolo + host + porta opcional).

    Formato esperado:
    - http://dominio.com
    - https://dominio.com
    - http://dominio.com:8080
    - http://192.168.1.1:80

    Args:
        dominio (str): Domínio a ser validado

    Returns:
        bool: True se válido, False caso contrário

    Examples:
        >>> validar_formato_dominio('http://exemplo.com')
        True
        >>> validar_formato_dominio('http://exemplo.com:8080')
        True
        >>> validar_formato_dominio('ftp://exemplo.com')
        False
        >>> validar_formato_dominio('exemplo.com')
        False
    """
    if not dominio or not isinstance(dominio, str):
        return False

    # Regex para validar: ^(http|https)://[host](:[porta])?$
    # - Protocolo: http ou https
    # - Host: letras, números, pontos, hífens
    # - Porta (opcional): : seguido de 1-5 dígitos
    pattern = r'^https?://[a-zA-Z0-9.-]+(:[0-9]{1,5})?$'

    return bool(re.match(pattern, dominio.strip()))


def extrair_dominio_de_url(url: str) -> str:
    """
    Extrai apenas o domínio (protocolo + netloc) de uma URL completa.

    Args:
        url (str): URL completa

    Returns:
        str: Domínio extraído (protocolo + netloc)

    Examples:
        >>> extrair_dominio_de_url('http://exemplo.com/get.php?user=123')
        'http://exemplo.com'
        >>> extrair_dominio_de_url('http://exemplo.com:8080/path/to/file')
        'http://exemplo.com:8080'
        >>> extrair_dominio_de_url('https://sub.exemplo.com/file')
        'https://sub.exemplo.com'
    """
    from urllib.parse import urlparse

    if not url or not isinstance(url, str):
        return ''

    try:
        parsed = urlparse(url.strip())

        # Reconstrói apenas protocolo + netloc
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

        return ''
    except Exception as e:
        logger.error(f"Erro ao extrair domínio da URL '{url}': {e}")
        return ''


def substituir_dominio_em_url(url_completa: str, dominio_origem: str, dominio_destino: str) -> str:
    """
    Substitui o domínio em uma URL completa, preservando path, query params e fragment.

    Fluxo:
    1. Extrai domínio da URL completa
    2. Verifica se corresponde ao dominio_origem
    3. Substitui pelo dominio_destino
    4. Preserva path, query string e fragment

    Args:
        url_completa (str): URL completa a ser modificada
        dominio_origem (str): Domínio esperado (para validação)
        dominio_destino (str): Novo domínio a ser aplicado

    Returns:
        str: URL com domínio substituído

    Raises:
        ValueError: Se o domínio da URL não corresponder ao dominio_origem

    Examples:
        >>> substituir_dominio_em_url(
        ...     'http://old.com/get.php?user=123',
        ...     'http://old.com',
        ...     'http://new.com:8080'
        ... )
        'http://new.com:8080/get.php?user=123'

        >>> substituir_dominio_em_url(
        ...     'http://old.com:80/path/to/file?param=value#section',
        ...     'http://old.com:80',
        ...     'http://new.com'
        ... )
        'http://new.com/path/to/file?param=value#section'
    """
    from urllib.parse import urlparse, urlunparse

    if not url_completa or not isinstance(url_completa, str):
        raise ValueError("URL completa não pode ser vazia")

    if not dominio_origem or not isinstance(dominio_origem, str):
        raise ValueError("Domínio origem não pode ser vazio")

    if not dominio_destino or not isinstance(dominio_destino, str):
        raise ValueError("Domínio destino não pode ser vazio")

    try:
        # Parse da URL completa
        parsed_url = urlparse(url_completa.strip())

        # Extrai domínio da URL
        dominio_atual = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # Valida se corresponde ao domínio origem
        if dominio_atual != dominio_origem.strip():
            raise ValueError(
                f"Domínio da URL ({dominio_atual}) não corresponde ao domínio origem esperado ({dominio_origem})"
            )

        # Parse do domínio destino
        parsed_destino = urlparse(dominio_destino.strip())

        # Reconstrói URL com novo domínio, preservando path, params, query, fragment
        nova_url = urlunparse((
            parsed_destino.scheme,      # scheme (http/https)
            parsed_destino.netloc,      # netloc (host:port)
            parsed_url.path,            # path (preservado)
            parsed_url.params,          # params (preservado)
            parsed_url.query,           # query string (preservado)
            parsed_url.fragment         # fragment (preservado)
        ))

        return nova_url

    except ValueError:
        # Re-lança ValueError (já tratado acima)
        raise
    except Exception as e:
        logger.error(
            f"Erro ao substituir domínio: URL='{url_completa}', "
            f"Origem='{dominio_origem}', Destino='{dominio_destino}'. Erro: {e}"
        )
        raise Exception(f"Erro ao substituir domínio: {e}")
