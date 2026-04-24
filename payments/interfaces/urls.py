from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PagamentoViewSet

router = DefaultRouter()
router.register(r'', PagamentoViewSet, basename='pagamento')

urlpatterns = [path('', include(router.urls))]