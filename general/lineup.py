import operator as op
from ortools.linear_solver import pywraplp

from .models import *


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


POSITION_LIMITS = [
    ["QB", 1, 1],
    ["RB", 2, 3],
    ["WR", 3, 4],
    ["TE", 1, 2],
    ["DEF", 1, 1],
    ["RB,WR,TE", 7, 7]
]

ROSTER_SIZE = {
    'FanDuel': 9,
    'DraftKings': 9,
    'Yahoo': 9,
}

TEAM_LIMIT = {
    'FanDuel': 2,
    'DraftKings': 2,
    'Yahoo': 3
}

def get_lineup(ds, players, locked, ban, max_point, min_salary, max_salary):
    solver = pywraplp.Solver('nfl-lineup', pywraplp.Solver.CBC_MIXED_INTEGER_PROGRAMMING)

    variables = []

    for i, player in enumerate(players):
        if player.id in locked:
            variables.append(solver.IntVar(1, 1, str(player)+str(i)))
        elif player.id in ban:
            variables.append(solver.IntVar(0, 0, str(player)+str(i)))
        else:
            variables.append(solver.IntVar(0, 1, str(player)+str(i)))

    objective = solver.Objective()
    objective.SetMaximization()

    for i, player in enumerate(players):
        objective.SetCoefficient(variables[i], player.proj_points)

    salary_cap = solver.Constraint(min_salary, max_salary)
    for i, player in enumerate(players):
        salary_cap.SetCoefficient(variables[i], player.salary)

    point_cap = solver.Constraint(0, max_point)
    for i, player in enumerate(players):
        point_cap.SetCoefficient(variables[i], player.proj_points)

    for position, min_limit, max_limit in POSITION_LIMITS:
        position_cap = solver.Constraint(min_limit, max_limit)

        for i, player in enumerate(players):
            if player.position in position:
                position_cap.SetCoefficient(variables[i], 1)

    # no more than n players from one team
    # teams = _team_stack.keys()
    # for team in teams:
    #     team_cap = solver.Constraint(_team_stack[team]['min'], _team_stack[team]['max'])
    #     for i, player in enumerate(players):
    #         if team == player.team:
    #             team_cap.SetCoefficient(variables[i], 1)

    size_cap = solver.Constraint(ROSTER_SIZE[ds], ROSTER_SIZE[ds])
    for variable in variables:
        size_cap.SetCoefficient(variable, 1)

    solution = solver.Solve()

    if solution == solver.OPTIMAL:
        roster = Roster(ds)

        for i, player in enumerate(players):
            if variables[i].solution_value() == 1:
                roster.add_player(player)

        return roster


def get_num_lineups(player, lineups):
    num = 0
    for ii in lineups:
        if ii.is_member(player):
            num = num + 1
    return num


def get_exposure(players, lineups):
    return { ii.id: get_num_lineups(ii, lineups) for ii in players }


def get_percent_team(lineups, team, team_info):
    num = 0
    for lineup in lineups:
        num_players = 0
        for ii in lineup.players:
            if ii.team == team:
                num_players += 1
        if num_players >= team_info['min']:
            num += 1
    return num


def calc_lineups(players, num_lineups, locked, ds, min_salary, max_salary, exposure, cus_proj):
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

        roster = get_lineup(ds, players, locked, ban, max_point, min_salary, max_salary)

        if not roster:
            return result

        max_point = float(roster.projected()) - 0.001
        if roster.get_num_teams() >= TEAM_LIMIT[ds]:
            result.append(roster)
            if len(result) == num_lineups:
                return result
