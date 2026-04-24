from rest_framework import serializers
from payments.infrastructure.models import Pagamento


class PagamentoSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(
        source='emprestimo.cliente.nome', read_only=True
    )
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)

    class Meta:
        model = Pagamento
        fields = [
            'id', 'emprestimo', 'parcela',
            'cliente_nome', 'valor', 'tipo', 'tipo_display',
            'data_pagamento',
            'valor_juros_pagos', 'valor_capital_pago',
            'capital_antes', 'capital_depois',
            'observacoes', 'created_at',
        ]
        read_only_fields = fields