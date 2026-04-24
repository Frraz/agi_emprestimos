"""Configurações de desenvolvimento local."""
from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ['*']

# Debug toolbar
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
INTERNAL_IPS = ['127.0.0.1']

# CORS liberado em desenvolvimento
CORS_ALLOW_ALL_ORIGINS = True

# E-mail no console (não envia de verdade)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Logging detalhado
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
    'loggers': {
        # Silencia SQL queries em desenvolvimento (descomente para debugar)
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}