from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmprestimoViewSet

router = DefaultRouter()
router.register(r'', EmprestimoViewSet, basename='emprestimo')

urlpatterns = [
    path('', include(router.urls)),
]