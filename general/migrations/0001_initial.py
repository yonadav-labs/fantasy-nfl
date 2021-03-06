# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2021-09-07 10:44
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Game',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('home_team', models.CharField(max_length=20)),
                ('visit_team', models.CharField(max_length=20)),
                ('time', models.CharField(blank=True, default='', max_length=20, null=True)),
                ('home_score', models.CharField(blank=True, max_length=50, null=True)),
                ('visit_score', models.CharField(blank=True, max_length=50, null=True)),
                ('ou', models.FloatField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='Player',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rid', models.CharField(max_length=100)),
                ('first_name', models.CharField(max_length=50)),
                ('last_name', models.CharField(max_length=50)),
                ('avatar', models.CharField(default='/static/img/nba.ico', max_length=250)),
                ('injury', models.CharField(blank=True, max_length=250)),
                ('opponent', models.CharField(max_length=50)),
                ('position', models.CharField(max_length=50)),
                ('actual_position', models.CharField(max_length=50)),
                ('proj_points', models.DecimalField(decimal_places=2, max_digits=5)),
                ('proj_delta', models.FloatField()),
                ('salary', models.IntegerField()),
                ('team', models.CharField(max_length=50)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='Slate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data_source', models.CharField(choices=[('DraftKings', 'DraftKings'), ('FanDuel', 'FanDuel'), ('Yahoo', 'Yahoo')], max_length=30)),
                ('name', models.CharField(max_length=120)),
                ('date', models.DateField()),
            ],
        ),
        migrations.AddField(
            model_name='player',
            name='slate',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='players', to='general.Slate'),
        ),
        migrations.AddField(
            model_name='game',
            name='slate',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='games', to='general.Slate'),
        ),
    ]
