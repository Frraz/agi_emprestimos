from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GarantiaViewSet

router = DefaultRouter()
router.register(r'', GarantiaViewSet, basename='garantia')

urlpatterns = [path('', include(router.urls))]