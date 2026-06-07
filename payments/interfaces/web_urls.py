from django.urls import path
from . import web_views

app_name = 'web_payments'

urlpatterns = [
    path('', web_views.pagamento_list, name='list'),
    path('<uuid:pk>/editar/', web_views.pagamento_editar, name='editar'),
    path('<uuid:pk>/desativar/', web_views.pagamento_desativar, name='desativar'),
    path('<uuid:pk>/ativar/', web_views.pagamento_ativar, name='ativar'),
    path('<uuid:pk>/apagar/', web_views.pagamento_apagar, name='apagar'),
]