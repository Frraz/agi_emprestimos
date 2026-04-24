from rest_framework import serializers
from customers.infrastructure.models import Cliente, DocumentoCliente
from core.utils import validar_cpf, formatar_cpf


class DocumentoClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoCliente
        fields = ['id', 'tipo', 'arquivo', 'descricao', 'created_at']
        read_only_fields = ['id', 'created_at']


class ClienteListSerializer(serializers.ModelSerializer):
    """Serializer leve para listagem — sem documentos nem campos pesados."""

    class Meta:
        model = Cliente
        fields = [
            'id', 'nome', 'cpf', 'telefone_principal',
            'cidade', 'estado', 'classificacao', 'updated_at',
        ]


class ClienteSerializer(serializers.ModelSerializer):
    """Serializer completo para criação, detalhe e edição."""
    documentos = DocumentoClienteSerializer(many=True, read_only=True)
    tem_emprestimo_ativo = serializers.SerializerMethodField()
    saldo_devedor_total = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            'id', 'nome', 'cpf', 'rg', 'data_nascimento', 'foto',
            'telefone_principal', 'telefone_secundario', 'email',
            'cep', 'logradouro', 'numero', 'complemento',
            'bairro', 'cidade', 'estado',
            'redes_sociais', 'origem', 'indicador',
            'perfil_psicologico', 'observacoes', 'classificacao',
            'tem_emprestimo_ativo', 'saldo_devedor_total',
            'documentos', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'classificacao', 'created_at', 'updated_at']

    def get_tem_emprestimo_ativo(self, obj) -> bool:
        return obj.tem_emprestimo_ativo

    def get_saldo_devedor_total(self, obj):
        return obj.saldo_devedor_total

    def validate_cpf(self, value):
        cpf = formatar_cpf(value)
        if not validar_cpf(cpf):
            raise serializers.ValidationError('CPF inválido.')
        return cpf

    def validate(self, attrs):
        cpf = attrs.get('cpf')
        instance = self.instance
        qs = Cliente.objects.filter(cpf=cpf, deleted_at__isnull=True)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError({'cpf': 'CPF já cadastrado.'})
        return attrs