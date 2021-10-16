from ortools.linear_solver import pywraplp

from .models import *
from .constants import POSITION_LIMITS_SHOWDOWN, ROSTER_SIZE_SHOWDOWN, TEAM_LIMIT
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
        pos = ['MVP', 'FLEX', 'FLEX', 'FLEX', 'FLEX']
        if self.ds == 'DraftKings':
            pos += ['FLEX']
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


def get_lineup(ds, players, locked, ban, max_point, min_salary, max_salary, con_mul):
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

    for position, min_limit, max_limit in POSITION_LIMITS_SHOWDOWN[ds]:
        position_cap = solver.Constraint(min_limit, max_limit)

        for player in players:
            key = f'{player.id}-{player.position}'
            if player.position in position:
                position_cap.SetCoefficient(variables[key], 1)

    size_cap = solver.Constraint(ROSTER_SIZE_SHOWDOWN[ds], ROSTER_SIZE_SHOWDOWN[ds])
    for player in players:
        key = f'{player.id}-{player.position}'
        size_cap.SetCoefficient(variables[key], 1)

    for ii in locked:
        lock_cap = solver.Constraint(1, 1)

        for jj in ii:
            lock_cap.SetCoefficient(variables[jj], 1)

    for ii in con_mul:
        mul_pos_cap = solver.Constraint(0, 1)

        for jj in ii:
            mul_pos_cap.SetCoefficient(variables[jj], 1)

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


def calc_lineups_showdown(players, num_lineups, locked, ds, min_salary, max_salary, exposure, cus_proj):
    result = []
    max_point = 10000
    exposure_d = { ii['id']: ii for ii in exposure }

    con_mul = []
    players_ = []

    for player in players:
        p = vars(player)
        p.pop('_state')
        proj_points = float(cus_proj.get(str(player.id), player.proj_points))

        # as a flex
        p['position'] = 'FLEX'
        p['proj_points'] = proj_points
        players_.append(Player(**p))

        # as a mvp
        p['position'] = 'MVP'
        p['proj_points'] = proj_points * 1.5
        if ds == 'DraftKings':
            p['salary'] = player.salary * 1.5
        players_.append(Player(**p))

        con_mul.append([f'{player.id}-MVP', f'{player.id}-FLEX'])

    players = players_
    ban = []

    while True:
        cur_exps = get_exposure(players, result)
        for pid, exp in cur_exps.items():
            if exp >= exposure_d[pid]['max'] and pid not in ban:
                ban.append(pid)

        roster = get_lineup(ds, players, locked, ban, max_point, min_salary, max_salary, con_mul)

        if not roster:
            return result

        max_point = float(roster.projected()) - 0.001
        if roster.get_num_teams() >= TEAM_LIMIT[ds]:
            result.append(roster)
            if len(result) == num_lineups:
                return result
