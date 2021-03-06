from django.contrib import admin

from general.models import Slate, Game, Player


@admin.register(Slate)
class SlateAdmin(admin.ModelAdmin):
    list_display = ('name', 'data_source', 'date', 'mode')
    list_filter = ('data_source', 'mode')


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'rid', 'position', 'actual_position', 'team', 'opponent', 'salary',
                    'proj_points', 'proj_delta', 'updated_at']
    search_fields = ['first_name', 'last_name', 'team']
    list_filter = ['slate__data_source', 'team', 'position', 'slate__name']


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['slate', 'visit_team', 'home_team', 'ou', 'time', 'updated_at']
    search_fields = ['home_team', 'visit_team']
    list_filter = ['slate__name', 'slate__data_source']
