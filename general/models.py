from django.db import models

from general.constants import DATA_SOURCE


class Slate(models.Model):
    SLATE_MODE = (
        ('classic', 'Classic'),
        ('showdown', 'Showdown')
    )
    data_source = models.CharField(max_length=30, choices=DATA_SOURCE)
    name = models.CharField(max_length=120)
    date = models.DateField()
    mode = models.CharField(max_length=20, choices=SLATE_MODE, default='classic')

    def __str__(self):
        return self.name


class Game(models.Model):
    slate = models.ForeignKey(Slate, on_delete=models.CASCADE, related_name="games")
    home_team = models.CharField(max_length=20)
    visit_team = models.CharField(max_length=20)
    time = models.CharField(max_length=20, null=True, blank=True, default="")
    home_score = models.CharField(max_length=50, null=True, blank=True)
    visit_score = models.CharField(max_length=50, null=True, blank=True)
    ou = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'{self.visit_team}@{self.home_team}'


class Player(models.Model):
    slate = models.ForeignKey(Slate, on_delete=models.CASCADE, related_name="players")
    rid = models.CharField(max_length=100)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    avatar = models.CharField(max_length=250, default="/static/img/nba.ico")
    injury = models.CharField(max_length=250, blank=True)
    opponent = models.CharField(max_length=50)
    position = models.CharField(max_length=50)
    actual_position = models.CharField(max_length=50)
    proj_points = models.DecimalField(max_digits=5, decimal_places=2)
    proj_delta = models.FloatField()
    salary = models.IntegerField()
    team = models.CharField(max_length=50)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'
