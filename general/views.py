import csv
import math

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.forms.models import model_to_dict
from django.db.models import Sum
from django.apps import apps

from general.models import *
from general.lineup import *
from general.lineup_showdown import calc_lineups_showdown
from general.dao import get_slate, load_games, load_players
from general.utils import parse_players_csv, parse_projection_csv, mean, get_num_lineups, get_cell_to_export
from general.constants import CSV_FIELDS, CSV_FIELDS_SHOWDOWN, SALARY_CAP


@xframe_options_exempt
def lineup_builder(request):
    data_sources = DATA_SOURCE
    mode = request.GET.get('mode', 'main')
    other_mode = 'showdown' if mode == 'main' else 'main'
    num_lineups = request.session.get('DraftKings_num_lineups', 1)
    if mode == 'showdown':
        data_sources = DATA_SOURCE[:2]

    return render(request, 'lineup-builder.html', locals())


@xframe_options_exempt
def lineup_optimizer(request):
    data_sources = DATA_SOURCE
    mode = request.GET.get('mode', 'main')
    other_mode = 'showdown' if mode == 'main' else 'main'
    if mode == 'showdown':
        data_sources = DATA_SOURCE[:2]

    return render(request, 'lineup-optimizer.html', locals())


def _is_full_lineup(lineup, ds):
    if not lineup:
        return False

    num_players = sum([1 for ii in lineup if ii['player']])

    return num_players == ROSTER_SIZE[ds]


def get_team_match(ds):
    team_match = {}
    for ii in Game.objects.filter(slate__data_source=ds):
        team_match[ii.home_team] = {
            'opponent': ii.visit_team,
            'type': 1
        }
        team_match[ii.visit_team] = {
            'opponent': ii.home_team,
            'type': 2
        }

    return team_match


@csrf_exempt
def check_manual_lineups(request):
    ds = request.POST.get('ds')
    mode = request.POST.get('mode')
    num_lineups_key = f'{mode}-{ds}-num-lineups'
    num_lineups = request.session.get(num_lineups_key, 1)

    res = []
    for ii in range(1, num_lineups+1):
        lineup_session_key = f'{mode}-{ds}-lineup-{ii}'
        lineup = request.session.get(lineup_session_key)
        res.append([ii, 'checked' if _is_full_lineup(lineup, ds) else 'disabled'])

    return JsonResponse(res, safe=False)


@csrf_exempt
def build_lineup(request):
    ds = request.POST.get('ds')
    mode = request.POST.get('mode')
    pid = request.POST.get('pid')
    position = request.POST.get('position')
    idx = int(request.POST.get('idx'))
    positions = CSV_FIELDS_SHOWDOWN[ds] if mode == 'showdown' else CSV_FIELDS

    cus_proj = request.session.get('cus_proj', {})
    request.session['ds'] = ds
    request.session['mode'] = mode

    num_lineups_key = f'{mode}-{ds}-num-lineups'
    lineup_session_key = f'{mode}-{ds}-lineup-{idx}'
    num_lineups = request.session.get(num_lineups_key, 1)
    lineup_ = [{ 'pos':ii, 'player': '' } for ii in positions]
    # current roster
    lineup = request.session.get(lineup_session_key, lineup_)

    # validate the lineup
    for ii in lineup:
        if ii['player']:
            if not Player.objects.filter(id=ii['player']).exists():
                ii['player'] = ''

    if idx > num_lineups:           # add lineup
        num_lineups = idx
        request.session[num_lineups_key] = idx
        request.session[lineup_session_key] = lineup_

    msg = ''
    if pid == "999999999":          # remove all lineups
        request.session[num_lineups_key] = 1
        lineup_session_key = f'{mode}-{ds}-lineup-1'
        request.session[lineup_session_key] = lineup_

        for ii in range(2, num_lineups+1):
            lineup_session_key = f'{mode}-{ds}-lineup-{ii}'
            request.session.pop(lineup_session_key)
    elif '-' in pid:                # remove a player
        for ii in lineup:
            if ii['player'] == pid.strip('-'):
                ii['player'] = ''
    elif pid == 'optimize':         # manual optimize
        ids = request.POST.get('ids').strip('ids=').split('&ids=')
        players = Player.objects.filter(id__in=ids)
        num_lineups = 1
        _exposure = [{ 'min': 0, 'max': 1, 'id': ii.id } for ii in players]

        if mode == 'main':
            locked = []
            for ii in lineup:
                if ii['player']:
                    if ii['pos'] != 'FLEX':
                        locked.append([f"{ii['player']}-{ii['pos']}"])
                    else:
                        player = Player.objects.get(id=ii['player'])
                        locked.append([f"{player.id}-{player.position}"])
            team_match = get_team_match(ds)
            lineups = calc_lineups(players, num_lineups, locked, ds, 0, SALARY_CAP[ds], _exposure, cus_proj, team_match)
        else:
            locked = [[f"{ii['player']}-{ii['pos']}"] for ii in lineup if ii['player']]
            lineups = calc_lineups_showdown(players, num_lineups, locked, ds, 0, SALARY_CAP[ds], _exposure, cus_proj)


        if lineups:
            roster = lineups[0].get_players()
            lineup = [{ 'pos':ii, 'player': str(roster[idx].id) } for idx, ii in enumerate(positions)]
            request.session[lineup_session_key] = lineup
        else:
            msg = 'Sorry, something is wrong.'
    elif pid:                       # add a player
        # check whether he is available
        sum_salary = Player.objects.filter(id__in=[ii['player'] for ii in lineup if ii['player']]) \
                                   .aggregate(Sum('salary'))['salary__sum'] or 0
        available = False

        player = Player.objects.get(id=pid)
        if SALARY_CAP[ds] >= sum_salary + player.salary:
            for ii in lineup:
                if not ii['player']:
                    if (position in 'RB/WR/TE' and ii['pos'] == 'FLEX') or ii['pos'] in position:
                        available = True
                        ii['player'] = pid
                        break
            # TODO: check team number constraint
            if available:
                # save lineup
                request.session[lineup_session_key] = lineup
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
        player = {}
        if ii['player']:
            player = Player.objects.get(id=ii['player'])

        if player:
            pids.append(ii)
            num_players += 1
            sum_salary += player.salary
            sum_proj += float(cus_proj.get(str(player.id), player.proj_points))

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
    slate_id = request.POST.get('slate_id')
    is_optimizer = request.POST.get('is_optimizer') == 'true'
    slate = Slate.objects.get(pk=slate_id)
    ds = slate.data_source
    order = request.POST.get('order', 'proj_points')
    if order == '-':
        order = 'proj_points'

    reverse = False if '-' in order else True
    order = order.replace('-', '')
    teams = request.POST.get('games').strip(';').replace(';', '-').split('-')

    factor = 1 if ds == 'Yahoo' else 1000
    players = []

    cus_proj = request.session.get('cus_proj', {})
    for ii in Player.objects.filter(slate=slate, team__in=teams):
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
    num_lineups_key = f'{slate.mode}-{ds}-num-lineups'

    result = { 
        'html': render_to_string('player-list_.html', locals()),
        'num_lineups': request.session.get(num_lineups_key, 1),
    }

    return JsonResponse(result, safe=False)


