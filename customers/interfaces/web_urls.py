from django.urls import path
from . import web_views

app_name = 'web_customers'

urlpatterns = [
    path('', web_views.cliente_list, name='list'),
    path('novo/', web_views.cliente_create, name='create'),
    path('tags/', web_views.tag_manage, name='tags'),
    path('tags/<uuid:pk>/excluir/', web_views.tag_delete, name='tag_delete'),
    path('buscar-indicador/', web_views.buscar_indicador, name='buscar_indicador'),
    path('buscar-cep/', web_views.buscar_cep, name='buscar_cep'),
    path('<uuid:pk>/', web_views.cliente_detail, name='detail'),
    path('<uuid:pk>/editar/', web_views.cliente_update, name='update'),
    path('<uuid:pk>/desativar/', web_views.cliente_desativar, name='desativar'),
    path('<uuid:pk>/ativar/', web_views.cliente_ativar, name='ativar'),
    path('<uuid:pk>/apagar/', web_views.cliente_apagar, name='apagar'),
    path('<uuid:pk>/tags/', web_views.cliente_set_tags, name='set_tags'),
]