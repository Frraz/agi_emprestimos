from rest_framework import serializers
from loans.infrastructure.models import Emprestimo, ParcelaEmprestimo


class ParcelaSerializer(serializers.ModelSerializer):
    valor_em_aberto = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    esta_atrasada = serializers.SerializerMethodField()

    class Meta:
        model = ParcelaEmprestimo
        fields = [
            'id', 'numero', 'valor_parcela', 'valor_principal', 'valor_juros',
            'saldo_devedor_antes', 'saldo_devedor_depois',
            'valor_pago', 'valor_em_aberto', 'esta_atrasada',
            'data_vencimento', 'data_pagamento', 'status',
        ]
        read_only_fields = fields

    def get_esta_atrasada(self, obj) -> bool:
        return obj.esta_atrasada


class EmprestimoListSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome', read_only=True)
    taxa_display = serializers.CharField(source='taxa_percentual_display', read_only=True)

    class Meta:
        model = Emprestimo
        fields = [
            'id', 'cliente_nome', 'tipo', 'subtipo_parcelado',
            'capital_inicial', 'capital_atual', 'taxa_display',
            'status', 'data_inicio', 'data_vencimento', 'updated_at',
        ]


class EmprestimoSerializer(serializers.ModelSerializer):
    parcelas = ParcelaSerializer(many=True, read_only=True)
    cliente_nome = serializers.CharField(source='cliente.nome', read_only=True)
    taxa_display = serializers.CharField(source='taxa_percentual_display', read_only=True)
    total_pago = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    total_garantias = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = Emprestimo
        fields = [
            'id', 'cliente', 'cliente_nome',
            'tipo', 'subtipo_parcelado',
            'capital_inicial', 'capital_atual',
            'taxa_juros_mensal', 'taxa_display',
            'n_parcelas', 'data_inicio', 'data_vencimento', 'data_quitacao',
            'status', 'observacoes',
            'total_pago', 'total_garantias',
            'parcelas', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'capital_atual', 'status', 'data_quitacao',
            'created_at', 'updated_at',
        ]


class CriarEmprestimoComumSerializer(serializers.Serializer):
    """Serializer de entrada para criação de empréstimo COMUM."""
    cliente_id = serializers.UUIDField()
    capital = serializers.DecimalField(max_digits=12, decimal_places=2)
    taxa_mensal = serializers.DecimalField(max_digits=8, decimal_places=6)
    data_inicio = serializers.DateField()
    observacoes = serializers.CharField(required=False, allow_blank=True, default='')


class CriarEmprestimoParceladoSerializer(serializers.Serializer):
    """Serializer de entrada para criação de empréstimo PARCELADO."""
    cliente_id = serializers.UUIDField()
    capital = serializers.DecimalField(max_digits=12, decimal_places=2)
    taxa_mensal = serializers.DecimalField(max_digits=8, decimal_places=6)
    n_parcelas = serializers.IntegerField(min_value=1, max_value=360)
    subtipo = serializers.ChoiceField(choices=['fixo', 'sac'])
    data_inicio = serializers.DateField()
    data_primeira_parcela = serializers.DateField()
    observacoes = serializers.CharField(required=False, allow_blank=True, default='')


class PagamentoComumSerializer(serializers.Serializer):
    """Serializer de entrada para registrar pagamento em empréstimo COMUM."""
    valor = serializers.DecimalField(max_digits=12, decimal_places=2)
    data_pagamento = serializers.DateField()
    observacoes = serializers.CharField(required=False, allow_blank=True, default='')