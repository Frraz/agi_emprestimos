# Proxy de importação — Django descobre os models via este arquivo.
from customers.infrastructure.models import Cliente, DocumentoCliente  # noqa

__all__ = ['Cliente', 'DocumentoCliente']