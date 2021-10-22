from fuzzywuzzy import fuzz
from fuzzywuzzy import process

from general.models import Slate, Game, Player
from general.utils import parse_name, parse_game_info, get_delta


def get_slate(date, name, data_source, mode):
    slate, _ = Slate.objects.update_or_create(name=name, data_source=data_source, date=date, mode=mode)
    return slate


def get_custom_projection(name, player_names):
    match = process.extractOne(name, player_names, scorer=fuzz.token_sort_ratio)
    proj_str = match[0].split('@#@')[1]
    proj = float(proj_str)
    delta = get_delta(proj)

    return proj, delta


def load_players(slate, players_info, projection_info):
    players = []
    for player_info in players_info:
        if player_info.get('Roster Position') == 'CPT':
            continue

        if slate.data_source == 'DraftKings':
            rid = player_info['ID']
            name = player_info['Name']
            first_name, last_name = parse_name(name)
            game_info = player_info['Game Info']
            team = player_info['TeamAbbrev']
            actual_position = player_info['Position'].replace('DST', 'D')
            # position = player_info['Roster Position'].replace('DST', 'DEF')
            position = player_info['Position'].replace('DST', 'DEF')
            salary = player_info['Salary'] or 0
            injury = ''
        elif slate.data_source == 'FanDuel':
            rid = player_info['Id']
            name = player_info['Nickname']
            first_name = player_info['First Name']
            last_name = player_info['Last Name']
            game_info = player_info['Game']
            team = player_info['Team']
            actual_position = player_info['Position']
            # position = player_info['Roster Position']
            position = player_info['Position'].replace('D', 'DEF')
            salary = player_info['Salary'] or 0
            injury = player_info['Injury Details'] or ''
        elif slate.data_source == 'Yahoo':
            rid = player_info['ID']
            first_name = player_info['First Name']
            last_name = player_info['Last Name']
            name = f'{first_name} {last_name}'
            game_info = f"{player_info['Game']} {player_info['Time']}"
            team = player_info['Team']
            actual_position = player_info['Position']
            # position = player_info['Roster Position']
            position = player_info['Position']
            salary = player_info['Salary'] or 0
            injury = player_info['Injury Status'].strip() or ''

        visit_team, home_team, _ = parse_game_info(slate.data_source, game_info)
        if not visit_team:
            continue
        opponent = f'@{home_team}' if visit_team==team else visit_team

        original_proj, delta = get_custom_projection(name, projection_info)

        player, _ = Player.objects.update_or_create(slate=slate,
                                                    rid=rid,
                                                    first_name=first_name,
                                                    last_name=last_name,
                                                    team=team,
                                                    opponent=opponent,
                                                    actual_position=actual_position,
                                                    position=position,
                                                    proj_points=original_proj+delta,
                                                    proj_delta=delta,
                                                    salary=salary,
                                                    injury=injury
                                                    )
        if original_proj:
            players.append(player)

    return players


def load_games(slate, players_info):
    # get unique texts
    if slate.data_source == 'DraftKings':
        games_data = set(player['Game Info'] for player in players_info)
    elif slate.data_source == 'FanDuel':
        games_data = set(player['Game'] for player in players_info)
    elif slate.data_source == 'Yahoo':
        games_data = set(f"{player['Game']} {player['Time']}" for player in players_info)

    games = []
    for game_info in games_data:
        visit_team, home_team, time = parse_game_info(slate.data_source, game_info)
        if not visit_team:
            continue

        game, _ = Game.objects.update_or_create(slate=slate,
                                                home_team=home_team,
                                                visit_team=visit_team,
                                                defaults={
                                                    'time': time
                                                })
        games.append(game)

    return games
