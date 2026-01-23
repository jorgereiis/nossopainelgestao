"""
Serviço de integração com API-Football
"""
import os
import logging
import httpx
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)


class APIFootballService:
    """
    Serviço para comunicação com a API-Football.
    Atua como proxy para proteger a chave da API.
    """

    BASE_URL = "https://v3.football.api-sports.io"
    BAHIA_TEAM_ID = 118  # ID do Bahia na API-Football

    # Ligas disponíveis para consulta
    LEAGUES = {
        # Nacionais
        71: "Campeonato Brasileiro Série A",
        72: "Campeonato Brasileiro Série B",
        75: "Campeonato Brasileiro Série C",
        76: "Campeonato Brasileiro Série D",
        # Copas
        73: "Copa do Brasil",
        13: "Copa Libertadores",
        11: "Copa Sul-Americana",
        612: "Copa do Nordeste",
        # Estaduais
        602: "Campeonato Baiano",
        475: "Campeonato Paulista",
        477: "Campeonato Gaúcho",
        609: "Campeonato Cearense",
        606: "Campeonato Paranaense",
    }

    @classmethod
    def _get_headers(cls):
        """Retorna headers com a chave da API"""
        api_key = getattr(settings, 'API_FOOTBALL_KEY', None)
        if not api_key:
            api_key = os.getenv('API_FOOTBALL_KEY', '')
        return {
            'x-apisports-key': api_key or ''
        }

    @classmethod
    def _make_request(cls, endpoint, params=None):
        """Faz requisição à API-Football"""
        try:
            logger.debug(f"Requisição API: {endpoint} com params: {params}")
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{cls.BASE_URL}/{endpoint}",
                    params=params or {},
                    headers=cls._get_headers()
                )

                if response.status_code != 200:
                    logger.error(f"Erro na API: {response.status_code} - {response.text[:200]}")
                    raise Exception(f"Erro na API: {response.status_code}")

                data = response.json()
                logger.debug(f"Resposta API: {len(data.get('response', []))} resultados")
                return data

        except httpx.TimeoutException:
            logger.error(f"Timeout ao consultar {endpoint}")
            raise Exception("Timeout ao consultar API externa")
        except httpx.RequestError as e:
            logger.error(f"Erro de conexão: {str(e)}")
            raise Exception(f"Erro de conexão: {str(e)}")

    @classmethod
    def get_bahia_fixtures(cls, season=None, from_date=None, to_date=None):
        """
        Busca jogos do Bahia.
        """
        if season is None:
            season = datetime.now().year

        params = {
            "team": cls.BAHIA_TEAM_ID,
            "season": season
        }

        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        data = cls._make_request("fixtures", params)
        return data.get("response", [])

    @classmethod
    def get_fixture_by_id(cls, fixture_id):
        """
        Busca um jogo específico pelo ID.
        """
        params = {"id": fixture_id}
        data = cls._make_request("fixtures", params)
        response = data.get("response", [])
        return response[0] if response else None

    @classmethod
    def get_league_fixtures_by_round(cls, league_id, season=None, round_number=None, round_raw=None):
        """
        Busca jogos de uma liga por rodada.
        Retorna jogos formatados com o jogo do Bahia destacado.

        Args:
            league_id: ID da liga
            season: Temporada (ano)
            round_number: Número da rodada (para ligas com "Regular Season - X")
            round_raw: Nome raw da rodada da API (ex: "1st Phase - 1", "Semi-finals")
        """
        if league_id not in cls.LEAGUES:
            raise ValueError("Liga não disponível")

        if season is None:
            season = datetime.now().year

        params = {
            "league": league_id,
            "season": season
        }

        # Usar round_raw se fornecido, senão construir a partir do round_number
        if round_raw:
            params["round"] = round_raw
        elif round_number:
            params["round"] = f"Regular Season - {round_number}"

        data = cls._make_request("fixtures", params)
        fixtures = data.get("response", [])

        # Formatar jogos
        matches = []
        bahia_match = None

        for fixture in fixtures:
            match = cls._format_fixture(fixture)

            # Verificar se é jogo do Bahia
            is_bahia = (
                fixture.get("teams", {}).get("home", {}).get("id") == cls.BAHIA_TEAM_ID or
                fixture.get("teams", {}).get("away", {}).get("id") == cls.BAHIA_TEAM_ID
            )

            if is_bahia:
                bahia_match = match
            else:
                matches.append(match)

        # Colocar jogo do Bahia no topo
        if bahia_match:
            matches.insert(0, bahia_match)

        # Extrair informações da rodada dos fixtures
        round_label = round_raw or (f"Rodada {round_number}" if round_number else None)
        if fixtures:
            round_label = fixtures[0].get("league", {}).get("round", round_label)

        return {
            "league_id": league_id,
            "league_name": cls.LEAGUES.get(league_id, ""),
            "season": season,
            "round": round_number,
            "round_raw": round_raw or (f"Regular Season - {round_number}" if round_number else None),
            "round_label": round_label,
            "matches": matches
        }

    @classmethod
    def _format_fixture(cls, fixture, use_local_teams=True):
        """Formata um fixture da API para exibição."""
        fixture_data = fixture.get("fixture", {})
        teams = fixture.get("teams", {})
        goals = fixture.get("goals", {})
        league = fixture.get("league", {})
        venue = fixture_data.get("venue") or {}

        home = teams.get("home", {})
        away = teams.get("away", {})

        # Mapeia status
        api_status = fixture_data.get("status", {}).get("short", "")
        if api_status in ["NS", "TBD", "PST"]:
            status = "upcoming"
        elif api_status in ["1H", "HT", "2H", "ET", "BT", "P", "LIVE"]:
            status = "live"
        elif api_status in ["FT", "AET", "PEN"]:
            status = "finished"
        elif api_status in ["CANC", "ABD", "AWD", "WO"]:
            status = "cancelled"
        else:
            status = "postponed"

        # Parse da data
        date_str = fixture_data.get("date", "")
        date = None
        if date_str:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

        is_bahia = home.get("id") == cls.BAHIA_TEAM_ID or away.get("id") == cls.BAHIA_TEAM_ID

        # Nomes e logos dos times
        home_name = home.get("name", "")
        home_logo = home.get("logo", "")
        away_name = away.get("name", "")
        away_logo = away.get("logo", "")

        # Usar dados locais do BrazilianTeam se disponível
        if use_local_teams:
            try:
                from jampabet.models import BrazilianTeam

                home_team_local = BrazilianTeam.get_by_api_id(home.get("id"))
                if home_team_local:
                    home_name = home_team_local.get_display_name
                    home_logo = home_team_local.get_logo or home_logo

                away_team_local = BrazilianTeam.get_by_api_id(away.get("id"))
                if away_team_local:
                    away_name = away_team_local.get_display_name
                    away_logo = away_team_local.get_logo or away_logo
            except Exception:
                pass  # Fallback para dados da API

        return {
            "id": fixture_data.get("id"),
            "home_team": home_name,
            "home_logo": home_logo,
            "home_goals": goals.get("home"),
            "away_team": away_name,
            "away_logo": away_logo,
            "away_goals": goals.get("away"),
            "date": date.isoformat() if date else None,
            "status": status,
            "round": league.get("round", ""),
            "is_bahia": is_bahia,
            "venue": venue.get("name") or "",
            "venue_city": venue.get("city") or ""
        }

    @classmethod
    def get_league_rounds(cls, league_id, season=None):
        """
        Retorna lista de rodadas disponíveis para uma liga.
        Suporta diferentes formatos de competição:
        - "Regular Season - X" (Brasileirão)
        - "1st Phase - X", "Semi-finals", "Final" (Estaduais)
        - "Group X - Y" (Copas com grupos)
        """
        if league_id not in cls.LEAGUES:
            raise ValueError("Liga não disponível")

        if season is None:
            season = datetime.now().year

        params = {
            "league": league_id,
            "season": season
        }

        data = cls._make_request("fixtures/rounds", params)
        rounds_raw = data.get("response", [])

        # Retorna estrutura completa com tipo de competição
        rounds_info = []
        phases = set()

        for r in rounds_raw:
            round_info = {"raw": r, "label": r, "number": None, "phase": "regular"}

            # Formato Brasileirão: "Regular Season - X"
            if "Regular Season - " in r:
                try:
                    num = int(r.replace("Regular Season - ", ""))
                    round_info["number"] = num
                    round_info["label"] = f"Rodada {num}"
                    round_info["phase"] = "regular"
                except ValueError:
                    pass

            # Formato Estaduais: "1st Phase - X", "2nd Phase - X"
            elif "Phase - " in r:
                parts = r.split(" - ")
                if len(parts) == 2:
                    phase_name = parts[0]
                    try:
                        num = int(parts[1])
                        round_info["number"] = num
                        round_info["label"] = f"{phase_name} - Rodada {num}"
                        round_info["phase"] = phase_name.lower().replace(" ", "_")
                        phases.add(phase_name)
                    except ValueError:
                        pass

            # Fases eliminatórias
            elif r in ["Semi-finals", "Quarter-finals", "Round of 16", "Final"]:
                round_info["phase"] = "knockout"
                phase_labels = {
                    "Round of 16": "Oitavas de Final",
                    "Quarter-finals": "Quartas de Final",
                    "Semi-finals": "Semifinal",
                    "Final": "Final"
                }
                round_info["label"] = phase_labels.get(r, r)

            # Formato Copa: "Group A - 1"
            elif "Group " in r:
                parts = r.split(" - ")
                if len(parts) == 2:
                    group = parts[0]
                    try:
                        num = int(parts[1])
                        round_info["number"] = num
                        round_info["label"] = f"{group} - Rodada {num}"
                        round_info["phase"] = "group"
                    except ValueError:
                        pass

            rounds_info.append(round_info)

        # Determina o tipo de competição baseado na estrutura das rodadas
        competition_type = "league"  # default (pontos corridos)
        if phases:
            competition_type = "state"  # estadual com fases (1st Phase, 2nd Phase, etc)
        elif any(r.get("phase") == "group" for r in rounds_info):
            competition_type = "cup_groups"  # copa com fase de grupos
        elif all(r.get("phase") == "knockout" for r in rounds_info):
            competition_type = "cup"  # copa só mata-mata

        # Nota: current_round_index é calculado apenas quando dados vêm do banco (cache)
        # Quando vem da API externa, usamos 0 como default (primeira rodada)
        return {
            "rounds": rounds_info,
            "competition_type": competition_type,
            "has_knockout": any(r.get("phase") == "knockout" for r in rounds_info),
            "phases": list(phases),
            "current_round_index": 0
        }

    @classmethod
    def get_standings(cls, league_id, season=None):
        """
        Busca classificação de uma liga.
        Retorna dados formatados.
        """
        if league_id not in cls.LEAGUES:
            raise ValueError("Liga não disponível")

        if season is None:
            season = datetime.now().year

        params = {
            "league": league_id,
            "season": season
        }

        data = cls._make_request("standings", params)

        if not data.get("response"):
            return {
                "league_id": league_id,
                "league_name": cls.LEAGUES.get(league_id, ""),
                "season": season,
                "standings": []
            }

        league_data = data["response"][0]
        standings_data = league_data.get("league", {}).get("standings", [[]])

        if standings_data and len(standings_data) > 0:
            raw_standings = standings_data[0]
        else:
            raw_standings = []

        standings = []
        for item in raw_standings:
            team = item.get("team", {})
            stats = item.get("all", {})

            standings.append({
                "position": item.get("rank", 0),
                "team_id": team.get("id", 0),
                "team_name": team.get("name", ""),
                "team_logo": team.get("logo", ""),
                "points": item.get("points", 0),
                "played": stats.get("played", 0),
                "wins": stats.get("win", 0),
                "draws": stats.get("draw", 0),
                "losses": stats.get("lose", 0),
                "goals_for": stats.get("goals", {}).get("for", 0),
                "goals_against": stats.get("goals", {}).get("against", 0),
                "goal_difference": item.get("goalsDiff", 0),
                "form": item.get("form", ""),  # Últimas 5 partidas (ex: DWDWL)
            })

        return {
            "league_id": league_id,
            "league_name": cls.LEAGUES.get(league_id, ""),
            "season": season,
            "standings": standings
        }

    @classmethod
    def parse_fixture_to_match_data(cls, fixture):
        """
        Converte dados da API para formato do modelo Match.
        """
        fixture_data = fixture.get("fixture", {})
        teams = fixture.get("teams", {})
        goals = fixture.get("goals", {})
        league = fixture.get("league", {})

        home_team = teams.get("home", {})
        away_team = teams.get("away", {})

        # Determina se Bahia joga em casa ou fora
        is_bahia_home = home_team.get("id") == cls.BAHIA_TEAM_ID

        if is_bahia_home:
            opponent = away_team
            location = "home"
            result_bahia = goals.get("home")
            result_opponent = goals.get("away")
        else:
            opponent = home_team
            location = "away"
            result_bahia = goals.get("away")
            result_opponent = goals.get("home")

        # Mapeia status
        api_status = fixture_data.get("status", {}).get("short", "")
        if api_status in ["NS", "TBD", "PST"]:
            status = "upcoming"
        elif api_status in ["1H", "HT", "2H", "ET", "BT", "P", "LIVE"]:
            status = "live"
        elif api_status in ["FT", "AET", "PEN"]:
            status = "finished"
        elif api_status in ["CANC", "ABD", "AWD", "WO"]:
            status = "cancelled"
        else:
            status = "postponed"

        # Parse da data
        date_str = fixture_data.get("date", "")
        if date_str:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            date = None

        return {
            "external_id": str(fixture_data.get("id")),
            "home_team": "Bahia" if is_bahia_home else opponent.get("name"),
            "away_team": opponent.get("name") if is_bahia_home else "Bahia",
            "home_team_logo": "https://media.api-sports.io/football/teams/118.png" if is_bahia_home else opponent.get("logo", ""),
            "away_team_logo": opponent.get("logo", "") if is_bahia_home else "https://media.api-sports.io/football/teams/118.png",
            "date": date,
            "competition": league.get("name", ""),
            "competition_logo": league.get("logo", ""),
            "venue": (fixture_data.get("venue") or {}).get("name") or "",
            "location": location,
            "round": league.get("round", ""),
            "status": status,
            "result_bahia": result_bahia,
            "result_opponent": result_opponent,
            "elapsed_time": fixture_data.get("status", {}).get("elapsed")
        }

    @classmethod
    def sync_matches(cls, Match):
        """
        Sincroniza partidas da API com o banco de dados.
        Match é o modelo Django passado como parâmetro.
        Retorna o número de partidas atualizadas/criadas.
        """
        current_year = datetime.now().year
        count = 0
        created = 0
        updated = 0

        logger.info(f"Iniciando sincronização de partidas (temporadas {current_year} e {current_year + 1})")

        for season in [current_year, current_year + 1]:
            try:
                fixtures = cls.get_bahia_fixtures(season=season)
                logger.info(f"Temporada {season}: {len(fixtures)} partidas encontradas na API")

                for fixture in fixtures:
                    match_data = cls.parse_fixture_to_match_data(fixture)

                    if not match_data.get("date"):
                        continue

                    existing = Match.objects.filter(
                        external_id=match_data["external_id"]
                    ).first()

                    if existing:
                        # Atualiza campos
                        for key, value in match_data.items():
                            setattr(existing, key, value)
                        existing.save()
                        updated += 1
                    else:
                        # Cria novo
                        Match.objects.create(**match_data)
                        created += 1

                    count += 1

            except Exception as e:
                logger.error(f"Erro ao sincronizar temporada {season}: {e}")

        logger.info(f"Sincronização concluída: {count} processadas ({created} criadas, {updated} atualizadas)")
        return count

    @classmethod
    def get_teams_from_league(cls, league_id, season=None):
        """
        Busca todos os times de uma liga.
        Retorna lista de times com informações básicas.
        """
        if season is None:
            season = datetime.now().year

        params = {
            "league": league_id,
            "season": season
        }

        data = cls._make_request("teams", params)
        teams = data.get("response", [])

        result = []
        for item in teams:
            team = item.get("team", {})
            venue = item.get("venue", {})

            result.append({
                "id": team.get("id"),
                "name": team.get("name", ""),
                "code": team.get("code", ""),
                "logo": team.get("logo", ""),
                "country": team.get("country", "Brazil"),
                "founded": team.get("founded"),
                "stadium": venue.get("name", ""),
                "stadium_capacity": venue.get("capacity"),
                "city": venue.get("city", ""),
            })

        return result

    @classmethod
    def get_team_info(cls, team_id):
        """
        Busca informações detalhadas de um time pelo ID.
        """
        params = {"id": team_id}
        data = cls._make_request("teams", params)
        teams = data.get("response", [])

        if not teams:
            return None

        item = teams[0]
        team = item.get("team", {})
        venue = item.get("venue", {})

        return {
            "id": team.get("id"),
            "name": team.get("name", ""),
            "code": team.get("code", ""),
            "logo": team.get("logo", ""),
            "country": team.get("country", "Brazil"),
            "founded": team.get("founded"),
            "stadium": venue.get("name", ""),
            "stadium_capacity": venue.get("capacity"),
            "city": venue.get("city", ""),
        }

    @classmethod
    def sync_brazilian_teams(cls, BrazilianTeam):
        """
        Sincroniza times brasileiros da Série A e B com o banco de dados.
        BrazilianTeam é o modelo Django passado como parâmetro.
        Retorna o número de times atualizados/criados.
        """
        current_year = datetime.now().year
        count = 0
        created = 0
        updated = 0

        # Mapeamento de nomes curtos para times conhecidos
        SHORT_NAMES = {
            "Atletico-MG": "Atlético-MG",
            "Atletico Mineiro": "Atlético-MG",
            "Athletico-PR": "Athletico-PR",
            "Athletico Paranaense": "Athletico-PR",
            "Atletico-GO": "Atlético-GO",
            "Atletico Goianiense": "Atlético-GO",
            "Bahia": "Bahia",
            "EC Bahia": "Bahia",
            "Botafogo": "Botafogo",
            "Botafogo FR": "Botafogo",
            "Bragantino": "Bragantino",
            "Red Bull Bragantino": "Bragantino",
            "Corinthians": "Corinthians",
            "SC Corinthians Paulista": "Corinthians",
            "Cruzeiro": "Cruzeiro",
            "Cruzeiro EC": "Cruzeiro",
            "Cuiaba": "Cuiabá",
            "Cuiabá": "Cuiabá",
            "Flamengo": "Flamengo",
            "CR Flamengo": "Flamengo",
            "Fluminense": "Fluminense",
            "Fluminense FC": "Fluminense",
            "Fortaleza": "Fortaleza",
            "Fortaleza EC": "Fortaleza",
            "Gremio": "Grêmio",
            "Grêmio": "Grêmio",
            "Gremio FBPA": "Grêmio",
            "Internacional": "Inter",
            "SC Internacional": "Inter",
            "Juventude": "Juventude",
            "EC Juventude": "Juventude",
            "Palmeiras": "Palmeiras",
            "SE Palmeiras": "Palmeiras",
            "Santos": "Santos",
            "Santos FC": "Santos",
            "Sao Paulo": "São Paulo",
            "São Paulo": "São Paulo",
            "Sao Paulo FC": "São Paulo",
            "Sport Recife": "Sport",
            "Sport": "Sport",
            "Vasco DA Gama": "Vasco",
            "Vasco da Gama": "Vasco",
            "CR Vasco da Gama": "Vasco",
            "Vitoria": "Vitória",
            "Vitória": "Vitória",
            "EC Vitoria": "Vitória",
            "America-MG": "América-MG",
            "America Mineiro": "América-MG",
            "Ceara": "Ceará",
            "Ceará": "Ceará",
            "Ceara SC": "Ceará",
            "Goias": "Goiás",
            "Goiás": "Goiás",
            "Goias EC": "Goiás",
            "Coritiba": "Coritiba",
            "Coritiba FC": "Coritiba",
            "Chapecoense-SC": "Chapecoense",
            "Chapecoense": "Chapecoense",
            "Mirassol": "Mirassol",
            "Mirassol FC": "Mirassol",
            "Criciuma": "Criciúma",
            "Criciúma": "Criciúma",
        }

        # Configurações especiais para times específicos
        SPECIAL_DISPLAY = {
            "Vitória": {
                "display_name": "Vicetória",
                "custom_logo_url": "https://images.uncyc.org/pt/f/f5/Escudo_do_Vit%C3%B3ria_2024.png"
            }
        }

        # Estados dos times
        TEAM_STATES = {
            "Bahia": "BA",
            "Vitória": "BA",
            "Sport": "PE",
            "Fortaleza": "CE",
            "Ceará": "CE",
            "Flamengo": "RJ",
            "Fluminense": "RJ",
            "Botafogo": "RJ",
            "Vasco": "RJ",
            "São Paulo": "SP",
            "Corinthians": "SP",
            "Palmeiras": "SP",
            "Santos": "SP",
            "Bragantino": "SP",
            "Mirassol": "SP",
            "Grêmio": "RS",
            "Inter": "RS",
            "Juventude": "RS",
            "Atlético-MG": "MG",
            "Cruzeiro": "MG",
            "América-MG": "MG",
            "Athletico-PR": "PR",
            "Coritiba": "PR",
            "Atlético-GO": "GO",
            "Goiás": "GO",
            "Cuiabá": "MT",
            "Criciúma": "SC",
            "Chapecoense": "SC",
        }

        logger.info(f"Iniciando sincronização de times brasileiros (temporada {current_year})")

        # Buscar times da Série A e B
        for league_id in [71, 72]:  # 71 = Série A, 72 = Série B
            try:
                teams = cls.get_teams_from_league(league_id, season=current_year)
                logger.info(f"Liga {league_id}: {len(teams)} times encontrados")

                for team in teams:
                    team_name = team.get("name", "")
                    short_name = SHORT_NAMES.get(team_name, team_name)

                    # Configurações especiais
                    special = SPECIAL_DISPLAY.get(short_name, {})
                    display_name = special.get("display_name", "")
                    custom_logo = special.get("custom_logo_url", "")

                    # Estado
                    state = TEAM_STATES.get(short_name, "")

                    team_data = {
                        "name": team_name,
                        "short_name": short_name,
                        "display_name": display_name,
                        "logo_url": team.get("logo") or "",
                        "custom_logo_url": custom_logo,
                        "code": team.get("code") or "",
                        "country": team.get("country") or "Brazil",
                        "city": team.get("city") or "",
                        "state": state,
                        "stadium": team.get("stadium") or "",
                        "stadium_capacity": team.get("stadium_capacity"),
                        "founded": team.get("founded"),
                    }

                    existing = BrazilianTeam.objects.filter(
                        external_id=team.get("id")
                    ).first()

                    if existing:
                        # Atualiza apenas campos que não são customizados
                        existing.name = team_data["name"]
                        existing.logo_url = team_data["logo_url"]
                        existing.code = team_data["code"]
                        existing.city = team_data["city"]
                        existing.stadium = team_data["stadium"]
                        existing.stadium_capacity = team_data["stadium_capacity"]
                        existing.founded = team_data["founded"]
                        # Só atualiza short_name se estiver vazio
                        if not existing.short_name:
                            existing.short_name = team_data["short_name"]
                        # Só atualiza display_name se estiver vazio e houver valor
                        if not existing.display_name and team_data["display_name"]:
                            existing.display_name = team_data["display_name"]
                        # Só atualiza custom_logo se estiver vazio e houver valor
                        if not existing.custom_logo_url and team_data["custom_logo_url"]:
                            existing.custom_logo_url = team_data["custom_logo_url"]
                        # Só atualiza state se estiver vazio
                        if not existing.state and team_data["state"]:
                            existing.state = team_data["state"]
                        existing.save()
                        updated += 1
                    else:
                        # Cria novo
                        BrazilianTeam.objects.create(
                            external_id=team.get("id"),
                            **team_data
                        )
                        created += 1

                    count += 1

            except Exception as e:
                logger.error(f"Erro ao sincronizar times da liga {league_id}: {e}")

        logger.info(f"Sincronização de times concluída: {count} processados ({created} criados, {updated} atualizados)")
        return count

    # Competições brasileiras conhecidas (IDs da API-Football)
    BRAZILIAN_COMPETITIONS = {
        # Campeonatos nacionais
        71: {"name": "Campeonato Brasileiro Série A", "short_name": "Brasileirão A", "type": "league"},
        72: {"name": "Campeonato Brasileiro Série B", "short_name": "Brasileirão B", "type": "league"},
        75: {"name": "Campeonato Brasileiro Série C", "short_name": "Brasileirão C", "type": "league"},
        76: {"name": "Campeonato Brasileiro Série D", "short_name": "Brasileirão D", "type": "league"},
        # Copas
        73: {"name": "Copa do Brasil", "short_name": "Copa do Brasil", "type": "cup"},
        13: {"name": "Copa Libertadores", "short_name": "Libertadores", "type": "cup"},
        11: {"name": "Copa Sul-Americana", "short_name": "Sul-Americana", "type": "cup"},
        612: {"name": "Copa do Nordeste", "short_name": "Copa do Nordeste", "type": "cup"},
        # Estaduais
        602: {"name": "Campeonato Baiano", "short_name": "Baianão", "type": "state"},
        475: {"name": "Campeonato Paulista", "short_name": "Paulistão", "type": "state"},
        477: {"name": "Campeonato Gaúcho", "short_name": "Gauchão", "type": "state"},
        609: {"name": "Campeonato Cearense", "short_name": "Cearense", "type": "state"},
        606: {"name": "Campeonato Paranaense", "short_name": "Paranaense", "type": "state"},
    }

    @classmethod
    def get_league_info(cls, league_id, season=None):
        """Busca informações de uma liga na API"""
        if season is None:
            season = datetime.now().year

        params = {
            "id": league_id,
            "season": season
        }

        data = cls._make_request("leagues", params)
        leagues = data.get("response", [])

        if not leagues:
            return None

        league = leagues[0].get("league", {})
        country = leagues[0].get("country", {})
        seasons = leagues[0].get("seasons", [])

        # Encontrar temporada atual
        current_season = None
        for s in seasons:
            if s.get("current"):
                current_season = s.get("year")
                break

        return {
            "id": league.get("id"),
            "name": league.get("name"),
            "logo": league.get("logo"),
            "country": country.get("name"),
            "current_season": current_season or season,
            "type": league.get("type", "league")
        }

    @classmethod
    def sync_competitions(cls, Competition):
        """
        Sincroniza competições brasileiras com o banco de dados.
        """
        current_year = datetime.now().year
        count = 0
        created = 0
        updated = 0

        logger.info("Iniciando sincronização de competições brasileiras")

        for league_id, info in cls.BRAZILIAN_COMPETITIONS.items():
            try:
                # Buscar info da API
                api_info = cls.get_league_info(league_id, current_year)

                comp_data = {
                    "name": info["name"],
                    "short_name": info["short_name"],
                    "competition_type": info["type"],
                    "country": "Brazil",
                    "current_season": current_year,
                }

                if api_info:
                    comp_data["logo_url"] = api_info.get("logo", "")
                    comp_data["current_season"] = api_info.get("current_season", current_year)

                existing = Competition.objects.filter(external_id=league_id).first()

                if existing:
                    existing.name = comp_data["name"]
                    existing.short_name = comp_data["short_name"]
                    existing.competition_type = comp_data["competition_type"]
                    existing.current_season = comp_data["current_season"]
                    if api_info and api_info.get("logo"):
                        existing.logo_url = api_info["logo"]
                    existing.save()
                    updated += 1
                else:
                    Competition.objects.create(
                        external_id=league_id,
                        **comp_data
                    )
                    created += 1

                count += 1

            except Exception as e:
                logger.error(f"Erro ao sincronizar competição {league_id}: {e}")

        logger.info(f"Sincronização de competições concluída: {count} ({created} criadas, {updated} atualizadas)")
        return count

    @classmethod
    def sync_fixtures(cls, Fixture, Competition, BrazilianTeam, league_id=None, season=None):
        """
        Sincroniza partidas de uma competição ou todas as monitoradas.
        """
        if season is None:
            season = datetime.now().year

        count = 0
        created = 0
        updated = 0

        # Se league_id especificado, sincroniza apenas essa liga
        if league_id:
            competitions = Competition.objects.filter(external_id=league_id)
        else:
            # Sincroniza todas as competições monitoradas
            competitions = Competition.get_tracked_competitions()

        logger.info(f"Sincronizando partidas de {competitions.count()} competições")

        for competition in competitions:
            try:
                params = {
                    "league": competition.external_id,
                    "season": season
                }

                data = cls._make_request("fixtures", params)
                fixtures = data.get("response", [])

                logger.info(f"Competição {competition.name}: {len(fixtures)} partidas encontradas")

                for fixture_data in fixtures:
                    try:
                        fixture_info = fixture_data.get("fixture", {})
                        teams = fixture_data.get("teams", {})
                        goals = fixture_data.get("goals", {})
                        league = fixture_data.get("league", {})
                        venue = fixture_info.get("venue") or {}

                        home = teams.get("home", {})
                        away = teams.get("away", {})

                        # Buscar times locais
                        home_team = BrazilianTeam.get_by_api_id(home.get("id"))
                        away_team = BrazilianTeam.get_by_api_id(away.get("id"))

                        # Mapear status
                        api_status = fixture_info.get("status", {}).get("short", "")
                        status_map = {
                            "NS": "scheduled", "TBD": "scheduled",
                            "1H": "live", "HT": "live", "2H": "live",
                            "ET": "live", "BT": "live", "P": "live", "LIVE": "live",
                            "FT": "finished", "AET": "finished", "PEN": "finished",
                            "PST": "postponed", "CANC": "cancelled",
                            "SUSP": "suspended", "INT": "interrupted",
                            "ABD": "abandoned", "AWD": "finished", "WO": "finished"
                        }
                        status = status_map.get(api_status, "scheduled")

                        # Extrair número da rodada
                        round_str = league.get("round", "")
                        round_number = None
                        if "Regular Season - " in round_str:
                            try:
                                round_number = int(round_str.replace("Regular Season - ", ""))
                            except ValueError:
                                pass

                        # Parse da data
                        date_str = fixture_info.get("date", "")
                        if date_str:
                            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        else:
                            continue

                        fixture_dict = {
                            "competition": competition,
                            "season": season,
                            "round": round_str,
                            "round_number": round_number,
                            "home_team": home_team,
                            "away_team": away_team,
                            "home_team_api_id": home.get("id"),
                            "away_team_api_id": away.get("id"),
                            "home_team_name": home.get("name", ""),
                            "away_team_name": away.get("name", ""),
                            "home_team_logo": home.get("logo", ""),
                            "away_team_logo": away.get("logo", ""),
                            "home_goals": goals.get("home"),
                            "away_goals": goals.get("away"),
                            "home_goals_ht": fixture_data.get("score", {}).get("halftime", {}).get("home"),
                            "away_goals_ht": fixture_data.get("score", {}).get("halftime", {}).get("away"),
                            "date": date,
                            "venue": venue.get("name") or "",
                            "venue_city": venue.get("city") or "",
                            "status": status,
                            "elapsed_time": fixture_info.get("status", {}).get("elapsed"),
                            "last_api_update": date.replace(tzinfo=date.tzinfo) if date else None  # usa timezone da data
                        }

                        existing = Fixture.objects.filter(
                            external_id=fixture_info.get("id")
                        ).first()

                        if existing:
                            for key, value in fixture_dict.items():
                                setattr(existing, key, value)
                            existing.save()
                            updated += 1
                        else:
                            Fixture.objects.create(
                                external_id=fixture_info.get("id"),
                                **fixture_dict
                            )
                            created += 1

                        count += 1

                    except Exception as e:
                        logger.error(f"Erro ao processar partida: {e}")
                        continue

            except Exception as e:
                logger.error(f"Erro ao sincronizar partidas da competição {competition.name}: {e}")

        logger.info(f"Sincronização de partidas concluída: {count} ({created} criadas, {updated} atualizadas)")
        return count

    @classmethod
    def get_fixtures_from_db(cls, Fixture, BrazilianTeam, league_id, season=None, round_number=None, round_raw=None):
        """
        Busca partidas do banco de dados (cache local).
        Retorna no mesmo formato que get_league_fixtures_by_round.

        Args:
            Fixture: Modelo Django Fixture
            BrazilianTeam: Modelo Django BrazilianTeam
            league_id: ID da liga
            season: Temporada (ano)
            round_number: Número da rodada (para ligas com "Regular Season - X")
            round_raw: Nome raw da rodada da API (ex: "1st Phase - 1", "Semi-finals")
        """
        if season is None:
            season = datetime.now().year

        queryset = Fixture.objects.filter(
            competition__external_id=league_id,
            season=season
        ).select_related('home_team', 'away_team', 'competition')

        # Filtra por round_raw (prioridade) ou round_number
        if round_raw:
            queryset = queryset.filter(round=round_raw)
        elif round_number:
            queryset = queryset.filter(round_number=round_number)

        queryset = queryset.order_by('date')

        matches = []
        bahia_match = None
        round_label = None

        for fixture in queryset:
            # Pega o round_label do primeiro fixture
            if round_label is None:
                round_label = fixture.round

            match = {
                "id": fixture.external_id,
                "home_team": fixture.get_home_name,
                "home_logo": fixture.get_home_logo or fixture.home_team_logo,
                "home_goals": fixture.home_goals,
                "away_team": fixture.get_away_name,
                "away_logo": fixture.get_away_logo or fixture.away_team_logo,
                "away_goals": fixture.away_goals,
                "date": fixture.date.isoformat() if fixture.date else None,
                "status": fixture.status.replace("scheduled", "upcoming"),
                "round": fixture.round,
                "is_bahia": fixture.is_bahia_match,
                "venue": fixture.venue,
                "venue_city": fixture.venue_city,
            }

            if fixture.is_bahia_match:
                bahia_match = match
            else:
                matches.append(match)

        # Colocar jogo do Bahia no topo
        if bahia_match:
            matches.insert(0, bahia_match)

        return {
            "league_id": league_id,
            "league_name": cls.LEAGUES.get(league_id, ""),
            "season": season,
            "round": round_number,
            "round_raw": round_raw or (f"Regular Season - {round_number}" if round_number else None),
            "round_label": round_label,
            "matches": matches,
            "from_cache": True
        }

    @classmethod
    def get_rounds_from_db(cls, Fixture, league_id, season=None):
        """
        Busca rodadas disponíveis do banco de dados.
        Retorna no mesmo formato que get_league_rounds para compatibilidade.
        """
        if season is None:
            season = datetime.now().year

        # Busca rodadas únicas (campo 'round' que é o raw string da API)
        rounds_raw = Fixture.objects.filter(
            competition__external_id=league_id,
            season=season
        ).exclude(round='').values_list('round', flat=True).distinct()

        rounds_raw = list(set(rounds_raw))

        # Processa as rodadas no mesmo formato que get_league_rounds
        rounds_info = []
        phases = set()

        for r in rounds_raw:
            round_info = {"raw": r, "label": r, "number": None, "phase": "regular"}

            # Formato Brasileirão: "Regular Season - X"
            if "Regular Season - " in r:
                try:
                    num = int(r.replace("Regular Season - ", ""))
                    round_info["number"] = num
                    round_info["label"] = f"Rodada {num}"
                    round_info["phase"] = "regular"
                except ValueError:
                    pass

            # Formato Estaduais: "1st Phase - X", "2nd Phase - X"
            elif "Phase - " in r:
                parts = r.split(" - ")
                if len(parts) == 2:
                    phase_name = parts[0]
                    try:
                        num = int(parts[1])
                        round_info["number"] = num
                        round_info["label"] = f"{phase_name} - Rodada {num}"
                        round_info["phase"] = phase_name.lower().replace(" ", "_")
                        phases.add(phase_name)
                    except ValueError:
                        pass

            # Fases eliminatórias
            elif r in ["Semi-finals", "Quarter-finals", "Round of 16", "Final"]:
                round_info["phase"] = "knockout"
                phase_labels = {
                    "Round of 16": "Oitavas de Final",
                    "Quarter-finals": "Quartas de Final",
                    "Semi-finals": "Semifinal",
                    "Final": "Final"
                }
                round_info["label"] = phase_labels.get(r, r)

            # Formato Copa: "Group A - 1"
            elif "Group " in r:
                parts = r.split(" - ")
                if len(parts) == 2:
                    group = parts[0]
                    try:
                        num = int(parts[1])
                        round_info["number"] = num
                        round_info["label"] = f"{group} - Rodada {num}"
                        round_info["phase"] = "group"
                    except ValueError:
                        pass

            rounds_info.append(round_info)

        # Ordena por fase e número
        def sort_key(r):
            phase_order = {"regular": 0, "1st_phase": 1, "2nd_phase": 2, "group": 3, "knockout": 4}
            phase = r.get("phase", "regular")
            num = r.get("number") or 999
            return (phase_order.get(phase, 99), num)

        rounds_info.sort(key=sort_key)

        # Determina o tipo de competição baseado na estrutura das rodadas
        has_knockout = any(r.get("phase") == "knockout" for r in rounds_info)
        has_groups = any(r.get("phase") == "group" for r in rounds_info)
        has_rounds = any("Round" in r.get("raw", "") for r in rounds_info)  # "1st Round", "3rd Round", etc

        competition_type = "league"  # default (pontos corridos)
        if phases:
            competition_type = "state"  # estadual com fases (1st Phase, 2nd Phase, etc)
        elif has_groups:
            competition_type = "cup_groups"  # copa com fase de grupos
        elif has_knockout and has_rounds:
            competition_type = "cup"  # copa com rodadas + mata-mata
        elif has_knockout and len(rounds_info) < 10:
            competition_type = "cup"  # provavelmente copa se poucos rounds e tem knockout

        # Determina a rodada atual (próxima a acontecer)
        # Busca a primeira rodada que tem pelo menos uma partida com status 'scheduled'
        # e data >= agora
        from django.utils import timezone
        now = timezone.now()
        current_round_index = 0

        for i, round_info in enumerate(rounds_info):
            round_raw = round_info.get("raw")
            # Verifica se há partidas futuras nesta rodada
            upcoming_count = Fixture.objects.filter(
                competition__external_id=league_id,
                season=season,
                round=round_raw,
                date__gte=now
            ).exclude(status='finished').count()

            if upcoming_count > 0:
                current_round_index = i
                break
        else:
            # Se todas as rodadas já passaram, mostra a última
            current_round_index = len(rounds_info) - 1 if rounds_info else 0

        return {
            "rounds": rounds_info,
            "competition_type": competition_type,
            "has_knockout": has_knockout,
            "phases": list(phases),
            "current_round_index": current_round_index,
            "from_cache": True
        }
