"""
Views do JampaBet
"""
import json
import logging
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import models
from django.contrib.auth.hashers import make_password

from .models import JampabetUser, Match, Bet, AuditLog, BrazilianTeam, Competition
from .auth import JampabetAuth, jampabet_login_required
from .services.bet_service import BetService

logger = logging.getLogger(__name__)


# ==================== PAGINAS DE AUTENTICACAO ====================

def login_view(request):
    """
    Pagina de login com splash screen e modal 2FA.
    NAO renderiza o app - apenas o formulario de login.
    """
    # Se ja esta autenticado, vai para o app
    if JampabetAuth.is_authenticated(request):
        return redirect('jampabet:app')

    return render(request, 'jampabet/login.html')


@require_POST
def api_login_step1(request):
    """
    API: Etapa 1 do login - valida email/senha e envia token 2FA.
    """
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not email or not password:
            return JsonResponse({'error': 'Preencha todos os campos'}, status=400)

        # Autentica credenciais
        user = JampabetAuth.authenticate(email, password)
        if not user:
            return JsonResponse({'error': 'E-mail ou senha incorretos'}, status=401)

        # Verifica se conta esta verificada
        if not user.is_verified:
            return JsonResponse({
                'error': 'Conta nao verificada. Verifique seu e-mail para ativar a conta.'
            }, status=403)

        # Verifica se conta esta ativa
        if not user.is_active:
            return JsonResponse({'error': 'Conta desativada.'}, status=403)

        # Envia token 2FA por e-mail
        login_token = JampabetAuth.send_login_token(user, request)
        if not login_token:
            return JsonResponse({
                'error': 'Erro ao enviar codigo de verificacao. Tente novamente.'
            }, status=500)

        # Salva user_id temporario na sessao (ainda nao logado)
        request.session['pending_2fa_user'] = user.id
        request.session['pending_2fa_expires'] = (timezone.now() + timedelta(minutes=10)).isoformat()
        request.session.modified = True

        # Mascara o e-mail para exibicao
        at_index = email.index('@')
        email_hint = email[:3] + '***' + email[at_index:]

        return JsonResponse({
            'success': True,
            'message': 'Codigo enviado para seu e-mail',
            'email_hint': email_hint
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Dados invalidos'}, status=400)
    except Exception as e:
        logger.error(f"Erro em api_login_step1: {e}")
        return JsonResponse({'error': 'Erro interno'}, status=500)


@require_POST
def api_login_step2(request):
    """
    API: Etapa 2 do login - valida token 2FA e cria sessao.
    """
    try:
        data = json.loads(request.body)
        token = data.get('token', '').strip()

        if not token or len(token) != 6:
            return JsonResponse({'error': 'Digite os 6 digitos do codigo'}, status=400)

        # Verifica sessao pendente
        user_id = request.session.get('pending_2fa_user')
        expires = request.session.get('pending_2fa_expires')

        if not user_id or not expires:
            return JsonResponse({
                'error': 'Sessao expirada. Faca login novamente.'
            }, status=400)

        # Verifica se sessao expirou
        from datetime import datetime
        expires_dt = datetime.fromisoformat(expires)
        if timezone.now() > timezone.make_aware(expires_dt.replace(tzinfo=None)):
            # Limpa sessao
            request.session.pop('pending_2fa_user', None)
            request.session.pop('pending_2fa_expires', None)
            return JsonResponse({
                'error': 'Sessao expirada. Faca login novamente.'
            }, status=400)

        # Busca usuario
        try:
            user = JampabetUser.objects.get(id=user_id)
        except JampabetUser.DoesNotExist:
            return JsonResponse({'error': 'Usuario nao encontrado'}, status=400)

        # Valida token 2FA
        if not JampabetAuth.verify_login_token(user, token):
            return JsonResponse({
                'error': 'Codigo invalido ou expirado'
            }, status=401)

        # Login efetivo
        JampabetAuth.login(request, user)

        # Limpa dados temporarios
        request.session.pop('pending_2fa_user', None)
        request.session.pop('pending_2fa_expires', None)

        return JsonResponse({
            'success': True,
            'redirect': '/app/'  # Sera reescrito pelo middleware para /app/bahia/app/
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Dados invalidos'}, status=400)
    except Exception as e:
        logger.error(f"Erro em api_login_step2: {e}")
        return JsonResponse({'error': 'Erro interno'}, status=500)


@require_POST
def api_resend_token(request):
    """
    API: Reenvia token 2FA.
    """
    try:
        # Verifica sessao pendente
        user_id = request.session.get('pending_2fa_user')
        if not user_id:
            return JsonResponse({
                'error': 'Sessao expirada. Faca login novamente.'
            }, status=400)

        try:
            user = JampabetUser.objects.get(id=user_id)
        except JampabetUser.DoesNotExist:
            return JsonResponse({'error': 'Usuario nao encontrado'}, status=400)

        # Envia novo token
        login_token = JampabetAuth.send_login_token(user, request)
        if not login_token:
            return JsonResponse({
                'error': 'Erro ao enviar codigo. Tente novamente.'
            }, status=500)

        # Renova sessao
        request.session['pending_2fa_expires'] = (timezone.now() + timedelta(minutes=10)).isoformat()
        request.session.modified = True

        return JsonResponse({
            'success': True,
            'message': 'Novo codigo enviado'
        })

    except Exception as e:
        logger.error(f"Erro em api_resend_token: {e}")
        return JsonResponse({'error': 'Erro interno'}, status=500)


@require_POST
def logout_view(request):
    """Logout"""
    JampabetAuth.logout(request)
    return redirect('jampabet:login')


def activate_view(request, token):
    """
    Pagina de ativacao de conta.
    """
    error = None
    success = False
    user = None

    # Busca usuario pelo token
    try:
        user = JampabetUser.objects.get(
            verification_token=token,
            is_verified=False
        )

        # Verifica se token expirou
        if not user.is_verification_token_valid():
            error = 'Este link de ativacao expirou. Entre em contato com o administrador.'
            user = None

    except JampabetUser.DoesNotExist:
        error = 'Link de ativacao invalido ou conta ja ativada.'

    if request.method == 'POST' and user:
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        if len(password) < 8:
            error = 'A senha deve ter pelo menos 8 caracteres'
        elif password != password_confirm:
            error = 'As senhas nao coincidem'
        else:
            # Ativa conta
            activated_user = JampabetAuth.activate_account(token, password)
            if activated_user:
                success = True
                user = None  # Esconde o formulario
            else:
                error = 'Erro ao ativar conta. Tente novamente.'

    return render(request, 'jampabet/activate.html', {
        'user': user,
        'token': token,
        'error': error,
        'success': success
    })


# ==================== APP PRINCIPAL (REQUER AUTENTICACAO) ====================

@jampabet_login_required
def app_view(request):
    """
    App principal - renderiza o app completo para usuarios autenticados.
    """
    user = request.jampabet_user
    now = timezone.now()

    # Proxima partida
    next_match = Match.objects.filter(
        status='upcoming',
        date__gte=now - timedelta(hours=3)
    ).order_by('date').first()

    # Posicao no ranking
    users_above = JampabetUser.objects.filter(
        is_active=True,
        is_verified=True,
        points__gt=user.points
    ).count()
    user_position = users_above + 1

    # Total de participantes
    total_players = JampabetUser.objects.filter(is_active=True, is_verified=True).count()

    # Top 3 para podio
    ranking_top3 = list(JampabetUser.objects.filter(
        is_active=True,
        is_verified=True
    ).order_by('-points', 'name')[:3])

    # Ranking completo
    ranking = list(JampabetUser.objects.filter(
        is_active=True,
        is_verified=True
    ).order_by('-points', 'name')[:20])

    # Apostas do usuario
    user_bets = list(Bet.objects.filter(user=user).select_related('match').order_by('-created_at')[:10])

    # Proximas partidas
    upcoming_matches = list(Match.objects.filter(
        status__in=['upcoming', 'live'],
        date__gte=now - timedelta(hours=3)
    ).order_by('date')[:10])

    # Verifica se esta em modo de desenvolvimento
    from django.conf import settings
    is_dev_mode = settings.DEBUG

    context = {
        'next_match': next_match,
        'user_position': user_position,
        'total_players': total_players,
        'ranking_top3': ranking_top3,
        'ranking': ranking,
        'user_bets': user_bets,
        'upcoming_matches': upcoming_matches,
        'active_tab': 'palpites',
        'is_dev_mode': is_dev_mode,
    }

    return render(request, 'jampabet/app.html', context)


# ==================== PAGINAS LEGADAS (redirecionam para app) ====================

def home(request):
    """Pagina inicial - renderiza app ou login diretamente"""
    if JampabetAuth.is_authenticated(request):
        # Renderiza o app diretamente (evita redirect que duplica /app/)
        return app_view(request)
    return redirect('jampabet:login')


@jampabet_login_required
def dashboard(request):
    """Dashboard - redireciona para app"""
    return redirect('jampabet:app')


@jampabet_login_required
def ranking(request):
    """Ranking - redireciona para app"""
    return redirect('jampabet:app')


@jampabet_login_required
def matches(request):
    """Partidas - redireciona para app"""
    return redirect('jampabet:app')


@jampabet_login_required
def standings(request):
    """Classificacoes - redireciona para app"""
    return redirect('jampabet:app')


@jampabet_login_required
def my_bets(request):
    """Minhas apostas - redireciona para app"""
    return redirect('jampabet:app')


# ==================== API ENDPOINTS ====================

@require_http_methods(['GET'])
def api_matches(request):
    """API: Lista todas as partidas"""
    status = request.GET.get('status')

    queryset = Match.objects.all()
    if status:
        queryset = queryset.filter(status=status)

    matches = list(queryset.values(
        'id', 'external_id', 'home_team', 'away_team',
        'home_team_logo', 'away_team_logo', 'date',
        'competition', 'venue', 'location', 'round',
        'status', 'result_bahia', 'result_opponent'
    ))

    # Converte datetime para string
    for match in matches:
        match['date'] = match['date'].isoformat()

    return JsonResponse({'matches': matches})


@require_http_methods(['GET'])
def api_upcoming_matches(request):
    """API: Proximas partidas"""
    now = timezone.now()
    limit = int(request.GET.get('limit', 10))

    matches = Match.objects.filter(
        status__in=['upcoming', 'live'],
        date__gte=now - timedelta(hours=3)
    ).order_by('date')[:limit]

    data = []
    for match in matches:
        can_bet, _ = BetService.can_place_bet(match)
        data.append({
            'id': match.id,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'date': match.date.isoformat(),
            'competition': match.competition,
            'status': match.status,
            'can_bet': can_bet
        })

    return JsonResponse({'matches': data})


@require_http_methods(['GET'])
def api_next_bahia_match(request):
    """
    API: Retorna a proxima partida do Bahia para o card principal.

    Logica:
    - Retorna a partida mais proxima que ainda nao passou de "ontem"
    - Se ao vivo, retorna com status 'live'
    - Se encerrou hoje ou ontem, retorna com status 'finished'
    - Inclui informacao de se pode palpitar e tempo restante
    """
    now = timezone.now()
    yesterday = now - timedelta(days=1)
    yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)

    # Busca partida ao vivo primeiro
    live_match = Match.objects.filter(status='live').first()

    if live_match:
        match = live_match
    else:
        # Busca proxima partida (agendada) OU partida de ontem/hoje que ainda nao "expirou"
        match = Match.objects.filter(
            date__gte=yesterday_start
        ).exclude(
            status='cancelled'
        ).order_by('date').first()

    if not match:
        return JsonResponse({'match': None})

    # Verifica se pode palpitar
    can_bet, reason = BetService.can_place_bet(match)

    # Calcula tempo restante para palpitar (10 min antes)
    bet_deadline = match.date - timedelta(minutes=10)
    time_until_lock = None
    if now < bet_deadline:
        delta = bet_deadline - now
        total_seconds = int(delta.total_seconds())
        if total_seconds > 0:
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            if days > 0:
                time_until_lock = f"{days}d {hours}h"
            elif hours > 0:
                time_until_lock = f"{hours}h {minutes}min"
            elif minutes > 0:
                time_until_lock = f"{minutes}min {seconds}s"
            else:
                time_until_lock = f"{seconds}s"

    # Busca palpite do usuario se autenticado
    user_bet = None
    bet = None
    if hasattr(request, 'jampabet_user') and request.jampabet_user:
        bet = Bet.objects.filter(user=request.jampabet_user, match=match).first()
        if bet:
            user_bet = {
                'home_win_bahia': bet.home_win_bahia,
                'home_win_opponent': bet.home_win_opponent,
                'draw_bahia': bet.draw_bahia,
                'draw_opponent': bet.draw_opponent,
                'points_earned': bet.points_earned
            }

    # Determina resultado do palpite (hit/miss/none)
    bet_result = None
    if match.status == 'finished' and match.result_bahia is not None:
        if bet:
            if bet.points_earned > 0:
                bet_result = 'hit'
            else:
                bet_result = 'miss'
        else:
            bet_result = 'none'

    return JsonResponse({
        'match': {
            'id': match.id,
            'external_id': match.external_id,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'home_team_logo': match.home_team_logo,
            'away_team_logo': match.away_team_logo,
            'date': match.date.isoformat(),
            'competition': match.competition,
            'competition_logo': match.competition_logo,
            'venue': match.venue,
            'location': match.location,
            'round': match.round,
            'status': match.status,
            'result_bahia': match.result_bahia,
            'result_opponent': match.result_opponent,
            'elapsed_time': match.elapsed_time,
            'can_bet': can_bet,
            'bet_reason': reason,
            'time_until_lock': time_until_lock,
            'user_bet': user_bet,
            'bet_result': bet_result,
        }
    })


@require_http_methods(['GET'])
@jampabet_login_required
def api_user_bets_history(request):
    """
    API: Retorna historico de palpites do usuario para a aba de Palpites.

    Retorna:
    - upcoming: partidas futuras (pode palpitar)
    - recent: ultimas 2 partidas passadas (sempre visiveis)
    - older: demais partidas passadas (area colapsavel)
    """
    user = request.jampabet_user
    now = timezone.now()
    yesterday = now - timedelta(days=1)
    yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)

    # Partidas futuras (para palpitar) - exclui a que esta no card principal se for live
    upcoming_matches = Match.objects.filter(
        status='upcoming',
        date__gt=now
    ).exclude(
        status='live'
    ).order_by('date')[:10]

    # Partidas passadas (finalizadas ou de ontem pra tras)
    past_matches = Match.objects.filter(
        date__lt=now
    ).exclude(
        status__in=['cancelled', 'postponed']
    ).order_by('-date')

    # Busca todos os palpites do usuario de uma vez
    user_bets = {bet.match_id: bet for bet in Bet.objects.filter(user=user)}

    def serialize_match(match, include_bet=True):
        bet = user_bets.get(match.id) if include_bet else None

        # Determina resultado do palpite
        bet_result = None  # 'hit', 'miss', 'none'
        if match.status == 'finished' and match.result_bahia is not None:
            if bet:
                if bet.points_earned > 0:
                    bet_result = 'hit'
                else:
                    bet_result = 'miss'
            else:
                bet_result = 'none'

        can_bet, reason = BetService.can_place_bet(match)

        return {
            'id': match.id,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'home_team_logo': match.home_team_logo,
            'away_team_logo': match.away_team_logo,
            'date': match.date.isoformat(),
            'competition': match.competition,
            'location': match.location,
            'status': match.status,
            'result_bahia': match.result_bahia,
            'result_opponent': match.result_opponent,
            'can_bet': can_bet,
            'bet': {
                'home_win_bahia': bet.home_win_bahia,
                'home_win_opponent': bet.home_win_opponent,
                'draw_bahia': bet.draw_bahia,
                'draw_opponent': bet.draw_opponent,
                'points_earned': bet.points_earned
            } if bet else None,
            'bet_result': bet_result  # 'hit', 'miss', 'none', ou None se nao finalizado
        }

    # Serializa partidas
    upcoming_data = [serialize_match(m) for m in upcoming_matches]

    # Partidas passadas: separa em recentes (2) e antigas
    past_list = list(past_matches[:50])  # Limita a 50 mais recentes
    recent_data = [serialize_match(m) for m in past_list[:2]]
    older_data = [serialize_match(m) for m in past_list[2:]]

    return JsonResponse({
        'upcoming': upcoming_data,
        'recent': recent_data,
        'older': older_data,
        'stats': {
            'total_bets': len(user_bets),
            'total_hits': sum(1 for b in user_bets.values() if b.points_earned > 0),
            'total_points': user.points
        }
    })


@require_http_methods(['GET'])
def api_match_detail(request, match_id):
    """
    API: Retorna detalhes de uma partida especifica pelo ID.

    Usado pelo modal de palpites quando os dados nao sao passados diretamente.
    """
    try:
        match = Match.objects.get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'error': 'Partida nao encontrada'}, status=404)

    # Verifica se pode palpitar
    can_bet, reason = BetService.can_place_bet(match)

    # Busca palpite do usuario se autenticado
    user_bet = None
    user = JampabetAuth.get_user(request)
    if user:
        bet = Bet.objects.filter(user=user, match=match).first()
        if bet:
            user_bet = {
                'home_win_bahia': bet.home_win_bahia,
                'home_win_opponent': bet.home_win_opponent,
                'draw_bahia': bet.draw_bahia,
                'draw_opponent': bet.draw_opponent,
                'points_earned': bet.points_earned
            }

    return JsonResponse({
        'match': {
            'id': match.id,
            'external_id': match.external_id,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'home_team_logo': match.home_team_logo,
            'away_team_logo': match.away_team_logo,
            'date': match.date.isoformat(),
            'competition': match.competition,
            'competition_logo': match.competition_logo,
            'venue': match.venue,
            'location': match.location,
            'round': match.round,
            'status': match.status,
            'result_bahia': match.result_bahia,
            'result_opponent': match.result_opponent,
            'elapsed_time': match.elapsed_time,
            'can_bet': can_bet,
            'bet_reason': reason,
            'user_bet': user_bet,
        }
    })


