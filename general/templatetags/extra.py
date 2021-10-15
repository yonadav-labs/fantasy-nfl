from django import template

from general.models import *


register = template.Library()


@register.filter
def percent(val):
    return val if val else '-';


@register.filter
def cus_proj(player, session):
    cus_proj = session.get('cus_proj', {})
    cus_proj = cus_proj.get(str(player['id']), player['proj_points'])
    return f'{float(cus_proj):.2f}'


@register.filter
def cus_proj_cls(player, session):
    cus_proj = session.get('cus_proj', {})
    return 'custom' if str(player['id']) in cus_proj else ''


@register.filter
def cus_proj_(player, session):
    if player:
        cus_proj = session.get('cus_proj', {})
        proj = cus_proj.get(str(player.id), player.proj_points)
        return f'{float(proj):.2f}'
    return ''


@register.filter
def check_drop(name, drop):
    return 'text-danger' if drop == name else ''
