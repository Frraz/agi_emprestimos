from django.urls import path
from . import web_views

app_name = 'web_collaterals'

urlpatterns = [
    path('novo/<uuid:emprestimo_pk>/', web_views.garantia_create, name='create'),
    path('<uuid:pk>/excluir/', web_views.garantia_delete, name='delete'),
]