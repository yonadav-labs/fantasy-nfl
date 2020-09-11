# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import json
import math
import datetime
import mimetypes
from wsgiref.util import FileWrapper

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils.encoding import smart_str
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Avg, Q, Sum
from django.views.decorators.clickjacking import xframe_options_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.forms.models import model_to_dict

from general.models import *
from general.lineup import *

from scripts.roto import get_players as roto_get_players
from scripts.roto_games import get_games as roto_get_games


def players(request):
    players = Player.objects.filter(data_source='FanDuel').order_by('first_name')
    return render(request, 'players.html', locals())


@xframe_options_exempt
def lineup_builder(request):
    data_sources = DATA_SOURCE
    num_lineups = request.session.get('DraftKings_num_lineups', 1)
    return render(request, 'lineup-builder.html', locals())


@xframe_options_exempt
def lineup_optimizer(request):
    data_sources = DATA_SOURCE

    return render(request, 'lineup-optimizer.html', locals())


def _is_full_lineup(lineup, ds):
    if not lineup:
        return False

    num_players = sum([1 for ii in lineup if ii['player']])

    return num_players == ROSTER_SIZE[ds]


@csrf_exempt
def get_team_stack_dlg(request, ds):
    teams = []
    for ii in Game.objects.filter(data_source=ds, display=True):
        teams.append(ii.home_team.lower())
        teams.append(ii.visit_team.lower())

    return render(request, 'team-stack-dlg.html', locals())


@csrf_exempt
def check_mlineups(request):
    ds = request.POST.get('ds')
    num_lineups = request.session.get(ds+'_num_lineups', 1)
    res = []
    for ii in range(1, num_lineups+1):
        key = '{}_lineup_{}'.format(ds, ii)
        lineup = request.session.get(key)
        res.append([ii, 'checked' if _is_full_lineup(lineup, ds) else 'disabled'])

    return JsonResponse(res, safe=False)


@csrf_exempt
def build_lineup(request):
    ds = request.POST.get('ds')
    pid = request.POST.get('pid')
    idx = int(request.POST.get('idx'))

    cus_proj = request.session.get('cus_proj', {})
    request.session['ds'] = ds
    key = '{}_lineup_{}'.format(ds, idx)
    num_lineups = request.session.get(ds+'_num_lineups', 1)
    lineup = request.session.get(key, [{ 'pos':ii, 'player': '' } for ii in CSV_FIELDS])

    if idx > num_lineups:           # add lineup
        num_lineups = idx
        request.session[ds+'_num_lineups'] = idx
        request.session[key] = lineup

    msg = ''
    if pid == "123456789":          # remove all lineups
        request.session[ds+'_num_lineups'] = 1
        lineup = [{ 'pos':ii, 'player': '' } for ii in CSV_FIELDS]
        request.session['{}_lineup_{}'.format(ds, 1)] = lineup

        for ii in range(2, num_lineups+1):
            request.session.pop('{}_lineup_{}'.format(ds, ii))
    elif '-' in pid:                # remove a player
        pid = pid.strip('-')
        for ii in lineup:
            if ii['player'] == pid:
                ii['player'] = ''
    elif pid == 'optimize':         # manual optimize
        ids = request.POST.get('ids').split('&ids=')[1:]
        players = Player.objects.filter(id__in=ids)
        num_lineups = 1
        locked = [int(ii['player']) for ii in lineup if ii['player']]

        teams = players.values_list('team', flat=True).distinct()
        _team_stack = {ii: { 'min': 0, 'max': TEAM_MEMEBER_LIMIT[ds] } for ii in teams if ii}
        _exposure = [{ 'min': 0, 'max': 1, 'id': ii.id } for ii in players]

        lineups = calc_lineups(players, num_lineups, locked, ds, 0, SALARY_CAP[ds], _team_stack, _exposure, cus_proj)
        if lineups:
            roster = lineups[0].get_players()
            lineup = [{ 'pos':ii, 'player': str(roster[idx].id) } for idx, ii in enumerate(CSV_FIELDS)]
            request.session[key] = lineup
        else:
            msg = 'Sorry, something is wrong.'
    elif pid:                       # add a player
        # check whether he is available
        sum_salary = 0
        available = False
        for ii in lineup:
            if ii['player']:
                player = Player.objects.get(id=ii['player'])
                sum_salary += player.salary

        player = Player.objects.get(id=pid)
        if SALARY_CAP[ds] >= sum_salary + player.salary:
            for ii in lineup:
                if not ii['player']:
                    if (player.position in 'RB/WR/TE' and ii['pos'] == 'FLEX') or ii['pos'] in player.position:
                        available = True
                        ii['player'] = pid
                        break
            if available:
                # save lineup
                request.session[key] = lineup
            else:
                msg = 'He is not applicable to any position.'
        else:
            msg = 'Lineup salary exceeds the salary cap.'

    players = []
    sum_proj = 0
    sum_salary = 0
    num_players = 0
    pids = []

    for ii in lineup:
        if ii['player']:
            pids.append(ii['player'])
            player = Player.objects.get(id=ii['player'])
            num_players += 1
            sum_salary += player.salary
            sum_proj += float(cus_proj.get(str(player.id), player.proj_points))
        else:
            player = {}
        players.append({ 'pos':ii['pos'], 'player': player })

    rem = (SALARY_CAP[ds] - sum_salary) / (ROSTER_SIZE[ds] - num_players) if ROSTER_SIZE[ds] != num_players else 0
    full = num_players == ROSTER_SIZE[ds]

    result = { 
        'html': render_to_string('lineup-body.html', locals()),
        'pids': pids,
        'msg': msg
    }

    return JsonResponse(result, safe=False)


