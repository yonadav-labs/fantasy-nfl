# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

DATA_SOURCE = (
    ('DraftKings', 'DraftKings'),
    ('FanDuel', 'FanDuel'),
    ('Yahoo', 'Yahoo'),
)


def parse_name(name):
    # get first and last name from name string after processing
    name = name.strip().replace('.', '')
    name_ = name.split(' ')
    if len(name_) > 1:
        return name_[0], ' '.join(name_[1:])
    return name, ''


class Player(models.Model):
    uid = models.IntegerField()
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    avatar = models.CharField(max_length=250, default="/static/img/nba.ico")
    injury = models.CharField(max_length=250, blank=True, null=True)
    opponent = models.CharField(max_length=50, blank=True, null=True)

    minutes = models.FloatField(default=0)
    money_line = models.IntegerField(default=0)
    over_under = models.FloatField(default=0)
    point_spread = models.FloatField(default=0)
    position = models.CharField(max_length=50)
    actual_position = models.CharField(max_length=50)

    proj_points = models.FloatField()
    proj_delta = models.FloatField(default=0)
    salary = models.IntegerField(default=0)

    salary_original = models.FloatField(default=0)
    team = models.CharField(max_length=50)
    team_points = models.FloatField(default=0)
    value = models.FloatField(default=0)
    play_today = models.BooleanField(default=False)
    lock_update = models.BooleanField(default=False)

    rid = models.CharField(max_length=100, null=True, blank=True)
    data_source = models.CharField(max_length=30, choices=DATA_SOURCE, default='FanDuel')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{} {}'.format(self.first_name, self.last_name)


@receiver(post_save, sender=Player, dispatch_uid="sync_fanduel_proj")
def sync_proj(sender, instance, **kwargs):
    if instance.data_source == 'FanDuel':
        Player.objects.filter(uid=instance.uid, data_source='Yahoo').update(proj_points=instance.proj_points)


class FavPlayer(models.Model):
    player = models.ForeignKey(Player)

    def __str__(self):
        return '{} {}'.format(self.player.first_name, self.player.last_name)



class Game(models.Model):

    GAME_STATUS = (
        ('started', 'Started'),
        ('upcomming', 'Upcomming')
    )

    home_team = models.CharField(max_length=20)
    visit_team = models.CharField(max_length=20)
    home_score = models.CharField(max_length=50, null=True, blank=True)
    visit_score = models.CharField(max_length=50, null=True, blank=True)
    ou = models.FloatField()
    ml = models.CharField(max_length=20)
    date = models.DateTimeField()
    game_status = models.CharField(max_length=50, choices=GAME_STATUS, default='started')
    data_source = models.CharField(max_length=30, choices=DATA_SOURCE, default='FanDuel')

    lock_update = models.BooleanField(default=False)
    display = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return '{} - {}'.format(self.home_team, self.visit_team)
