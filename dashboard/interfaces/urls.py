from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard-index'),
    path('metricas/', views.metricas_api, name='dashboard-metricas'),
    path('capital/', views.capital_config, name='capital-config'),
]