@require_http_methods(['GET'])
def api_ranking(request):
    """
    API: Ranking completo de usuarios.

    Retorna:
    - top3: Top 3 para o podio
    - ranking: Posicoes 4-10
    - current_user: Posicao do usuario logado (se fora do top 10)
    - total_players: Total de participantes
    """
    from django.db.models import Count

    # Busca todos os usuarios ativos
    all_users = list(JampabetUser.objects.filter(
        is_active=True,
        is_verified=True
    ).order_by('-points', '-hits', 'name'))

    total_players = len(all_users)

    # Usuario atual (se logado)
    current_user_id = None
    current_user_position = None
    current_user_data = None

    if hasattr(request, 'jampabet_user') and request.jampabet_user:
        current_user_id = request.jampabet_user.id
        # Encontra posicao do usuario atual
        for i, user in enumerate(all_users, 1):
            if user.id == current_user_id:
                current_user_position = i
                if i > 10:
                    # Usuario fora do top 10, inclui seus dados
                    current_user_data = {
                        'position': i,
                        'id': user.id,
                        'name': user.name,
                        'points': user.points,
                        'hits': user.hits,
                        'total_bets': Bet.objects.filter(user=user).count()
                    }
                break

    def serialize_user(user, position):
        return {
            'position': position,
            'id': user.id,
            'name': user.name,
            'points': user.points,
            'hits': user.hits,
            'total_bets': Bet.objects.filter(user=user).count(),
            'is_current_user': user.id == current_user_id
        }

    # Top 3 para o podio
    top3 = [serialize_user(user, i+1) for i, user in enumerate(all_users[:3])]

    # Posicoes 4-10
    ranking_4_10 = [serialize_user(user, i+4) for i, user in enumerate(all_users[3:10])]

    return JsonResponse({
        'top3': top3,
        'ranking': ranking_4_10,
        'current_user': current_user_data,
        'current_user_position': current_user_position,
        'total_players': total_players
    })


