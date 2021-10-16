from ortools.linear_solver import pywraplp

from .models import *
from .constants import POSITION_LIMITS, ROSTER_SIZE, TEAM_LIMIT
from .utils import get_num_lineups


class Roster:

    def __init__(self, ds):
        self.players = []
        self.ds = ds
        self.drop = None

    def add_player(self, player):
        self.players.append(player)

    def get_num_teams(self):
        teams = set([ii.team for ii in self.players])
        return len(teams)

    def is_member(self, player):
        return player.id in [ii.id for ii in self.players]

    def spent(self):
        return sum(map(lambda x: getattr(x, 'salary'), self.players))

    def projected(self):
        return sum(map(lambda x: getattr(x, 'proj_points'), self.players))

    def get_players(self):
        pos = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'RB,WR,TE', 'DEF']
        players = list(self.players)
        players_ = []

        for ii in pos:
            for jj in players:
                if jj.position in ii:
                    players_.append(jj)
                    players.remove(jj)
                    break
        return players_ + players

    def __repr__(self):
        s = '\n'.join(str(x) for x in self.get_players())
        s += "\n\nProjected Score: %s" % self.projected()
        s += "\tCost: $%s" % self.spent()
        return s


def get_lineup(ds, players, locked, ban, max_point, min_salary, max_salary, team_match):
    '''
    :param: locked: list of list. e.g) [['432-WR', '432-TE'], ['634-TE']]
    :param: ban: list of ids. e.g) [243, 643]
    '''
    solver = pywraplp.Solver('nfl-lineup', pywraplp.Solver.CBC_MIXED_INTEGER_PROGRAMMING)

    variables = {}

    for player in players:
        key = f'{player.id}-{player.position}'
        if player.id in ban:
            variables[key] = solver.IntVar(0, 0, key)
        else:
            variables[key] = solver.IntVar(0, 1, key)

    objective = solver.Objective()
    objective.SetMaximization()

    for player in players:
        key = f'{player.id}-{player.position}'
        objective.SetCoefficient(variables[key], player.proj_points)

    salary_cap = solver.Constraint(min_salary, max_salary)
    for player in players:
        key = f'{player.id}-{player.position}'
        salary_cap.SetCoefficient(variables[key], player.salary)

    point_cap = solver.Constraint(0, max_point)
    for player in players:
        key = f'{player.id}-{player.position}'
        point_cap.SetCoefficient(variables[key], player.proj_points)

    for position, min_limit, max_limit in POSITION_LIMITS:
        position_cap = solver.Constraint(min_limit, max_limit)

        for player in players:
            key = f'{player.id}-{player.position}'
            if player.position in position:
                position_cap.SetCoefficient(variables[key], 1)

    # QB paired with 1 WR/TE of same team
    # team_cap = solver.Constraint(0.999999, 1)
    # for ti, team in enumerate(team_match.keys()):
    #     for player in players:
    #         key = f'{player.id}-{player.position}'
    #         if player.team == team:
    #             if player.position in ['WR', 'TE']:
    #                 team_cap.SetCoefficient(variables[key], 1/(ti+3))
    #             elif player.position == 'QB':
    #                 team_cap.SetCoefficient(variables[key], (ti+2)/(ti+3))

    size_cap = solver.Constraint(ROSTER_SIZE[ds], ROSTER_SIZE[ds])
    for player in players:
        key = f'{player.id}-{player.position}'
        size_cap.SetCoefficient(variables[key], 1)

    for ii in locked:
        lock_cap = solver.Constraint(1, 1)

        for jj in ii:
            lock_cap.SetCoefficient(variables[jj], 1)

    solution = solver.Solve()

    if solution == solver.OPTIMAL:
        roster = Roster(ds)

        for player in players:
            key = f'{player.id}-{player.position}'
            if variables[key].solution_value() == 1:
                roster.add_player(player)

        return roster


def get_exposure(players, lineups):
    return { ii.id: get_num_lineups(ii, lineups) for ii in players }


def calc_lineups(players, num_lineups, locked, ds, min_salary, max_salary, exposure, cus_proj, team_match):
    result = []
    max_point = 10000
    exposure_d = { ii['id']: ii for ii in exposure }
    ban = []
    # use custom projection
    for player in players:
        player.proj_points = float(cus_proj.get(str(player.id), player.proj_points))

    while True:
        # check and update all users' status
        cur_exps = get_exposure(players, result)
        for pid, exp in cur_exps.items():
            if exp >= exposure_d[pid]['max'] and pid not in ban:
                ban.append(pid)

        roster = get_lineup(ds, players, locked, ban, max_point, min_salary, max_salary, team_match)

        if not roster:
            return result

        max_point = float(roster.projected()) - 0.001
        if roster.get_num_teams() >= TEAM_LIMIT[ds]:
            result.append(roster)
            if len(result) == num_lineups:
                return result
