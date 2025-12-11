"""
Serviço de Apostas do JampaBet
"""
from django.utils import timezone
from datetime import timedelta
from ..models import Bet, Match, JampabetUser, AuditLog, APIConfig


class BetService:
    """Serviço para operações relacionadas a apostas"""

    @classmethod
    def get_config(cls):
        """Retorna configuracoes do sistema"""
        return APIConfig.get_config()

    @classmethod
    def can_place_bet(cls, match):
        """
        Verifica se é possível fazer aposta na partida.
        Retorna (bool, mensagem)
        """
        if not match:
            return False, 'Partida não encontrada'

        if match.status == 'finished':
            return False, 'Partida já encerrada'

        if match.status == 'live':
            return False, 'Partida em andamento'

        if match.status == 'cancelled':
            return False, 'Partida cancelada'

        if match.status == 'postponed':
            return False, 'Partida adiada'

        # Verifica tempo até a partida (usa config do banco)
        config = cls.get_config()
        lock_minutes = config.minutes_before_match

        now = timezone.now()
        lock_time = match.date - timedelta(minutes=lock_minutes)

        if now >= lock_time:
            return False, f'Palpites bloqueados. Menos de {lock_minutes} minutos para o início.'

        return True, 'Pode apostar'

    @classmethod
    def validate_bet_scores(cls, home_win_bahia, home_win_opponent, draw_bahia, draw_opponent):
        """Valida os placares do palpite"""
        # Valores não negativos
        if any(s < 0 for s in [home_win_bahia, home_win_opponent, draw_bahia, draw_opponent]):
            raise ValueError('Placares não podem ser negativos')

        # Palpite de vitória: Bahia deve vencer
        if home_win_bahia <= home_win_opponent:
            raise ValueError('No palpite de vitória, Bahia deve ter mais gols')

        # Palpite de empate: placares iguais
        if draw_bahia != draw_opponent:
            raise ValueError('No palpite de empate, os placares devem ser iguais')

    @classmethod
    def create_bet(cls, user, match, home_win_bahia, home_win_opponent,
                   draw_bahia, draw_opponent, request=None):
        """Cria uma nova aposta"""
        # Valida se pode apostar
        can_bet, message = cls.can_place_bet(match)
        if not can_bet:
            raise ValueError(message)

        # Valida placares
        cls.validate_bet_scores(home_win_bahia, home_win_opponent, draw_bahia, draw_opponent)

        # Verifica se já existe aposta
        if Bet.objects.filter(user=user, match=match).exists():
            raise ValueError('Você já tem um palpite para esta partida')

        # Cria a aposta
        bet = Bet.objects.create(
            user=user,
            match=match,
            home_win_bahia=home_win_bahia,
            home_win_opponent=home_win_opponent,
            draw_bahia=draw_bahia,
            draw_opponent=draw_opponent
        )

        # Log de auditoria
        cls._log_bet_action(
            user=user,
            action='create_bet',
            bet=bet,
            request=request,
            new_value={
                'match_id': match.id,
                'home_win': {'bahia': home_win_bahia, 'opponent': home_win_opponent},
                'draw': {'bahia': draw_bahia, 'opponent': draw_opponent}
            }
        )

        return bet

    @classmethod
    def update_bet(cls, bet, home_win_bahia, home_win_opponent,
                   draw_bahia, draw_opponent, request=None):
        """Atualiza uma aposta existente"""
        # Valida se pode apostar
        can_bet, message = cls.can_place_bet(bet.match)
        if not can_bet:
            raise ValueError(message)

        # Valida placares
        cls.validate_bet_scores(home_win_bahia, home_win_opponent, draw_bahia, draw_opponent)

        # Guarda valores antigos para auditoria
        old_value = {
            'home_win': {'bahia': bet.home_win_bahia, 'opponent': bet.home_win_opponent},
            'draw': {'bahia': bet.draw_bahia, 'opponent': bet.draw_opponent}
        }

        # Atualiza
        bet.home_win_bahia = home_win_bahia
        bet.home_win_opponent = home_win_opponent
        bet.draw_bahia = draw_bahia
        bet.draw_opponent = draw_opponent
        bet.save()

        # Log de auditoria
        cls._log_bet_action(
            user=bet.user,
            action='update_bet',
            bet=bet,
            request=request,
            old_value=old_value,
            new_value={
                'home_win': {'bahia': home_win_bahia, 'opponent': home_win_opponent},
                'draw': {'bahia': draw_bahia, 'opponent': draw_opponent}
            }
        )

        return bet

    @classmethod
    def delete_bet(cls, bet, request=None):
        """Exclui uma aposta"""
        # Valida se pode modificar
        can_bet, message = cls.can_place_bet(bet.match)
        if not can_bet:
            raise ValueError(message)

        old_value = {
            'match_id': bet.match_id,
            'home_win': {'bahia': bet.home_win_bahia, 'opponent': bet.home_win_opponent},
            'draw': {'bahia': bet.draw_bahia, 'opponent': bet.draw_opponent}
        }

        user = bet.user
        bet_id = bet.id

        bet.delete()

        # Log de auditoria
        cls._log_bet_action(
            user=user,
            action='delete_bet',
            bet_id=bet_id,
            request=request,
            old_value=old_value
        )

    @classmethod
    def calculate_points(cls, bet_bahia, bet_opponent, result_bahia, result_opponent, is_victory=True):
        """
        Calcula pontos de uma aposta.
        Apenas placar exato pontua.

        Args:
            bet_bahia: Gols do Bahia no palpite
            bet_opponent: Gols do adversario no palpite
            result_bahia: Gols do Bahia no resultado
            result_opponent: Gols do adversario no resultado
            is_victory: Se True, usa pontuacao de vitoria; se False, usa de empate

        Returns:
            Quantidade de pontos ganhos (0 se errou)
        """
        config = cls.get_config()

        # Apenas placar exato pontua
        if bet_bahia == result_bahia and bet_opponent == result_opponent:
            if is_victory:
                return config.points_exact_victory
            else:
                return config.points_exact_draw

        # Sem pontuacao para quem apenas acertar o resultado
        return 0

    @classmethod
    def process_match_result(cls, match, result_bahia, result_opponent, admin_user=None, request=None):
        """
        Processa o resultado de uma partida e calcula pontos das apostas.
        """
        # Se já tinha resultado, reverte pontos anteriores
        if match.result_bahia is not None and match.result_opponent is not None:
            cls._revert_points(match)

        # Atualiza resultado da partida
        old_value = {
            'result_bahia': match.result_bahia,
            'result_opponent': match.result_opponent,
            'status': match.status
        }

        match.result_bahia = result_bahia
        match.result_opponent = result_opponent
        match.status = 'finished'
        match.save()

        # Calcula pontos de cada aposta
        bets = Bet.objects.filter(match=match)
        for bet in bets:
            # Determina qual palpite usar baseado no resultado
            if result_bahia > result_opponent:
                # Bahia venceu - usa palpite de vitoria (is_victory=True)
                points = cls.calculate_points(
                    bet.home_win_bahia, bet.home_win_opponent,
                    result_bahia, result_opponent,
                    is_victory=True
                )
            elif result_bahia == result_opponent:
                # Empate - usa palpite de empate (is_victory=False)
                points = cls.calculate_points(
                    bet.draw_bahia, bet.draw_opponent,
                    result_bahia, result_opponent,
                    is_victory=False
                )
            else:
                # Bahia perdeu - sem pontos (nao ha palpite de derrota)
                points = 0

            bet.points_earned = points
            bet.save()

            # Atualiza pontos do usuario
            if points > 0:
                bet.user.points += points
                bet.user.hits += 1
                bet.user.save()

        # Log de auditoria
        if admin_user:
            AuditLog.objects.create(
                user=admin_user,
                action='register_result',
                entity_type='match',
                entity_id=match.id,
                old_value=old_value,
                new_value={
                    'result_bahia': result_bahia,
                    'result_opponent': result_opponent,
                    'status': 'finished'
                },
                ip_address=request.META.get('REMOTE_ADDR') if request else None,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500] if request else ''
            )

        return match

    @classmethod
    def _revert_points(cls, match):
        """Reverte pontos de uma partida (para recálculo)"""
        bets = Bet.objects.filter(match=match)
        for bet in bets:
            if bet.points_earned > 0:
                bet.user.points -= bet.points_earned
                bet.user.hits -= 1
                bet.user.save()
                bet.points_earned = 0
                bet.save()

    @classmethod
    def _log_bet_action(cls, user, action, bet=None, bet_id=None, request=None,
                        old_value=None, new_value=None):
        """Registra ação de aposta no log"""
        ip_address = None
        user_agent = ''

        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')

            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        AuditLog.objects.create(
            user=user,
            action=action,
            entity_type='bet',
            entity_id=bet.id if bet else bet_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent
        )