@require_http_methods(['GET'])
def api_competitions(request):
    """
    API: Lista competicoes disponiveis para o select do frontend.
    Retorna apenas competicoes ativas (is_tracked=True) se existirem no banco,
    senao retorna a lista padrao de competicoes.
    """
    from .models import Competition
    from .services.api_football import APIFootballService

    # Tenta buscar do banco (competicoes monitoradas)
    tracked_competitions = Competition.objects.filter(is_tracked=True).order_by('name')

    if tracked_competitions.exists():
        competitions = []
        for comp in tracked_competitions:
            competitions.append({
                'id': comp.external_id,
                'name': comp.name,
                'short_name': comp.short_name,
                'type': comp.competition_type,
                'logo_url': comp.logo_url,
            })
        return JsonResponse({
            'competitions': competitions,
            'from_db': True
        })

    # Fallback: retorna lista padrao de competicoes
    default_competitions = []
    for league_id, name in APIFootballService.LEAGUES.items():
        default_competitions.append({
            'id': league_id,
            'name': name,
            'short_name': name,
            'type': 'league',
            'logo_url': f'https://media.api-sports.io/football/leagues/{league_id}.png',
        })

    return JsonResponse({
        'competitions': default_competitions,
        'from_db': False
    })


@require_http_methods(['GET'])
def api_standings(request, league_id):
    """
    API: Classificacao de uma liga.
    Usa cache do Django para evitar chamadas excessivas a API.
    Cache expira em 1 hora.

    Query params:
        - season: Temporada (ano)
        - force_api: Se '1', forca busca na API ignorando cache
    """
    from django.core.cache import cache
    from .services.api_football import APIFootballService
    from datetime import datetime

    season = request.GET.get('season')
    force_api = request.GET.get('force_api') == '1'

    try:
        # Converte season para int se fornecido
        if season:
            season = int(season)
        else:
            season = datetime.now().year

        cache_key = f"standings_{league_id}_{season}"

        # Tenta buscar do cache primeiro
        if not force_api:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f"[Standings] Cache hit: league={league_id}")
                cached_data['from_cache'] = True
                return JsonResponse(cached_data)

        # Se nao houver no cache ou force_api=1, busca da API
        logger.debug(f"[Standings] Cache miss, buscando da API (league={league_id})")
        data = APIFootballService.get_standings(league_id, season)
        data['from_cache'] = False

        # Adiciona tipo de competicao (para diferenciar liga de copa/mata-mata)
        try:
            comp = Competition.objects.filter(external_id=league_id).first()
            if comp:
                data['competition_type'] = comp.competition_type
        except Exception:
            pass

        # Armazena no cache por 1 hora (3600 segundos)
        cache.set(cache_key, data, timeout=3600)

        return JsonResponse(data)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Erro ao buscar standings: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(['GET'])