@csrf_exempt
def get_players(request):
    ds = request.POST.get('ds')
    order = request.POST.get('order', 'proj_points')
    if order == '-':
        order = 'proj_points'

    reverse = False if '-' in order else True
    order = order.replace('-', '')
    teams = request.POST.get('games').strip(';').replace(';', '-').split('-')

    factor = 1 if ds == 'Yahoo' else 1000
    players = []

    cus_proj = request.session.get('cus_proj', {})

    for ii in Player.objects.filter(data_source=ds, team__in=teams, play_today=True):
        player = model_to_dict(ii, fields=['id', 'injury', 'avatar', 'salary', 'team',
                                           'actual_position', 'first_name', 'last_name',
                                           'opponent'])
        if player['opponent'].startswith('@'):
            player['opponent'] = '@ '+player['opponent'][1:]
        else:
            player['opponent'] = 'vs '+player['opponent']

        player['proj_points'] = float(cus_proj.get(str(ii.id), ii.proj_points))
        player['pt_sal'] = player['proj_points'] * factor / ii.salary if ii.salary else 0
        players.append(player)

    players = sorted(players, key=lambda k: k[order], reverse=reverse)
    result = { 
        'html': render_to_string('player-list_.html', locals()),
        'num_lineups': request.session.get(ds+'_num_lineups', 1),
    }

    return JsonResponse(result, safe=False)


def get_player(full_name, team):
    '''
    FanDuel has top priority
    '''
    names = full_name.split(' ')
    players = Player.objects.filter(first_name=names[0], last_name=names[1], team=team) \
                            .order_by('data_source')
    player = players.filter(data_source='FanDuel').first()
    if not player:
        player = players.first()
    return player


def mean(numbers):
    return float(sum(numbers)) / max(len(numbers), 1)


def get_num_lineups(player, lineups):
    num = 0
    for ii in lineups:
        if ii.is_member(player):
            num = num + 1
    return num


@csrf_exempt
def gen_lineups(request):
    lineups, players = _get_lineups(request)
    avg_points = mean([ii.projected() for ii in lineups])

    players_ = [{ 'name': '{} {}'.format(ii.first_name, ii.last_name), 
                  'team': ii.team, 
                  'position': ii.actual_position,
                  'id': ii.id, 
                  'avatar': ii.avatar, 
                  'lineups': get_num_lineups(ii, lineups)} 
                for ii in players if get_num_lineups(ii, lineups)]
    players_ = sorted(players_, key=lambda k: k['lineups'], reverse=True)

    ds = request.POST.get('ds')
    header = CSV_FIELDS + ['Spent', 'Projected']
    
    rows = [[[str(jj) for jj in ii.get_players()]+[int(ii.spent()), '{:.2f}'.format(ii.projected())], ii.drop]
            for ii in lineups]

    result = {
        'player_stat': render_to_string('player-lineup.html', locals()),
        'preview_lineups': render_to_string('preview-lineups.html', locals())
    }

    return JsonResponse(result, safe=False)


