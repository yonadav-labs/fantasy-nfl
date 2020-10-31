import datetime
import requests

import os
from os import sys, path
import django

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fantasy_nfl.settings")
django.setup()

from general.models import *
from general import html2text
from scripts.get_slate import get_slate
from general.utils import get_delta


def get_players(data_source):
    try:
        slate, type = get_slate(data_source)

        url = 'https://www.rotowire.com/daily/tables/optimizer-nfl.php?sport=NFL&' + \
              'site={}&projections=&type={}&slate={}'.format(data_source, type, slate)

        print (url)

        players = requests.get(url).json()

        fields = ['point_spread', 'team_points', 'opponent', 'money_line',
                  'actual_position', 'salary', 'team']

        print (data_source, len(players))
        if len(players) > 20:
            Player.objects.filter(data_source=data_source, lock_update=False).update(play_today=False)

            for ii in players:
                defaults = { key: str(ii[key]).replace(',', '') for key in fields }
                defaults['play_today'] = True

                defaults['position'] = ii['position'] if ii['position'] != 'D' else 'DEF'
                # defaults['available'] = ii['team'] in teams
                defaults['injury'] = html2text.html2text(ii['injury']).strip().upper()
                # defaults['value'] = ii['salary'] / 250.0 + 10

                player = Player.objects.filter(uid=ii['id'], data_source=data_source).first()
                if not player:
                    defaults['uid'] = ii['id']
                    defaults['data_source'] = data_source
                    defaults['first_name'] = ii['first_name'].replace('.', '')
                    defaults['last_name'] = ii['last_name'].replace('.', '')

                    defaults['proj_delta'] = get_delta(data_source)
                    proj_points = float(ii['proj_points']) + defaults['proj_delta']
                    defaults['proj_points'] = proj_points if proj_points > 0 else 0
        
                    Player.objects.create(**defaults)
                else:
                    if not player.lock_update:
                        criteria = datetime.datetime.combine(datetime.date.today(), datetime.time(22, 30, 0)) # utc time - 5:30 pm EST
                        if player.updated_at.replace(tzinfo=None) < criteria:
                            defaults['proj_delta'] = get_delta(data_source)
                            proj_points = float(ii['proj_points']) + defaults['proj_delta']
                            defaults['proj_points'] = proj_points if proj_points > 0 else 0

                    for attr, value in defaults.items():
                        setattr(player, attr, value)

                    player.save()
    except:
        print("*** some thing is wrong ***")


if __name__ == "__main__":
    for ds in ['DraftKings', 'FanDuel', 'Yahoo']:
        get_players(ds)
