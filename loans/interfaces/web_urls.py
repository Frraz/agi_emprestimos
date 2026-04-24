from django.urls import path
from . import web_views

app_name = 'web_loans'

urlpatterns = [
    path('', web_views.emprestimo_list, name='list'),
    path('<uuid:pk>/', web_views.emprestimo_detail, name='detail'),
    path('novo/comum/<uuid:cliente_pk>/', web_views.emprestimo_criar_comum, name='criar_comum'),
    path('novo/parcelado/<uuid:cliente_pk>/', web_views.emprestimo_criar_parcelado, name='criar_parcelado'),
    path('<uuid:pk>/pagar/', web_views.emprestimo_pagar, name='pagar'),
]