def api_league_fixtures(request, league_id):
    """
    API: Jogos de uma liga por rodada.
    Estrategia cache-first:
    1. Busca primeiro do banco de dados (cache)
    2. Se nao houver dados ou force_api=1, busca da API

    Query params:
        - season: Temporada (ano)
        - round: Numero da rodada (para ligas com "Regular Season - X")
        - round_raw: Nome raw da rodada da API (ex: "1st Phase - 1", "Semi-finals")
        - force_api: Se '1', forca busca na API ignorando cache
    """
    from .services.api_football import APIFootballService
    from .models import Fixture, BrazilianTeam

    season = request.GET.get('season')
    round_number = request.GET.get('round')
    round_raw = request.GET.get('round_raw')  # Nome raw da rodada da API
    force_api = request.GET.get('force_api') == '1'

    try:
        if round_number:
            round_number = int(round_number)

        # Converte season para int se fornecido
        if season:
            season = int(season)

        # Tenta buscar do banco primeiro (cache)
        if not force_api:
            db_data = APIFootballService.get_fixtures_from_db(
                Fixture, BrazilianTeam, league_id, season, round_number, round_raw
            )
            if db_data.get('matches'):
                logger.debug(f"[Fixtures] Cache hit: {len(db_data['matches'])} partidas do banco")
                return JsonResponse(db_data)

        # Se nao houver no banco ou force_api=1, busca da API
        logger.debug(f"[Fixtures] Cache miss, buscando da API (league={league_id}, round_raw={round_raw})")
        data = APIFootballService.get_league_fixtures_by_round(
            league_id, season, round_number, round_raw
        )
        data['from_cache'] = False
        return JsonResponse(data)

    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Erro ao buscar fixtures: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(['GET'])
