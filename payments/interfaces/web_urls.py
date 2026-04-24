from django.urls import path
from . import web_views

app_name = 'web_payments'

urlpatterns = [
    path('', web_views.pagamento_list, name='list'),
]