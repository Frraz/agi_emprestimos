"""Settings temporário para rodar testes/migrações sem Postgres local.
Herda de development e troca o banco por SQLite em memória."""
from .development import *  # noqa

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
