"""Configurações de produção — preencher conforme infraestrutura."""
from .base import *  # noqa

DEBUG = False

CORS_ALLOWED_ORIGINS = [
    # 'https://seu-dominio.com.br',
]

# Segurança HTTPS
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
# SECURE_SSL_REDIRECT = True  # Ativar após configurar HTTPS
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True