def api_league_rounds(request, league_id):
    """
    API: Lista de rodadas disponiveis para uma liga.
    Estrategia cache-first:
    1. Busca primeiro do banco de dados (cache)
    2. Se nao houver dados ou force_api=1, busca da API

    Query params:
        - season: Temporada (ano)
        - force_api: Se '1', forca busca na API ignorando cache
    """
    from .services.api_football import APIFootballService
    from .models import Fixture

    season = request.GET.get('season')
    force_api = request.GET.get('force_api') == '1'

    try:
        # Converte season para int se fornecido
        if season:
            season = int(season)

        # Tenta buscar do banco primeiro (cache)
        if not force_api:
            db_data = APIFootballService.get_rounds_from_db(Fixture, league_id, season)
            if db_data.get('rounds'):
                logger.debug(f"[Rounds] Cache hit: {len(db_data['rounds'])} rodadas do banco")
                return JsonResponse(db_data)

        # Se nao houver no banco ou force_api=1, busca da API
        logger.debug(f"[Rounds] Cache miss, buscando da API (league={league_id})")
        data = APIFootballService.get_league_rounds(league_id, season)
        data['from_cache'] = False
        return JsonResponse(data)

    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Erro ao buscar rodadas da liga {league_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(['POST'])
def api_place_bet(request):
    """API: Criar/atualizar aposta"""
    if not JampabetAuth.is_authenticated(request):
        return JsonResponse({'error': 'Nao autenticado'}, status=401)

    user = JampabetAuth.get_user(request)

    try:
        data = json.loads(request.body)
        match_id = data.get('match_id')
        match = get_object_or_404(Match, id=match_id)

        can_bet, message = BetService.can_place_bet(match)
        if not can_bet:
            return JsonResponse({'error': message}, status=400)

        existing_bet = Bet.objects.filter(user=user, match=match).first()

        if existing_bet:
            bet = BetService.update_bet(
                existing_bet,
                data['home_win_bahia'], data['home_win_opponent'],
                data['draw_bahia'], data['draw_opponent'],
                request
            )
        else:
            bet = BetService.create_bet(
                user, match,
                data['home_win_bahia'], data['home_win_opponent'],
                data['draw_bahia'], data['draw_opponent'],
                request
            )

        return JsonResponse({
            'success': True,
            'bet_id': bet.id,
            'message': 'Palpite atualizado' if existing_bet else 'Palpite criado'
        })

    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Erro em api_place_bet: {e}")
        return JsonResponse({'error': 'Erro interno'}, status=500)


@require_http_methods(['GET'])
def api_get_bet(request, match_id):
    """API: Obtem aposta do usuario para uma partida"""
    if not JampabetAuth.is_authenticated(request):
        return JsonResponse({'error': 'Nao autenticado'}, status=401)

    user = JampabetAuth.get_user(request)

    bet = Bet.objects.filter(user=user, match_id=match_id).first()

    if not bet:
        return JsonResponse({'bet': None})

    return JsonResponse({
        'bet': {
            'id': bet.id,
            'home_win_bahia': bet.home_win_bahia,
            'home_win_opponent': bet.home_win_opponent,
            'draw_bahia': bet.draw_bahia,
            'draw_opponent': bet.draw_opponent,
            'points_earned': bet.points_earned
        }
    })


# ==================== APIs ADMINISTRATIVAS ====================

def _is_admin(request):
    """Verifica se o usuario e admin do JampaBet"""
    # Verifica se a sessao tem o usuario JampaBet
    session_key = 'jampabet_user_id'
    user_id = request.session.get(session_key)
    logger.debug(f"_is_admin: session jampabet_user_id={user_id}")

    is_auth = JampabetAuth.is_authenticated(request)
    logger.debug(f"_is_admin check: is_authenticated={is_auth}")
    if not is_auth:
        logger.warning(f"_is_admin: Usuario nao autenticado (session_keys={list(request.session.keys())})")
        return False
    user = JampabetAuth.get_user(request)
    is_admin = user and user.is_admin
    logger.debug(f"_is_admin check: user={user}, user.email={user.email if user else None}, is_admin={is_admin}")
    return is_admin


@require_http_methods(['GET'])
def api_admin_check(request):
    """API: Verifica status de autenticacao admin (para debug)"""
    session_key = 'jampabet_user_id'
    user_id = request.session.get(session_key)
    is_auth = JampabetAuth.is_authenticated(request)
    user = JampabetAuth.get_user(request)

    return JsonResponse({
        'session_user_id': user_id,
        'is_authenticated': is_auth,
        'user_email': user.email if user else None,
        'is_admin': user.is_admin if user else False,
        'session_keys': list(request.session.keys()),
    })


@require_http_methods(['GET'])
def api_admin_stats(request):
    """API: Estatisticas administrativas"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .models import BrazilianTeam, Competition, Fixture

    stats = {
        'teams': BrazilianTeam.objects.count(),
        'competitions': Competition.objects.count(),
        'competitions_tracked': Competition.objects.filter(is_tracked=True).count(),
        'fixtures': Fixture.objects.count(),
        'fixtures_live': Fixture.objects.filter(status='live').count(),
        'fixtures_scheduled': Fixture.objects.filter(status='scheduled').count(),
        'fixtures_finished': Fixture.objects.filter(status='finished').count(),
        'users': JampabetUser.objects.count(),
        'bets': Bet.objects.count(),
    }

    return JsonResponse({'stats': stats})


@csrf_exempt
@require_http_methods(['POST'])
def api_admin_sync_teams(request):
    """API: Sincroniza times brasileiros da API"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .services.api_football import APIFootballService
    from .models import BrazilianTeam

    try:
        count = APIFootballService.sync_brazilian_teams(BrazilianTeam)
        return JsonResponse({
            'success': True,
            'message': f'{count} times sincronizados',
            'count': count
        })
    except Exception as e:
        logger.error(f"Erro ao sincronizar times: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def api_admin_sync_competitions(request):
    """API: Sincroniza competicoes brasileiras da API"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .services.api_football import APIFootballService
    from .models import Competition

    try:
        count = APIFootballService.sync_competitions(Competition)
        return JsonResponse({
            'success': True,
            'message': f'{count} competicoes sincronizadas',
            'count': count
        })
    except Exception as e:
        logger.error(f"Erro ao sincronizar competicoes: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def api_admin_sync_fixtures(request):
    """API: Sincroniza partidas das competicoes monitoradas"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .services.api_football import APIFootballService
    from .models import Competition, Fixture, BrazilianTeam

    try:
        data = json.loads(request.body) if request.body else {}
        league_id = data.get('league_id')
        season = data.get('season')

        count = APIFootballService.sync_fixtures(
            Fixture, Competition, BrazilianTeam,
            league_id=league_id, season=season
        )
        return JsonResponse({
            'success': True,
            'message': f'{count} partidas sincronizadas',
            'count': count
        })
    except Exception as e:
        logger.error(f"Erro ao sincronizar partidas: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def api_admin_toggle_competition(request, competition_id):
    """API: Ativa/desativa monitoramento de uma competicao"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .models import Competition

    try:
        competition = Competition.objects.get(id=competition_id)
        competition.is_tracked = not competition.is_tracked
        competition.save()

        return JsonResponse({
            'success': True,
            'is_tracked': competition.is_tracked,
            'message': f'{competition.name} {"ativada" if competition.is_tracked else "desativada"}'
        })
    except Competition.DoesNotExist:
        return JsonResponse({'error': 'Competicao nao encontrada'}, status=404)
    except Exception as e:
        logger.error(f"Erro ao alterar competicao: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(['GET'])
def api_admin_competitions(request):
    """API: Lista todas as competicoes com status"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .models import Competition, Fixture

    competitions = []
    for comp in Competition.objects.all().order_by('name'):
        fixture_count = Fixture.objects.filter(competition=comp).count()
        competitions.append({
            'id': comp.id,
            'external_id': comp.external_id,
            'name': comp.name,
            'short_name': comp.short_name,
            'type': comp.competition_type,
            'logo_url': comp.logo_url,
            'is_tracked': comp.is_tracked,
            'is_active': comp.is_active,
            'fixture_count': fixture_count,
            'current_season': comp.current_season,
        })

    return JsonResponse({'competitions': competitions})


@require_http_methods(['GET'])
def api_admin_teams(request):
    """API: Lista todos os times cadastrados"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .models import BrazilianTeam

    teams = []
    for team in BrazilianTeam.objects.all().order_by('name'):
        teams.append({
            'id': team.id,
            'external_id': team.external_id,
            'name': team.name,
            'short_name': team.short_name,
            'display_name': team.display_name,
            'logo_url': team.logo_url,
            'custom_logo_url': team.custom_logo_url,
            'state': team.state,
            'city': team.city,
            'stadium': team.stadium,
        })

    return JsonResponse({'teams': teams})


# ==================== APIs DE GERENCIAMENTO DE PARTIDAS (DEV ONLY) ====================

def _is_dev_admin(request):
    """
    Verifica se o usuario e admin E estamos em ambiente de desenvolvimento.
    Retorna True apenas se DEBUG=True e usuario e admin.
    """
    from django.conf import settings
    if not settings.DEBUG:
        return False
    return _is_admin(request)


@require_http_methods(['GET'])
def api_admin_matches(request):
    """
    API: Lista todas as partidas para gerenciamento (DEV ONLY).
    Retorna partidas ordenadas por data (mais recentes primeiro).
    """
    if not _is_dev_admin(request):
        return JsonResponse({'error': 'Acesso negado. Requer admin em ambiente de desenvolvimento.'}, status=403)

    matches = []
    for match in Match.objects.all().order_by('-date')[:50]:
        matches.append({
            'id': match.id,
            'external_id': match.external_id,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'home_team_logo': match.home_team_logo,
            'away_team_logo': match.away_team_logo,
            'date': match.date.isoformat() if match.date else None,
            'competition': match.competition,
            'competition_logo': match.competition_logo,
            'venue': match.venue,
            'location': match.location,
            'round': match.round,
            'status': match.status,
            'result_bahia': match.result_bahia,
            'result_opponent': match.result_opponent,
            'elapsed_time': match.elapsed_time,
            'created_at': match.created_at.isoformat() if match.created_at else None,
            'updated_at': match.updated_at.isoformat() if match.updated_at else None,
        })

    return JsonResponse({'matches': matches})


@require_http_methods(['GET'])
def api_admin_match_detail(request, match_id):
    """
    API: Retorna detalhes de uma partida especifica (DEV ONLY).
    """
    if not _is_dev_admin(request):
        return JsonResponse({'error': 'Acesso negado. Requer admin em ambiente de desenvolvimento.'}, status=403)

    try:
        match = Match.objects.get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'error': 'Partida nao encontrada'}, status=404)

    # Conta palpites dessa partida
    bets_count = Bet.objects.filter(match=match).count()

    return JsonResponse({
        'match': {
            'id': match.id,
            'external_id': match.external_id,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'home_team_logo': match.home_team_logo,
            'away_team_logo': match.away_team_logo,
            'date': match.date.isoformat() if match.date else None,
            'competition': match.competition,
            'competition_logo': match.competition_logo,
            'venue': match.venue,
            'location': match.location,
            'round': match.round,
            'status': match.status,
            'result_bahia': match.result_bahia,
            'result_opponent': match.result_opponent,
            'elapsed_time': match.elapsed_time,
            'created_at': match.created_at.isoformat() if match.created_at else None,
            'updated_at': match.updated_at.isoformat() if match.updated_at else None,
        },
        'bets_count': bets_count
    })


@csrf_exempt
@require_http_methods(['POST'])
def api_admin_match_create(request):
    """
    API: Cria uma nova partida (DEV ONLY).

    Body esperado:
    {
        "home_team": "Bahia",
        "away_team": "Vitoria",
        "date": "2025-12-15T16:00:00",
        "competition": "Campeonato Baiano",
        "venue": "Arena Fonte Nova",
        "location": "home",
        "round": "1",
        "status": "upcoming"
    }
    """
    if not _is_dev_admin(request):
        return JsonResponse({'error': 'Acesso negado. Requer admin em ambiente de desenvolvimento.'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    # Campos obrigatorios
    required_fields = ['home_team', 'away_team', 'date', 'competition', 'location']
    for field in required_fields:
        if not data.get(field):
            return JsonResponse({'error': f'Campo obrigatorio: {field}'}, status=400)

    # Valida location
    if data['location'] not in ['home', 'away']:
        return JsonResponse({'error': 'Location deve ser "home" ou "away"'}, status=400)

    # Valida status
    valid_statuses = ['upcoming', 'live', 'finished', 'cancelled', 'postponed']
    status = data.get('status', 'upcoming')
    if status not in valid_statuses:
        return JsonResponse({'error': f'Status invalido. Valores aceitos: {", ".join(valid_statuses)}'}, status=400)

    # Parse da data
    try:
        from datetime import datetime
        match_date = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
        if timezone.is_naive(match_date):
            match_date = timezone.make_aware(match_date)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Formato de data invalido. Use ISO 8601 (ex: 2025-12-15T16:00:00)'}, status=400)

    # Cria a partida
    match = Match.objects.create(
        home_team=data['home_team'],
        away_team=data['away_team'],
        home_team_logo=data.get('home_team_logo', ''),
        away_team_logo=data.get('away_team_logo', ''),
        date=match_date,
        competition=data['competition'],
        competition_logo=data.get('competition_logo', ''),
        venue=data.get('venue', ''),
        location=data['location'],
        round=data.get('round', ''),
        status=status,
        result_bahia=data.get('result_bahia'),
        result_opponent=data.get('result_opponent'),
        elapsed_time=data.get('elapsed_time'),
    )

    logger.info(f"Partida criada pelo admin: {match}")

    return JsonResponse({
        'success': True,
        'message': 'Partida criada com sucesso',
        'match_id': match.id
    })


@csrf_exempt
@require_http_methods(['PUT', 'PATCH'])
def api_admin_match_update(request, match_id):
    """
    API: Atualiza uma partida existente (DEV ONLY).

    Body esperado (todos os campos sao opcionais):
    {
        "home_team": "Bahia",
        "away_team": "Vitoria",
        "date": "2025-12-15T16:00:00",
        "status": "finished",
        "result_bahia": 2,
        "result_opponent": 1,
        ...
    }

    IMPORTANTE: Se o status for 'finished' e houver placar definido,
    o sistema processara automaticamente as pontuacoes dos palpites.
    Se a partida ja tinha resultado e o placar for alterado, as pontuacoes
    serao recalculadas (revertendo as anteriores e aplicando as novas).
    """
    if not _is_dev_admin(request):
        return JsonResponse({'error': 'Acesso negado. Requer admin em ambiente de desenvolvimento.'}, status=403)

    try:
        match = Match.objects.get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'error': 'Partida nao encontrada'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    # Guarda valores anteriores para detectar mudanca de resultado
    old_status = match.status
    old_result_bahia = match.result_bahia
    old_result_opponent = match.result_opponent

    # Campos atualizaveis (exceto result_bahia e result_opponent que serao tratados separadamente)
    updatable_fields = [
        'home_team', 'away_team', 'home_team_logo', 'away_team_logo',
        'competition', 'competition_logo', 'venue', 'location', 'round',
        'status', 'elapsed_time', 'external_id'
    ]

    updated_fields = []
    for field in updatable_fields:
        if field in data:
            # Validacoes especificas
            if field == 'location' and data[field] not in ['home', 'away']:
                return JsonResponse({'error': 'Location deve ser "home" ou "away"'}, status=400)
            if field == 'status':
                valid_statuses = ['upcoming', 'live', 'finished', 'cancelled', 'postponed']
                if data[field] not in valid_statuses:
                    return JsonResponse({'error': f'Status invalido. Valores aceitos: {", ".join(valid_statuses)}'}, status=400)

            setattr(match, field, data[field])
            updated_fields.append(field)

    # Trata data separadamente (precisa de parse)
    if 'date' in data:
        try:
            from datetime import datetime
            match_date = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
            if timezone.is_naive(match_date):
                match_date = timezone.make_aware(match_date)
            match.date = match_date
            updated_fields.append('date')
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Formato de data invalido. Use ISO 8601'}, status=400)

    # Trata resultado separadamente para processar pontuacoes
    new_result_bahia = data.get('result_bahia')
    new_result_opponent = data.get('result_opponent')
    new_status = data.get('status', match.status)

    # Verifica se precisa processar pontuacoes
    should_process_scores = False
    scores_message = None

    # Caso 1: Partida sendo encerrada com placar
    if new_status == 'finished' and new_result_bahia is not None and new_result_opponent is not None:
        should_process_scores = True

    # Caso 2: Partida ja encerrada tendo placar alterado
    elif old_status == 'finished' and (
        (new_result_bahia is not None and new_result_bahia != old_result_bahia) or
        (new_result_opponent is not None and new_result_opponent != old_result_opponent)
    ):
        should_process_scores = True

    # Caso 3: Partida saindo do status 'finished' para outro status
    # Deve reverter pontos e limpar resultado
    if old_status == 'finished' and new_status != 'finished':
        from .services.bet_service import BetService
        BetService._revert_points(match)
        match.result_bahia = None
        match.result_opponent = None
        if 'result_bahia' not in updated_fields:
            updated_fields.append('result_bahia')
        if 'result_opponent' not in updated_fields:
            updated_fields.append('result_opponent')
        scores_message = 'Pontuacoes revertidas: partida voltou para status nao-encerrado'
        # Salva imediatamente para garantir que as alteracoes sejam persistidas
        match.save()

    elif should_process_scores:
        # Define os valores do placar (usa novos ou mantem antigos)
        final_result_bahia = new_result_bahia if new_result_bahia is not None else old_result_bahia
        final_result_opponent = new_result_opponent if new_result_opponent is not None else old_result_opponent

        # Valida que ambos os placares estao definidos
        if final_result_bahia is None or final_result_opponent is None:
            return JsonResponse({
                'error': 'Para encerrar uma partida, informe result_bahia e result_opponent'
            }, status=400)

        # Processa pontuacoes via BetService
        from .services.bet_service import BetService

        # Obtem usuario admin para auditoria
        admin_user = getattr(request, 'jampabet_user', None)

        # process_match_result ja faz: reverte pontos anteriores (se houver),
        # atualiza resultado, e calcula novos pontos
        BetService.process_match_result(
            match=match,
            result_bahia=int(final_result_bahia),
            result_opponent=int(final_result_opponent),
            admin_user=admin_user,
            request=request
        )

        if 'result_bahia' in data:
            updated_fields.append('result_bahia')
        if 'result_opponent' in data:
            updated_fields.append('result_opponent')

        # Conta quantos palpites foram processados
        from .models import Bet
        bets_count = Bet.objects.filter(match=match).count()
        bets_with_points = Bet.objects.filter(match=match, points_earned__gt=0).count()

        scores_message = f"Pontuacoes processadas: {bets_with_points}/{bets_count} palpites pontuaram"
        logger.info(f"Partida {match_id} encerrada. {scores_message}")

    else:
        # Atualiza resultado sem processar pontuacoes (partida nao encerrada)
        if 'result_bahia' in data:
            match.result_bahia = data['result_bahia']
            updated_fields.append('result_bahia')
        if 'result_opponent' in data:
            match.result_opponent = data['result_opponent']
            updated_fields.append('result_opponent')

        if updated_fields:
            match.save()

    if updated_fields:
        logger.info(f"Partida {match_id} atualizada pelo admin. Campos: {updated_fields}")

    response_data = {
        'success': True,
        'message': 'Partida atualizada com sucesso',
        'updated_fields': updated_fields
    }

    if scores_message:
        response_data['scores_processed'] = True
        response_data['scores_message'] = scores_message

    return JsonResponse(response_data)


@csrf_exempt
@require_http_methods(['DELETE'])
def api_admin_match_delete(request, match_id):
    """
    API: Deleta uma partida (DEV ONLY).
    ATENCAO: Isso tambem remove todos os palpites associados!
    """
    if not _is_dev_admin(request):
        return JsonResponse({'error': 'Acesso negado. Requer admin em ambiente de desenvolvimento.'}, status=403)

    try:
        match = Match.objects.get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'error': 'Partida nao encontrada'}, status=404)

    # Conta palpites que serao deletados
    bets_count = Bet.objects.filter(match=match).count()

    match_str = str(match)
    match.delete()

    logger.warning(f"Partida deletada pelo admin: {match_str} ({bets_count} palpites removidos)")

    return JsonResponse({
        'success': True,
        'message': 'Partida deletada com sucesso',
        'bets_deleted': bets_count
    })


@require_http_methods(['GET'])
def api_admin_check_dev_mode(request):
    """
    API: Verifica se estamos em modo de desenvolvimento.
    Util para o frontend saber se deve mostrar opcoes de gerenciamento.
    """
    from django.conf import settings

    is_admin = _is_admin(request) if JampabetAuth.is_authenticated(request) else False

    return JsonResponse({
        'debug': settings.DEBUG,
        'is_admin': is_admin,
        'can_manage_matches': settings.DEBUG and is_admin
    })


# ==================== APIs DE BUSCA PARA AUTOCOMPLETE (DEV ONLY) ====================

@require_http_methods(['GET'])
def api_admin_search_teams(request):
    """
    API: Busca times para autocomplete (DEV ONLY).
    Query param: q (termo de busca)
    """
    if not _is_dev_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    query = request.GET.get('q', '').strip()

    # Se nao tiver query, retorna todos os times ativos
    if query:
        teams = BrazilianTeam.objects.filter(
            is_active=True
        ).filter(
            models.Q(name__icontains=query) |
            models.Q(short_name__icontains=query) |
            models.Q(display_name__icontains=query)
        )[:20]
    else:
        teams = BrazilianTeam.objects.filter(is_active=True)[:50]

    teams_data = [{
        'id': team.id,
        'external_id': team.external_id,
        'name': team.name,
        'short_name': team.short_name,
        'display_name': team.get_display_name,
        'logo': team.get_logo,
        'stadium': team.stadium,
        'city': team.city,
        'state': team.state
    } for team in teams]

    return JsonResponse({'teams': teams_data})


@require_http_methods(['GET'])
def api_admin_search_competitions(request):
    """
    API: Busca competicoes para autocomplete (DEV ONLY).
    Query param: q (termo de busca)
    """
    if not _is_dev_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    query = request.GET.get('q', '').strip()

    # Se nao tiver query, retorna todas as competicoes ativas
    if query:
        competitions = Competition.objects.filter(
            is_active=True
        ).filter(
            models.Q(name__icontains=query) |
            models.Q(short_name__icontains=query)
        )[:20]
    else:
        competitions = Competition.objects.filter(is_active=True)[:50]

    competitions_data = [{
        'id': comp.id,
        'external_id': comp.external_id,
        'name': comp.name,
        'short_name': comp.short_name or comp.name,
        'logo': comp.logo_url,
        'type': comp.competition_type,
        'current_season': comp.current_season
    } for comp in competitions]

    return JsonResponse({'competitions': competitions_data})


# ==================== GERENCIAMENTO DE USUARIOS ====================

@require_http_methods(['GET'])
def api_admin_users(request):
    """API: Lista todos os usuarios do sistema"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    # Filtros
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '').strip()

    users = JampabetUser.objects.all()

    if role_filter:
        users = users.filter(role=role_filter)

    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    elif status_filter == 'verified':
        users = users.filter(is_verified=True)
    elif status_filter == 'unverified':
        users = users.filter(is_verified=False)

    if search:
        users = users.filter(
            models.Q(name__icontains=search) |
            models.Q(email__icontains=search)
        )

    users = users.order_by('-created_at')

    users_data = [{
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'role': user.role,
        'role_display': user.get_role_display(),
        'points': user.points,
        'hits': user.hits,
        'is_active': user.is_active,
        'is_verified': user.is_verified,
        'created_at': user.created_at.isoformat(),
        'updated_at': user.updated_at.isoformat(),
    } for user in users]

    # Estatisticas
    stats = {
        'total': JampabetUser.objects.count(),
        'admins': JampabetUser.objects.filter(role='admin').count(),
        'supervisors': JampabetUser.objects.filter(role='supervisor').count(),
        'users': JampabetUser.objects.filter(role='user').count(),
        'active': JampabetUser.objects.filter(is_active=True).count(),
        'verified': JampabetUser.objects.filter(is_verified=True).count(),
    }

    return JsonResponse({'users': users_data, 'stats': stats})


@require_http_methods(['GET'])
def api_admin_user_detail(request, user_id):
    """API: Detalhes de um usuario especifico"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    try:
        user = JampabetUser.objects.get(id=user_id)
    except JampabetUser.DoesNotExist:
        return JsonResponse({'error': 'Usuario nao encontrado'}, status=404)

    # Busca palpites do usuario
    bets = Bet.objects.filter(user=user).order_by('-created_at')[:10]
    bets_data = [{
        'id': bet.id,
        'match': f"{bet.match.home_team} vs {bet.match.away_team}",
        'match_date': bet.match.date.isoformat(),
        'points_earned': bet.points_earned,
        'created_at': bet.created_at.isoformat(),
    } for bet in bets]

    return JsonResponse({
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'role': user.role,
            'role_display': user.get_role_display(),
            'points': user.points,
            'hits': user.hits,
            'is_active': user.is_active,
            'is_verified': user.is_verified,
            'created_at': user.created_at.isoformat(),
            'updated_at': user.updated_at.isoformat(),
        },
        'bets': bets_data,
        'total_bets': Bet.objects.filter(user=user).count(),
    })


@require_http_methods(['POST'])
@csrf_exempt
def api_admin_user_create(request):
    """API: Cria um novo usuario"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        name = data.get('name', '').strip()
        role = data.get('role', 'user')
        password = data.get('password', '')
        send_activation = data.get('send_activation', True)

        # Validacoes
        if not email or not name:
            return JsonResponse({'error': 'E-mail e nome sao obrigatorios'}, status=400)

        if role not in ['admin', 'supervisor', 'user']:
            return JsonResponse({'error': 'Categoria invalida'}, status=400)

        if JampabetUser.objects.filter(email=email).exists():
            return JsonResponse({'error': 'E-mail ja cadastrado'}, status=400)

        # Cria usuario
        user = JampabetUser(
            email=email,
            name=name,
            role=role,
            is_admin=(role == 'admin'),  # Mantém compatibilidade
            is_active=True,
            is_verified=not send_activation,  # Se nao enviar ativacao, ja fica verificado
        )

        # Se tiver senha, define
        if password:
            user.password_hash = make_password(password)
            user.is_verified = True  # Senha definida = conta ativada

        user.save()

        # Se precisar enviar e-mail de ativacao
        if send_activation and not password:
            user.generate_verification_token()
            # TODO: enviar e-mail de ativacao

        return JsonResponse({
            'success': True,
            'user_id': user.id,
            'message': 'Usuario criado com sucesso'
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Dados invalidos'}, status=400)
    except Exception as e:
        logger.error(f"Erro em api_admin_user_create: {e}")
        return JsonResponse({'error': 'Erro interno'}, status=500)


@require_http_methods(['POST'])
@csrf_exempt
def api_admin_user_update(request, user_id):
    """API: Atualiza um usuario existente"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    try:
        user = JampabetUser.objects.get(id=user_id)
    except JampabetUser.DoesNotExist:
        return JsonResponse({'error': 'Usuario nao encontrado'}, status=404)

    # Nao permite editar o proprio usuario admin (protecao)
    current_user = JampabetAuth.get_user(request)
    if current_user and current_user.id == user.id:
        # Permite apenas algumas edicoes no proprio perfil
        pass

    try:
        data = json.loads(request.body)

        # Campos que podem ser atualizados
        if 'name' in data:
            user.name = data['name'].strip()

        if 'email' in data:
            new_email = data['email'].strip().lower()
            if new_email != user.email:
                if JampabetUser.objects.filter(email=new_email).exclude(id=user.id).exists():
                    return JsonResponse({'error': 'E-mail ja cadastrado por outro usuario'}, status=400)
                user.email = new_email

        if 'role' in data:
            new_role = data['role']
            if new_role not in ['admin', 'supervisor', 'user']:
                return JsonResponse({'error': 'Categoria invalida'}, status=400)
            user.role = new_role
            user.is_admin = (new_role == 'admin')  # Mantém compatibilidade

        if 'is_active' in data:
            user.is_active = bool(data['is_active'])

        if 'is_verified' in data:
            user.is_verified = bool(data['is_verified'])

        if 'password' in data and data['password']:
            user.password_hash = make_password(data['password'])

        if 'points' in data:
            user.points = int(data['points'])

        if 'hits' in data:
            user.hits = int(data['hits'])

        user.save()

        return JsonResponse({
            'success': True,
            'message': 'Usuario atualizado com sucesso'
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Dados invalidos'}, status=400)
    except Exception as e:
        logger.error(f"Erro em api_admin_user_update: {e}")
        return JsonResponse({'error': 'Erro interno'}, status=500)


@require_http_methods(['POST'])
@csrf_exempt
def api_admin_user_delete(request, user_id):
    """API: Remove um usuario"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    try:
        user = JampabetUser.objects.get(id=user_id)
    except JampabetUser.DoesNotExist:
        return JsonResponse({'error': 'Usuario nao encontrado'}, status=404)

    # Nao permite deletar o proprio usuario
    current_user = JampabetAuth.get_user(request)
    if current_user and current_user.id == user.id:
        return JsonResponse({'error': 'Voce nao pode deletar seu proprio usuario'}, status=400)

    # Nao permite deletar o ultimo admin
    if user.role == 'admin' or user.is_admin:
        admin_count = JampabetUser.objects.filter(
            models.Q(role='admin') | models.Q(is_admin=True)
        ).count()
        if admin_count <= 1:
            return JsonResponse({'error': 'Nao e possivel deletar o ultimo administrador'}, status=400)

    user_name = user.name
    user.delete()

    return JsonResponse({
        'success': True,
        'message': f'Usuario {user_name} removido com sucesso'
    })


@require_http_methods(['POST'])
@csrf_exempt
def api_admin_user_toggle_status(request, user_id):
    """API: Ativa/desativa um usuario"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    try:
        user = JampabetUser.objects.get(id=user_id)
    except JampabetUser.DoesNotExist:
        return JsonResponse({'error': 'Usuario nao encontrado'}, status=404)

    # Nao permite desativar o proprio usuario
    current_user = JampabetAuth.get_user(request)
    if current_user and current_user.id == user.id:
        return JsonResponse({'error': 'Voce nao pode desativar seu proprio usuario'}, status=400)

    user.is_active = not user.is_active
    user.save(update_fields=['is_active', 'updated_at'])

    status_text = 'ativado' if user.is_active else 'desativado'
    return JsonResponse({
        'success': True,
        'is_active': user.is_active,
        'message': f'Usuario {user.name} {status_text}'
    })


@require_http_methods(['POST'])
@csrf_exempt
def api_admin_user_reset_password(request, user_id):
    """API: Envia e-mail de redefinicao de senha"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    try:
        user = JampabetUser.objects.get(id=user_id)
    except JampabetUser.DoesNotExist:
        return JsonResponse({'error': 'Usuario nao encontrado'}, status=404)

    # Gera novo token de verificacao
    user.generate_verification_token()

    # TODO: Enviar e-mail com link de redefinicao
    # Por enquanto apenas retorna sucesso

    return JsonResponse({
        'success': True,
        'message': f'Link de redefinicao enviado para {user.email}'
    })


# ==================== APIs DE CONFIGURACAO ====================

@require_http_methods(['GET'])
def api_admin_config(request):
    """API: Retorna configuracoes da API"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .models import APIConfig

    config = APIConfig.get_config()

    # Formata data do ultimo polling
    last_poll = None
    if config.last_poll_at:
        last_poll = config.last_poll_at.strftime('%d/%m/%Y %H:%M:%S')

    return JsonResponse({
        'api_enabled': config.api_enabled,
        'polling_interval': config.polling_interval,
        'auto_start_matches': config.auto_start_matches,
        'auto_update_scores': config.auto_update_scores,
        'minutes_before_match': config.minutes_before_match,
        'last_poll_at': last_poll,
        'last_poll_status': config.last_poll_status,
        'last_poll_message': config.last_poll_message,
        'total_api_calls_today': config.total_api_calls_today,
        # Configuracoes de pontuacao
        'points_exact_victory': config.points_exact_victory,
        'points_exact_draw': config.points_exact_draw,
        'round_cost': float(config.round_cost),
    })


@require_http_methods(['POST'])
@csrf_exempt
def api_admin_config_update(request):
    """API: Atualiza configuracoes da API"""
    if not _is_admin(request):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    from .models import APIConfig

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    config = APIConfig.get_config()

    # Atualiza campos
    if 'api_enabled' in data:
        config.api_enabled = bool(data['api_enabled'])

    if 'polling_interval' in data:
        interval = int(data['polling_interval'])
        config.polling_interval = max(30, min(300, interval))  # Entre 30s e 5min

    if 'auto_start_matches' in data:
        config.auto_start_matches = bool(data['auto_start_matches'])

    if 'auto_update_scores' in data:
        config.auto_update_scores = bool(data['auto_update_scores'])

    if 'minutes_before_match' in data:
        minutes = int(data['minutes_before_match'])
        config.minutes_before_match = max(5, min(60, minutes))  # Entre 5 e 60 min

    # Configuracoes de pontuacao
    if 'points_exact_victory' in data:
        points = int(data['points_exact_victory'])
        config.points_exact_victory = max(0, min(100, points))

    if 'points_exact_draw' in data:
        points = int(data['points_exact_draw'])
        config.points_exact_draw = max(0, min(100, points))

    if 'round_cost' in data:
        from decimal import Decimal
        cost = Decimal(str(data['round_cost']))
        config.round_cost = max(Decimal('0'), min(Decimal('1000'), cost))

    config.save()

    return JsonResponse({
        'success': True,
        'message': 'Configuracoes atualizadas com sucesso',
        'config': {
            'api_enabled': config.api_enabled,
            'polling_interval': config.polling_interval,
            'auto_start_matches': config.auto_start_matches,
            'auto_update_scores': config.auto_update_scores,
            'minutes_before_match': config.minutes_before_match,
            'points_exact_victory': config.points_exact_victory,
            'points_exact_draw': config.points_exact_draw,
            'round_cost': float(config.round_cost),
        }
    })
