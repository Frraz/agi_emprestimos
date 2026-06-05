from django.urls import path
from . import web_views

app_name = 'exports'

urlpatterns = [
    path('', web_views.backup_index, name='index'),
    path('backup/<str:fmt>/', web_views.exportar_backup, name='backup'),
    path('<str:dataset>/<str:fmt>/', web_views.exportar, name='exportar'),
]
