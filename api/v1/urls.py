from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenBlacklistView,
)

urlpatterns = [
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/logout/', TokenBlacklistView.as_view(), name='token_blacklist'),

    path('clientes/', include('customers.interfaces.urls')),
    path('emprestimos/', include('loans.interfaces.urls')),
    path('pagamentos/', include('payments.interfaces.urls')),
    path('garantias/', include('collaterals.interfaces.urls')),
    path('dashboard/', include(('dashboard.interfaces.urls', 'dashboard-api'))),
]