@csrf_exempt
def update_point(request):
    pid = request.POST.get('pid')
    points = request.POST.get('val')

    player = Player.objects.get(id=pid.strip('-'))
    factor = 1 if player.data_source == 'Yahoo' else 1000

    cus_proj = request.session.get('cus_proj', {})
    if '-' in pid:
        del cus_proj[pid[1:]]
        points = player.proj_points
    else:
        cus_proj[pid] = points

    request.session['cus_proj'] = cus_proj

    result = {
        'points': '{:.1f}'.format(float(points)),
        'pt_sal': '{:.1f}'.format(float(points) * factor / player.salary if player.salary else 0)
    }

    return JsonResponse(result, safe=False)


def _get_export_cell(player, ds):
    if ds == 'Yahoo':
        return str(player)
    else:
        return player.rid or str(player) + ' - No ID'


@xframe_options_exempt
@csrf_exempt
def export_lineups(request):
    lineups, _ = _get_lineups(request)
    ds = request.POST.get('ds')
    csv_fields = CSV_FIELDS
    path = "/tmp/.fantasy_nfl_{}.csv".format(ds.lower())

    with open(path, 'w') as f:
        f.write(','.join(csv_fields)+'\n')
        for ii in lineups:
            f.write(','.join([_get_export_cell(jj, ds) for jj in ii.get_players()])+'\n')
    
    wrapper = FileWrapper( open( path, "r" ) )
    content_type = mimetypes.guess_type( path )[0]

    response = HttpResponse(wrapper, content_type = content_type)
    response['Content-Length'] = os.path.getsize( path )
    response['Content-Disposition'] = 'attachment; filename=%s' % smart_str( os.path.basename( path ) )
    response['X-Frame-Options'] = 'GOFORIT'

    return response


@xframe_options_exempt
@csrf_exempt
def export_manual_lineup(request):
    ds = request.session.get('ds')
    lidx = request.GET.getlist('lidx')
    path = "/tmp/.fantasy_nfl_{}.csv".format(ds.lower())
    csv_fields = CSV_FIELDS

    with open(path, 'w') as f:
        f.write(','.join(csv_fields)+'\n')
        for idx in lidx:
            key = '{}_lineup_{}'.format(ds, idx)
            lineup = request.session.get(key)
            players = [Player.objects.get(id=ii['player']) for ii in lineup]
            f.write(','.join([_get_export_cell(ii, ds) for ii in players])+'\n')
        
    wrapper = FileWrapper( open( path, "r" ) )
    content_type = mimetypes.guess_type( path )[0]

    response = HttpResponse(wrapper, content_type = content_type)
    response['Content-Length'] = os.path.getsize( path )
    response['Content-Disposition'] = 'attachment; filename=%s' % smart_str( os.path.basename( path ) )
    response['X-Frame-Options'] = 'GOFORIT'

    return response


@staff_member_required
def put_ids(request):
    last_updated = Game.objects.all().order_by('-updated_at').first().updated_at

    if request.method == 'GET':
        result = '-'
    else:
        ds = request.POST.get('ds')
        ids = request.POST.get('ids').strip()
        ids_ = ids.split('\r\n')
        names = request.POST.get('names').strip()
        names_ = names.split('\r\n')

        failed = ''
        for idx, name in enumerate(names_):
            d = { 'rid': ids_[idx] }
            first_name, last_name = parse_name(name)
            flag = Player.objects.filter(first_name__iexact=first_name, 
                                         last_name__iexact=last_name, 
                                         data_source=ds).update(**d)
            if not flag:
                failed += '{}\n'.format(ids_[idx], name)
        result = '{} / {}'.format(len(failed.split('\n')), len(ids_))

    return render(request, 'put-ids.html', locals())