@csrf_exempt
def generate_lineups(request):
    lineups, players = _get_lineups(request)
    avg_points = mean([ii.projected() for ii in lineups])

    players_ = [{ 'name': f'{ii.first_name} {ii.last_name}',
                  'team': ii.team, 
                  'position': ii.actual_position,
                  'id': ii.id, 
                  'avatar': ii.avatar, 
                  'lineups': get_num_lineups(ii, lineups)} 
                for ii in players if get_num_lineups(ii, lineups)]
    players_ = sorted(players_, key=lambda k: k['lineups'], reverse=True)

    ds = request.POST.get('ds')
    mode = request.POST.get('mode')
    header = CSV_FIELDS_SHOWDOWN[ds] if mode == 'showdown' else CSV_FIELDS
    header = header.copy() + ['Spent', 'Projected']

    rows = [[[str(jj) for jj in ii.get_players()]+[int(ii.spent()), f'{ii.projected():.2f}'], ii.drop]
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
    factor = 1 if player.slate.data_source == 'Yahoo' else 1000

    cus_proj = request.session.get('cus_proj', {})
    if '-' in pid:
        del cus_proj[pid[1:]]
        points = player.proj_points
    else:
        cus_proj[pid] = points

    request.session['cus_proj'] = cus_proj
    pt_sal = float(points) * factor / player.salary if player.salary else 0

    result = {
        'points': f'{float(points):.1f}',
        'pt_sal': f'{pt_sal:.1f}'
    }

    return JsonResponse(result, safe=False)


@xframe_options_exempt
@csrf_exempt
def export_lineups(request):
    lineups, _ = _get_lineups(request)
    ds = request.POST.get('ds')
    mode = request.POST.get('mode')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="fantasy_nfl_{ds.lower()}_{mode}.csv"'
    response['X-Frame-Options'] = 'GOFORIT'

    header = CSV_FIELDS_SHOWDOWN[ds] if mode == 'showdown' else CSV_FIELDS
    writer = csv.writer(response)
    writer.writerow(header)
    for ii in lineups:
        writer.writerow([get_cell_to_export(jj) for jj in ii.get_players()])

    return response


@xframe_options_exempt
@csrf_exempt
def export_manual_lineup(request):
    ds = request.session.get('ds')
    mode = request.session.get('mode')
    lidx = request.GET.getlist('lidx')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="fantasy_nfl_{ds.lower()}_{mode}.csv"'
    response['X-Frame-Options'] = 'GOFORIT'

    header = CSV_FIELDS_SHOWDOWN[ds] if mode == 'showdown' else CSV_FIELDS
    writer = csv.writer(response)
    writer.writerow(header)

    for idx in lidx:
        lineup_session_key = f'{mode}-{ds}-lineup-{idx}'
        lineup = request.session.get(lineup_session_key)
        players = [Player.objects.get(id=ii['player']) for ii in lineup]
        writer.writerow([get_cell_to_export(ii) for ii in players])

    return response


@staff_member_required
def load_slate(request, slate_id):
    load_empty_proj = request.GET.get('emtpy')
    slate = Slate.objects.get(pk=slate_id)
    games = Game.objects.filter(slate=slate)

    q = dict(slate=slate, proj_points=0) if load_empty_proj else dict(slate=slate, proj_points__gt=0)
    players = Player.objects.filter(**q)

    return render(request, 'edit-slate.html', locals())


@staff_member_required
def upload_data(request):
    if request.method == 'GET':
        mode = 'main'
        fd_slates = Slate.objects.filter(data_source="FanDuel").order_by('date', 'mode')
        dk_slates = Slate.objects.filter(data_source="DraftKings").order_by('date')
        yh_slates = Slate.objects.filter(data_source="Yahoo").order_by('date')

        return render(request, 'upload-slate.html', locals())
    else:
        date = request.POST['date']
        slate_name = request.POST['slate']
        data_source = request.POST['data_source']
        mode = request.POST['mode']
        slate = get_slate(date, slate_name, data_source, mode)

        err_msg = ''
        try:
            projection_file = request.FILES['projection_file']
            projection_info = parse_projection_csv(projection_file)
            projection_info = [f"{row['name']} @#@{row['fpts'] or 0}" for row in projection_info]
        except Exception:
            err_msg = 'Projection file is invalid'
            return render(request, 'upload-slate.html', locals())

        try:
            players_file = request.FILES['players_file']
            players_info = parse_players_csv(players_file, data_source)
            games = load_games(slate, players_info)
            players = load_players(slate, players_info, projection_info)
        except Exception:
            err_msg = 'Player file is invalid'
            return render(request, 'upload-slate.html', locals())

        return render(request, 'edit-slate.html', locals())


@staff_member_required
@csrf_exempt
def update_field(request):
    data = request.POST
    model_name = data.get('model')
    id = data.get('id')
    field = data.get('field')
    val = data.get('val')

    model_cls = apps.get_model('general', model_name)
    model = model_cls.objects.get(pk=id)
    setattr(model, field, val)
    model.save()

    return HttpResponse()


@csrf_exempt
def get_games(request):
    slate_id = request.POST.get('slate_id')
    games = Game.objects.filter(slate_id=slate_id)

    return render(request, 'game-list.html', locals())


@csrf_exempt
def get_slates(request):
    ds = request.POST.get('ds')
    mode = request.POST.get('mode')
    slates = Slate.objects.filter(data_source=ds, mode=mode)

    return render(request, 'slate-list.html', locals())


def _get_lineups(request):
    params = request.POST

    ids = params.getlist('ids')
    locked_ids = [int(ii) for ii in params.getlist('locked')]
    num_lineups = min(int(params.get('num-lineups', 1)), 150)
    ds = params.get('ds', 'DraftKings')
    mode = params.get('mode')
    min_salary = int(params.get('min_salary', 0))
    max_salary = int(params.get('max_salary', SALARY_CAP[ds]))

    exposure = params.get('exposure')
    team_stack = params.get('team_stack', {})
    cus_proj = request.session.get('cus_proj', {})

    ids = [ii for ii in ids if ii]
    flt = { 'proj_points__gt': 0, 'id__in': ids, 'salary__gt': 0 }
    players = Player.objects.filter(**flt).order_by('-proj_points')

    # get exposure for each valid player
    _exposure = []

    for ii in players:
        if ii.id in locked_ids:
            _exposure.append({ 'min': num_lineups, 'max': num_lineups, 'id': ii.id })
        else:
            _exposure.append({
                'min': int(math.ceil(float(params.get(f'min_xp_{ii.id}', 0)) * num_lineups / 100)),
                'max': int(math.floor(float(params.get(f'max_xp_{ii.id}', 0)) * num_lineups / 100)),
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

    players_ = Player.objects.filter(id__in=locked_ids)

    if mode == 'main':
        team_match = get_team_match(ds)
        locked = [[f'{player.id}-{player.position}'] for player in players_]
        lineups = calc_lineups(players, num_lineups, locked, ds, min_salary, max_salary, _exposure, cus_proj, team_match)
    elif mode == 'showdown':
        locked = [[f'{player.id}-MVP', f'{player.id}-FLEX'] for player in players_]
        lineups = calc_lineups_showdown(players, num_lineups, locked, ds, min_salary, max_salary, _exposure, cus_proj)

    return lineups, players
