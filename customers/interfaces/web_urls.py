from django.urls import path
from . import web_views

app_name = 'web_customers'

urlpatterns = [
    path('', web_views.cliente_list, name='list'),
    path('novo/', web_views.cliente_create, name='create'),
    path('buscar-indicador/', web_views.buscar_indicador, name='buscar_indicador'),
    path('buscar-cep/', web_views.buscar_cep, name='buscar_cep'),
    path('<uuid:pk>/', web_views.cliente_detail, name='detail'),
    path('<uuid:pk>/editar/', web_views.cliente_update, name='update'),
    path('<uuid:pk>/excluir/', web_views.cliente_delete, name='delete'),
]