@staff_member_required
def put_projection(request):
    last_updated = Game.objects.all().order_by('-updated_at').first().updated_at

    if request.method == 'GET':
        result = '-'
    else:
        ds = request.POST.get('ds')
        projection = request.POST.get('projection').strip()
        projection_ = projection.split('\r\n')
        names = request.POST.get('names').strip()
        names_ = names.split('\r\n')

        failed = ''
        for idx, name in enumerate(names_):
            d = { 'proj_points': projection_[idx], 'lock_update': True }
            first_name, last_name = parse_name(name)
            flag = Player.objects.filter(first_name__iexact=first_name, 
                                         last_name__iexact=last_name, 
                                         data_source=ds).update(**d)

            if not flag:  # check for team (DEF)
                flag = Player.objects.filter(first_name__iexact=name, 
                                             last_name='', 
                                             data_source=ds).update(**d)
            
            if not flag:
                failed += '{} ({})\n'.format(name, projection_[idx])
        result = '{} / {}'.format(len(failed.split('\n')), len(projection_))

    return render(request, 'put-projection.html', locals())


@staff_member_required
@csrf_exempt
def trigger_scraper(request):
    Player.objects.all().update(play_today=False)
    for ds in DATA_SOURCE:
        roto_get_players(ds[0])
        roto_get_games(ds[0])

    return HttpResponse('Completed')


def go_dfs(request):
    return render(request, 'go-dfs.html')


@csrf_exempt
def get_slates(request):
    ds = request.POST.get('ds')
    games = Game.objects.filter(data_source=ds, display=True)
    return render(request, 'game-slates.html', locals())


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


def _get_lineups(request):
    params = request.POST

    ids = params.getlist('ids')
    locked = [int(ii) for ii in params.getlist('locked')]
    num_lineups = min(int(params.get('num-lineups', 1)), 150)
    ds = params.get('ds', 'DraftKings')
    min_salary = int(params.get('min_salary', 0))
    max_salary = int(params.get('max_salary', SALARY_CAP[ds]))

    exposure = params.get('exposure')
    team_stack = params.get('team_stack', {})
    cus_proj = request.session.get('cus_proj', {})

    ids = [ii for ii in ids if ii]
    flt = { 'proj_points__gt': 0, 'id__in': ids, 'salary__gt': 0 }
    players = Player.objects.filter(**flt).order_by('-proj_points')

    # generate team stack
    _team_stack = {}
    teams = players.values_list('team', flat=True).distinct()
    for ii in teams:
        if not ii:
            continue

        min_team_member_ = int(params.get('team-min-{}'.format(ii.lower()), 0))
        max_team_member_ = int(params.get('team-max-{}'.format(ii.lower()), TEAM_MEMEBER_LIMIT[ds]))
        percent_team_member_ = int(params.get('team-percent-{}'.format(ii.lower()), 100))

        if percent_team_member_ == 0:
            min_team_member_ = 0
            max_team_member_ = 0
        else:
            percent_team_member_ = int(num_lineups * percent_team_member_ / 100.0 + 0.5) or 1

        _team_stack[ii] = { 
            'min': min_team_member_, 
            'max': max_team_member_, 
            'percent': percent_team_member_ 
        }

    # get exposure for each valid player
    _exposure = []

    for ii in players:
        if ii.id in locked:
            _exposure.append({ 'min': num_lineups, 'max': num_lineups, 'id': ii.id })
        else:
            _exposure.append({
                'min': int(math.ceil(float(params.get('min_xp_{}'.format(ii.id), 0)) * num_lineups / 100)),
                'max': int(math.floor(float(params.get('max_xp_{}'.format(ii.id), 0)) * num_lineups / 100)),
                'id': ii.id
            })

    # check validity of exposure for minimal
    while True:
        possible_players = 0
        for ii in _exposure:
            possible_players += ii['max']
        if possible_players < ROSTER_SIZE[ds] * num_lineups:
            for ii in _exposure:
                ii['max'] = ii['max'] + 1
        else:
            break

    lineups = calc_lineups(players, num_lineups, locked, ds, min_salary, max_salary, _team_stack, _exposure, cus_proj)

    return lineups, players
