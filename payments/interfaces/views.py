from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from payments.infrastructure.models import Pagamento
from payments.interfaces.serializers import PagamentoSerializer


class PagamentoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Pagamentos são imutáveis — apenas leitura via API.
    Registro ocorre via EmprestimoViewSet.pagar().
    """
    queryset = Pagamento.objects.select_related(
        'emprestimo__cliente'
    ).order_by('-data_pagamento')
    serializer_class = PagamentoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['tipo', 'data_pagamento', 'emprestimo']
    ordering_fields = ['data_pagamento', 'valor']