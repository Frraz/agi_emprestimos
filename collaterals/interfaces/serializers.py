from rest_framework import serializers
from collaterals.infrastructure.models import Garantia, DocumentoGarantia
from loans.domain.calculators import CalculadoraInadimplencia


class DocumentoGarantiaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoGarantia
        fields = ['id', 'arquivo', 'descricao', 'created_at']
        read_only_fields = ['id', 'created_at']


class GarantiaSerializer(serializers.ModelSerializer):
    documentos = DocumentoGarantiaSerializer(many=True, read_only=True)
    exposicao = serializers.SerializerMethodField()

    class Meta:
        model = Garantia
        fields = [
            'id', 'emprestimo', 'tipo', 'descricao',
            'valor_estimado', 'percentual_recuperacao',
            'detalhes', 'exposicao', 'documentos',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_exposicao(self, obj) -> dict:
        return obj.calcular_exposicao()