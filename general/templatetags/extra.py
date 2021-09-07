from django import template

from general.models import *


register = template.Library()


@register.filter
def percent(val):
    return val if val else '-';


@register.filter
def ou_ml(game, team):
    if not game.ml:
        return ''

    if team in game.ml:
        return '( {} )'.format(game.ml.split(' ')[-1])
    else:
        return '( {} )'.format(int(game.ou))


@register.filter
def cus_proj(player, session):
    cus_proj = session.get('cus_proj', {})
    cus_proj = cus_proj.get(str(player['id']), player['proj_points'])
    return '{:.2f}'.format(float(cus_proj))


@register.filter
def cus_proj_cls(player, session):
    cus_proj = session.get('cus_proj', {})
    return 'custom' if str(player['id']) in cus_proj else ''


@register.filter
def cus_proj_(player, session):
    if player:
        cus_proj = session.get('cus_proj', {})
        proj = cus_proj.get(str(player.id), player.proj_points)
        return '{:.2f}'.format(float(proj))
    return ''


@register.filter
def check_drop(name, drop):
    return 'text-danger' if drop == name else ''
