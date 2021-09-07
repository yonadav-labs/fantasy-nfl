DATA_SOURCE = (
    ('DraftKings', 'DraftKings'),
    ('FanDuel', 'FanDuel'),
    ('Yahoo', 'Yahoo'),
)


CSV_FIELDS = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'FLEX', 'DEF']


SALARY_CAP = {
    'FanDuel': 60000,
    'DraftKings': 50000,
    'Yahoo': 200
}

TEAM_MEMEBER_LIMIT = {
    'FanDuel': 4,
    'DraftKings': 5,
    'Yahoo': 5
}


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
