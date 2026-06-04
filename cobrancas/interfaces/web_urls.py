from django.urls import path
from . import web_views

app_name = 'web_cobrancas'

urlpatterns = [
    path('', web_views.cobrancas_index, name='index'),
    path('calendario/', web_views.cobrancas_calendario, name='calendario'),
]
