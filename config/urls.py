from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from customers.interfaces import web_views as customer_web

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── Auth web ───────────────────────────────────────────────────────────
    path('login/', auth_views.LoginView.as_view(template_name='base/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),

    # ── API REST ───────────────────────────────────────────────────────────
    path('api/v1/', include('api.v1.urls')),

    # ── Web ────────────────────────────────────────────────────────────────
    path('', include(('dashboard.interfaces.urls', 'dashboard'))),
    path('clientes/', include('customers.interfaces.web_urls')),
    path('emprestimos/', include('loans.interfaces.web_urls')),
    path('pagamentos/', include('payments.interfaces.web_urls')),

    path('garantias/', include('collaterals.interfaces.web_urls')),
    path('api/cep/', customer_web.buscar_cep, name='buscar_cep'),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)